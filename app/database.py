# In Z:\Docker\AppData\Config\bluesky-social-bot\app\database.py

import sqlite3
import json
from datetime import datetime, timedelta
from contextlib import contextmanager
from config import Config
import time
import threading

class Database:
    def __init__(self, db_path=Config.DATABASE_PATH):
        self.db_path = db_path
        # Set a thread-local storage for connections
        self.local = threading.local()
        self.init_db()
    
    def get_connection(self):
        """Get a thread-local connection"""
        if not hasattr(self.local, 'conn'):
            # Enable WAL mode for better concurrency
            self.local.conn = sqlite3.connect(self.db_path, timeout=30)  # 30 second timeout
            self.local.conn.row_factory = sqlite3.Row
            # Enable foreign keys and WAL mode
            self.local.conn.execute("PRAGMA foreign_keys = ON")
            self.local.conn.execute("PRAGMA journal_mode = WAL")
            self.local.conn.execute("PRAGMA synchronous = NORMAL")
            self.local.conn.execute("PRAGMA cache_size = 10000")
            self.local.conn.execute("PRAGMA temp_store = MEMORY")
        return self.local.conn
    
    @contextmanager
    def get_cursor(self):
        """Get a cursor with automatic commit/rollback"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
    
    def close_connection(self):
        """Close the thread-local connection"""
        if hasattr(self.local, 'conn'):
            self.local.conn.close()
            delattr(self.local, 'conn')
    
    def init_db(self):
        """Initialize database tables"""
        try:
            with self.get_cursor() as c:
                # Configuration table
                c.execute("""
                    CREATE TABLE IF NOT EXISTS configuration (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        updated_at TIMESTAMP
                    )
                """)
                
                # Keywords table
                c.execute("""
                    CREATE TABLE IF NOT EXISTS keywords (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT UNIQUE,
                        group_name TEXT,
                        active BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP
                    )
                """)
                
                # Check if group_name column exists, if not add it
                c.execute("PRAGMA table_info(keywords)")
                columns = [column[1] for column in c.fetchall()]
                if 'group_name' not in columns:
                    c.execute("ALTER TABLE keywords ADD COLUMN group_name TEXT")
                
                # Followed users (users WE followed)
                c.execute("""
                    CREATE TABLE IF NOT EXISTS followed_users (
                        did TEXT PRIMARY KEY,
                        handle TEXT,
                        display_name TEXT,
                        followed_at TIMESTAMP,
                        last_checked TIMESTAMP,
                        profile_data TEXT,
                        is_following_us BOOLEAN DEFAULT 0,
                        follow_back_checked_at TIMESTAMP
                    )
                """)
                
                # Liked posts
                c.execute("""
                    CREATE TABLE IF NOT EXISTS liked_posts (
                        uri TEXT PRIMARY KEY,
                        user_did TEXT,
                        user_handle TEXT,
                        liked_at TIMESTAMP,
                        post_data TEXT
                    )
                """)
                
                # Daily stats
                c.execute("""
                    CREATE TABLE IF NOT EXISTS daily_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT UNIQUE,
                        likes INTEGER DEFAULT 0,
                        follows INTEGER DEFAULT 0,
                        users_checked INTEGER DEFAULT 0,
                        posts_found INTEGER DEFAULT 0,
                        new_followers INTEGER DEFAULT 0,
                        unfollowers INTEGER DEFAULT 0,
                        followed_back INTEGER DEFAULT 0
                    )
                """)
                
                c.execute("PRAGMA table_info(daily_stats)")
                columns = [column[1] for column in c.fetchall()]
                if 'follows' not in columns:
                    c.execute("ALTER TABLE daily_stats ADD COLUMN follows INTEGER DEFAULT 0")
                if 'new_followers' not in columns:
                    c.execute("ALTER TABLE daily_stats ADD COLUMN new_followers INTEGER DEFAULT 0")
                if 'unfollowers' not in columns:
                    c.execute("ALTER TABLE daily_stats ADD COLUMN unfollowers INTEGER DEFAULT 0")
                if 'followed_back' not in columns:
                    c.execute("ALTER TABLE daily_stats ADD COLUMN followed_back INTEGER DEFAULT 0")
                
                # Bot status
                c.execute("""
                    CREATE TABLE IF NOT EXISTS bot_status (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        is_running BOOLEAN DEFAULT 1,
                        last_run TIMESTAMP,
                        next_run TIMESTAMP,
                        error TEXT
                    )
                """)
                
                # Whitelist table
                c.execute("""
                    CREATE TABLE IF NOT EXISTS whitelist (
                        did TEXT PRIMARY KEY,
                        handle TEXT,
                        display_name TEXT,
                        added_at TIMESTAMP,
                        reason TEXT
                    )
                """)
                
                # Unfollowers table (users who unfollowed US)
                c.execute("""
                    CREATE TABLE IF NOT EXISTS unfollowers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        did TEXT,
                        handle TEXT,
                        display_name TEXT,
                        unfollowed_at TIMESTAMP,
                        last_followed_at TIMESTAMP,
                        profile_data TEXT,
                        UNIQUE(did, unfollowed_at)
                    )
                """)
                
                # Our followers table (users who follow US)
                c.execute("""
                    CREATE TABLE IF NOT EXISTS my_followers (
                        did TEXT PRIMARY KEY,
                        handle TEXT,
                        display_name TEXT,
                        followed_at TIMESTAMP,
                        last_checked TIMESTAMP,
                        profile_data TEXT,
                        is_following_them BOOLEAN DEFAULT 0
                    )
                """)
                
                # Follow backs tracking
                c.execute("""
                    CREATE TABLE IF NOT EXISTS follow_backs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        did TEXT,
                        handle TEXT,
                        display_name TEXT,
                        followed_back_at TIMESTAMP,
                        original_follow_at TIMESTAMP,
                        UNIQUE(did)
                    )
                """)
                
                # Insert default bot status
                c.execute("INSERT OR IGNORE INTO bot_status (id, is_running) VALUES (1, 1)")
                
                # Insert default keywords
                default_keywords = getattr(Config, 'DEFAULT_KEYWORDS', ['bikes', 'cycling', 'bicycle'])
                for keyword in default_keywords:
                    c.execute("""
                        INSERT OR IGNORE INTO keywords (keyword, active, created_at)
                        VALUES (?, 1, ?)
                    """, (keyword, datetime.now()))
        except Exception as e:
            print(f"Error initializing database: {e}")
            raise
    
    # Keywords methods
    def get_active_keywords(self, group=None):
        """Get active keywords, optionally filtered by group"""
        with self.get_cursor() as c:
            if group:
                c.execute("SELECT keyword FROM keywords WHERE active = 1 AND group_name = ?", (group,))
            else:
                c.execute("SELECT keyword FROM keywords WHERE active = 1")
            return [row['keyword'] for row in c.fetchall()]
    
    def get_all_keywords(self):
        """Get all keywords with groups"""
        with self.get_cursor() as c:
            c.execute('''
                SELECT id, keyword, group_name, active, created_at
                FROM keywords
                ORDER BY created_at DESC
            ''')
            rows = c.fetchall()
            return [{
                'id': row['id'], 
                'keyword': row['keyword'], 
                'group': row['group_name'], 
                'active': bool(row['active']), 
                'created_at': row['created_at']
            } for row in rows]
    
    def get_keywords_by_group(self, group_name):
        """Get keywords for a specific group"""
        with self.get_cursor() as c:
            c.execute('''
                SELECT id, keyword, group_name, active, created_at
                FROM keywords
                WHERE group_name = ?
                ORDER BY created_at DESC
            ''', (group_name,))
            rows = c.fetchall()
            return [{
                'id': row['id'], 
                'keyword': row['keyword'], 
                'group': row['group_name'], 
                'active': bool(row['active']), 
                'created_at': row['created_at']
            } for row in rows]
    
    def get_all_groups(self):
        """Get all unique group names"""
        with self.get_cursor() as c:
            c.execute('''
                SELECT DISTINCT group_name 
                FROM keywords 
                WHERE group_name IS NOT NULL AND group_name != ''
                ORDER BY group_name
            ''')
            return [row['group_name'] for row in c.fetchall()]
    
    def add_keyword(self, keyword, group=None):
        """Add a new keyword with optional group"""
        try:
            with self.get_cursor() as c:
                c.execute('''
                    INSERT OR IGNORE INTO keywords (keyword, group_name, active, created_at)
                    VALUES (?, ?, 1, ?)
                ''', (keyword.lower().strip(), group, datetime.now()))
                return c.rowcount > 0
        except Exception as e:
            print(f"Error adding keyword: {e}")
            return False
    
    def update_keyword(self, keyword_id, active):
        """Update keyword active status"""
        with self.get_cursor() as c:
            c.execute("UPDATE keywords SET active = ? WHERE id = ?", (active, keyword_id))
    
    def update_keyword_group(self, keyword_id, group):
        """Update keyword group"""
        with self.get_cursor() as c:
            c.execute("UPDATE keywords SET group_name = ? WHERE id = ?", (group, keyword_id))
    
    def delete_keyword(self, keyword_id):
        """Delete a keyword"""
        with self.get_cursor() as c:
            c.execute("DELETE FROM keywords WHERE id = ?", (keyword_id,))
    
    def delete_keywords_by_group(self, group_name):
        """Delete all keywords in a group"""
        with self.get_cursor() as c:
            c.execute("DELETE FROM keywords WHERE group_name = ?", (group_name,))
            return c.rowcount
    
    # Followed users methods (users WE followed)
    def add_follow(self, user_did, user_handle, display_name=None):
        with self.get_cursor() as c:
            try:
                c.execute("""
                    INSERT INTO followed_users (did, handle, display_name, followed_at, last_checked)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_did, user_handle, display_name, datetime.now(), datetime.now()))
                
                # Update daily stats
                self.update_daily_stats(follows=1)
                return True
            except sqlite3.IntegrityError:
                return False
    
    def was_followed(self, user_did):
        with self.get_cursor() as c:
            c.execute("SELECT 1 FROM followed_users WHERE did = ?", (user_did,))
            return c.fetchone() is not None
    
    def get_followed_count_today(self):
        with self.get_cursor() as c:
            today = datetime.now().date().isoformat()
            c.execute("""
                SELECT COUNT(*) FROM followed_users 
                WHERE date(followed_at) = ?
            """, (today,))
            return c.fetchone()[0]
    
    def add_followed_user(self, did, handle, display_name=None, profile_data=None):
        with self.get_cursor() as c:
            c.execute("""
                INSERT OR REPLACE INTO followed_users 
                (did, handle, display_name, followed_at, last_checked, profile_data)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (did, handle, display_name, datetime.now(), datetime.now(), 
                  json.dumps(profile_data) if profile_data else None))
    
    def get_followed_users(self):
        with self.get_cursor() as c:
            c.execute("SELECT * FROM followed_users ORDER BY followed_at DESC")
            return [dict(row) for row in c.fetchall()]
    
    def update_last_checked(self, did):
        with self.get_cursor() as c:
            c.execute("UPDATE followed_users SET last_checked = ? WHERE did = ?", 
                     (datetime.now(), did))
    
    def update_follow_back_status(self, did, is_following_us):
        """Update whether a user we followed is following us back"""
        with self.get_cursor() as c:
            c.execute("""
                UPDATE followed_users 
                SET is_following_us = ?, follow_back_checked_at = ?
                WHERE did = ?
            """, (is_following_us, datetime.now(), did))
    
    def get_users_to_check_follow_back(self, hours=24):
        """Get users we followed that need follow-back status checked"""
        with self.get_cursor() as c:
            cutoff = datetime.now() - timedelta(hours=hours)
            c.execute("""
                SELECT * FROM followed_users 
                WHERE (follow_back_checked_at IS NULL OR follow_back_checked_at < ?)
                AND followed_at > ?
                ORDER BY followed_at DESC
            """, (cutoff, datetime.now() - timedelta(days=30)))
            return [dict(row) for row in c.fetchall()]
    
    # My followers methods (users who follow US)
    def add_my_follower(self, did, handle, display_name=None, profile_data=None):
        """Add a user who follows us"""
        with self.get_cursor() as c:
            c.execute("""
                INSERT OR REPLACE INTO my_followers 
                (did, handle, display_name, followed_at, last_checked, profile_data)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (did, handle, display_name, datetime.now(), datetime.now(),
                  json.dumps(profile_data) if profile_data else None))
    
    def update_my_follower(self, did, handle=None, display_name=None, profile_data=None):
        """Update an existing follower"""
        with self.get_cursor() as c:
            c.execute("""
                UPDATE my_followers 
                SET handle = COALESCE(?, handle),
                    display_name = COALESCE(?, display_name),
                    last_checked = ?,
                    profile_data = COALESCE(?, profile_data)
                WHERE did = ?
            """, (handle, display_name, datetime.now(), 
                  json.dumps(profile_data) if profile_data else None, did))
    
    def remove_my_follower(self, did):
        """Remove a follower (they unfollowed us)"""
        with self.get_cursor() as c:
            c.execute("DELETE FROM my_followers WHERE did = ?", (did,))
            return c.rowcount > 0
    
    def get_my_followers(self):
        """Get all current followers"""
        with self.get_cursor() as c:
            c.execute("SELECT * FROM my_followers ORDER BY followed_at DESC")
            return [dict(row) for row in c.fetchall()]
    
    def get_my_followers_count(self):
        """Get total follower count"""
        with self.get_cursor() as c:
            c.execute("SELECT COUNT(*) FROM my_followers")
            return c.fetchone()[0]
    
    def is_my_follower(self, did):
        """Check if a user follows us"""
        with self.get_cursor() as c:
            c.execute("SELECT 1 FROM my_followers WHERE did = ?", (did,))
            return c.fetchone() is not None
    
    def update_follower_following_status(self, did, is_following_them):
        """Update whether we follow this follower back"""
        with self.get_cursor() as c:
            c.execute("""
                UPDATE my_followers 
                SET is_following_them = ?
                WHERE did = ?
            """, (is_following_them, did))
    
    # Follow backs tracking
    def add_follow_back(self, did, handle, display_name=None):
        """Track when someone follows us back"""
        with self.get_cursor() as c:
            try:
                # Check when we originally followed them
                c.execute("SELECT followed_at FROM followed_users WHERE did = ?", (did,))
                row = c.fetchone()
                original_follow = row['followed_at'] if row else None
                
                c.execute("""
                    INSERT OR REPLACE INTO follow_backs 
                    (did, handle, display_name, followed_back_at, original_follow_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (did, handle, display_name, datetime.now(), original_follow))
                
                # Update daily stats
                self.update_daily_stats(followed_back=1)
                return True
            except Exception as e:
                print(f"Error adding follow back: {e}")
                return False
    
    def get_follow_backs(self, days=30):
        """Get recent follow backs"""
        with self.get_cursor() as c:
            cutoff = datetime.now() - timedelta(days=days)
            c.execute("""
                SELECT * FROM follow_backs 
                WHERE followed_back_at > ?
                ORDER BY followed_back_at DESC
            """, (cutoff,))
            return [dict(row) for row in c.fetchall()]
    
    def get_follow_backs_today(self):
        """Get number of follow backs today"""
        with self.get_cursor() as c:
            today = datetime.now().date().isoformat()
            c.execute("""
                SELECT COUNT(*) FROM follow_backs 
                WHERE date(followed_back_at) = ?
            """, (today,))
            return c.fetchone()[0]
    
    # Liked posts methods
    def add_liked_post(self, uri, user_did, user_handle, post_data=None):
        with self.get_cursor() as c:
            try:
                c.execute("""
                    INSERT INTO liked_posts (uri, user_did, user_handle, liked_at, post_data)
                    VALUES (?, ?, ?, ?, ?)
                """, (uri, user_did, user_handle, datetime.now(), 
                      json.dumps(post_data) if post_data else None))
                
                # Update daily stats
                self.update_daily_stats(likes=1)
                return True
            except sqlite3.IntegrityError:
                return False
    
    def was_liked(self, uri):
        with self.get_cursor() as c:
            c.execute("SELECT 1 FROM liked_posts WHERE uri = ?", (uri,))
            return c.fetchone() is not None
    
    def get_recent_likes(self, limit=50):
        with self.get_cursor() as c:
            c.execute("""
                SELECT * FROM liked_posts 
                ORDER BY liked_at DESC LIMIT ?
            """, (limit,))
            return [dict(row) for row in c.fetchall()]
    
    def get_likes_count_today(self):
        with self.get_cursor() as c:
            today = datetime.now().date().isoformat()
            c.execute("""
                SELECT COUNT(*) FROM liked_posts 
                WHERE date(liked_at) = ?
            """, (today,))
            return c.fetchone()[0]
    
    # Stats methods
    def update_daily_stats(self, likes=0, follows=0, users_checked=0, posts_found=0, 
                          new_followers=0, unfollowers=0, followed_back=0):
        with self.get_cursor() as c:
            today = datetime.now().date().isoformat()
            
            c.execute("SELECT id FROM daily_stats WHERE date = ?", (today,))
            if c.fetchone():
                c.execute("""
                    UPDATE daily_stats 
                    SET likes = likes + ?, 
                        follows = follows + ?,
                        users_checked = users_checked + ?, 
                        posts_found = posts_found + ?,
                        new_followers = new_followers + ?,
                        unfollowers = unfollowers + ?,
                        followed_back = followed_back + ?
                    WHERE date = ?
                """, (likes, follows, users_checked, posts_found, new_followers, 
                      unfollowers, followed_back, today))
            else:
                c.execute("""
                    INSERT INTO daily_stats 
                    (date, likes, follows, users_checked, posts_found, new_followers, unfollowers, followed_back)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (today, likes, follows, users_checked, posts_found, new_followers, 
                      unfollowers, followed_back))
    
    def get_today_stats(self):
        with self.get_cursor() as c:
            today = datetime.now().date().isoformat()
            c.execute("SELECT * FROM daily_stats WHERE date = ?", (today,))
            row = c.fetchone()
            if row:
                return dict(row)
            return {
                'likes': 0, 
                'follows': 0,
                'users_checked': 0, 
                'posts_found': 0,
                'new_followers': 0,
                'unfollowers': 0,
                'followed_back': 0
            }
    
    def get_historical_stats(self, days=7):
        with self.get_cursor() as c:
            c.execute("""
                SELECT * FROM daily_stats 
                ORDER BY date DESC LIMIT ?
            """, (days,))
            return [dict(row) for row in c.fetchall()]
    
    # Bot status methods
    def update_bot_status(self, is_running=None, last_run=None, next_run=None, error=None):
        with self.get_cursor() as c:
            updates = []
            params = []
            
            if is_running is not None:
                updates.append("is_running = ?")
                params.append(is_running)
            if last_run is not None:
                updates.append("last_run = ?")
                params.append(last_run)
            if next_run is not None:
                updates.append("next_run = ?")
                params.append(next_run)
            if error is not None:
                updates.append("error = ?")
                params.append(error)
            
            if updates:
                query = f"UPDATE bot_status SET {', '.join(updates)} WHERE id = 1"
                c.execute(query, params)
    
    def get_bot_status(self):
        with self.get_cursor() as c:
            c.execute("SELECT * FROM bot_status WHERE id = 1")
            row = c.fetchone()
            return dict(row) if row else {}
    
    # Whitelist methods
    def add_to_whitelist(self, did, handle, display_name=None, reason=None):
        """Add a user to whitelist"""
        try:
            with self.get_cursor() as c:
                c.execute("""
                    INSERT OR REPLACE INTO whitelist (did, handle, display_name, added_at, reason)
                    VALUES (?, ?, ?, ?, ?)
                """, (did, handle, display_name, datetime.now(), reason))
                return True
        except Exception as e:
            print(f"Error adding to whitelist: {e}")
            # Try one more time with a fresh connection
            time.sleep(0.5)
            with self.get_cursor() as c:
                c.execute("""
                    INSERT OR REPLACE INTO whitelist (did, handle, display_name, added_at, reason)
                    VALUES (?, ?, ?, ?, ?)
                """, (did, handle, display_name, datetime.now(), reason))
            return True
    
    def remove_from_whitelist(self, did):
        """Remove a user from whitelist"""
        with self.get_cursor() as c:
            c.execute("DELETE FROM whitelist WHERE did = ?", (did,))
            return c.rowcount > 0
    
    def is_whitelisted(self, did):
        """Check if user is whitelisted"""
        with self.get_cursor() as c:
            c.execute("SELECT 1 FROM whitelist WHERE did = ?", (did,))
            return c.fetchone() is not None
    
    def get_whitelist(self):
        """Get all whitelisted users"""
        with self.get_cursor() as c:
            c.execute("SELECT * FROM whitelist ORDER BY added_at DESC")
            return [dict(row) for row in c.fetchall()]
    
    # Unfollowers methods (users who unfollowed US)
    def add_unfollower(self, did, handle, display_name=None, profile_data=None):
        """Track someone who unfollowed us"""
        try:
            with self.get_cursor() as c:
                # Check when they started following us
                c.execute("SELECT followed_at FROM my_followers WHERE did = ?", (did,))
                row = c.fetchone()
                followed_since = row['followed_at'] if row else None
                
                c.execute("""
                    INSERT INTO unfollowers (did, handle, display_name, unfollowed_at, last_followed_at, profile_data)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (did, handle, display_name, datetime.now(), followed_since,
                      json.dumps(profile_data) if profile_data else None))
                
                # Remove from my_followers
                c.execute("DELETE FROM my_followers WHERE did = ?", (did,))
                
                # Update daily stats
                self.update_daily_stats(unfollowers=1)
                return True
        except Exception as e:
            print(f"Error adding unfollower: {e}")
            return False
    
    def get_unfollowers(self, days=30):
        """Get unfollowers from last X days"""
        with self.get_cursor() as c:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            c.execute("""
                SELECT * FROM unfollowers 
                WHERE unfollowed_at > ?
                ORDER BY unfollowed_at DESC
            """, (cutoff,))
            return [dict(row) for row in c.fetchall()]
    
    def get_all_unfollowers(self):
        """Get all unfollowers history"""
        with self.get_cursor() as c:
            c.execute("SELECT * FROM unfollowers ORDER BY unfollowed_at DESC")
            return [dict(row) for row in c.fetchall()]
    
    def get_unfollowers_count_today(self):
        """Get number of unfollowers today"""
        with self.get_cursor() as c:
            today = datetime.now().date().isoformat()
            c.execute("""
                SELECT COUNT(*) FROM unfollowers 
                WHERE date(unfollowed_at) = ?
            """, (today,))
            return c.fetchone()[0]
    
    # Follower sync methods
    def sync_followers(self, current_followers):
        """
        Sync the current follower list
        current_followers: list of dicts with 'did', 'handle', 'display_name', 'profile_data'
        Returns: (new_followers, unfollowers)
        """
        new_followers = []
        unfollowers = []
        
        # Get current followers from DB
        with self.get_cursor() as c:
            c.execute("SELECT did FROM my_followers")
            db_followers = {row['did'] for row in c.fetchall()}
        
        current_dids = {f['did'] for f in current_followers}
        
        # Find new followers
        for follower in current_followers:
            if follower['did'] not in db_followers:
                # New follower!
                self.add_my_follower(
                    follower['did'],
                    follower['handle'],
                    follower.get('display_name'),
                    follower.get('profile_data')
                )
                new_followers.append(follower)
                
                # Update daily stats
                self.update_daily_stats(new_followers=1)
                
                # Check if we follow them back
                if self.was_followed(follower['did']):
                    self.add_follow_back(
                        follower['did'],
                        follower['handle'],
                        follower.get('display_name')
                    )
                    self.update_follower_following_status(follower['did'], True)
        
        # Find unfollowers
        for did in db_followers:
            if did not in current_dids:
                # They unfollowed us
                c.execute("SELECT handle, display_name, profile_data FROM my_followers WHERE did = ?", (did,))
                row = c.fetchone()
                if row:
                    unfollower = {
                        'did': did,
                        'handle': row['handle'],
                        'display_name': row['display_name'],
                        'profile_data': row['profile_data']
                    }
                    self.add_unfollower(
                        did,
                        row['handle'],
                        row['display_name'],
                        json.loads(row['profile_data']) if row['profile_data'] else None
                    )
                    unfollowers.append(unfollower)
        
        return new_followers, unfollowers
    
    # Activity feed methods
    def get_follower_activity(self, limit=20):
        """Get combined follower activity (new followers + follow backs)"""
        new_followers = []
        follow_backs = []
        
        with self.get_cursor() as c:
            # Get recent new followers
            c.execute("""
                SELECT did, handle, display_name, followed_at as timestamp, 'new' as type
                FROM my_followers
                ORDER BY followed_at DESC
                LIMIT ?
            """, (limit,))
            new_followers = [dict(row) for row in c.fetchall()]
            
            # Get recent follow backs
            c.execute("""
                SELECT f.did, f.handle, f.display_name, f.followed_back_at as timestamp, 'follow_back' as type
                FROM follow_backs f
                ORDER BY followed_back_at DESC
                LIMIT ?
            """, (limit,))
            follow_backs = [dict(row) for row in c.fetchall()]
        
        # Combine and sort
        all_activity = new_followers + follow_backs
        all_activity.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return all_activity[:limit]
    
    def get_unfollower_activity(self, limit=20):
        """Get recent unfollowers"""
        with self.get_cursor() as c:
            c.execute("""
                SELECT did, handle, display_name, unfollowed_at as timestamp
                FROM unfollowers
                ORDER BY unfollowed_at DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in c.fetchall()]