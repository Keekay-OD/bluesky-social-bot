# In Z:\Docker\AppData\Config\bluesky-social-bot\app\bot.py

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
        self.stop_event = threading.Event()

        # Session counters
        self.followed_today = 0
        self.likes_today = 0
        self.reposts_today = 0

        # Lifetime counters (optional)
        self.total_actions = 0
        
        # Follower tracking
        self.last_follower_sync = None

    # -------------------------------------------------
    # UTILS
    # -------------------------------------------------
    def jitter(self, min_s=2, max_s=5):
        delay = random.uniform(min_s, max_s)
        print(f"⏱️ Sleeping {delay:.2f}s")
        time.sleep(delay)

    def retry(self, func, retries=3, base_delay=2):
        for attempt in range(retries):
            try:
                return func()
            except Exception as e:
                print(f"⚠️ Retry {attempt+1}/{retries}: {e}")
                time.sleep(base_delay * (attempt + 1))
        return None

    def safe_get(self, obj, attr, default=None):
        return getattr(obj, attr, default) if obj else default

    # -------------------------------------------------
    # AUTH
    # -------------------------------------------------
    def login(self):
        try:
            self.client.login(Config.BLUESKY_HANDLE, Config.BLUESKY_PASSWORD)
            print("✅ Logged into Bluesky")
            return True
        except Exception as e:
            print(f"❌ Login failed: {e}")
            return False

    # -------------------------------------------------
    # FOLLOWER SYNC (NEW)
    # -------------------------------------------------
    def sync_followers(self):
        """Sync our followers list and track changes"""
        try:
            print("\n🔄 Syncing followers...")
            
            # Get our followers from Bluesky
            followers = []
            cursor = None
            
            while True:
                response = self.client.get_followers(self.client.me.did, cursor=cursor, limit=100)
                
                for follower in response.followers:
                    followers.append({
                        'did': follower.did,
                        'handle': follower.handle,
                        'display_name': getattr(follower, 'display_name', None),
                        'profile_data': {
                            'description': getattr(follower, 'description', None),
                            'avatar': getattr(follower, 'avatar', None),
                            'followers_count': getattr(follower, 'followers_count', 0),
                            'follows_count': getattr(follower, 'follows_count', 0),
                            'posts_count': getattr(follower, 'posts_count', 0)
                        }
                    })
                
                if not response.cursor:
                    break
                cursor = response.cursor
                time.sleep(1)
            
            # Sync with database
            new_followers, unfollowers = self.db.sync_followers(followers)
            
            print(f"📊 Follower sync complete:")
            print(f"   • Total followers: {len(followers)}")
            print(f"   • New followers: {len(new_followers)}")
            print(f"   • Unfollowers: {len(unfollowers)}")
            
            # Check follow-back status for users we followed
            self.check_follow_backs()
            
            self.last_follower_sync = datetime.now()
            
        except Exception as e:
            print(f"⚠️ Follower sync error: {e}")
    
    def check_follow_backs(self):
        """Check which users we followed are following us back"""
        users_to_check = self.db.get_users_to_check_follow_back(hours=24)
        
        for user in users_to_check:
            try:
                # Check if they follow us
                follows = self.client.app.bsky.graph.get_follows({
                    'actor': user['did']
                })
                
                is_following_us = any(follow.subject.did == self.client.me.did 
                                      for follow in follows.follows)
                
                self.db.update_follow_back_status(user['did'], is_following_us)
                
                if is_following_us:
                    print(f"🔄 @{user['handle']} followed you back!")
                    self.db.add_follow_back(
                        user['did'],
                        user['handle'],
                        user.get('display_name')
                    )
                
                time.sleep(2)
                
            except Exception as e:
                print(f"⚠️ Error checking follow-back for @{user['handle']}: {e}")

    # -------------------------------------------------
    # SEARCH
    # -------------------------------------------------
    def search_posts_by_keywords(self, keywords):
        all_posts = []

        for keyword in keywords[:5]:
            try:
                print(f"🔍 Searching: {keyword}")

                response = self.retry(lambda: self.client.app.bsky.feed.search_posts({
                    "q": keyword,
                    "limit": 20,
                    "sort": "latest"
                }))

                if not response or not hasattr(response, "posts"):
                    continue

                for post in response.posts:
                    # Skip our own posts
                    if post.author.did == self.client.me.did:
                        continue
                        
                    all_posts.append({
                        'uri': post.uri,
                        'cid': post.cid,
                        'author_did': post.author.did,
                        'author_handle': post.author.handle,
                        'author_display_name': getattr(post.author, 'display_name', None),
                        'text': getattr(post.record, 'text', ''),
                        'keyword': keyword,
                        'created_at': getattr(post.record, 'created_at', None)
                    })

                print(f"   → {len(response.posts)} posts")
                self.jitter(1, 3)

            except Exception as e:
                print(f"⚠️ Search error: {e}")

        # Deduplicate
        seen = set()
        unique = []
        for p in all_posts:
            if p['uri'] not in seen:
                seen.add(p['uri'])
                unique.append(p)

        print(f"📊 Unique posts: {len(unique)}")
        return unique

    # -------------------------------------------------
    # ENGAGEMENT SCORE
    # -------------------------------------------------
    def should_engage(self, post):
        text = post['text'].lower()

        score = 0

        # Keyword boost
        if any(k in text for k in self.db.get_active_keywords()):
            score += 2

        # Engagement randomness
        score += random.randint(0, 3)

        # Short posts often perform better
        if len(text) < 200:
            score += 1
            
        # Don't engage with users who unfollowed us recently
        unfollowers = self.db.get_unfollowers(days=7)
        if any(u['did'] == post['author_did'] for u in unfollowers):
            score -= 5  # Strong penalty

        return score >= 3

    # -------------------------------------------------
    # FOLLOW
    # -------------------------------------------------
    def follow_user(self, did, handle, name=None):
        if not Config.AUTO_FOLLOW:
            return False

        if self.db.get_followed_count_today() >= Config.MAX_FOLLOWS_PER_DAY:
            return False

        if self.db.was_followed(did):
            return False
            
        # Don't follow users who unfollowed us recently
        unfollowers = self.db.get_unfollowers(days=14)
        if any(u['did'] == did for u in unfollowers):
            print(f"⏭️ Skipping @{handle} - they unfollowed recently")
            return False

        try:
            print(f"➕ Following @{handle}")

            self.retry(lambda: self.client.follow(did))

            self.db.add_follow(did, handle, name)
            self.followed_today += 1
            return True

        except Exception as e:
            print(f"⚠️ Follow error: {e}")
            return False

    # -------------------------------------------------
    # LIKE
    # -------------------------------------------------
    def like_post(self, post):
        if self.db.was_liked(post['uri']):
            return False

        if self.db.get_likes_count_today() >= Config.MAX_LIKES_PER_DAY:
            return False

        try:
            print(f"❤️ @{post['author_handle']}")

            self.retry(lambda: self.client.like(post['uri'], post['cid']))

            self.db.add_liked_post(
                post['uri'],
                post['author_did'],
                post['author_handle'],
                {"text": post['text'][:150]}
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
        if random.random() > 0.15:
            return False

        try:
            print(f"🔄 Reposting @{post['author_handle']}")

            self.retry(lambda: self.client.repost(post['uri'], post['cid']))

            self.reposts_today += 1
            return True

        except Exception as e:
            print(f"⚠️ Repost error: {e}")
            return False

    # -------------------------------------------------
    # PROCESS POST
    # -------------------------------------------------
    def process_post(self, post):
        print(f"\n📌 @{post['author_handle']}")
        print(f"📝 {post['text'][:80]}...")

        if not self.should_engage(post):
            print("⏭️ Skipped (low score)")
            return 0

        actions = 0

        if self.follow_user(post['author_did'], post['author_handle'], post['author_display_name']):
            actions += 1

        if random.random() < 0.6:
            if self.like_post(post):
                actions += 1

        if self.repost_post(post):
            actions += 1

        self.total_actions += actions
        return actions

    # -------------------------------------------------
    # MAIN RUN
    # -------------------------------------------------
    def run_once(self):
        print(f"\n🚀 Run @ {datetime.now()}")

        if self.paused or not self.running:
            return

        if not self.client.me:
            if not self.login():
                return
                
        # Sync followers every hour
        if (self.last_follower_sync is None or 
            datetime.now() - self.last_follower_sync > timedelta(hours=1)):
            self.sync_followers()

        keywords = self.db.get_active_keywords()
        if not keywords:
            print("⚠️ No keywords")
            return

        posts = self.search_posts_by_keywords(keywords)

        random.shuffle(posts)

        processed = 0

        for post in posts:
            if self.stop_event.is_set() or self.paused:
                break

            self.process_post(post)
            processed += 1
            self.jitter(8, 20)

        self.db.update_bot_status(
            last_run=datetime.now(),
            next_run=datetime.now() + timedelta(seconds=Config.CHECK_INTERVAL),
            error=None
        )

        print("\n📊 SUMMARY")
        print(f"Posts processed: {processed}")
        print(f"Likes: {self.likes_today}")
        print(f"Follows: {self.followed_today}")
        print(f"Reposts: {self.reposts_today}")
        print(f"Total actions: {self.total_actions}")

    # -------------------------------------------------
    # LOOP
    # -------------------------------------------------
    def _run_loop(self):
        while not self.stop_event.is_set():
            try:
                if not self.paused:
                    self.run_once()

                wait = Config.CHECK_INTERVAL + random.randint(-30, 60)
                print(f"💤 Sleeping {wait}s")

                if self.stop_event.wait(wait):
                    break

            except Exception as e:
                print(f"⚠️ Loop crash: {e}")
                if self.stop_event.wait(120):
                    break

    # -------------------------------------------------
    # CONTROL
    # -------------------------------------------------
    def start(self):
        if self.thread and self.thread.is_alive():
            return

        self.running = True
        self.paused = False
        self.stop_event.clear()

        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

        print("✅ Bot started")
        self.db.update_bot_status(is_running=True)

    def stop(self):
        print("⏹️ Stopping...")

        self.running = False
        self.stop_event.set()

        if self.thread:
            self.thread.join(timeout=5)

        self.db.update_bot_status(is_running=False)
        print("✅ Stopped")

    def pause(self):
        self.paused = True
        print("⏸️ Paused")

    def resume(self):
        self.paused = False
        self.running = True
        print("▶️ Resumed")