from flask import Flask, render_template, request, jsonify
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
import threading
import time
import json
import os
import traceback

from config import Config
from database import Database
from bot import BlueskyBot
from follower_manager import follower_bp


# ============================================================
# APP INITIALIZATION
# ============================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = Config.SECRET_KEY
app.config["DEBUG"] = Config.DEBUG

db = Database()
bot = BlueskyBot()

BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"

print(f"Looking for .env at: {ENV_FILE}")

app.register_blueprint(follower_bp)


# ============================================================
# GLOBAL STATE
# ============================================================

bot_lock = threading.RLock()

run_now_state = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "success": None,
    "error": None,
}


# ============================================================
# HELPERS
# ============================================================

def json_body():
    """
    Safely return request JSON.

    Prevents crashes when a request has no JSON body.
    """
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {}

    return data


def error_response(message, status=400, **extra):
    """
    Consistent API error format.
    """
    payload = {
        "success": False,
        "error": str(message),
    }

    payload.update(extra)

    return jsonify(payload), status


def success_response(message=None, **data):
    """
    Consistent API success format.
    """
    payload = {
        "success": True,
    }

    if message:
        payload["message"] = message

    payload.update(data)

    return jsonify(payload)


def safe_int(value, default=0):
    """
    Convert something to int without throwing.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default=0):
    """
    Convert something to float without throwing.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_json_loads(value, default=None):
    """
    Safely decode JSON stored in the database.
    """
    if default is None:
        default = {}

    if not value:
        return default

    if isinstance(value, dict):
        return value

    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def env_to_bool(value, default=False):
    """
    Convert common environment boolean values.
    """
    if value is None:
        return default

    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def read_env_file():
    """
    Read the existing .env file without destroying unrelated settings.
    """
    env_vars = {}

    if not ENV_FILE.exists():
        return env_vars

    try:
        with open(ENV_FILE, "r", encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()

                if not line:
                    continue

                if line.startswith("#"):
                    continue

                if "=" not in line:
                    continue

                key, value = line.split("=", 1)

                env_vars[key.strip()] = value.strip()

    except OSError as exc:
        print(f"Failed reading .env: {exc}")

    return env_vars


def write_env_file(env_vars):
    """
    Write .env while preserving all known values.
    """
    try:
        with open(ENV_FILE, "w", encoding="utf-8") as file:

            for key, value in env_vars.items():
                file.write(f"{key}={value}\n")

        return True

    except OSError as exc:
        print(f"Failed writing .env: {exc}")
        return False


def ensure_bot_logged_in():
    """
    Make sure the Bluesky client is authenticated.
    """
    with bot_lock:

        try:

            if not bot.client or not bot.client.me:
                result = bot.login()

                if result is False:
                    return False

            return True

        except Exception:
            traceback.print_exc()
            return False


def get_bot_runtime_status():
    """
    Return actual runtime state without relying only on the DB.
    """
    try:
        running = bool(bot.is_running())
    except Exception:
        running = False

    return running


def config_snapshot():
    """
    Centralized configuration response.

    Keeping this in one place prevents the dashboard,
    configuration page and APIs from drifting apart.
    """

    return {
        "CHECK_INTERVAL": getattr(
            Config,
            "CHECK_INTERVAL",
            0,
        ),

        "MAX_LIKES_PER_DAY": getattr(
            Config,
            "MAX_LIKES_PER_DAY",
            0,
        ),

        "MAX_LIKES_PER_USER": getattr(
            Config,
            "MAX_LIKES_PER_USER",
            0,
        ),

        "LIKE_DELAY_MIN": getattr(
            Config,
            "LIKE_DELAY_MIN",
            0,
        ),

        "LIKE_DELAY_MAX": getattr(
            Config,
            "LIKE_DELAY_MAX",
            0,
        ),

        "AUTO_FOLLOW": getattr(
            Config,
            "AUTO_FOLLOW",
            False,
        ),

        "MAX_FOLLOWS_PER_DAY": getattr(
            Config,
            "MAX_FOLLOWS_PER_DAY",
            0,
        ),

        "ENGAGEMENT_THRESHOLD": getattr(
            Config,
            "ENGAGEMENT_THRESHOLD",
            3,
        ),

        "BLUESKY_HANDLE": getattr(
            Config,
            "BLUESKY_HANDLE",
            "",
        ),
    }


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):
    """
    Return JSON for API requests and normal 404 for pages.
    """

    if request.path.startswith("/api/"):
        return error_response(
            "API endpoint not found",
            404,
            path=request.path,
        )

    return error


