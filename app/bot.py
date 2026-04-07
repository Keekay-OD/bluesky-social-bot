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
        self._stop_lock = threading.Lock()
        self._thread_stopped = True

        # Session counters
        self.followed_today = 0
        self.likes_today = 0
        self.reposts_today = 0

        # Lifetime counters
        self.total_actions = 0
        
        # Follower tracking
        self.last_follower_sync = None

    # -------------------------------------------------
    # UTILS
    # -------------------------------------------------
    def jitter(self, min_s=2, max_s=5):
        delay = random.uniform(min_s, max_s)
        print(f"⏱️ Sleeping {delay:.2f}s")
        
        # Break sleep into 0.5 second chunks to check stop_event
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
                print(f"⚠️ Retry {attempt+1}/{retries}: {e}")
                # Check stop_event during retry delay
                for _ in range(base_delay * (attempt + 1)):
                    if self.stop_event.is_set():
                        return None
                    time.sleep(1)
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
    # FOLLOWER SYNC
    # -------------------------------------------------
    def sync_followers(self):
        """Sync our followers list and track changes"""
        if self.stop_event.is_set():
            return
            
        try:
            print("\n🔄 Syncing followers...")
            
            # Get our followers from Bluesky
            followers = []
            cursor = None
            
            while True:
                if self.stop_event.is_set():
                    return
                    
                response = self.client.get_followers(self.client.me.did, cursor=cursor, limit=100)
                
                for follower in response.followers:
                    followers.append({
                        'did': follower.did,
                        'handle': follower.handle,
                        'display_name': getattr(follower, 'display_name', None),
                        'avatar': getattr(follower, 'avatar', None),
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
                
                # Check stop_event during pagination
                if self.stop_event.wait(1):
                    return
            
            # Sync with database
            new_followers, unfollowers = self.db.sync_followers(followers)
            
            print(f"📊 Follower sync complete:")
            print(f"   • Total followers: {len(followers)}")
            print(f"   • New followers: {len(new_followers)}")
            print(f"   • Unfollowers: {len(unfollowers)}")
            
            # Check follow-back status for users we followed
            if not self.stop_event.is_set():
                self.check_follow_backs()
            
            self.last_follower_sync = datetime.now()
            
        except Exception as e:
            print(f"⚠️ Follower sync error: {e}")
    
    def check_follow_backs(self):
        """Check which users we followed are following us back"""
        if self.stop_event.is_set():
            return
            
        users_to_check = self.db.get_users_to_check_follow_back(hours=24)
        
        for user in users_to_check:
            if self.stop_event.is_set():
                return
                
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
                
                # Check stop_event during delay
                for _ in range(2):
                    if self.stop_event.is_set():
                        return
                    time.sleep(1)
                
            except Exception as e:
                print(f"⚠️ Error checking follow-back for @{user['handle']}: {e}")

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
                        'author_avatar': getattr(post.author, 'avatar', None),
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
            score -= 5

        return score >= 3

    # -------------------------------------------------
    # FOLLOW
    # -------------------------------------------------
    def follow_user(self, did, handle, name=None, avatar=None):
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

            self.db.add_follow(did, handle, name, avatar)
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
                {
                    "text": post['text'][:150],
                    "author_avatar": post.get('author_avatar'),
                    "author_display_name": post.get('author_display_name'),
                    "created_at": post.get('created_at')
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
        if self.stop_event.is_set():
            return 0
            
        print(f"\n📌 @{post['author_handle']}")
        print(f"📝 {post['text'][:80]}...")

        if not self.should_engage(post):
            print("⏭️ Skipped (low score)")
            return 0

        actions = 0

        if self.follow_user(post['author_did'], post['author_handle'], 
                           post['author_display_name'], post.get('author_avatar')):
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
        if self.stop_event.is_set() or self.paused or not self.running:
            return

        print(f"\n🚀 Run @ {datetime.now()}")

        if not self.client.me:
            if not self.login():
                return
                
        # Sync followers every hour
        if (self.last_follower_sync is None or 
            datetime.now() - self.last_follower_sync > timedelta(hours=1)):
            if not self.stop_event.is_set():
                self.sync_followers()

        keywords = self.db.get_active_keywords()
        if not keywords:
            print("⚠️ No keywords")
            return

        posts = self.search_posts_by_keywords(keywords)
        
        if self.stop_event.is_set():
            return

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
    # LOOP - COMPLETELY REWRITTEN WITH PROPER STOP CHECKING
    # -------------------------------------------------
    def _run_loop(self):
        self._thread_stopped = False
        print("🟢 Bot loop started")
        
        while not self.stop_event.is_set():
            try:
                # Only run if not paused and running
                if not self.paused and self.running and not self.stop_event.is_set():
                    self.run_once()

                # Calculate wait time
                wait = Config.CHECK_INTERVAL + random.randint(-30, 60)
                wait = max(10, wait)  # Minimum 10 seconds
                print(f"💤 Sleeping {wait}s")
                
                # CRITICAL FIX: Break sleep into 1-second chunks and check stop_event each time
                for _ in range(wait):
                    if self.stop_event.is_set():
                        print("🛑 Stop event detected during sleep")
                        break
                    time.sleep(1)

            except Exception as e:
                print(f"⚠️ Loop crash: {e}")
                # Short sleep on error, checking stop_event
                for _ in range(5):
                    if self.stop_event.is_set():
                        break
                    time.sleep(1)
        
        self._thread_stopped = True
        print("🛑 Bot loop ended")

    # -------------------------------------------------
    # CONTROL - FIXED WITH PROPER THREAD MANAGEMENT
    # -------------------------------------------------
    def start(self):
        with self._stop_lock:
            # Kill any existing thread first
            if self.thread and self.thread.is_alive():
                print("⚠️ Stopping existing thread...")
                self.stop()
                
            # Wait for thread to fully stop
            time.sleep(1)
            
            # Reset everything
            self.running = True
            self.paused = False
            self.stop_event.clear()
            
            # Reset counters for new session
            self.followed_today = 0
            self.likes_today = 0
            self.reposts_today = 0
            self.total_actions = 0

            # Create and start new thread
            self.thread = threading.Thread(target=self._run_loop, daemon=True)
            self.thread.start()

            print("✅ Bot started")
            self.db.update_bot_status(is_running=True)

    def stop(self):
        print("⏹️ Stopping bot...")
        
        with self._stop_lock:
            # Signal stop FIRST
            self.running = False
            self.stop_event.set()
            
            # Wait for thread to finish
            if self.thread and self.thread.is_alive():
                print("⏳ Waiting for thread to stop...")
                # Wait up to 15 seconds
                self.thread.join(timeout=15)
                
                if self.thread.is_alive():
                    print("⚠️ Thread still alive after 15 seconds - forcing cleanup")
                    # Force additional checks
                    self.stop_event.set()
                    self.running = False
                else:
                    print("✅ Thread stopped")
            
            self.thread = None
            self.db.update_bot_status(is_running=False)
            print("✅ Bot stopped")

    def pause(self):
        self.paused = True
        print("⏸️ Bot paused")
        self.db.update_bot_status(is_running=True)  # Keep running status but paused

    def resume(self):
        self.paused = False
        self.running = True
        print("▶️ Bot resumed")
        self.db.update_bot_status(is_running=True)
    
    def is_running(self):
        """Check if bot is actually running"""
        return self.running and self.thread and self.thread.is_alive() and not self.stop_event.is_set()