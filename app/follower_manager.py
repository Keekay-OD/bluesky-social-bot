from flask import Blueprint, render_template, request, jsonify
from atproto import Client
import time
import logging

from database import Database
from config import Config

logger = logging.getLogger(__name__)

# Blueprint
follower_bp = Blueprint(
    "follower_manager",
    __name__,
    template_folder="web/templates",
    static_folder="web/static"
)


class FollowerManager:

    def __init__(self):
        self.client = None
        self.repo_did = None
        self.authenticated = False
        self.db = Database()

    # -----------------------------
    # AUTH
    # -----------------------------

    def authenticate(self):
        try:

            if self.client and self.authenticated:
                return True

            self.client = Client()

            profile = self.client.login(
                Config.BLUESKY_HANDLE,
                Config.BLUESKY_PASSWORD
            )

            self.repo_did = profile.did
            self.authenticated = True

            logger.info(f"Authenticated as {self.repo_did}")

            return True

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            self.authenticated = False
            return False

    # -----------------------------
    # FOLLOWERS
    # -----------------------------

    def get_all_followers(self):

        followers = []
        cursor = None

        while True:

            response = self.client.get_followers(
                actor=Config.BLUESKY_HANDLE,
                cursor=cursor,
                limit=100
            )

            if response and hasattr(response, "followers"):
                followers.extend(response.followers)

            cursor = getattr(response, "cursor", None)

            if not cursor:
                break

        return followers

    # -----------------------------
    # FOLLOWS
    # -----------------------------

    def get_all_follows(self):

        follows = []
        cursor = None

        while True:

            response = self.client.get_follows(
                actor=Config.BLUESKY_HANDLE,
                cursor=cursor,
                limit=100
            )

            if response and hasattr(response, "follows"):
                follows.extend(response.follows)

            cursor = getattr(response, "cursor", None)

            if not cursor:
                break

        return follows

    # -----------------------------
    # FOLLOW URI EXTRACTOR
    # -----------------------------

    def extract_follow_uri(self, follow):

        try:

            # Most reliable
            if hasattr(follow, "viewer") and follow.viewer:
                if hasattr(follow.viewer, "following") and follow.viewer.following:
                    return follow.viewer.following

            if hasattr(follow, "uri") and follow.uri:
                return follow.uri

            if hasattr(follow, "view") and follow.view:
                if hasattr(follow.view, "uri") and follow.view.uri:
                    return follow.view.uri

        except Exception as e:
            logger.error(f"URI extraction failed: {e}")

        return None

    # -----------------------------
    # UNFOLLOW
    # -----------------------------

    def unfollow_user(self, follow_uri):
        """Unfollow a user by deleting the follow record"""

        if not self.authenticated and not self.authenticate():
            return False, "Authentication failed"

        try:

            if not follow_uri:
                return False, "Missing follow URI"

            if not follow_uri.startswith("at://"):
                return False, f"Invalid URI: {follow_uri}"

            # at://did/app.bsky.graph.follow/rkey
            uri = follow_uri.replace("at://", "")
            parts = uri.split("/")

            if len(parts) < 3:
                return False, f"Malformed URI: {follow_uri}"

            collection = parts[1]
            rkey = parts[2]

            logger.info(
                f"Deleting follow record repo={self.repo_did} collection={collection} rkey={rkey}"
            )

            self.client.com.atproto.repo.delete_record(
                data={
                    "repo": self.repo_did,
                    "collection": collection,
                    "rkey": rkey
                }
            )

            return True, None

        except Exception as e:
            logger.error(f"Unfollow failed: {e}")
            return False, str(e)

    # -----------------------------
    # STATUS ANALYSIS
    # -----------------------------

    def get_following_status(self):

        if not self.authenticate():
            return None, "Authentication failed"

        try:

            followers = self.get_all_followers()
            follows = self.get_all_follows()

            follower_dids = set()

            for f in followers:
                if hasattr(f, "did"):
                    follower_dids.add(f.did)

            results = []

            for follow in follows:

                try:

                    did = getattr(follow, "did", None)

                    if not did:
                        continue

                    handle = getattr(follow, "handle", "unknown")

                    display_name = getattr(follow, "display_name", None) or getattr(
                        follow, "displayName", None)

                    avatar = getattr(follow, "avatar", None)
                    description = getattr(follow, "description", None)

                    follows_you = did in follower_dids

                    whitelisted = self.db.is_whitelisted(did)

                    follow_uri = self.extract_follow_uri(follow)

                    logger.info(
                        f"User {handle} follow_uri={follow_uri}")

                    results.append({
                        "did": did,
                        "handle": handle,
                        "display_name": display_name or handle,
                        "avatar": avatar,
                        "description": description,
                        "follows_you": follows_you,
                        "whitelisted": whitelisted,
                        "follow_uri": follow_uri
                    })

                except Exception as e:
                    logger.error(f"Follow processing failed: {e}")

            return results, None

        except Exception as e:
            logger.error(f"Status analysis failed: {e}")
            return None, str(e)


