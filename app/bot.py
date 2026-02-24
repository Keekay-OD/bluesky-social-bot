import time
import random
import threading
from datetime import datetime, timedelta
from atproto import Client
from atproto.exceptions import AtProtocolError
from database import Database
from config import Config


class BlueskyBot:
    def __init__(self):
        self.db = Database()
        self.client = Client()
        self.running = False
        self.thread = None
        self.paused = False

    # -------------------------------------------------
    # AUTH
    # -------------------------------------------------
    def login(self):
        try:
            self.client.login(Config.BLUESKY_HANDLE, Config.BLUESKY_PASSWORD)
            print("✅ Bluesky login successful")
            return True
        except Exception as e:
            print(f"❌ Login failed: {e}")
            return False

    # -------------------------------------------------
    # SAFE ATTRIBUTE HELPERS
    # -------------------------------------------------
    def safe_get(self, obj, attr, default=None):
        return getattr(obj, attr, default) if obj else default

    # -------------------------------------------------
    # FOLLOWING LIST
    # -------------------------------------------------
    def get_following(self):
        """Get users we follow safely"""
        try:
            following = []
            cursor = None

            while True:
                params = {
                    "actor": Config.BLUESKY_HANDLE,
                    "limit": 100,
                }
                if cursor:
                    params["cursor"] = cursor

                response = self.client.app.bsky.graph.get_follows(params)

                for profile in response.follows:
                    following.append({
                        "did": self.safe_get(profile, "did"),
                        "handle": self.safe_get(profile, "handle"),
                        "display_name": self.safe_get(profile, "display_name"),
                    })

                if not response.cursor:
                    break

                cursor = response.cursor

            return following

        except Exception as e:
            print(f"⚠️ Failed to get following list: {e}")
            return []

    # -------------------------------------------------
    # POSTS
    # -------------------------------------------------
    def get_user_posts(self, user_did, limit=20):
        try:
            response = self.client.app.bsky.feed.get_author_feed({
                "actor": user_did,
                "limit": limit,
                "filter": "posts_no_replies"
            })
            return response.feed if response else []
        except Exception as e:
            print(f"⚠️ Failed to get posts for {user_did}: {e}")
            return []

    def get_post_text(self, post):
        try:
            post_obj = post.post if hasattr(post, "post") else post
            record = self.safe_get(post_obj, "record")

            if isinstance(record, dict):
                return record.get("text", "") or ""

            return self.safe_get(record, "text", "") or ""

        except Exception:
            return ""

    # -------------------------------------------------
    # KEYWORD MATCH
    # -------------------------------------------------
    def text_contains_keyword(self, text, keywords):
        if not text:
            return False

        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in keywords)

    # -------------------------------------------------
    # LIKE
    # -------------------------------------------------
    def like_post(self, post, reason=""):
        try:
            post_obj = post.post if hasattr(post, "post") else post

            post_uri = self.safe_get(post_obj, "uri")
            post_cid = self.safe_get(post_obj, "cid")
            author = self.safe_get(post_obj, "author")

            author_handle = self.safe_get(author, "handle", "unknown")
            author_did = self.safe_get(author, "did", "unknown")

            if not post_uri or not post_cid:
                return False

            if self.db.was_liked(post_uri):
                return False

            today_stats = self.db.get_today_stats()
            if today_stats["likes"] >= Config.MAX_LIKES_PER_DAY:
                print("⚠️ Daily like limit reached")
                return False

            self.client.like(post_uri, post_cid)

            post_text = self.get_post_text(post_obj)

            # Record like
            self.db.add_liked_post(
                post_uri,
                author_did,
                author_handle,
                {
                    "uri": post_uri,
                    "cid": post_cid,
                    "text": post_text[:150],
                    "reason": reason,
                    "created_at": str(datetime.now())
                }
            )

            self.db.update_daily_stats(likes=1)

            print(f"❤️ Liked @{author_handle}")

            # -----------------------------------------
            # Random Re-skeet Logic
            # -----------------------------------------
            today_stats = self.db.get_today_stats()
            total_likes_today = today_stats["likes"]

            if total_likes_today > 0 and total_likes_today % 20 == 0:
                try:
                    if random.random() < 0.6:  # 60% chance to re-skeet
                        self.client.repost(post_uri, post_cid)
                        print(f"🔁 Re-skeeted @{author_handle}")
                except Exception as e:
                    print(f"⚠️ Re-skeet failed: {e}")

            return True

        except Exception as e:
            print(f"⚠️ Like failed: {e}")
            return False

    # -------------------------------------------------
    # FOLLOW
    # -------------------------------------------------
    def follow_user(self, user_did, user_handle):
        """Follow user safely and skip if already followed"""

        if not Config.AUTO_FOLLOW:
            print("Auto follow disabled")
            return False

        if not user_did:
            return False

        # Daily follow limit
        if self.db.get_followed_count_today() >= Config.MAX_FOLLOWS_PER_DAY:
            print("⚠️ Daily follow limit reached")
            return False

        # Already followed in DB
        if self.db.was_followed(user_did):
            print(f"↩️ Already followed @{user_handle} (DB)")
            return False

        try:
            # Check if already following via Bluesky API
            profile = self.client.app.bsky.actor.get_profile({"actor": user_did})

            if hasattr(profile.viewer, "following") and profile.viewer.following:
                print(f"↩️ Already following @{user_handle} (Bluesky)")
                self.db.add_follow(user_did, user_handle)
                return False

            # Perform follow
            self.client.follow(user_did)

            self.db.add_follow(user_did, user_handle)
            self.db.update_daily_stats(follows=1)

            print(f"➕ Followed @{user_handle}")
            return True

        except AtProtocolError as e:
            print(f"⚠️ Follow failed (API): {e}")
            return False
        except Exception as e:
            print(f"⚠️ Follow failed (unexpected): {e}")
            return False


    # -------------------------------------------------
    # PROCESS USER
    # -------------------------------------------------
    def process_user(self, user, keywords):
        print(f"\n👤 Checking @{user['handle']}")

        posts = self.get_user_posts(user["did"])
        if not posts:
            return 0

        likes_added = 0
        matched = False

        for post in posts[:Config.MAX_LIKES_PER_USER]:
            if self.paused or not self.running:
                break

            text = self.get_post_text(post)

            if self.text_contains_keyword(text, keywords):
                matched = True

                if self.like_post(post, reason="keyword match"):
                    likes_added += 1

                    # Follow immediately after first successful like
                    if likes_added == 1:
                        self.follow_user(user["did"], user["handle"])

                    delay = random.randint(
                        Config.LIKE_DELAY_MIN,
                        Config.LIKE_DELAY_MAX
                    )
                    time.sleep(delay)

        print(f"Matched user: {matched}, Likes added: {likes_added}")

        if matched:
            self.follow_user(user["did"], user["handle"])

        return likes_added

    # -------------------------------------------------
    # RUN ONCE
    # -------------------------------------------------
    def run_once(self):
        print(f"\n🚀 Bot run at {datetime.now()}")

        if self.paused or not self.running:
            return

        if not self.client.me:
            if not self.login():
                return

        keywords = self.db.get_active_keywords()
        if not keywords:
            print("No active keywords")
            return

        following = self.get_following()
        if not following:
            print("No followed users")
            return

        random.shuffle(following)

        total_likes = 0

        for user in following:
            if self.paused or not self.running:
                break

            if self.db.get_today_stats()["likes"] >= Config.MAX_LIKES_PER_DAY:
                break

            total_likes += self.process_user(user, keywords)
            time.sleep(random.randint(2, 5))

        self.db.update_bot_status(
            last_run=datetime.now(),
            next_run=datetime.now() + timedelta(seconds=Config.CHECK_INTERVAL),
            error=None
        )

        print(f"✅ Run complete: {total_likes} likes")

    # -------------------------------------------------
    # THREAD LOOP
    # -------------------------------------------------
    def _run_loop(self):
        while self.running:
            try:
                if not self.paused:
                    self.run_once()
                    time.sleep(Config.CHECK_INTERVAL)
                else:
                    time.sleep(30)
            except Exception as e:
                print(f"⚠️ Loop error: {e}")
                time.sleep(300)

    # -------------------------------------------------
    # CONTROL
    # -------------------------------------------------
    def start(self):
        if self.thread and self.thread.is_alive():
            return

        self.running = True
        self.paused = False

        self.thread = threading.Thread(target=self._run_loop)
        self.thread.daemon = True
        self.thread.start()

        print("Bot started")

    def stop(self):
        self.running = False
        self.paused = False
        print("Bot stopped")

    def pause(self):
        self.paused = True
        print("Bot paused")

    def resume(self):
        self.paused = False
        self.running = True
        print("Bot resumed")
