#!/usr/bin/env python3
"""
Bluesky Social Bot - Main entry point
Runs both the bot and web interface
"""

import threading
import time
import sys
from web.app import app
from bot import BlueskyBot
from database import Database
from config import Config

def run_flask():
    """Run the Flask web interface"""
    app.run(host=Config.FLASK_HOST, port=Config.FLASK_PORT, debug=Config.DEBUG, use_reloader=False)

def main():
    """Main function"""
    print("=" * 60)
    print("🚀 Bluesky Social Bot")
    print("=" * 60)
    
    # Initialize database
    print("📊 Initializing database...")
    db = Database()
    
    # Initialize bot
    print("🤖 Initializing bot...")
    bot = BlueskyBot()
    
    # Login to Bluesky
    print("🔑 Logging into Bluesky...")
    if not bot.login():
        print("❌ Failed to login. Check your credentials in .env file")
        print("💡 Make sure you're using an App Password, not your main password")
        sys.exit(1)
    
    # Start bot in background
    print("▶️ Starting bot...")
    bot.start()
    
    # Start Flask in a separate thread
    print("🌐 Starting web interface on http://localhost:5000")
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("\n✅ Bot is running!")
    print("📊 Web interface available at: http://localhost:5000")
    print("=" * 60)
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
        bot.stop()
        print("✅ Bot stopped")
        sys.exit(0)

if __name__ == "__main__":
    main()