@app.errorhandler(500)
def internal_error(error):
    """
    Keep API errors readable instead of returning an
    unexplained HTML error page.
    """

    if request.path.startswith("/api/"):

        return error_response(
            "Internal server error",
            500,
        )

    return error


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
def index():
    """
    Main dashboard.
    """

    try:

        stats = db.get_today_stats() or {}
        bot_status = db.get_bot_status() or {}

        recent_likes = (
            db.get_recent_likes(10)
            or []
        )

        followed_today = (
            db.get_followed_count_today()
            or 0
        )

        total_followed = (
            db.get_followed_total()
            or 0
        )

        total_follow_backs = (
            db.get_follow_backs_total()
            or 0
        )

        follow_back_rate = round(
            (
                total_follow_backs
                /
                total_followed
                *
                100
            )
            if total_followed > 0
            else 0,
            1,
        )

        config_dict = {
            "MAX_LIKES_PER_DAY":
                getattr(
                    Config,
                    "MAX_LIKES_PER_DAY",
                    100,
                ),

            "MAX_FOLLOWS_PER_DAY":
                getattr(
                    Config,
                    "MAX_FOLLOWS_PER_DAY",
                    0,
                ),

            "AUTO_FOLLOW":
                getattr(
                    Config,
                    "AUTO_FOLLOW",
                    False,
                ),
        }

        return render_template(
            "index.html",

            stats=stats,

            status=bot_status,

            recent_likes=recent_likes,

            followed_today=followed_today,

            config=config_dict,

            total_followed=total_followed,

            total_follow_backs=total_follow_backs,

            follow_back_rate=follow_back_rate,

            now=datetime.now(),
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Dashboard failed to load: {exc}",
            500,
        )


# ============================================================
# BOT CONTROL
# ============================================================

@app.route(
    "/api/bot/start",
    methods=["POST"],
)
def start_bot():

    try:

        with bot_lock:

            if get_bot_runtime_status():
                return success_response(
                    "Bot is already running.",
                    status="running",
                )

            if not ensure_bot_logged_in():

                return error_response(
                    "Unable to log in to Bluesky.",
                    500,
                    status="login_failed",
                )

            bot.start()

        return success_response(
            "Bot started.",
            status="running",
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Failed to start bot: {exc}",
            500,
        )


@app.route(
    "/api/bot/stop",
    methods=["POST"],
)
def stop_bot():

    try:

        with bot_lock:

            if not get_bot_runtime_status():

                return success_response(
                    "Bot is already stopped.",
                    status="stopped",
                )

            bot.stop()

        # Give the worker a moment to shut down.
        time.sleep(0.5)

        running = get_bot_runtime_status()

        return success_response(
            (
                "Bot stopped."
                if not running
                else
                "Bot stop requested."
            ),
            status=(
                "stopped"
                if not running
                else
                "stopping"
            ),
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Failed to stop bot: {exc}",
            500,
        )


@app.route(
    "/api/bot/pause",
    methods=["POST"],
)
def pause_bot():

    try:

        bot.pause()

        return success_response(
            "Bot paused.",
            status="paused",
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Failed to pause bot: {exc}",
            500,
        )


@app.route(
    "/api/bot/resume",
    methods=["POST"],
)
def resume_bot():

    try:

        bot.resume()

        return success_response(
            "Bot resumed.",
            status="running",
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Failed to resume bot: {exc}",
            500,
        )


