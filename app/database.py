import sqlite3
import json
from datetime import datetime, timedelta
from contextlib import contextmanager
from config import Config

class Database:
    def __init__(self, db_path=Config.DATABASE_PATH):
        self.db_path = db_path
        self.init_db()
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def init_db(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            
            # Settings table
            c.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP
                )
            """)
            
            # Keywords table - with group_name column
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
            
            # Followed users
            c.execute("""
                CREATE TABLE IF NOT EXISTS followed_users (
                    did TEXT PRIMARY KEY,
                    handle TEXT,
                    display_name TEXT,
                    followed_at TIMESTAMP,
                    last_checked TIMESTAMP,
                    profile_data TEXT
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
                    users_checked INTEGER DEFAULT 0,
                    posts_found INTEGER DEFAULT 0
                )
            """)
            
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
            
            # Insert default bot status
            c.execute("INSERT OR IGNORE INTO bot_status (id, is_running) VALUES (1, 1)")
            
            # Insert default keywords
            default_keywords = Config.DEFAULT_KEYWORDS
            for keyword in default_keywords:
                c.execute("""
                    INSERT OR IGNORE INTO keywords (keyword, active, created_at)
                    VALUES (?, 1, ?)
                """, (keyword, datetime.now()))
            
            conn.commit()
    
    # Keywords methods
    def get_active_keywords(self, group=None):
        """Get active keywords, optionally filtered by group"""
        with self.get_connection() as conn:
            c = conn.cursor()
            if group:
                c.execute("SELECT keyword FROM keywords WHERE active = 1 AND group_name = ?", (group,))
            else:
                c.execute("SELECT keyword FROM keywords WHERE active = 1")
            return [row['keyword'] for row in c.fetchall()]
    
    def get_all_keywords(self):
        """Get all keywords with groups"""
        with self.get_connection() as conn:
            c = conn.cursor()
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
        with self.get_connection() as conn:
            c = conn.cursor()
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
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT DISTINCT group_name 
                FROM keywords 
                WHERE group_name IS NOT NULL AND group_name != ''
                ORDER BY group_name
            ''')
            return [row['group_name'] for row in c.fetchall()]
    
    def add_keyword(self, keyword, group=None):
        """Add a new keyword with optional group"""
        with self.get_connection() as conn:
            c = conn.cursor()
            try:
                c.execute('''
                    INSERT OR IGNORE INTO keywords (keyword, group_name, active, created_at)
                    VALUES (?, ?, 1, ?)
                ''', (keyword.lower().strip(), group, datetime.now()))
                conn.commit()
                return c.rowcount > 0
            except Exception as e:
                print(f"Error adding keyword: {e}")
                return False
    
    def update_keyword(self, keyword_id, active):
        """Update keyword active status"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE keywords SET active = ? WHERE id = ?", (active, keyword_id))
            conn.commit()
    
    def update_keyword_group(self, keyword_id, group):
        """Update keyword group"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE keywords SET group_name = ? WHERE id = ?", (group, keyword_id))
            conn.commit()
    
    def delete_keyword(self, keyword_id):
        """Delete a keyword"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM keywords WHERE id = ?", (keyword_id,))
            conn.commit()
    
    def delete_keywords_by_group(self, group_name):
        """Delete all keywords in a group"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM keywords WHERE group_name = ?", (group_name,))
            conn.commit()
            return c.rowcount
    
    # Followed users methods
    def add_follow(self, user_did, user_handle, display_name=None):
        with self.get_connection() as conn:
            c = conn.cursor()
            try:
                c.execute("""
                    INSERT INTO followed_users (did, handle, display_name, followed_at, last_checked)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_did, user_handle, display_name, datetime.now(), datetime.now()))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    
    def was_followed(self, user_did):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT 1 FROM followed_users WHERE did = ?", (user_did,))
            return c.fetchone() is not None
    
    def get_followed_count_today(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            today = datetime.now().date().isoformat()
            c.execute("""
                SELECT COUNT(*) FROM followed_users 
                WHERE date(followed_at) = ?
            """, (today,))
            return c.fetchone()[0]
    
    def add_followed_user(self, did, handle, display_name=None, profile_data=None):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO followed_users 
                (did, handle, display_name, followed_at, last_checked, profile_data)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (did, handle, display_name, datetime.now(), datetime.now(), 
                  json.dumps(profile_data) if profile_data else None))
            conn.commit()
    
    def get_followed_users(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM followed_users ORDER BY followed_at DESC")
            return [dict(row) for row in c.fetchall()]
    
    def update_last_checked(self, did):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE followed_users SET last_checked = ? WHERE did = ?", 
                     (datetime.now(), did))
            conn.commit()
    
    # Liked posts methods
    def add_liked_post(self, uri, user_did, user_handle, post_data=None):
        with self.get_connection() as conn:
            c = conn.cursor()
            try:
                c.execute("""
                    INSERT INTO liked_posts (uri, user_did, user_handle, liked_at, post_data)
                    VALUES (?, ?, ?, ?, ?)
                """, (uri, user_did, user_handle, datetime.now(), 
                      json.dumps(post_data) if post_data else None))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    
    def was_liked(self, uri):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT 1 FROM liked_posts WHERE uri = ?", (uri,))
            return c.fetchone() is not None
    
    def get_recent_likes(self, limit=50):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT * FROM liked_posts 
                ORDER BY liked_at DESC LIMIT ?
            """, (limit,))
            return [dict(row) for row in c.fetchall()]
    
    # Stats methods
    def update_daily_stats(self, likes=0, users_checked=0, posts_found=0):
        with self.get_connection() as conn:
            c = conn.cursor()
            today = datetime.now().date().isoformat()
            
            c.execute("SELECT id FROM daily_stats WHERE date = ?", (today,))
            if c.fetchone():
                c.execute("""
                    UPDATE daily_stats 
                    SET likes = likes + ?, users_checked = users_checked + ?, 
                        posts_found = posts_found + ?
                    WHERE date = ?
                """, (likes, users_checked, posts_found, today))
            else:
                c.execute("""
                    INSERT INTO daily_stats (date, likes, users_checked, posts_found)
                    VALUES (?, ?, ?, ?)
                """, (today, likes, users_checked, posts_found))
            
            conn.commit()
    
    def get_today_stats(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            today = datetime.now().date().isoformat()
            c.execute("SELECT * FROM daily_stats WHERE date = ?", (today,))
            row = c.fetchone()
            return dict(row) if row else {'likes': 0, 'users_checked': 0, 'posts_found': 0}
    
    def get_historical_stats(self, days=7):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT * FROM daily_stats 
                ORDER BY date DESC LIMIT ?
            """, (days,))
            return [dict(row) for row in c.fetchall()]
    
    # Bot status methods
    def update_bot_status(self, is_running=None, last_run=None, next_run=None, error=None):
        with self.get_connection() as conn:
            c = conn.cursor()
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
                conn.commit()
    
    def get_bot_status(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM bot_status WHERE id = 1")
            row = c.fetchone()
            return dict(row) if row else {}