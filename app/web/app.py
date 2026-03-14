from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime
import threading
import time
import os
from pathlib import Path

from config import Config
from database import Database
from bot import BlueskyBot
from follower_manager import follower_bp  # Changed from relative to absolute import

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY  # Fixed: should be FLASK_SECRET_KEY, not SECRET_KEY
app.config['DEBUG'] = Config.DEBUG  # Fixed: should be FLASK_DEBUG, not DEBUG

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
def followed_today():
    return jsonify({'count': db.get_followed_count_today()})

@app.route('/settings')
def settings():
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
    
    return render_template('settings.html', 
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
    bot.stop()
    return jsonify({'message': 'Bot stopped', 'status': 'stopped'})

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

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Update bot settings"""
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
        
        return jsonify({'success': True, 'message': 'Settings saved successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/status', methods=['GET'])
def bot_status():
    """Get bot status"""
    status = db.get_bot_status()
    return jsonify(status)

@app.route('/api/bot/run-now', methods=['POST'])
def run_now():
    """Run bot immediately (in background)"""
    def run_bot():
        bot.run_once()
    
    thread = threading.Thread(target=run_bot)
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Bot run started'})

@app.route('/api/stats/today', methods=['GET'])
def today_stats():
    """Get today's stats"""
    stats = db.get_today_stats()
    return jsonify(stats)

@app.route('/api/stats/historical', methods=['GET'])
def historical_stats():
    """Get historical stats"""
    days = request.args.get('days', 7, type=int)
    stats = db.get_historical_stats(days)
    return jsonify(stats)

@app.route('/api/followed-users', methods=['GET'])
def get_followed_users():
    """Get list of followed users"""
    users = db.get_followed_users()
    return jsonify(users)

@app.route('/api/recent-likes', methods=['GET'])
def get_recent_likes():
    """Get recent likes"""
    limit = request.args.get('limit', 50, type=int)
    likes = db.get_recent_likes(limit)
    return jsonify(likes)

if __name__ == '__main__':
    app.run(host=Config.FLASK_HOST, port=Config.FLASK_PORT, debug=Config.FLASK_DEBUG)