@app.route(
    "/api/bot/status",
    methods=["GET"],
)
def bot_status():

    try:

        status = (
            db.get_bot_status()
            or {}
        )

        actual_running = (
            get_bot_runtime_status()
        )

        status["actually_running"] = (
            actual_running
        )

        status["runtime_running"] = (
            actual_running
        )

        status["run_now"] = {
            "running":
                run_now_state["running"],

            "started_at":
                run_now_state["started_at"],

            "finished_at":
                run_now_state["finished_at"],

            "success":
                run_now_state["success"],

            "error":
                run_now_state["error"],
        }

        return jsonify(status)

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Unable to get bot status: {exc}",
            500,
        )


# ============================================================
# RUN BOT NOW
# ============================================================

def _run_bot_once_worker():

    global run_now_state

    run_now_state["running"] = True
    run_now_state["started_at"] = (
        datetime.now().isoformat()
    )
    run_now_state["finished_at"] = None
    run_now_state["success"] = None
    run_now_state["error"] = None

    try:

        print(
            "[Dashboard] Starting manual bot run..."
        )

        with bot_lock:

            if not ensure_bot_logged_in():

                raise RuntimeError(
                    "Unable to log in to Bluesky."
                )

            bot.run_once()

        run_now_state["success"] = True

        print(
            "[Dashboard] Manual bot run completed."
        )

    except Exception as exc:

        run_now_state["success"] = False
        run_now_state["error"] = str(exc)

        print(
            "[Dashboard] Manual bot run failed:"
        )

        traceback.print_exc()

    finally:

        run_now_state["running"] = False
        run_now_state["finished_at"] = (
            datetime.now().isoformat()
        )


@app.route(
    "/api/bot/run-now",
    methods=["POST"],
)
def run_now():

    if run_now_state["running"]:

        return error_response(
            "A manual bot run is already in progress.",
            409,
            status="running",
        )

    thread = threading.Thread(
        target=_run_bot_once_worker,
        name="bluesky-manual-run",
        daemon=True,
    )

    thread.start()

    return success_response(
        "Bot run started.",
        status="running",
    )


# ============================================================
# FOLLOWED TODAY
# ============================================================

@app.route(
    "/api/followed/today",
    methods=["GET"],
)
def followed_today_api():

    try:

        return jsonify({
            "count":
                db.get_followed_count_today()
                or 0,
        })

    except Exception as exc:

        return error_response(
            f"Unable to get followed count: {exc}",
            500,
        )


# ============================================================
# CONFIGURATION PAGE
# ============================================================

@app.route("/configuration")
def configuration():

    try:

        keywords = (
            db.get_all_keywords()
            or []
        )

        config = config_snapshot()

        # Never send the password to the browser.
        config["BLUESKY_PASSWORD"] = (
            "********"
            if getattr(
                Config,
                "BLUESKY_PASSWORD",
                None,
            )
            else ""
        )

        return render_template(
            "configuration.html",
            keywords=keywords,
            config=config,
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Configuration failed to load: {exc}",
            500,
        )


# ============================================================
# STATISTICS PAGE
# ============================================================

@app.route("/stats")
@app.route("/analytics")
def stats():

    try:

        daily_stats = (
            db.get_historical_stats(30)
            or []
        )

        followed_users = (
            db.get_followed_users()
            or []
        )

        recent_likes = (
            db.get_recent_likes(100)
            or []
        )

        return render_template(
            "stats.html",

            daily_stats=daily_stats,

            followed_users=followed_users,

            recent_likes=recent_likes,
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Statistics failed to load: {exc}",
            500,
        )


# ============================================================
# KEYWORDS
# ============================================================

@app.route(
    "/api/keywords",
    methods=["GET"],
)
def get_keywords():

    try:

        return jsonify(
            db.get_all_keywords()
            or []
        )

    except Exception as exc:

        return error_response(
            f"Unable to load keywords: {exc}",
            500,
        )


@app.route(
    "/api/keywords",
    methods=["POST"],
)
def add_keyword():

    data = json_body()

    keyword = str(
        data.get("keyword", "")
    ).strip().lower()

    group = str(
        data.get("group", "")
    ).strip()

    if not keyword:

        return error_response(
            "Keyword required.",
            400,
        )

    try:

        success = db.add_keyword(
            keyword,
            group,
        )

        if not success:

            return error_response(
                "Keyword already exists.",
                409,
            )

        return success_response(
            "Keyword added.",
            keyword=keyword,
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Failed to add keyword: {exc}",
            500,
        )


