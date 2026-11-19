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
Open **http://localhost:5000** in your browser. Database tables and schema migrations initialize automatically on startup.

---

## ☁️ Deployment

Ready for one-click deployment on platforms like Heroku, Render, or Railway:

- **Procfile** included: `web: gunicorn main:app`
- Automatically detects `DATABASE_URL` (PostgreSQL) when deployed to the cloud.

---

## 📄 License

This project is licensed under the MIT License.
