from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime
import threading
import time
import json
import os
from pathlib import Path

from config import Config
from database import Database
from bot import BlueskyBot
from follower_manager import follower_bp  # Changed from relative to absolute import

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['DEBUG'] = Config.DEBUG

# Initialize database and bot
db = Database()
bot = BlueskyBot()

# Get the correct path for .env file
BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / '.env'

print(f"Looking for .env at: {ENV_FILE}")

# Register the follower manager blueprint
app.register_blueprint(follower_bp)

# Routes
@app.route('/')
def index():
    stats = db.get_today_stats()
    bot_status = db.get_bot_status()
    recent_likes = db.get_recent_likes(10)
    followed_today = db.get_followed_count_today()
    
    # Get additional stats for better analytics
    total_followed = db.get_followed_total()
    total_follow_backs = db.get_follow_backs_total()
    follow_back_rate = round((total_follow_backs / total_followed * 100) if total_followed > 0 else 0, 1)
    
    config_dict = {
        'MAX_LIKES_PER_DAY': Config.MAX_LIKES_PER_DAY,
        'MAX_FOLLOWS_PER_DAY': Config.MAX_FOLLOWS_PER_DAY,
        'AUTO_FOLLOW': Config.AUTO_FOLLOW
    }
    return render_template('index.html',
                         stats=stats,
                         status=bot_status,
                         recent_likes=recent_likes,
                         followed_today=followed_today,
                         config=config_dict,
                         total_followed=total_followed,
                         total_follow_backs=total_follow_backs,
                         follow_back_rate=follow_back_rate,
                         now=datetime.now())

@app.route('/api/bot/pause', methods=['POST'])
def pause_bot():
    """Pause the bot"""
    bot.pause()
    return jsonify({'message': 'Bot paused', 'status': 'paused'})

@app.route('/api/bot/resume', methods=['POST'])
def resume_bot():
    """Resume the bot"""
    bot.resume()
    return jsonify({'message': 'Bot resumed', 'status': 'running'})

@app.route('/api/followed/today', methods=['GET'])
def followed_today_api():
    """Get followed count today"""
    return jsonify({'count': db.get_followed_count_today()})

@app.route('/configuration')
def configuration():
    """Settings page"""
    keywords = db.get_all_keywords()
    config = {
        'CHECK_INTERVAL': Config.CHECK_INTERVAL,
        'MAX_LIKES_PER_DAY': Config.MAX_LIKES_PER_DAY,
        'MAX_LIKES_PER_USER': Config.MAX_LIKES_PER_USER,
        'LIKE_DELAY_MIN': Config.LIKE_DELAY_MIN,
        'LIKE_DELAY_MAX': Config.LIKE_DELAY_MAX,
        'AUTO_FOLLOW': Config.AUTO_FOLLOW,
        'MAX_FOLLOWS_PER_DAY': Config.MAX_FOLLOWS_PER_DAY,
        'BLUESKY_HANDLE': Config.BLUESKY_HANDLE,
        'BLUESKY_PASSWORD': '********' if Config.BLUESKY_PASSWORD else ''
    }
    
    return render_template('configuration.html', 
                         keywords=keywords,
                         config=config)

@app.route('/stats')
def stats():
    """Statistics page"""
    daily_stats = db.get_historical_stats(30)
    followed_users = db.get_followed_users()
    recent_likes = db.get_recent_likes(100)
    
    return render_template('stats.html',
                         daily_stats=daily_stats,
                         followed_users=followed_users,
                         recent_likes=recent_likes)

# API Routes
@app.route('/api/keywords', methods=['GET'])
def get_keywords():
    """Get all keywords"""
    keywords = db.get_all_keywords()
    return jsonify(keywords)

@app.route('/api/keywords', methods=['POST'])
def add_keyword():
    """Add a new keyword"""
    data = request.json
    keyword = data.get('keyword', '').strip().lower()
    group = data.get('group', '')
    
    if not keyword:
        return jsonify({'error': 'Keyword required'}), 400
    
    success = db.add_keyword(keyword, group)
    if success:
        return jsonify({'message': 'Keyword added', 'keyword': keyword})
    else:
        return jsonify({'error': 'Keyword already exists'}), 400

@app.route('/api/keywords/<int:keyword_id>', methods=['PUT'])
def update_keyword(keyword_id):
    """Update keyword active status"""
    data = request.json
    active = data.get('active', False)
    
    db.update_keyword(keyword_id, active)
    return jsonify({'message': 'Keyword updated'})