@app.route(
    "/api/keywords/<int:keyword_id>",
    methods=["PUT"],
)
def update_keyword(keyword_id):

    data = json_body()

    active = bool(
        data.get("active", False)
    )

    try:

        db.update_keyword(
            keyword_id,
            active,
        )

        return success_response(
            "Keyword updated.",
            keyword_id=keyword_id,
            active=active,
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Failed to update keyword: {exc}",
            500,
        )


@app.route(
    "/api/keywords/<int:keyword_id>",
    methods=["DELETE"],
)
def delete_keyword(keyword_id):

    try:

        db.delete_keyword(
            keyword_id
        )

        return success_response(
            "Keyword deleted.",
            keyword_id=keyword_id,
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Failed to delete keyword: {exc}",
            500,
        )


@app.route(
    "/api/keywords/performance",
    methods=["GET"],
)
def keywords_performance():

    try:

        keywords = (
            db.get_all_keywords()
            or []
        )

        keyword_stats = (
            db.get_keyword_performance()
            or []
        )

        stats_map = {
            stat.get("keyword"):
                stat
            for stat in keyword_stats
            if stat.get("keyword")
        }

        result = []

        for keyword in keywords:

            kw_text = (
                keyword.get("keyword", "")
            )

            stats = (
                stats_map.get(
                    kw_text,
                    {},
                )
                or {}
            )

            result.append({
                **keyword,

                "engagements":
                    safe_int(
                        stats.get(
                            "engagements",
                            0,
                        )
                    ),

                "follows":
                    safe_int(
                        stats.get(
                            "follows",
                            0,
                        )
                    ),

                "posts_found":
                    safe_int(
                        stats.get(
                            "posts_found",
                            stats.get(
                                "engagements",
                                0,
                            ),
                        )
                    ),

                "active":
                    bool(
                        keyword.get(
                            "active",
                            True,
                        )
                    ),
            })

        return jsonify(result)

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Unable to load keyword performance: {exc}",
            500,
        )


# ============================================================
# KEYWORD GROUPS
# ============================================================

@app.route(
    "/api/keywords/groups",
    methods=["GET"],
)
def get_keyword_groups():

    try:

        return jsonify(
            db.get_all_groups()
            or []
        )

    except Exception as exc:

        return error_response(
            f"Unable to load keyword groups: {exc}",
            500,
        )


@app.route(
    "/api/keywords/groups",
    methods=["POST"],
)
def add_keyword_group():

    data = json_body()

    group_name = str(
        data.get("name", "")
    ).strip()

    if not group_name:

        return error_response(
            "Group name required.",
            400,
        )

    # Groups are metadata attached to keywords.
    # Existing architecture does not provide a
    # separate group creation method.
    return success_response(
        "Group ready.",
        name=group_name,
    )


@app.route(
    "/api/keywords/groups/<path:group_name>",
    methods=["DELETE"],
)
def delete_keyword_group(group_name):

    try:

        with db.get_cursor() as cursor:

            cursor.execute(
                """
                UPDATE keywords
                SET group_name = NULL
                WHERE group_name = ?
                """,
                (
                    group_name,
                ),
            )

        return success_response(
            "Group removed from keywords.",
            name=group_name,
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Failed to remove keyword group: {exc}",
            500,
        )


@app.route(
    "/api/keywords/<int:keyword_id>/group",
    methods=["PUT"],
)
def update_keyword_group(keyword_id):

    data = json_body()

    group = data.get("group")

    if group is not None:
        group = str(group).strip()

    try:

        db.update_keyword_group(
            keyword_id,
            group,
        )

        return success_response(
            "Keyword group updated.",
            keyword_id=keyword_id,
            group=group,
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Failed to update keyword group: {exc}",
            500,
        )


# ============================================================
# FOLLOWER ACTIVITY
# ============================================================

