# ✦ DreamShelf

> *"Every story deserves a shelf."*

A modern, celestial dark-mode web application for curating, tracking, and showcasing your favorite movies, series, and books. Inspired by Letterboxd and modern streaming platforms.

---

## ✨ Features

- **Dual Shelf (Movies & Books)** — Track movies, series, animation, and anime alongside categorized books in one unified library.
- **Watch & Read Status** — Instant toggles between *To Watch* / *Watched* and *To Read* / *Read*.
- **All-Time Favorites (Top 10)** — Curate your top 10 movies with drag-and-drop reordering, Rank #1 crown badge, and slot replacement.
- **Custom Collections** — Create themed movie collections with public or private visibility and poster collage previews.
- **Cosmic Discovery** — Browse trending movies, series, and books powered by live TMDB and Google Books API integrations.
- **Rich Media Dossiers** — View full trailers, backdrops, cast, director, and synopsis for any discovered title.
- **User Profiles & Social** — Customizable profile with banner and avatar uploads, bio, favorite genres, follow system, and live activity feed.
- **Personal Ratings & Reviews** — 10-star rating system with smart unrated exclusion, custom tags, and review journaling.
- **Visual Analytics** — Monthly reading/watching milestones, streak tracking, and rating distribution charts.
- **Watchlist Import** — Import watchlists from Letterboxd or custom CSV files with automatic 5-to-10 star conversion.
- **Google & Email Auth** — Sign in with Google OAuth 2.0 or traditional email/password.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.12, Flask, Flask-Login, Flask-SQLAlchemy, Flask-WTF
- **Database**: SQLite (local) / PostgreSQL (production-ready)
- **APIs**: The Movie Database (TMDB) API v3, Google Books API, Google OAuth 2.0
- **Frontend**: HTML5, CSS3 (Custom Dark Theme), Jinja2, Vanilla JavaScript, FontAwesome
- **Server**: Gunicorn (WSGI)

---

## 🚀 Quick Start

### 1. Clone & Setup Virtual Environment
```bash
git clone https://github.com/Haftom-Dreamer/dreamshelf.git
cd dreamshelf
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

```ini
SECRET_KEY=your_secret_key_here
TMDB_API_KEY=your_tmdb_api_key_here

# Optional: Google OAuth 2.0 (for Google Sign-In)
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:5000/auth/google/callback
```

### 4. Run the Application
```bash
python main.py
```

---

## 🩺 Health Check & Monitoring

DreamShelf provides a lightweight health check endpoint designed for uptime monitors (such as [UptimeRobot](https://uptimerobot.com/)) to prevent Render's free tier from sleeping:

- **Endpoint**: `GET /health`
- **Response**: `{"status": "healthy"}` (HTTP 200)
- **Authentication**: None required (public)

### Setting Up UptimeRobot
1. Create a free account at [uptimerobot.com](https://uptimerobot.com/).
2. Click **+ Add New Monitor**.
3. Set **Monitor Type** to `HTTP(s)`.
4. Enter a friendly name (e.g. `DreamShelf Keep-Alive`).
5. Set the **URL (or IP)** to `https://<your-render-app-name>.onrender.com/health` (replace with your actual Render service URL, e.g. `https://dreamshelf.onrender.com/health`).
6. Set the **Monitoring Interval** to every 5 or 10 minutes (Render free instances spin down after 15 minutes of inactivity).
7. Save the monitor.

