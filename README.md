# Bluesky Social Bot 🤖

A sophisticated automation bot for Bluesky Social that helps you engage with your community by automatically liking and following users based on keywords. Perfect for community managers, content creators, and anyone looking to grow their presence on Bluesky.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-supported-brightgreen.svg)](https://www.docker.com/)
[![Bluesky](https://img.shields.io/badge/Bluesky-API-blue)](https://bluesky.social)

## 📸 Screenshots

<!-- SCREENSHOT PLACEHOLDER - Add your dashboard screenshot here -->
<div align="center">
  <i>Dashboard Overview - Real-time bot statistics and controls</i>
  <br><br>
  <!-- Replace this with your image: ![Dashboard](screenshots/dashboard.png) -->
  <img src="https://i.imgur.com/1o4GKVD.png" alt="Dashboard Screenshot" width="800">
</div>

<br>

<div align="center">
  <table>
    <tr>
      <td align="center">
        <!-- Replace with your image: <img src="screenshots/settings.png" width="400"> -->
        <img src="https://i.imgur.com/yK9zX3S.png" width="400"><br>
        <i>Settings & Configuration</i>
      </td>
      <td align="center">
        <!-- Replace with your image: <img src="screenshots/stats.png" width="400"> -->
        <img src="https://i.imgur.com/vuTDZJr.png" width="400"><br>
        <i>Analytics & Statistics</i>
      </td>
    </tr>
  </table>
</div>

## ✨ Features

- **🤖 Automated Engagement** - Automatically likes posts containing your target keywords
- **👥 Smart Following** - Optional auto-follow users after liking their posts
- **📊 Real-time Dashboard** - Monitor bot activity, stats, and controls in real-time
- **🔑 Keyword Management** - Add/remove keywords with autocomplete and grouping
- **📈 Analytics** - Track likes, follows, and user engagement over time
- **⚙️ Customizable Settings** - Adjust delays, daily limits, and behavior
- **🔒 Safe Operation** - Built-in rate limiting and natural delays to avoid detection
- **📱 Web Interface** - Easy-to-use web UI for complete control
- **🐳 Docker Support** - One-command deployment with Docker

## 🚀 Quick Start

### Prerequisites

- Python 3.9+ or Docker
- Bluesky account with [App Password](https://bsky.app/settings/app-passwords)

### Installation

#### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/Keekay-OD/bluesky-social-bot.git
cd bluesky-social-bot

# Copy environment configuration
cp .env.example .env

# Edit .env with your Bluesky credentials
nano .env

# Run with Docker Compose
docker-compose up -d
```

#### Option 2: Manual Installation

```bash
# Clone the repository
git clone https://github.com/Keekay-OD/bluesky-social-bot.git
cd bluesky-social-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
nano .env

# Run the application
python main.py
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BLUESKY_HANDLE` | Your Bluesky handle (e.g., username.bsky.social) | - |
| `BLUESKY_PASSWORD` | Your Bluesky app password | - |
| `CHECK_INTERVAL` | How often to check for new posts (seconds) | 3600 |
| `MAX_LIKES_PER_DAY` | Maximum likes per day | 100 |
| `MAX_LIKES_PER_USER` | Maximum likes per user per check | 3 |
| `LIKE_DELAY_MIN` | Minimum delay between likes (seconds) | 30 |
| `LIKE_DELAY_MAX` | Maximum delay between likes (seconds) | 90 |
| `AUTO_FOLLOW` | Auto-follow users after liking | false |
| `MAX_FOLLOWS_PER_DAY` | Maximum follows per day | 30 |
| `FLASK_PORT` | Web interface port | 5000 |

### Keyword Groups

Organize your keywords into groups for different campaigns:
- **Cycling** - biking, cycling, bicycle, velo
- **Tech** - programming, coding, developer, tech
- **Art** - art, artist, drawing, painting
- **Music** - music, musician, band, song

## 📖 Usage

1. **Access the Dashboard**: Open `http://localhost:5000` in your browser
2. **Add Keywords**: Navigate to Settings → Add keywords with autocomplete
3. **Create Groups**: Organize keywords into campaigns
4. **Configure Settings**: Adjust delays, limits, and behavior
5. **Start the Bot**: Click "Start" on the dashboard
6. **Monitor Activity**: Watch real-time stats and recent activity

### Web Interface Pages

- **Dashboard** (`/`) - Main control center with real-time stats
- **Settings** (`/settings`) - Configure keywords, groups, and bot behavior
- **Statistics** (`/stats`) - Detailed analytics and historical data

## 📊 API Endpoints

The bot provides a RESTful API for integration:

- `GET /api/stats/today` - Today's statistics
- `GET /api/stats/historical?days=30` - Historical data
- `POST /api/bot/start` - Start the bot
- `POST /api/bot/stop` - Stop the bot
- `POST /api/bot/pause` - Pause the bot
- `POST /api/bot/resume` - Resume the bot
- `GET /api/keywords` - List all keywords
- `POST /api/keywords` - Add a new keyword
- `PUT /api/keywords/{id}` - Update keyword status
- `DELETE /api/keywords/{id}` - Delete a keyword

## 🏗️ Project Structure

```
bluesky-social-bot/
├── app/
│   ├── web/
│   │   ├── templates/          # HTML templates
│   │   │   ├── index.html      # Dashboard
│   │   │   ├── settings.html   # Settings page
│   │   │   └── stats.html      # Statistics page
│   │   └── app.py              # Flask web server
│   ├── bot.py                   # Main bot logic
│   ├── config.py                # Configuration
│   ├── database.py              # Database operations
│   └── main.py                   # Entry point
├── data/                         # SQLite database
├── .env                          # Environment variables
├── docker-compose.yml            # Docker Compose config
├── Dockerfile                     # Docker image
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```



## ☁️ Easy Deployment Options

### Quick Deploy with Docker (Any VPS)

```bash
# On your VPS
git clone https://github.com/Keekay-OD/bluesky-social-bot.git
cd bluesky-social-bot
cp .env.example .env
nano .env  # Add your credentials
docker-compose up -d
```

## ⚠️ Disclaimer

This bot is designed to help you engage with your community authentically. Please use responsibly and in accordance with Bluesky's Terms of Service. Excessive automation may result in account limitations.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Bluesky API](https://docs.bsky.app/) for the amazing platform
- [ATProtocol](https://github.com/MarshalX/atproto) for the Python SDK
- All contributors and users of this bot

## 📧 Contact

Keekay - [@bikes.keekay.cloud](https://bsky.app/profile/bikes.keekay.cloud) - bikes@keekay.cloud

Project Link: [https://github.com/Keekay-OD/bluesky-social-bot](https://github.com/Keekay-OD/bluesky-social-bot)

---

<div align="center">
  Made with ❤️ for the Bluesky Community
  <br><br>
  ⭐ Star this repo if you find it useful!
</div>
```