@app.route(
    "/api/followers/activity",
    methods=["GET"],
)
def follower_activity():

    try:

        activity = (
            db.get_follower_activity(
                limit=20
            )
            or []
        )

        follow_backs = (
            db.get_follow_backs(
                days=7
            )
            or []
        )

        formatted_activity = []

        for item in activity:

            handle = (
                item.get("handle")
                or item.get("user_handle")
                or "unknown"
            )

            display_name = (
                item.get("display_name")
                or item.get("user_display_name")
                or handle
            )

            timestamp = (
                item.get("timestamp")
                or item.get("followed_at")
            )

            formatted_activity.append({
                "user_handle":
                    handle,

                # Frontend-compatible name.
                "display_name":
                    display_name,

                # Backwards-compatible name.
                "user_display_name":
                    display_name,

                "followed_at":
                    timestamp,

                "type":
                    item.get(
                        "type",
                        "new",
                    ),

                "avatar":
                    item.get("avatar"),
            })

        formatted_follow_backs = []

        for fb in follow_backs:

            handle = (
                fb.get("handle")
                or fb.get("user_handle")
                or "unknown"
            )

            display_name = (
                fb.get("display_name")
                or fb.get("user_display_name")
                or handle
            )

            timestamp = (
                fb.get("followed_back_at")
                or fb.get("timestamp")
                or fb.get("followed_at")
            )

            formatted_follow_backs.append({
                "user_handle":
                    handle,

                "display_name":
                    display_name,

                "user_display_name":
                    display_name,

                # Normalize timestamp.
                "followed_at":
                    timestamp,

                "followed_back_at":
                    timestamp,

                "type":
                    "follow_back",

                "avatar":
                    fb.get("avatar"),
            })

        return jsonify({
            "follows":
                formatted_activity,

            "follow_backs":
                formatted_follow_backs,

            "count":
                len(formatted_activity),

            "follow_back_count":
                len(formatted_follow_backs),
        })

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Unable to load follower activity: {exc}",
            500,
        )


# ============================================================
# UNFOLLOWERS
# ============================================================

@app.route(
    "/api/unfollowers",
    methods=["GET"],
)
def unfollowers():

    days = request.args.get(
        "days",
        30,
        type=int,
    )

    days = max(
        1,
        min(days, 365),
    )

    try:

        users = (
            db.get_unfollowers(
                days=days
            )
            or []
        )

        formatted = []

        for user in users:

            handle = (
                user.get("handle")
                or "unknown"
            )

            display_name = (
                user.get("display_name")
                or handle
            )

            formatted.append({
                "user_handle":
                    handle,

                "display_name":
                    display_name,

                "user_display_name":
                    display_name,

                "unfollowed_at":
                    user.get(
                        "unfollowed_at"
                    ),

                "avatar":
                    user.get("avatar"),
            })

        return jsonify(formatted)

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Unable to load unfollowers: {exc}",
            500,
        )


# ============================================================
# TODAY'S STATS
# ============================================================

@app.route(
    "/api/stats/today",
    methods=["GET"],
)
def today_stats():

    try:

        stats = (
            db.get_today_stats()
            or {}
        )

        follow_backs_today = (
            db.get_follow_backs_count_today()
            or 0
        )

        return jsonify({

            "likes":
                safe_int(
                    stats.get(
                        "likes",
                        0,
                    )
                ),

            "follows":
                safe_int(
                    stats.get(
                        "follows",
                        0,
                    )
                ),

            "new_followers":
                safe_int(
                    stats.get(
                        "new_followers",
                        0,
                    )
                ),

            "unfollowers":
                safe_int(
                    stats.get(
                        "unfollowers",
                        0,
                    )
                ),

            "followed_back":
                safe_int(
                    follow_backs_today
                ),

            "users_checked":
                safe_int(
                    stats.get(
                        "users_checked",
                        0,
                    )
                ),

            "posts_found":
                safe_int(
                    stats.get(
                        "posts_found",
                        0,
                    )
                ),
        })

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Unable to load today's stats: {exc}",
            500,
        )


