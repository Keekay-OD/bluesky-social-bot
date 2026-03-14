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
        self.followed_today = 0
        self.likes_today = 0
        self.reposts_today = 0

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
    # SEARCH FOR POSTS WITH KEYWORDS
    # -------------------------------------------------
    def search_posts_by_keywords(self, keywords, limit=50):
        """Search for recent posts containing keywords"""
        all_posts = []
        
        for keyword in keywords[:5]:  # Limit to 5 keywords per run to avoid rate limits
            try:
                print(f"🔍 Searching for posts with keyword: '{keyword}'")
                
                # Search for posts with the keyword
                response = self.client.app.bsky.feed.search_posts({
                    "q": keyword,
                    "limit": 20,  # Get 20 posts per keyword
                    "sort": "latest"  # Get the most recent posts
                })
                
                if response and hasattr(response, 'posts'):
                    for post in response.posts:
                        post_info = {
                            'uri': post.uri,
                            'cid': post.cid,
                            'author_did': post.author.did,
                            'author_handle': post.author.handle,
                            'author_display_name': getattr(post.author, 'display_name', None),
                            'text': getattr(post.record, 'text', '') if hasattr(post, 'record') else '',
                            'indexed_at': post.indexed_at,
                            'keyword': keyword
                        }
                        all_posts.append(post_info)
                    
                    print(f"   Found {len(response.posts)} posts for keyword '{keyword}'")
                
                # Small delay between keyword searches
                time.sleep(2)
                
            except Exception as e:
                print(f"⚠️ Error searching for keyword '{keyword}': {e}")
                continue
        
        # Remove duplicates (same post found by different keywords)
        unique_posts = []
        seen_uris = set()
        for post in all_posts:
            if post['uri'] not in seen_uris:
                seen_uris.add(post['uri'])
                unique_posts.append(post)
        
        print(f"📊 Total unique posts found: {len(unique_posts)}")
        return unique_posts

    # -------------------------------------------------
    # FOLLOW USER
    # -------------------------------------------------
    def follow_user(self, user_did, user_handle, display_name=None):
        """Follow a new user"""
        
        if not Config.AUTO_FOLLOW:
            print("⏭️ Auto follow disabled in config")
            return False

        if not user_did:
            return False

        # Check daily follow limit
        followed_today = self.db.get_followed_count_today()
        if followed_today >= Config.MAX_FOLLOWS_PER_DAY:
            print(f"⚠️ Daily follow limit reached ({followed_today}/{Config.MAX_FOLLOWS_PER_DAY})")
            return False

        # Check if already followed in DB
        if self.db.was_followed(user_did):
            print(f"↩️ Already followed @{user_handle} (in database)")
            return False

        try:
            # Check if already following via Bluesky API
            print(f"🔍 Checking if already following @{user_handle}...")
            profile = self.client.app.bsky.actor.get_profile({"actor": user_did})

            if hasattr(profile.viewer, "following") and profile.viewer.following:
                print(f"↩️ Already following @{user_handle} (on Bluesky)")
                # Still add to DB to track it
                self.db.add_follow(user_did, user_handle, display_name)
                return False

            # Perform follow
            print(f"➕ Following @{user_handle}...")
            self.client.follow(user_did)

            # Record in database
            self.db.add_follow(user_did, user_handle, display_name)
            
            # Update daily stats
            self.db.update_daily_stats(follows=1)
            self.followed_today += 1

            print(f"✅ Successfully followed @{user_handle} (Follow #{self.followed_today} today)")
            return True

        except AtProtocolError as e:
            print(f"⚠️ Follow failed (API error): {e}")
            return False
        except Exception as e:
            print(f"⚠️ Follow failed (unexpected): {e}")
            return False

    # -------------------------------------------------
    # LIKE POST
    # -------------------------------------------------
    def like_post(self, post_uri, post_cid, author_handle, author_did, post_text=""):
        """Like a post"""
        try:
            # Check if already liked
            if self.db.was_liked(post_uri):
                print(f"↩️ Already liked this post from @{author_handle}")
                return False

            # Check daily like limit
            today_stats = self.db.get_today_stats()
            if today_stats["likes"] >= Config.MAX_LIKES_PER_DAY:
                print("⚠️ Daily like limit reached")
                return False

            # Perform the like
            print(f"❤️ Liking post from @{author_handle}...")
            self.client.like(post_uri, post_cid)

            # Record like in database
            post_data = {
                "uri": post_uri,
                "cid": post_cid,
                "text": post_text[:150],
                "created_at": str(datetime.now())
            }
            
            self.db.add_liked_post(
                post_uri,
                author_did,
                author_handle,
                post_data
            )

            self.db.update_daily_stats(likes=1)
            self.likes_today += 1

            print(f"✅ Liked post from @{author_handle} (Like #{self.likes_today} today)")
            return True

        except AtProtocolError as e:
            print(f"⚠️ Like failed (API error): {e}")
            return False
        except Exception as e:
            print(f"⚠️ Like failed: {e}")
            return False

    # -------------------------------------------------
    # REPOST (RE-SKEET)
    # -------------------------------------------------
    def repost_post(self, post_uri, post_cid, author_handle):
        """Repost (re-skeet) a post"""
        try:
            print(f"🔄 Re-skeeting post from @{author_handle}...")
            self.client.repost(post_uri, post_cid)
            self.reposts_today += 1
            print(f"✅ Re-skeeted post from @{author_handle} (Repost #{self.reposts_today} today)")
            return True
        except Exception as e:
            print(f"⚠️ Re-skeet failed: {e}")
            return False

    # -------------------------------------------------
    # PROCESS A SINGLE POST
    # -------------------------------------------------
    def process_post(self, post):
        """Process a single post - decide whether to like, follow, repost"""
        print(f"\n{'─'*50}")
        print(f"📌 Processing post from @{post['author_handle']}")
        print(f"📝 Preview: {post['text'][:100]}...")
        
        actions_taken = []
        
        # 1. FOLLOW THE USER (always if not already following)
        if Config.AUTO_FOLLOW:
            follow_success = self.follow_user(
                post['author_did'],
                post['author_handle'],
                post.get('author_display_name')
            )
            if follow_success:
                actions_taken.append("followed")
        
        # 2. LIKE THE POST (50% chance)
        if random.random() < 0.5:  # 50% chance to like
            like_success = self.like_post(
                post['uri'],
                post['cid'],
                post['author_handle'],
                post['author_did'],
                post['text']
            )
            if like_success:
                actions_taken.append("liked")
        
        # 3. MAYBE LIKE SOME OF THEIR OTHER POSTS (30% chance to check more)
        if random.random() < 0.3:  # 30% chance to check for more posts to like
            self.like_random_posts_from_user(post['author_did'], post['author_handle'])
        
        # 4. MAYBE REPOST (15% chance)
        if random.random() < 0.15:  # 15% chance to repost
            repost_success = self.repost_post(
                post['uri'],
                post['cid'],
                post['author_handle']
            )
            if repost_success:
                actions_taken.append("reposted")
        
        if actions_taken:
            print(f"✅ Actions taken on @{post['author_handle']}: {', '.join(actions_taken)}")
        else:
            print(f"⏭️ No actions taken on @{post['author_handle']}")
        
        return len(actions_taken)

    # -------------------------------------------------
    # LIKE RANDOM POSTS FROM A USER
    # -------------------------------------------------
    def like_random_posts_from_user(self, user_did, user_handle, max_posts=3):
        """Like random posts from a user's feed"""
        try:
            print(f"🔍 Checking more posts from @{user_handle}...")
            
            # Get user's recent posts
            response = self.client.app.bsky.feed.get_author_feed({
                "actor": user_did,
                "limit": 10,
                "filter": "posts_no_replies"
            })
            
            if not response or not response.feed:
                return 0
            
            # Randomly select 1-3 posts to like
            posts_to_like = random.sample(
                response.feed, 
                min(random.randint(1, max_posts), len(response.feed))
            )
            
            likes_added = 0
            for feed_view in posts_to_like:
                post = feed_view.post
                
                # Check daily limits
                today_stats = self.db.get_today_stats()
                if today_stats["likes"] >= Config.MAX_LIKES_PER_DAY:
                    break
                
                # Don't like the same post we already processed
                if self.db.was_liked(post.uri):
                    continue
                
                # Extract post text
                post_text = ""
                if hasattr(post, 'record') and hasattr(post.record, 'text'):
                    post_text = post.record.text
                
                # Like the post
                success = self.like_post(
                    post.uri,
                    post.cid,
                    user_handle,
                    user_did,
                    post_text
                )
                
                if success:
                    likes_added += 1
                    
                    # Random delay between likes
                    time.sleep(random.randint(5, 15))
            
            if likes_added > 0:
                print(f"✅ Liked {likes_added} additional posts from @{user_handle}")
            
            return likes_added
            
        except Exception as e:
            print(f"⚠️ Error getting more posts from @{user_handle}: {e}")
            return 0

    # -------------------------------------------------
    # MAIN RUN FUNCTION
    # -------------------------------------------------
    def run_once(self):
        print(f"\n{'='*60}")
        print(f"🚀 Bot run starting at {datetime.now()}")
        print(f"{'='*60}")

        if self.paused:
            print("⏸️ Bot is paused, skipping run")
            return
            
        if not self.running:
            print("⏹️ Bot is stopped, skipping run")
            return

        # Reset session counters
        self.followed_today = 0
        self.likes_today = 0
        self.reposts_today = 0

        # Check login
        if not self.client.me:
            print("🔑 Not logged in, attempting login...")
            if not self.login():
                print("❌ Login failed, aborting run")
                return

        # Get active keywords
        keywords = self.db.get_active_keywords()
        if not keywords:
            print("⚠️ No active keywords found")
            return
        
        print(f"📝 Active keywords ({len(keywords)}): {', '.join(keywords[:10])}{'...' if len(keywords) > 10 else ''}")

        # Search for posts with keywords
        print(f"\n🔎 Searching Bluesky for posts with keywords...")
        posts = self.search_posts_by_keywords(keywords)
        self.db.update_daily_stats(posts_found=len(posts))

        if not posts:
            print("❌ No posts found with the given keywords")
            return
        
        print(f"\n📊 Found {len(posts)} unique posts to process")
        
        # Shuffle posts to randomize order
        random.shuffle(posts)
        
        # Process posts
        posts_processed = 0
        total_actions = 0
        
        for post in posts:
            if self.paused or not self.running:
                print("⏸️ Run interrupted by pause/stop")
                break
            
            # Check daily limits
            today_stats = self.db.get_today_stats()
            if today_stats["likes"] >= Config.MAX_LIKES_PER_DAY:
                print(f"⚠️ Daily like limit ({Config.MAX_LIKES_PER_DAY}) reached")
                break
            
            if Config.AUTO_FOLLOW and self.db.get_followed_count_today() >= Config.MAX_FOLLOWS_PER_DAY:
                print(f"⚠️ Daily follow limit ({Config.MAX_FOLLOWS_PER_DAY}) reached")
                # Can still like even if follow limit reached
            
            # Process the post
            actions = self.process_post(post)
            total_actions += actions
            posts_processed += 1
            
            # Random delay between posts
            if posts_processed < len(posts):
                delay = random.randint(10, 30)  # Longer delay between different users
                print(f"⏱️ Waiting {delay} seconds before next post...")
                time.sleep(delay)


        self.db.update_daily_stats(users_checked=1)
        # Update bot status
        self.db.update_bot_status(
            last_run=datetime.now(),
            next_run=datetime.now() + timedelta(seconds=Config.CHECK_INTERVAL),
            error=None
        )

        # Print run summary
        print(f"\n{'='*60}")
        print(f"📊 RUN SUMMARY")
        print(f"{'='*60}")
        print(f"📝 Posts processed: {posts_processed}")
        print(f"❤️ Likes added: {self.likes_today}")
        print(f"➕ Follows added: {self.followed_today}")
        print(f"🔄 Reposts added: {self.reposts_today}")
        print(f"📈 Total actions: {total_actions}")
        print(f"✅ Run complete at {datetime.now()}")
        print(f"⏰ Next run scheduled for: {datetime.now() + timedelta(seconds=Config.CHECK_INTERVAL)}")
        print(f"{'='*60}")

    # -------------------------------------------------
    # THREAD LOOP
    # -------------------------------------------------
    def _run_loop(self):

        while not self.stop_event.is_set():

            try:

                if not self.paused:
                    self.run_once()

                    print(f"\n💤 Sleeping {Config.CHECK_INTERVAL}s")

                    if self.stop_event.wait(Config.CHECK_INTERVAL):
                        break

                else:
                    print("⏸️ Bot paused")

                    if self.stop_event.wait(30):
                        break

            except Exception as e:
                print(f"⚠️ Loop error: {e}")

                if self.stop_event.wait(300):
                    break

    # -------------------------------------------------
    # CONTROL
    # -------------------------------------------------
    def start(self):
        if self.thread and self.thread.is_alive():
            print("⚠️ Bot thread already running")
            return

        self.running = True
        self.paused = False
        self.stop_event.clear()

        self.thread = threading.Thread(target=self._run_loop)
        self.thread.daemon = True
        self.thread.start()

        print("✅ Bot started successfully")
        self.db.update_bot_status(is_running=True)

    def stop(self):
        print("⏹️ Stopping bot...")

        self.running = False
        self.paused = False
        self.stop_event.set()

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

        print("✅ Bot fully stopped")
        self.db.update_bot_status(is_running=False)

    def pause(self):
        self.paused = True
        print("⏸️ Bot paused")

    def resume(self):
        self.paused = False
        self.running = True
        print("▶️ Bot resumed")