@app.route('/api/keywords/<int:keyword_id>', methods=['DELETE'])
def delete_keyword(keyword_id):
    """Delete a keyword"""
    db.delete_keyword(keyword_id)
    return jsonify({'message': 'Keyword deleted'})

@app.route('/api/keywords/performance', methods=['GET'])
def keywords_performance():
    """Get keyword performance data with actual metrics"""
    keywords = db.get_all_keywords()
    
    # Get performance metrics from database
    keyword_stats = db.get_keyword_performance()
    
    # Create a map of keyword to stats
    stats_map = {stat['keyword']: stat for stat in keyword_stats}
    
    # Enhance keywords with performance metrics
    for keyword in keywords:
        kw_text = keyword['keyword']
        if kw_text in stats_map:
            keyword['engagements'] = stats_map[kw_text].get('engagements', 0)
            keyword['follows'] = stats_map[kw_text].get('follows', 0)
        else:
            keyword['engagements'] = 0
            keyword['follows'] = 0
        keyword['posts_found'] = keyword['engagements']
        keyword['active'] = bool(keyword.get('active', True))
    
    return jsonify(keywords)

@app.route('/api/bot/start', methods=['POST'])
def start_bot():
    """Start the bot"""
    if not bot.client or not bot.client.me:
        bot.login()
    
    bot.start()
    return jsonify({'message': 'Bot started', 'status': 'running'})