# ============================================================
# HISTORICAL STATS
# ============================================================

@app.route(
    "/api/stats/historical",
    methods=["GET"],
)
def historical_stats():

    days = request.args.get(
        "days",
        7,
        type=int,
    )

    days = max(
        1,
        min(days, 3650),
    )

    try:

        stats = (
            db.get_historical_stats(
                days=days
            )
            or []
        )

        result = []

        for stat in stats:

            result.append({

                "date":
                    stat.get(
                        "date"
                    ),

                "likes":
                    safe_int(
                        stat.get(
                            "likes",
                            0,
                        )
                    ),

                "follows":
                    safe_int(
                        stat.get(
                            "follows",
                            0,
                        )
                    ),

                "new_followers":
                    safe_int(
                        stat.get(
                            "new_followers",
                            0,
                        )
                    ),

                "unfollowers":
                    safe_int(
                        stat.get(
                            "unfollowers",
                            0,
                        )
                    ),

                "followed_back":
                    safe_int(
                        stat.get(
                            "followed_back",
                            0,
                        )
                    ),

                "users_checked":
                    safe_int(
                        stat.get(
                            "users_checked",
                            0,
                        )
                    ),

                "posts_found":
                    safe_int(
                        stat.get(
                            "posts_found",
                            0,
                        )
                    ),
            })

        result.sort(
            key=lambda item:
                str(
                    item.get(
                        "date",
                        "",
                    )
                )
        )

        return jsonify(result)

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Unable to load historical stats: {exc}",
            500,
        )


# ============================================================
# FOLLOWER SYNC
# ============================================================

@app.route(
    "/api/followers/sync",
    methods=["POST"],
)
def sync_followers():

    if not ensure_bot_logged_in():

        return error_response(
            "Failed to log in to Bluesky.",
            500,
        )

    try:

        bot.sync_followers()

        return success_response(
            "Follower sync completed.",
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Follower sync failed: {exc}",
            500,
        )


# ============================================================
# DISCOVERED CONTENT
# ============================================================

@app.route(
    "/api/discovered-content",
    methods=["GET"],
)
def discovered_content():

    limit = request.args.get(
        "limit",
        20,
        type=int,
    )

    limit = max(
        1,
        min(limit, 100),
    )

    try:

        posts = (
            db.get_discovered_content(
                limit=limit
            )
            or []
        )

        formatted_posts = []

        for post in posts:

            formatted_posts.append({

                "uri":
                    post.get(
                        "uri"
                    ),

                "author_handle":
                    post.get(
                        "author_handle",
                        "unknown",
                    ),

                "author_display_name":
                    post.get(
                        "author_display_name"
                    ),

                "author_avatar":
                    post.get(
                        "author_avatar"
                    ),

                "text":
                    post.get(
                        "text",
                        "",
                    ),

                "discovered_at":
                    post.get(
                        "discovered_at"
                    ),
            })

        return jsonify({
            "posts":
                formatted_posts,

            "count":
                len(formatted_posts),
        })

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Unable to load discovered content: {exc}",
            500,
        )


# ============================================================
# POST DETAILS
# ============================================================

@app.route(
    "/api/post/<path:post_uri>",
    methods=["GET"],
)
def post_details(post_uri):

    try:

        decoded_uri = unquote(
            post_uri
        )

        with db.get_cursor() as cursor:

            cursor.execute(
                """
                SELECT *
                FROM liked_posts
                WHERE uri = ?
                LIMIT 1
                """,
                (
                    decoded_uri,
                ),
            )

            post = cursor.fetchone()

        if not post:

            return error_response(
                "Post not found.",
                404,
            )

        post_data = safe_json_loads(
            post["post_data"],
            {},
        )

        return jsonify({

            "uri":
                post["uri"],

            "author_handle":
                post["user_handle"],

            "author_display_name":
                post_data.get(
                    "author_display_name"
                ),

            "author_avatar":
                post_data.get(
                    "author_avatar"
                ),

            "text":
                post_data.get(
                    "text",
                    "",
                ),

            # If the stored post data contains a real
            # creation timestamp, use it.
            "created_at":
                post_data.get(
                    "created_at",
                    post_data.get(
                        "indexed_at",
                        post["liked_at"],
                    ),
                ),

            "liked_at":
                post["liked_at"],
        })

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Unable to load post: {exc}",
            500,
        )


