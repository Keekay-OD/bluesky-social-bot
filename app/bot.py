# In Z:\Docker\AppData\Config\bluesky-social-bot\app\bot.py

import time
import random
import re
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

        self.stop_event = threading.Event()
        self._stop_lock = threading.Lock()
        self._thread_stopped = True

        # -------------------------------------------------
        # SESSION COUNTERS
        # -------------------------------------------------
        self.followed_today = 0
        self.likes_today = 0
        self.reposts_today = 0

        # -------------------------------------------------
        # LIFETIME COUNTERS
        # -------------------------------------------------
        self.total_actions = 0

        # -------------------------------------------------
        # FOLLOWER TRACKING
        # -------------------------------------------------
        self.last_follower_sync = None

        # -------------------------------------------------
        # RELEVANCE SETTINGS
        # -------------------------------------------------

        # Strong cycling terms.
        # These are worth more because they are much less likely
        # to appear in completely unrelated posts.
        self.STRONG_CYCLING_TERMS = {
            "bicycle",
            "bicycles",
            "cycling",
            "cyclist",
            "cyclists",
            "bikepacking",
            "bikepacking",
            "velodrome",
            "peloton",
            "criterium",
            "crit race",
            "roadbike",
            "road bike",
            "mountain bike",
            "mountain biking",
            "mtb",
            "gravel bike",
            "gravel biking",
            "gravel cycling",
            "bmx",
            "ebike",
            "e-bike",
            "e bike",
            "electric bike",
            "cargo bike",
            "cargo bike",
            "folding bike",
            "fixie",
            "fixed gear",
            "single speed",
            "cyclocross",
            "cycle touring",
            "bike tour",
            "bike tour",
        }

        # General cycling vocabulary.
        self.CYCLING_TERMS = {
            "bike",
            "bikes",
            "biking",
            "ride",
            "riding",
            "rider",
            "riders",
            "pedal",
            "pedaling",
            "pedalling",
            "cycling",
            "cyclist",
            "cycle",
            "cycles",
            "bicycle",
            "bicycling",
            "two wheels",
            "two-wheel",
            "two wheeled",
            "bike lane",
            "bike lanes",
            "cycle lane",
            "cycle lanes",
            "bike path",
            "bike paths",
            "bike trail",
            "bike trails",
            "bike route",
            "bike routes",
            "cycling route",
            "cycling routes",
            "bike commute",
            "bike commuting",
            "cycle commute",
            "cycling commute",
            "bike commute",
            "commuting by bike",
            "ride to work",
            "bike ride",
            "bike rides",
            "cycling trip",
            "cycling trips",
            "group ride",
            "group rides",
            "road ride",
            "road rides",
            "trail ride",
            "trail rides",
            "long ride",
            "long rides",
            "morning ride",
            "evening ride",
            "night ride",
            "weekend ride",
            "training ride",
            "cycling training",
            "bike maintenance",
            "bike repair",
            "bike repairs",
            "bike mechanic",
            "bike mechanics",
            "bicycle mechanic",
            "bicycle mechanics",
            "bike shop",
            "bike shops",
        }

        # Technical bicycle terms.
        # These are especially useful because they strongly indicate
        # someone is actually talking about bicycles.
        self.TECHNICAL_CYCLING_TERMS = {
            "derailleur",
            "derailleurs",
            "rear derailleur",
            "front derailleur",
            "shifter",
            "shifters",
            "cassette",
            "cassettes",
            "freehub",
            "freehub body",
            "chainring",
            "chainrings",
            "chain",
            "bike chain",
            "chain wear",
            "chain tool",
            "crank",
            "crankset",
            "crank arm",
            "bottom bracket",
            "bottom brackets",
            "brake rotor",
            "brake rotors",
            "disc brake",
            "disc brakes",
            "hydraulic brakes",
            "rim brakes",
            "brake pads",
            "bike brakes",
            "handlebar",
            "handlebars",
            "drop bars",
            "dropbar",
            "flat bars",
            "stem",
            "bike stem",
            "seatpost",
            "seat post",
            "saddle",
            "bike saddle",
            "wheelset",
            "wheelsets",
            "hub",
            "hubs",
            "spokes",
            "rim",
            "rims",
            "tire",
            "tires",
            "tyre",
            "tyres",
            "tubeless",
            "tubeless ready",
            "inner tube",
            "inner tubes",
            "puncture",
            "puncture repair",
            "bike tire",
            "bike tyre",
            "frame",
            "bike frame",
            "fork",
            "bike fork",
            "thru axle",
            "through axle",
            "quick release",
            "bike fit",
            "bike fitting",
            "cadence",
            "power meter",
            "power meter",
            "watts",
            "ftp",
            "cycling power",
            "bike computer",
            "cycling computer",
            "garmin",
            "wahoo",
            "strava",
            "kom",
            "qom",
            "cycling jersey",
            "cycling shorts",
            "bib shorts",
            "cycling helmet",
            "bike helmet",
            "clipless",
            "clipless pedals",
            "spd",
            "spd-sl",
            "look pedals",
            "bikepacking bags",
            "panniers",
            "bike rack",
            "bicycle rack",
            "bike light",
            "bike lights",
            "bike lock",
            "cycling gloves",
        }

        # Cycling styles / disciplines.
        self.DISCIPLINE_TERMS = {
            "road cycling",
            "road bike",
            "road biking",
            "road riding",
            "mountain biking",
            "mountain bike",
            "mtb",
            "gravel",
            "gravel bike",
            "gravel riding",
            "gravel cycling",
            "bikepacking",
            "bicycle touring",
            "cycle touring",
            "touring bike",
            "commuter bike",
            "commuter cycling",
            "urban cycling",
            "city cycling",
            "bmx",
            "downhill",
            "downhill mtb",
            "enduro",
            "trail riding",
            "cross country mtb",
            "xc mtb",
            "cyclocross",
            "track cycling",
            "track bike",
            "criterium",
            "crit racing",
            "time trial",
            "tt bike",
            "triathlon bike",
            "tri bike",
            "fixed gear",
            "fixie",
            "single speed",
            "cargo cycling",
            "cargo bike",
            "ebike",
            "e-bike",
            "electric bike",
            "electric bicycle",
        }

        # Terms that should strongly reduce relevance.
        # These aren't necessarily bad posts, just posts that are
        # very likely to be unrelated to cycling.
        self.IRRELEVANT_TERMS = {
            "crypto",
            "cryptocurrency",
            "bitcoin",
            "ethereum",
            "nft",
            "airdrop",
            "token",
            "forex",
            "trading signals",
            "stock picks",
            "giveaway",
            "giveaways",
            "free money",
            "make money",
            "passive income",
            "onlyfans",
            "fansly",
            "porn",
            "porno",
            "pornography",
            "nsfw",
            "nudes",
            "nude",
            "sex",
            "sexual",
            "sexy",
            "xxx",
            "explicit",
            "erotic",
            "escort",
            "hookup",
            "hookups",
            "dating",
            "sugar daddy",
            "sugar mommy",
            "cash app",
            "telegram",
            "whatsapp me",
            "dm me",
            "follow for follow",
            "f4f",
            "followback",
            "follow back",
            "engagement bait",
            "rage bait",
            "politics",
            "political",
        }

        # Words/phrases that are strong enough to reject the post
        # even if a cycling word appears somewhere.
        self.HARD_BLOCK_TERMS = {
            "onlyfans",
            "fansly",
            "pornhub",
            "pornography",
            "explicit content",
            "sexual content",
            "sex video",
            "sex videos",
            "nude pics",
            "nudes",
            "send nudes",
            "nsfw account",
            "nsfw content",
            "xxx content",
        }

        # Cycling hashtags are particularly useful.
        self.CYCLING_HASHTAGS = {
            "#cycling",
            "#cyclist",
            "#cyclinglife",
            "#cyclinglifestyle",
            "#bike",
            "#bikes",
            "#biking",
            "#bikelife",
            "#bikeride",
            "#biketouring",
            "#bikepacking",
            "#roadcycling",
            "#roadbike",
            "#mtb",
            "#mountainbike",
            "#mountainbiking",
            "#gravel",
            "#gravelbike",
            "#gravelcycling",
            "#bmx",
            "#ebike",
            "#ebikes",
            "#e-bike",
            "#commutecycling",
            "#bikecommute",
            "#cyclingtips",
            "#bikerepair",
            "#bikemechanic",
            "#bikeshop",
            "#cyclingcommunity",
            "#cyclingphotography",
        }

        # -------------------------------------------------
        # UTILS
        # -------------------------------------------------

    def jitter(self, min_s=2, max_s=5):
        delay = random.uniform(min_s, max_s)
        print(f"⏱️ Sleeping {delay:.2f}s")

        sleep_start = time.time()

        while time.time() - sleep_start < delay:
            if self.stop_event.is_set():
                return

            time.sleep(0.5)

    def retry(self, func, retries=3, base_delay=2):
        for attempt in range(retries):
            if self.stop_event.is_set():
                return None

            try:
                return func()

            except Exception as e:
                print(f"⚠️ Retry {attempt + 1}/{retries}: {e}")

                for _ in range(base_delay * (attempt + 1)):
                    if self.stop_event.is_set():
                        return None

                    time.sleep(1)

        return None

    def safe_get(self, obj, attr, default=None):
        return getattr(obj, attr, default) if obj else default

    def normalize_text(self, text):
        """
        Normalize text before relevance checks.

        This helps make:
            ROAD-BIKE
            road bike
            road_bike
            ROADBIKE

        easier to detect.
        """
        if not text:
            return ""

        text = str(text).lower()

        # Normalize common separators.
        text = text.replace("_", " ")
        text = text.replace("-", " ")

        # Collapse whitespace.
        text = re.sub(r"\s+", " ", text)

        return text.strip()

    def contains_term(self, text, term):
        """
        More accurate matching than simple:
            if term in text

        This reduces false positives from words that merely contain
        another word.
        """
        text = self.normalize_text(text)
        term = self.normalize_text(term)

        if not text or not term:
            return False

        # For multi-word phrases, normal substring matching is okay.
        if " " in term:
            return term in text

        return bool(re.search(rf"\b{re.escape(term)}\b", text))

    def count_matches(self, text, terms):
        count = 0
        matched = []

        for term in terms:
            if self.contains_term(text, term):
                count += 1
                matched.append(term)

        return count, matched

    # -------------------------------------------------
    # AUTH
    # -------------------------------------------------

    def login(self):
        try:
            self.client.login(
                Config.BLUESKY_HANDLE,
                Config.BLUESKY_PASSWORD
            )

            print("✅ Logged into Bluesky")
            return True

        except Exception as e:
            print(f"❌ Login failed: {e}")
            return False

    # -------------------------------------------------
    # FOLLOWER SYNC
    # -------------------------------------------------

    def sync_followers(self):
        """Sync our followers list and track changes."""

        if self.stop_event.is_set():
            return

        try:
            print("\n🔄 Syncing followers...")

            followers = []
            cursor = None

            while True:
                if self.stop_event.is_set():
                    return

                response = self.client.get_followers(
                    self.client.me.did,
                    cursor=cursor,
                    limit=100
                )

                for follower in response.followers:
                    followers.append({
                        "did": follower.did,
                        "handle": follower.handle,
                        "display_name": getattr(
                            follower,
                            "display_name",
                            None
                        ),
                        "avatar": getattr(
                            follower,
                            "avatar",
                            None
                        ),
                        "profile_data": {
                            "description": getattr(
                                follower,
                                "description",
                                None
                            ),
                            "avatar": getattr(
                                follower,
                                "avatar",
                                None
                            ),
                            "followers_count": getattr(
                                follower,
                                "followers_count",
                                0
                            ),
                            "follows_count": getattr(
                                follower,
                                "follows_count",
                                0
                            ),
                            "posts_count": getattr(
                                follower,
                                "posts_count",
                                0
                            )
                        }
                    })

                if not response.cursor:
                    break

                cursor = response.cursor

                if self.stop_event.wait(1):
                    return

            new_followers, unfollowers = self.db.sync_followers(
                followers
            )

            print("📊 Follower sync complete:")
            print(f"   • Total followers: {len(followers)}")
            print(f"   • New followers: {len(new_followers)}")
            print(f"   • Unfollowers: {len(unfollowers)}")

            if not self.stop_event.is_set():
                self.check_follow_backs()

            self.last_follower_sync = datetime.now()

        except Exception as e:
            print(f"⚠️ Follower sync error: {e}")

    def check_follow_backs(self):
        """Check which users we followed are following us back."""

        if self.stop_event.is_set():
            return

        users_to_check = self.db.get_users_to_check_follow_back(
            hours=24
        )

        for user in users_to_check:
            if self.stop_event.is_set():
                return

            try:
                follows = self.client.app.bsky.graph.get_follows({
                    "actor": user["did"]
                })

                is_following_us = any(
                    follow.subject.did == self.client.me.did
                    for follow in follows.follows
                )

                self.db.update_follow_back_status(
                    user["did"],
                    is_following_us
                )

                if is_following_us:
                    print(
                        f"🔄 @{user['handle']} followed you back!"
                    )

                    self.db.add_follow_back(
                        user["did"],
                        user["handle"],
                        user.get("display_name")
                    )

                for _ in range(2):
                    if self.stop_event.is_set():
                        return

                    time.sleep(1)

            except Exception as e:
                print(
                    f"⚠️ Error checking follow-back for "
                    f"@{user['handle']}: {e}"
                )

    # -------------------------------------------------
    # SEARCH
    # -------------------------------------------------

    def search_posts_by_keywords(self, keywords):
        all_posts = []

        for keyword in keywords[:5]:
            if self.stop_event.is_set():
                return []

            try:
                print(f"🔍 Searching: {keyword}")

                response = self.retry(
                    lambda: self.client.app.bsky.feed.search_posts({
                        "q": keyword,
                        "limit": 20,
                        "sort": "latest"
                    })
                )

                if not response or not hasattr(response, "posts"):
                    continue

                for post in response.posts:

                    # Skip our own posts.
                    if post.author.did == self.client.me.did:
                        continue

                    post_view = getattr(post, "post", post)

                    # Some API versions expose labels here.
                    labels = getattr(post_view, "labels", None)

                    # Extract label values safely.
                    label_values = []

                    if labels:
                        for label in labels:
                            value = getattr(label, "val", None)

                            if value:
                                label_values.append(str(value).lower())

                    all_posts.append({
                        "uri": post.uri,
                        "cid": post.cid,

                        "author_did": post.author.did,
                        "author_handle": post.author.handle,

                        "author_display_name": getattr(
                            post.author,
                            "display_name",
                            None
                        ),

                        "author_avatar": getattr(
                            post.author,
                            "avatar",
                            None
                        ),

                        "author_description": getattr(
                            post.author,
                            "description",
                            ""
                        ),

                        "text": getattr(
                            post.record,
                            "text",
                            ""
                        ),

                        "keyword": keyword,

                        "created_at": getattr(
                            post.record,
                            "created_at",
                            None
                        ),

                        "labels": label_values
                    })

                print(f"   → {len(response.posts)} posts")

                self.jitter(1, 3)

            except Exception as e:
                print(f"⚠️ Search error: {e}")

        # -------------------------------------------------
        # DEDUPLICATE
        # -------------------------------------------------

        seen = set()
        unique = []

        for post in all_posts:
            if post["uri"] in seen:
                continue

            seen.add(post["uri"])
            unique.append(post)

        print(f"📊 Unique posts: {len(unique)}")

        return unique

    # -------------------------------------------------
    # NSFW / SPAM DETECTION
    # -------------------------------------------------

    def is_nsfw_or_explicit(self, post):
        """
        Detect obvious NSFW/sexual content.

        We intentionally reject rather than try to score this content.
        """

        text = self.normalize_text(
            post.get("text", "")
        )

        author_description = self.normalize_text(
            post.get("author_description", "")
        )

        author_name = self.normalize_text(
            post.get("author_display_name", "")
        )

        combined = " ".join([
            text,
            author_description,
            author_name
        ])

        # Check Bluesky moderation labels when available.
        labels = [
            str(label).lower()
            for label in post.get("labels", [])
        ]

        nsfw_labels = {
            "porn",
            "sexual",
            "nudity",
            "nsfw",
            "graphic-media",
            "adult",
        }

        if any(label in nsfw_labels for label in labels):
            return True, "Bluesky moderation label"

        # Hard block phrases.
        for term in self.HARD_BLOCK_TERMS:
            if self.contains_term(combined, term):
                return True, term

        return False, None

    def is_obvious_spam(self, post):
        """
        Detect obvious spam/promotional content that isn't cycling.
        """

        text = self.normalize_text(
            post.get("text", "")
        )

        spam_matches = [
            "airdrop",
            "free crypto",
            "free bitcoin",
            "crypto giveaway",
            "nft giveaway",
            "make money fast",
            "easy money",
            "passive income",
            "follow for follow",
            "followback",
            "f4f",
        ]

        for term in spam_matches:
            if self.contains_term(text, term):
                return True

        return False

    # -------------------------------------------------
    # CYCLING RELEVANCE
    # -------------------------------------------------

    def get_cycling_score(self, post):
        """
        Calculate how strongly a post is related to cycling.

        IMPORTANT:
        Randomness is NOT used to make irrelevant posts qualify.

        Score is based on actual content.
        """

        text = self.normalize_text(
            post.get("text", "")
        )

        author_description = self.normalize_text(
            post.get("author_description", "")
        )

        author_name = self.normalize_text(
            post.get("author_display_name", "")
        )

        # The main body gets the highest priority.
        body_text = text

        score = 0
        matched = []

        # -------------------------------------------------
        # HARD REJECTION
        # -------------------------------------------------

        nsfw, reason = self.is_nsfw_or_explicit(post)

        if nsfw:
            return {
                "score": -100,
                "qualified": False,
                "reason": f"NSFW/explicit: {reason}",
                "matched": []
            }

        if self.is_obvious_spam(post):
            return {
                "score": -50,
                "qualified": False,
                "reason": "obvious spam",
                "matched": []
            }

        # -------------------------------------------------
        # STRONG CYCLING TERMS
        # -------------------------------------------------

        strong_count, strong_matches = self.count_matches(
            body_text,
            self.STRONG_CYCLING_TERMS
        )

        if strong_count:
            score += min(strong_count * 4, 16)
            matched.extend(strong_matches)

        # -------------------------------------------------
        # TECHNICAL TERMS
        # -------------------------------------------------

        technical_count, technical_matches = self.count_matches(
            body_text,
            self.TECHNICAL_CYCLING_TERMS
        )

        if technical_count:
            score += min(technical_count * 3, 15)
            matched.extend(technical_matches)

        # -------------------------------------------------
        # DISCIPLINE TERMS
        # -------------------------------------------------

        discipline_count, discipline_matches = self.count_matches(
            body_text,
            self.DISCIPLINE_TERMS
        )

        if discipline_count:
            score += min(discipline_count * 4, 12)
            matched.extend(discipline_matches)

        # -------------------------------------------------
        # GENERAL CYCLING TERMS
        # -------------------------------------------------

        general_count, general_matches = self.count_matches(
            body_text,
            self.CYCLING_TERMS
        )

        if general_count:
            score += min(general_count * 2, 10)
            matched.extend(general_matches)

        # -------------------------------------------------
        # HASHTAGS
        # -------------------------------------------------

        for hashtag in self.CYCLING_HASHTAGS:
            if hashtag in body_text:
                score += 3
                matched.append(hashtag)

        # -------------------------------------------------
        # AUTHOR PROFILE
        # -------------------------------------------------

        profile_count, profile_matches = self.count_matches(
            author_description,
            self.CYCLING_TERMS |
            self.DISCIPLINE_TERMS |
            self.STRONG_CYCLING_TERMS
        )

        if profile_count:
            # Profile relevance is useful, but should never
            # make an unrelated post qualify by itself.
            score += min(profile_count * 1, 4)

        name_count, name_matches = self.count_matches(
            author_name,
            self.CYCLING_TERMS |
            self.DISCIPLINE_TERMS |
            self.STRONG_CYCLING_TERMS
        )

        if name_count:
            score += min(name_count, 2)

        # -------------------------------------------------
        # NEGATIVE TERMS
        # -------------------------------------------------

        negative_count, negative_matches = self.count_matches(
            body_text,
            self.IRRELEVANT_TERMS
        )

        if negative_count:
            score -= negative_count * 6

        # -------------------------------------------------
        # CONTEXTUAL BONUS
        # -------------------------------------------------

        # A single "bike" mention can be weak.
        # Two or more cycling concepts in the same post are
        # much more likely to be genuinely about cycling.
        if general_count + strong_count + technical_count >= 2:
            score += 4

        # Technical combinations are especially strong.
        if technical_count >= 2:
            score += 4

        # A post containing actual cycling + cycling activity
        # is stronger than a random mention of "bike".
        activity_terms = {
            "ride",
            "riding",
            "cycling",
            "biking",
            "commuting",
            "training",
            "race",
            "racing",
            "touring",
            "bikepacking",
        }

        equipment_terms = {
            "bike",
            "bicycle",
            "derailleur",
            "cassette",
            "chain",
            "tire",
            "tyre",
            "wheel",
            "wheels",
            "brake",
            "brakes",
            "helmet",
            "pedals",
            "pedal",
            "frame",
            "fork",
            "saddle",
            "handlebar",
            "tubeless",
        }

        has_activity = any(
            self.contains_term(body_text, term)
            for term in activity_terms
        )

        has_equipment = any(
            self.contains_term(body_text, term)
            for term in equipment_terms
        )

        if has_activity and has_equipment:
            score += 5

        # -------------------------------------------------
        # QUALIFICATION
        # -------------------------------------------------

        # Require actual cycling evidence.
        #
        # Profile alone cannot qualify a post.
        body_cycling_matches = (
            strong_count
            + technical_count
            + discipline_count
            + general_count
        )

        # Very strong cycling posts can qualify with one strong
        # technical/discipline term.
        strong_enough = (
            strong_count >= 1
            or technical_count >= 1
            or discipline_count >= 1
        )

        # Otherwise require at least two general signals.
        enough_context = (
            body_cycling_matches >= 2
        )

        # This is intentionally conservative.
        qualified = (
            score >= 7
            and strong_enough
            and (
                enough_context
                or technical_count >= 1
                or discipline_count >= 1
            )
            and negative_count == 0
        )

        if qualified:
            reason = "cycling relevance passed"
        elif negative_count:
            reason = "irrelevant/spam terms detected"
        elif not strong_enough:
            reason = "not enough cycling evidence"
        else:
            reason = "cycling score too low"

        # Remove duplicate matched terms.
        matched = list(dict.fromkeys(matched))

        return {
            "score": score,
            "qualified": qualified,
            "reason": reason,
            "matched": matched[:12],
        }

    # -------------------------------------------------
    # ENGAGEMENT SCORE
    # -------------------------------------------------

    def should_engage(self, post):
        """
        Decide whether the bot should engage.

        This now uses actual cycling relevance first.
        Randomness can influence engagement AFTER the post
        has already passed relevance.
        """

        relevance = self.get_cycling_score(post)

        print(
            f"   🎯 Relevance: {relevance['score']} "
            f"| {relevance['reason']}"
        )

        if relevance["matched"]:
            print(
                f"   🚲 Matches: "
                f"{', '.join(relevance['matched'][:8])}"
            )

        if not relevance["qualified"]:
            return False

        # Don't engage with users who unfollowed us recently.
        unfollowers = self.db.get_unfollowers(days=7)

        if any(
            u["did"] == post["author_did"]
            for u in unfollowers
        ):
            print(
                "   ⏭️ Author recently unfollowed us"
            )
            return False

        # Optional randomness AFTER relevance has passed.
        #
        # This means randomness can reduce activity,
        # but can never turn an irrelevant post into a
        # relevant post.
        engagement_probability = 0.85

        if random.random() > engagement_probability:
            print("   🎲 Random engagement skip")
            return False

        return True

    # -------------------------------------------------
    # FOLLOW
    # -------------------------------------------------

    def follow_user(
        self,
        did,
        handle,
        name=None,
        avatar=None
    ):
        if not Config.AUTO_FOLLOW:
            return False

        if (
            self.db.get_followed_count_today()
            >= Config.MAX_FOLLOWS_PER_DAY
        ):
            return False

        if self.db.was_followed(did):
            return False

        # Don't follow users who unfollowed us recently.
        unfollowers = self.db.get_unfollowers(days=14)

        if any(
            u["did"] == did
            for u in unfollowers
        ):
            print(
                f"⏭️ Skipping @{handle} - "
                f"they unfollowed recently"
            )
            return False

        try:
            print(f"➕ Following @{handle}")

            self.retry(
                lambda: self.client.follow(did)
            )

            self.db.add_follow(
                did,
                handle,
                name,
                avatar
            )

            self.followed_today += 1

            return True

        except Exception as e:
            print(f"⚠️ Follow error: {e}")
            return False

    # -------------------------------------------------
    # LIKE
    # -------------------------------------------------

    def like_post(self, post):
        if self.db.was_liked(post["uri"]):
            return False

        if (
            self.db.get_likes_count_today()
            >= Config.MAX_LIKES_PER_DAY
        ):
            return False

        try:
            print(
                f"❤️ Liking @{post['author_handle']}"
            )

            result = self.retry(
                lambda: self.client.like(
                    post["uri"],
                    post["cid"]
                )
            )

            if result is None:
                return False

            self.db.add_liked_post(
                post["uri"],
                post["author_did"],
                post["author_handle"],
                {
                    "text": post["text"][:150],
                    "author_avatar": post.get(
                        "author_avatar"
                    ),
                    "author_display_name": post.get(
                        "author_display_name"
                    ),
                    "created_at": post.get(
                        "created_at"
                    )
                }
            )

            self.likes_today += 1

            return True

        except Exception as e:
            print(f"⚠️ Like error: {e}")
            return False

    # -------------------------------------------------
    # REPOST
    # -------------------------------------------------

    def repost_post(self, post):
        """
        Repost only posts that already passed relevance.

        Probability is kept at 15% to avoid reposting
        everything we like.
        """

        if random.random() > 0.15:
            return False

        try:
            print(
                f"🔄 Reposting @{post['author_handle']}"
            )

            result = self.retry(
                lambda: self.client.repost(
                    post["uri"],
                    post["cid"]
                )
            )

            if result is None:
                return False

            self.reposts_today += 1

            return True

        except Exception as e:
            print(f"⚠️ Repost error: {e}")
            return False

    # -------------------------------------------------
    # PROCESS POST
    # -------------------------------------------------

    def process_post(self, post):
        if self.stop_event.is_set():
            return 0

        print(
            f"\n📌 @{post['author_handle']}"
        )

        preview = post.get("text", "").replace(
            "\n",
            " "
        )

        print(
            f"📝 {preview[:140]}"
            f"{'...' if len(preview) > 140 else ''}"
        )

        # -------------------------------------------------
        # NSFW CHECK BEFORE EVERYTHING ELSE
        # -------------------------------------------------

        nsfw, reason = self.is_nsfw_or_explicit(post)

        if nsfw:
            print(
                f"🚫 SKIPPED NSFW/EXPLICIT: {reason}"
            )
            return 0

        # -------------------------------------------------
        # RELEVANCE CHECK
        # -------------------------------------------------

        if not self.should_engage(post):
            print(
                "⏭️ Skipped - not sufficiently cycling-related"
            )
            return 0

        print(
            "✅ Cycling post passed relevance filter"
        )

        actions = 0

        # -------------------------------------------------
        # FOLLOW
        # -------------------------------------------------

        if self.follow_user(
            post["author_did"],
            post["author_handle"],
            post.get("author_display_name"),
            post.get("author_avatar")
        ):
            actions += 1

        # -------------------------------------------------
        # LIKE
        # -------------------------------------------------

        if random.random() < 0.70:
            if self.like_post(post):
                actions += 1

        # -------------------------------------------------
        # REPOST
        # -------------------------------------------------

        if self.repost_post(post):
            actions += 1

        self.total_actions += actions

        return actions

    # -------------------------------------------------
    # MAIN RUN
    # -------------------------------------------------

    def run_once(self):
        if (
            self.stop_event.is_set()
            or self.paused
            or not self.running
        ):
            return

        print(
            f"\n🚀 Run @ {datetime.now()}"
        )

        # -------------------------------------------------
        # LOGIN
        # -------------------------------------------------

        if not self.client.me:
            if not self.login():
                return

        # -------------------------------------------------
        # FOLLOWER SYNC
        # -------------------------------------------------

        if (
            self.last_follower_sync is None
            or (
                datetime.now()
                - self.last_follower_sync
                > timedelta(hours=1)
            )
        ):
            if not self.stop_event.is_set():
                self.sync_followers()

        # -------------------------------------------------
        # KEYWORDS
        # -------------------------------------------------

        keywords = self.db.get_active_keywords()

        if not keywords:
            print("⚠️ No keywords")
            return

        print(
            f"🔎 Active search keywords: "
            f"{', '.join(keywords)}"
        )

        # -------------------------------------------------
        # SEARCH
        # -------------------------------------------------

        posts = self.search_posts_by_keywords(
            keywords
        )

        if self.stop_event.is_set():
            return

        # Shuffle so we're not always processing the
        # same keyword order.
        random.shuffle(posts)

        processed = 0
        engaged = 0

        # -------------------------------------------------
        # PROCESS
        # -------------------------------------------------

        for post in posts:

            if (
                self.stop_event.is_set()
                or self.paused
            ):
                break

            actions = self.process_post(post)

            processed += 1

            if actions > 0:
                engaged += 1

            self.jitter(8, 20)

        # -------------------------------------------------
        # DATABASE STATUS
        # -------------------------------------------------

        self.db.update_bot_status(
            last_run=datetime.now(),
            next_run=(
                datetime.now()
                + timedelta(
                    seconds=Config.CHECK_INTERVAL
                )
            ),
            error=None
        )

        # -------------------------------------------------
        # SUMMARY
        # -------------------------------------------------

        print("\n📊 SUMMARY")
        print(
            f"Posts processed: {processed}"
        )
        print(
            f"Posts engaged: {engaged}"
        )
        print(
            f"Likes: {self.likes_today}"
        )
        print(
            f"Follows: {self.followed_today}"
        )
        print(
            f"Reposts: {self.reposts_today}"
        )
        print(
            f"Total actions: {self.total_actions}"
        )

    # -------------------------------------------------
    # LOOP
    # -------------------------------------------------

    def _run_loop(self):
        self._thread_stopped = False

        print("🟢 Bot loop started")

        while not self.stop_event.is_set():

            try:

                # Only run if not paused and running.
                if (
                    not self.paused
                    and self.running
                    and not self.stop_event.is_set()
                ):
                    self.run_once()

                # -------------------------------------------------
                # WAIT
                # -------------------------------------------------

                wait = (
                    Config.CHECK_INTERVAL
                    + random.randint(-30, 60)
                )

                wait = max(10, wait)

                print(
                    f"💤 Sleeping {wait}s"
                )

                # Break sleep into 1-second chunks so stop
                # works quickly.
                for _ in range(wait):

                    if self.stop_event.is_set():
                        print(
                            "🛑 Stop event detected "
                            "during sleep"
                        )
                        break

                    time.sleep(1)

            except Exception as e:

                print(
                    f"⚠️ Loop crash: {e}"
                )

                # Short recovery delay.
                for _ in range(5):

                    if self.stop_event.is_set():
                        break

                    time.sleep(1)

        self._thread_stopped = True

        print(
            "🛑 Bot loop ended"
        )

    # -------------------------------------------------
    # CONTROL
    # -------------------------------------------------

    def start(self):

        with self._stop_lock:

            # Kill existing thread first.
            if (
                self.thread
                and self.thread.is_alive()
            ):
                print(
                    "⚠️ Stopping existing thread..."
                )

                self.stop()

            # Give old thread a moment to finish.
            time.sleep(1)

            # Reset.
            self.running = True
            self.paused = False
            self.stop_event.clear()

            # Reset session counters.
            self.followed_today = 0
            self.likes_today = 0
            self.reposts_today = 0
            self.total_actions = 0

            # Create and start thread.
            self.thread = threading.Thread(
                target=self._run_loop,
                daemon=True
            )

            self.thread.start()

            print("✅ Bot started")

            self.db.update_bot_status(
                is_running=True
            )

    def stop(self):

        print("⏹️ Stopping bot...")

        with self._stop_lock:

            # Signal stop FIRST.
            self.running = False
            self.stop_event.set()

            # Wait for thread to finish.
            if (
                self.thread
                and self.thread.is_alive()
            ):

                print(
                    "⏳ Waiting for thread to stop..."
                )

                self.thread.join(
                    timeout=15
                )

                if self.thread.is_alive():

                    print(
                        "⚠️ Thread still alive "
                        "after 15 seconds"
                    )

                    # Ensure stop remains signaled.
                    self.stop_event.set()
                    self.running = False

                else:
                    print(
                        "✅ Thread stopped"
                    )

            self.thread = None

            self.db.update_bot_status(
                is_running=False
            )

            print("✅ Bot stopped")

    def pause(self):

        self.paused = True

        print("⏸️ Bot paused")

        self.db.update_bot_status(
            is_running=True
        )

    def resume(self):

        self.paused = False
        self.running = True

        print("▶️ Bot resumed")

        self.db.update_bot_status(
            is_running=True
        )

    def is_running(self):
        """Check if bot is actually running."""

        return (
            self.running
            and self.thread
            and self.thread.is_alive()
            and not self.stop_event.is_set()
        )