@app.route('/api/bot/stop', methods=['POST'])
def stop_bot():
    """Stop the bot"""
    try:
        bot.stop()
        # Verify bot stopped
        time.sleep(1)
        if not bot.is_running():
            return jsonify({'message': 'Bot stopped', 'status': 'stopped'})
        else:
            return jsonify({'message': 'Bot stop initiated', 'status': 'stopping'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/status', methods=['GET'])
def bot_status():
    """Get bot status"""
    status = db.get_bot_status()
    # Add actual running status
    status['actually_running'] = bot.is_running()
    return jsonify(status)

@app.route('/api/bot/run-now', methods=['POST'])
def run_now():
    """Run bot immediately (in background)"""
    def run_bot():
        try:
            bot.run_once()
        except Exception as e:
            print(f"Error in run_now: {e}")
    
    thread = threading.Thread(target=run_bot)
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Bot run started'})

# Follower Tracking API Routes
@app.route('/api/followers/activity', methods=['GET'])
def follower_activity():
    """Get follower activity feed with avatars and readable dates"""
    activity = db.get_follower_activity(limit=20)
    
    # Get follow backs
    follow_backs = db.get_follow_backs(days=7)
    
    # Format the response to match what the dashboard expects
    formatted_activity = []
    for item in activity:
        formatted_activity.append({
            'user_handle': item['handle'],
            'user_display_name': item.get('display_name'),
            'followed_at': item['timestamp'],
            'type': item['type'],
            'avatar': item.get('avatar')  # Add avatar if available
        })
    
    # Format follow backs
    formatted_follow_backs = []
    for fb in follow_backs:
        formatted_follow_backs.append({
            'user_handle': fb['handle'],
            'user_display_name': fb.get('display_name'),
            'followed_back_at': fb['followed_back_at'],
            'avatar': fb.get('avatar')
        })
    
    return jsonify({
        'follows': formatted_activity,
        'follow_backs': formatted_follow_backs
    })

@app.route('/api/unfollowers', methods=['GET'])
def unfollowers():
    """Get unfollowers list"""
    days = request.args.get('days', 30, type=int)
    unfollowers = db.get_unfollowers(days=days)
    
    # Format the response
    formatted = []
    for u in unfollowers:
        formatted.append({
            'user_handle': u['handle'],
            'user_display_name': u.get('display_name'),
            'unfollowed_at': u['unfollowed_at'],
            'avatar': u.get('avatar')
        })
    
    return jsonify(formatted)

@app.route('/api/stats/today', methods=['GET'])
def today_stats():
    """Get today's stats"""
    stats = db.get_today_stats()
    
    # Get follow backs count
    follow_backs_today = db.get_follow_backs_count_today()
    
    # Format response to match what the dashboard expects
    response = {
        'likes': stats.get('likes', 0),
        'follows': stats.get('follows', 0),
        'new_followers': stats.get('new_followers', 0),
        'unfollowers': stats.get('unfollowers', 0),
        'followed_back': follow_backs_today,
        'users_checked': stats.get('users_checked', 0),
        'posts_found': stats.get('posts_found', 0)
    }
    
    return jsonify(response)

@app.route('/api/stats/historical', methods=['GET'])
def historical_stats():
    """Get historical stats for charts"""
    days = request.args.get('days', 7, type=int)
    stats = db.get_historical_stats(days=days)
    
    # Format for chart
    result = []
    for stat in stats:
        result.append({
            'date': stat['date'],
            'likes': stat.get('likes', 0),
            'follows': stat.get('follows', 0),
            'new_followers': stat.get('new_followers', 0),
            'unfollowers': stat.get('unfollowers', 0),
            'followed_back': stat.get('followed_back', 0),
            'users_checked': stat.get('users_checked', 0)
        })
    
    # Sort by date ascending
    result.sort(key=lambda x: x['date'])
    
    return jsonify(result)

@app.route('/api/followers/sync', methods=['POST'])
def sync_followers():
    """Manually trigger follower sync"""
    if not bot.client or not bot.client.me:
        if not bot.login():
            return jsonify({'error': 'Failed to login'}), 500
    
    try:
        bot.sync_followers()
        return jsonify({'message': 'Follower sync completed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/discovered-content', methods=['GET'])
def discovered_content():
    """Get recently discovered posts with avatars"""
    posts = db.get_discovered_content(limit=20)
    
    # Format posts with avatar and readable dates
    formatted_posts = []
    for post in posts:
        formatted_posts.append({
            'uri': post['uri'],
            'author_handle': post.get('author_handle', 'unknown'),
            'author_display_name': post.get('author_display_name'),
            'author_avatar': post.get('author_avatar'),
            'text': post.get('text', ''),
            'discovered_at': post.get('discovered_at')
        })
    
    return jsonify({'posts': formatted_posts})

@app.route('/api/post/<path:post_uri>', methods=['GET'])
def post_details(post_uri):
    """Get post details by URI"""
    from urllib.parse import unquote
    
    # Decode the URI
    decoded_uri = unquote(post_uri)
    
    # Try to get from database
    with db.get_cursor() as c:
        c.execute("SELECT * FROM liked_posts WHERE uri = ?", (decoded_uri,))
        post = c.fetchone()
        
        if post:
            post_data = json.loads(post['post_data']) if post['post_data'] else {}
            return jsonify({
                'uri': post['uri'],
                'author_handle': post['user_handle'],
                'author_display_name': post_data.get('author_display_name'),
                'author_avatar': post_data.get('author_avatar'),
                'text': post_data.get('text', ''),
                'created_at': post['liked_at']
            })
    
    return jsonify({'error': 'Post not found'}), 404

@app.route('/api/likes/all', methods=['GET'])
def all_likes():
    """Get all likes history"""
    limit = request.args.get('limit', 100, type=int)
    likes = db.get_recent_likes(limit)
    
    # Format the response
    formatted = []
    for like in likes:
        post_data = json.loads(like['post_data']) if like['post_data'] else {}
        formatted.append({
            'uri': like['uri'],
            'user_handle': like['user_handle'],
            'liked_at': like['liked_at'],
            'post_data': post_data
        })
    
    return jsonify(formatted)

@app.route('/api/followed-users', methods=['GET'])
def get_followed_users():
    """Get list of followed users"""
    users = db.get_followed_users()
    
    # Format the response
    formatted = []
    for user in users:
        formatted.append({
            'did': user['did'],
            'handle': user['handle'],
            'display_name': user.get('display_name'),
            'avatar': user.get('avatar'),
            'followed_at': user['followed_at'],
            'is_following_us': user.get('is_following_us', False)
        })
    
    return jsonify(formatted)

@app.route('/api/recent-likes', methods=['GET'])
def get_recent_likes():
    """Get recent likes"""
    limit = request.args.get('limit', 50, type=int)
    likes = db.get_recent_likes(limit)
    
    # Format the response
    formatted = []
    for like in likes:
        post_data = json.loads(like['post_data']) if like['post_data'] else {}
        formatted.append({
            'uri': like['uri'],
            'user_handle': like['user_handle'],
            'user_display_name': post_data.get('author_display_name'),
            'user_avatar': post_data.get('author_avatar'),
            'liked_at': like['liked_at'],
            'post_data': post_data
        })
    
    return jsonify(formatted)

# Settings API Routes
@app.route('/api/credentials', methods=['POST'])
def update_credentials():
    """Update Bluesky credentials and restart bot"""
    try:
        data = request.json
        handle = data.get('handle')
        password = data.get('password')
        
        if not handle or not password:
            return jsonify({'error': 'Handle and password required'}), 400
        
        env_vars = {}
        if ENV_FILE.exists():
            with open(ENV_FILE, 'r') as f:
                for line in f:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        env_vars[key] = value
        
        env_vars['BLUESKY_HANDLE'] = handle
        env_vars['BLUESKY_PASSWORD'] = password
        
        with open(ENV_FILE, 'w') as f:
            for key, value in env_vars.items():
                f.write(f'{key}={value}\n')
        
        return jsonify({'success': True, 'message': 'Credentials saved'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/restart', methods=['POST'])
def restart_bot():
    """Restart the bot thread"""
    try:
        global bot
        bot.stop()
        time.sleep(2)
        bot = BlueskyBot()
        if bot.login():
            bot.start()
            return jsonify({'success': True, 'message': 'Bot restarted successfully'})
        else:
            return jsonify({'error': 'Failed to login with new credentials'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/configuration', methods=['GET'])
def get_settings():
    """Get current bot settings"""
    settings = {
        'CHECK_INTERVAL': Config.CHECK_INTERVAL,
        'MAX_LIKES_PER_DAY': Config.MAX_LIKES_PER_DAY,
        'MAX_LIKES_PER_USER': Config.MAX_LIKES_PER_USER,
        'LIKE_DELAY_MIN': Config.LIKE_DELAY_MIN,
        'LIKE_DELAY_MAX': Config.LIKE_DELAY_MAX,
        'AUTO_FOLLOW': Config.AUTO_FOLLOW,
        'MAX_FOLLOWS_PER_DAY': Config.MAX_FOLLOWS_PER_DAY,
        'ENGAGEMENT_THRESHOLD': getattr(Config, 'ENGAGEMENT_THRESHOLD', 3)
    }
    return jsonify(settings)

@app.route('/api/keywords/groups', methods=['GET'])
def get_keyword_groups():
    """Get all keyword groups"""
    groups = db.get_all_groups()
    return jsonify(groups)

@app.route('/api/keywords/groups', methods=['POST'])
def add_keyword_group():
    """Add a new keyword group"""
    data = request.json
    group_name = data.get('name', '').strip()
    
    if not group_name:
        return jsonify({'error': 'Group name required'}), 400
    
    # Groups are just metadata on keywords, so we don't need to store them separately
    # Just return success
    return jsonify({'message': 'Group added', 'name': group_name})

@app.route('/api/keywords/groups/<path:group_name>', methods=['DELETE'])
def delete_keyword_group(group_name):
    """Delete a keyword group (removes group from all keywords)"""
    # Remove this group from all keywords
    with db.get_cursor() as c:
        c.execute("UPDATE keywords SET group_name = NULL WHERE group_name = ?", (group_name,))
    
    return jsonify({'message': 'Group deleted'})

@app.route('/api/keywords/<int:keyword_id>/group', methods=['PUT'])
def update_keyword_group(keyword_id):
    """Update a keyword's group"""
    data = request.json
    group = data.get('group')
    
    db.update_keyword_group(keyword_id, group)
    
    return jsonify({'message': 'Keyword group updated'})

@app.route('/api/configuration', methods=['POST'])
def update_settings():
    """Update bot configuration"""
    try:
        data = request.json
        
        env_vars = {}
        if ENV_FILE.exists():
            with open(ENV_FILE, 'r') as f:
                for line in f:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        env_vars[key] = value
        
        settings_map = {
            'check_interval': 'CHECK_INTERVAL',
            'max_likes_per_day': 'MAX_LIKES_PER_DAY',
            'max_likes_per_user': 'MAX_LIKES_PER_USER',
            'like_delay_min': 'LIKE_DELAY_MIN',
            'like_delay_max': 'LIKE_DELAY_MAX',
            'auto_follow': 'AUTO_FOLLOW',
            'max_follows_per_day': 'MAX_FOLLOWS_PER_DAY'
        }
        
        for form_field, env_var in settings_map.items():
            if form_field in data:
                value = data[form_field]
                if env_var == 'AUTO_FOLLOW':
                    value = 'true' if value else 'false'
                env_vars[env_var] = str(value)
        
        with open(ENV_FILE, 'w') as f:
            for key, value in env_vars.items():
                f.write(f'{key}={value}\n')
        
        return jsonify({'success': True, 'message': 'Configuration saved successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host=Config.FLASK_HOST, port=Config.FLASK_PORT, debug=Config.FLASK_DEBUG)