# ============================================================
# ALL LIKES
# ============================================================

@app.route(
    "/api/likes/all",
    methods=["GET"],
)
def all_likes():

    limit = request.args.get(
        "limit",
        100,
        type=int,
    )

    limit = max(
        1,
        min(limit, 1000),
    )

    try:

        likes = (
            db.get_recent_likes(
                limit
            )
            or []
        )

        formatted = []

        for like in likes:

            post_data = safe_json_loads(
                like.get(
                    "post_data"
                ),
                {},
            )

            formatted.append({

                "uri":
                    like.get(
                        "uri"
                    ),

                "user_handle":
                    like.get(
                        "user_handle"
                    ),

                "liked_at":
                    like.get(
                        "liked_at"
                    ),

                "post_data":
                    post_data,
            })

        return jsonify(formatted)

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Unable to load engagement history: {exc}",
            500,
        )


# ============================================================
# FOLLOWED USERS
# ============================================================

@app.route(
    "/api/followed-users",
    methods=["GET"],
)
def get_followed_users():

    try:

        users = (
            db.get_followed_users()
            or []
        )

        formatted = []

        for user in users:

            handle = (
                user.get(
                    "handle"
                )
                or "unknown"
            )

            display_name = (
                user.get(
                    "display_name"
                )
                or handle
            )

            formatted.append({

                "did":
                    user.get(
                        "did"
                    ),

                "handle":
                    handle,

                "display_name":
                    display_name,

                "user_display_name":
                    display_name,

                "avatar":
                    user.get(
                        "avatar"
                    ),

                "followed_at":
                    user.get(
                        "followed_at"
                    ),

                "is_following_us":
                    bool(
                        user.get(
                            "is_following_us",
                            False,
                        )
                    ),
            })

        return jsonify(formatted)

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Unable to load followed users: {exc}",
            500,
        )


# ============================================================
# RECENT LIKES
# ============================================================

@app.route(
    "/api/recent-likes",
    methods=["GET"],
)
def get_recent_likes():

    limit = request.args.get(
        "limit",
        50,
        type=int,
    )

    limit = max(
        1,
        min(limit, 500),
    )

    try:

        likes = (
            db.get_recent_likes(
                limit
            )
            or []
        )

        formatted = []

        for like in likes:

            post_data = safe_json_loads(
                like.get(
                    "post_data"
                ),
                {},
            )

            display_name = (
                post_data.get(
                    "author_display_name"
                )
                or like.get(
                    "user_handle"
                )
            )

            avatar = (
                post_data.get(
                    "author_avatar"
                )
            )

            formatted.append({

                "uri":
                    like.get(
                        "uri"
                    ),

                "user_handle":
                    like.get(
                        "user_handle"
                    ),

                "display_name":
                    display_name,

                "user_display_name":
                    display_name,

                "avatar":
                    avatar,

                "user_avatar":
                    avatar,

                "liked_at":
                    like.get(
                        "liked_at"
                    ),

                "post_data":
                    post_data,
            })

        return jsonify(formatted)

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Unable to load recent likes: {exc}",
            500,
        )


# ============================================================
# CREDENTIALS
# ============================================================

@app.route(
    "/api/credentials",
    methods=["POST"],
)
def update_credentials():

    data = json_body()

    handle = str(
        data.get(
            "handle",
            "",
        )
    ).strip()

    password = str(
        data.get(
            "password",
            "",
        )
    ).strip()

    if not handle:

        return error_response(
            "Handle required.",
            400,
        )

    if not password:

        return error_response(
            "Password required.",
            400,
        )

    try:

        env_vars = read_env_file()

        env_vars[
            "BLUESKY_HANDLE"
        ] = handle

        env_vars[
            "BLUESKY_PASSWORD"
        ] = password

        if not write_env_file(
            env_vars
        ):

            return error_response(
                "Unable to save credentials.",
                500,
            )

        return success_response(
            "Credentials saved. Restart the bot to apply them.",
            requires_restart=True,
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Failed to save credentials: {exc}",
            500,
        )