# Manager instance
manager = FollowerManager()


# -----------------------------
# ROUTES
# -----------------------------

@follower_bp.route("/followers")
def followers_page():
    return render_template("followers.html")


@follower_bp.route("/api/followers/status")
def get_following_status():

    status, error = manager.get_following_status()

    if error:
        return jsonify({"error": error}), 500

    return jsonify({
        "success": True,
        "data": status,
        "stats": {
            "total_following": len(status),
            "non_followers": sum(1 for s in status if not s["follows_you"]),
            "whitelisted": sum(1 for s in status if s["whitelisted"])
        }
    })


@follower_bp.route("/api/followers/unfollow", methods=["POST"])
def unfollow_users():

    data = request.json
    users = data.get("users", [])

    if not users:
        return jsonify({"error": "No users provided"}), 400

    results = {
        "success": [],
        "failed": []
    }

    for user in users:

        did = user.get("did")
        handle = user.get("handle")
        follow_uri = user.get("follow_uri")

        logger.info(f"Unfollow request {handle} uri={follow_uri}")

        success, error = manager.unfollow_user(follow_uri)

        if success:

            results["success"].append(handle)

            try:
                manager.db.add_unfollower(
                    did=did,
                    handle=handle,
                    display_name=user.get("display_name"),
                    profile_data={"follow_uri": follow_uri}
                )
            except Exception as e:
                logger.error(f"DB error: {e}")

            time.sleep(0.3)

        else:

            results["failed"].append({
                "handle": handle,
                "reason": error
            })

    return jsonify({
        "success": True,
        "results": results
    })


@follower_bp.route("/api/followers/whitelist/add", methods=["POST"])
def add_to_whitelist():

    data = request.json

    did = data.get("did")
    handle = data.get("handle")
    display_name = data.get("display_name")
    reason = data.get("reason", "")

    if not did:
        return jsonify({"error": "Missing DID"}), 400

    manager.db.add_to_whitelist(
        did,
        handle,
        display_name,
        reason
    )

    return jsonify({"success": True})


@follower_bp.route("/api/followers/whitelist/remove", methods=["POST"])
def remove_from_whitelist():

    data = request.json
    did = data.get("did")

    if not did:
        return jsonify({"error": "Missing DID"}), 400

    manager.db.remove_from_whitelist(did)

    return jsonify({"success": True})


@follower_bp.route("/api/followers/whitelist")
def get_whitelist():

    whitelist = manager.db.get_whitelist()

    return jsonify({
        "success": True,
        "data": whitelist
    })


@follower_bp.route("/api/followers/unfollowers")
def get_unfollowers():

    days = request.args.get("days", 30, type=int)

    data = manager.db.get_unfollowers(days)

    return jsonify({
        "success": True,
        "data": data
    })