# ============================================================
# BOT RESTART
# ============================================================

@app.route(
    "/api/bot/restart",
    methods=["POST"],
)
def restart_bot():

    global bot

    try:

        with bot_lock:

            try:
                bot.stop()
            except Exception:
                pass

            time.sleep(0.75)

            new_bot = BlueskyBot()

            if not new_bot.login():

                return error_response(
                    "Failed to log in with the current credentials.",
                    500,
                )

            bot = new_bot

            bot.start()

        return success_response(
            "Bot restarted successfully.",
            status="running",
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Failed to restart bot: {exc}",
            500,
        )


# ============================================================
# CONFIGURATION API
# ============================================================

@app.route(
    "/api/configuration",
    methods=["GET"],
)
def get_settings():

    try:

        return jsonify(
            config_snapshot()
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Unable to load configuration: {exc}",
            500,
        )


@app.route(
    "/api/configuration",
    methods=["POST"],
)
def update_settings():

    data = json_body()

    settings_map = {

        "check_interval":
            "CHECK_INTERVAL",

        "max_likes_per_day":
            "MAX_LIKES_PER_DAY",

        "max_likes_per_user":
            "MAX_LIKES_PER_USER",

        "like_delay_min":
            "LIKE_DELAY_MIN",

        "like_delay_max":
            "LIKE_DELAY_MAX",

        "auto_follow":
            "AUTO_FOLLOW",

        "max_follows_per_day":
            "MAX_FOLLOWS_PER_DAY",
    }

    try:

        env_vars = read_env_file()

        changed = []

        for form_field, env_var in (
            settings_map.items()
        ):

            if form_field not in data:
                continue

            value = data[
                form_field
            ]

            if env_var == "AUTO_FOLLOW":

                value = (
                    "true"
                    if bool(value)
                    else
                    "false"
                )

            else:

                # Keep numeric settings numeric.
                try:

                    if (
                        isinstance(
                            value,
                            float,
                        )
                        or "."
                        in str(value)
                    ):
                        value = str(
                            float(value)
                        )

                    else:
                        value = str(
                            int(value)
                        )

                except (
                    TypeError,
                    ValueError,
                ):

                    return error_response(
                        f"Invalid value for {form_field}.",
                        400,
                    )

            env_vars[
                env_var
            ] = str(value)

            changed.append(
                env_var
            )

        if not changed:

            return error_response(
                "No configuration values supplied.",
                400,
            )

        if not write_env_file(
            env_vars
        ):

            return error_response(
                "Unable to save configuration.",
                500,
            )

        return success_response(
            "Configuration saved. Restart the bot to apply changes.",
            changed=changed,
            requires_restart=True,
        )

    except Exception as exc:

        traceback.print_exc()

        return error_response(
            f"Failed to save configuration: {exc}",
            500,
        )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/api/health",
    methods=["GET"],
)
def health():

    try:

        database_ok = True

        # Basic database check.
        # get_today_stats() already exists in your
        # Database class and is safe to use here.
        db.get_today_stats()

    except Exception as exc:

        database_ok = False
        database_error = str(exc)

    try:

        runtime_running = (
            get_bot_runtime_status()
        )

    except Exception:

        runtime_running = False

    response = {

        "success":
            True,

        "status":
            "ok"
            if database_ok
            else
            "degraded",

        "database":
            database_ok,

        "bot_running":
            runtime_running,

        "run_now_running":
            run_now_state["running"],

        "timestamp":
            datetime.now().isoformat(),
    }

    if not database_ok:

        response[
            "database_error"
        ] = database_error

    return jsonify(response)


# ============================================================
# APPLICATION START
# ============================================================

if __name__ == "__main__":

    app.run(
        host=Config.FLASK_HOST,
        port=Config.FLASK_PORT,
        debug=Config.FLASK_DEBUG,
    )