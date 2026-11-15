from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, session
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from wtforms import StringField, SubmitField, PasswordField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import os
import secrets
import urllib.parse
from datetime import datetime, date, timedelta
from collections import Counter, defaultdict
import io
import csv
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, Date

TMDB_API_KEY = "f319b185cd1af98f98b55a81304dfe9b"

# =====================
# --- Google OAuth Config ---
# =====================
# Set these in environment variables or a .env file before running.
# In Google Cloud Console: APIs & Services → Credentials → OAuth 2.0 Client IDs
# Authorized redirect URI must be: http://localhost:5000/auth/google/callback
GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:5000/auth/google/callback")

GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

app = Flask(__name__)
app.config['SECRET_KEY'] = '8BYkEfBA6O6donzWlSihBXox7Y0sKR6b'
Bootstrap(app)
db_path = os.path.abspath("favorite-movies.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access this page."

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

AVATAR_COLORS = ["#6c63ff", "#ff6584", "#43b89c", "#f5a623", "#4ecdc4", "#c56ef3"]

# =====================
# --- DB Models ---
# =====================

followers_table = db.Table('followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
)

class User(UserMixin, db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=True)   # nullable → Google-only accounts have no password
    google_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=True)  # Google OAuth sub claim
    avatar_color: Mapped[str] = mapped_column(String(20), nullable=False, default="#6c63ff")
    bio: Mapped[str] = mapped_column(String(500), nullable=True)
    avatar_url: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    movies: Mapped[list["Movie"]] = relationship("Movie", back_populates="owner", cascade="all, delete-orphan")
    books: Mapped[list["Book"]] = relationship("Book", back_populates="owner", cascade="all, delete-orphan")
    followed: Mapped[list["User"]] = relationship(
        'User', secondary=followers_table,
        primaryjoin=(followers_table.c.follower_id == id),
        secondaryjoin=(followers_table.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')

class Movie(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), nullable=False)
    tmdb_id: Mapped[str] = mapped_column(String(50), nullable=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    year: Mapped[str] = mapped_column(String(10), nullable=False)
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    description: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    review: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    img_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="to_watch")
    genre: Mapped[str] = mapped_column(String(200), nullable=True, default="")
    custom_tags: Mapped[str] = mapped_column(String(250), nullable=True, default="")
    date_added: Mapped[date] = mapped_column(Date, default=date.today)
    date_watched: Mapped[date] = mapped_column(Date, nullable=True)
    media_type: Mapped[str] = mapped_column(String(30), nullable=False, default="movie")
    owner: Mapped["User"] = relationship("User", back_populates="movies")

class Book(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), nullable=False)
    google_id: Mapped[str] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    author: Mapped[str] = mapped_column(String(250), nullable=False, default="Unknown")
    year: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    description: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    review: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    img_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="to_read")
    genre: Mapped[str] = mapped_column(String(200), nullable=True, default="")
    custom_tags: Mapped[str] = mapped_column(String(250), nullable=True, default="")
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="fiction")
    date_added: Mapped[date] = mapped_column(Date, default=date.today)
    date_read: Mapped[date] = mapped_column(Date, nullable=True)
    owner: Mapped["User"] = relationship("User", back_populates="books")

BOOK_CATEGORIES = {
    "fiction": {
        "label": "Fiction & Literature",
        "icon": "fa-book",
        "emoji": "📖",
        "keywords": ["fiction", "fantasy", "sci-fi", "science fiction", "novel", "classic", "literature", "dystopian", "adventure", "mystery", "thriller", "drama", "romance", "poetry"]
    },
    "philosophy": {
        "label": "Philosophy & Ethics",
        "icon": "fa-brain",
        "emoji": "🧠",
        "keywords": ["philosophy", "stoic", "stoicism", "wisdom", "ethics", "morality", "meditations", "epistemology", "existential", "logic", "theology"]
    },
    "self_help": {
        "label": "Self-Help & Growth",
        "icon": "fa-seedling",
        "emoji": "🌱",
        "keywords": ["self-help", "habits", "productivity", "growth", "motivation", "success", "happiness", "discipline", "mindset", "personal growth", "self-management", "lifestyle"]
    },
    "business": {
        "label": "Business & Finance",
        "icon": "fa-chart-line",
        "emoji": "💼",
        "keywords": ["finance", "money", "business", "investing", "economics", "strategy", "management", "entrepreneur", "wealth", "marketing", "leadership"]
    },
    "non_fiction": {
        "label": "Non-Fiction & Science",
        "icon": "fa-globe",
        "emoji": "🌍",
        "keywords": ["non-fiction", "biography", "history", "science", "physics", "technology", "society", "politics", "psychology", "memoir", "culture", "nature", "anthropology"]
    }
}

def detect_book_category(title="", genre="", description="", explicit_category=None):
    if explicit_category in BOOK_CATEGORIES:
        return explicit_category
    text = f"{title or ''} {genre or ''} {description or ''}".lower()
    for cat in ["philosophy", "self_help", "business", "non_fiction"]:
        keywords = BOOK_CATEGORIES[cat]["keywords"]
        if any(k in text for k in keywords):
            return cat
    return "fiction"

with app.app_context():
    db.create_all()
    # --- Schema migration: add google_id column if it doesn't exist yet ---
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    existing_cols = [c["name"] for c in inspector.get_columns("user")]
    if "google_id" not in existing_cols:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE user ADD COLUMN google_id VARCHAR(100)"))
            conn.commit()
    # Add media_type column to movie table if missing
    movie_cols = [c["name"] for c in inspector.get_columns("movie")]
    if "media_type" not in movie_cols:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE movie ADD COLUMN media_type VARCHAR(30) NOT NULL DEFAULT 'movie'"))
            conn.commit()

    # Add category column to book table if missing
    book_cols = [c["name"] for c in inspector.get_columns("book")]
    if "category" not in book_cols:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE book ADD COLUMN category VARCHAR(50) NOT NULL DEFAULT 'fiction'"))
            conn.commit()

    # One-time smart auto-categorization for existing animation/anime movies in DB
    with db.engine.connect() as conn:
        try:
            conn.execute(text("""
                UPDATE movie 
                SET media_type = 'anime'
                WHERE (media_type = 'movie' OR media_type = 'animation')
                  AND (LOWER(title) LIKE '%solo leveling%' 
                    OR LOWER(title) LIKE '%my hero academia%' 
                    OR LOWER(title) LIKE '%one piece%' 
                    OR LOWER(title) LIKE '%attack on titan%' 
                    OR LOWER(title) LIKE '%detective conan%' 
                    OR LOWER(title) LIKE '%spirited away%' 
                    OR LOWER(title) LIKE '%naruto%' 
                    OR LOWER(title) LIKE '%bleach%' 
                    OR LOWER(title) LIKE '%demon slayer%' 
                    OR LOWER(title) LIKE '%dragon ball%' 
                    OR LOWER(title) LIKE '%jujutsu%'
                    OR LOWER(title) LIKE '%anime%'
                    OR LOWER(genre) LIKE '%anime%')
            """))
            conn.execute(text("""
                UPDATE movie 
                SET media_type = 'animation'
                WHERE media_type = 'movie' 
                  AND LOWER(genre) LIKE '%animation%'
            """))

            # Smart auto-categorization for existing books
            conn.execute(text("""
                UPDATE book
                SET category = 'philosophy'
                WHERE LOWER(genre) LIKE '%philosophy%'
                   OR LOWER(genre) LIKE '%stoic%'
                   OR LOWER(genre) LIKE '%ethics%'
                   OR LOWER(genre) LIKE '%wisdom%'
                   OR LOWER(title) LIKE '%courage to be disliked%'
                   OR LOWER(title) LIKE '%meditations%'
                   OR LOWER(title) LIKE '%beyond good and evil%'
                   OR LOWER(title) LIKE '%48 laws of power%'
            """))
            conn.execute(text("""
                UPDATE book
                SET category = 'self_help'
                WHERE (category = 'fiction' OR category IS NULL)
                  AND (LOWER(genre) LIKE '%self-help%'
                   OR LOWER(genre) LIKE '%habits%'
                   OR LOWER(genre) LIKE '%productivity%'
                   OR LOWER(genre) LIKE '%growth%'
                   OR LOWER(genre) LIKE '%motivation%'
                   OR LOWER(title) LIKE '%atomic habits%'
                   OR LOWER(title) LIKE '%subtle art%'
                   OR LOWER(title) LIKE '%deep work%'
                   OR LOWER(title) LIKE '%can\'t hurt me%')
            """))
            conn.execute(text("""
                UPDATE book
                SET category = 'business'
                WHERE (category = 'fiction' OR category IS NULL)
                  AND (LOWER(genre) LIKE '%finance%'
                   OR LOWER(genre) LIKE '%business%'
                   OR LOWER(genre) LIKE '%money%'
                   OR LOWER(genre) LIKE '%economics%'
                   OR LOWER(genre) LIKE '%investing%'
                   OR LOWER(title) LIKE '%psychology of money%'
                   OR LOWER(title) LIKE '%rich dad%')
            """))
            conn.execute(text("""
                UPDATE book
                SET category = 'non_fiction'
                WHERE (category = 'fiction' OR category IS NULL)
                  AND (LOWER(genre) LIKE '%history%'
                   OR LOWER(genre) LIKE '%science%'
                   OR LOWER(genre) LIKE '%biography%'
                   OR LOWER(genre) LIKE '%non-fiction%'
                   OR LOWER(title) LIKE '%sapiens%'
                   OR LOWER(title) LIKE '%thinking, fast and slow%')
            """))
            conn.commit()
        except Exception:
            pass

    try:
        for b in Book.query.all():
            det = detect_book_category(b.title, b.genre, b.description)
            if b.category != det:
                b.category = det
        db.session.commit()
    except Exception:
        pass
    # Make password_hash nullable in SQLite (SQLite ignores NOT NULL on ALTER,
    # so existing rows stay intact; new Google-only rows will have NULL).


# =====================
# --- Auth Routes ---
# =====================

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    class RegisterForm(FlaskForm):
        username = StringField("Username", validators=[DataRequired(), Length(3, 80)])
        email = StringField("Email", validators=[DataRequired(), Email()])
        password = PasswordField("Password", validators=[DataRequired(), Length(6)])
        confirm = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password")])
        submit = SubmitField("Create Account")
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash("Email already registered. Please log in.", "error")
            return redirect(url_for("login"))
        if User.query.filter_by(username=form.username.data).first():
            flash("Username already taken.", "error")
            return redirect(url_for("register"))
        import random
        color = random.choice(AVATAR_COLORS)
        user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=generate_password_hash(form.password.data),
            avatar_color=color
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Welcome! Your account has been created.", "success")
        return redirect(url_for("dashboard"))
    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    class LoginForm(FlaskForm):
        email = StringField("Email", validators=[DataRequired(), Email()])
        password = PasswordField("Password", validators=[DataRequired()])
        submit = SubmitField("Sign In")
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.password_hash and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))
        elif user and not user.password_hash:
            # Account exists but was created via Google — guide them
            flash("This email is registered via Google Sign-In. Please use the \"Continue with Google\" button.", "error")
        else:
            flash("Invalid email or password.", "error")
    return render_template("login.html", form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("landing"))


# =====================
# --- Google OAuth Routes ---
# =====================

@app.route("/auth/google/login")
def google_login():
    """Redirect the user to Google's OAuth consent screen."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        flash("Google Sign-In is not configured. Please contact the administrator.", "error")
        return redirect(url_for("login"))

    # Ensure host matches GOOGLE_REDIRECT_URI so session cookies are preserved
    parsed_redirect = urllib.parse.urlparse(GOOGLE_REDIRECT_URI)
    if parsed_redirect.netloc and request.host != parsed_redirect.netloc:
        target = urllib.parse.urlunparse((
            parsed_redirect.scheme or request.scheme,
            parsed_redirect.netloc,
            request.path,
            '',
            request.query_string.decode('utf-8') if request.query_string else '',
            ''
        ))
        return redirect(target)

    # Generate a random state token to protect against CSRF
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    # Preserve the 'next' URL so we can redirect there after login
    next_url = request.args.get("next", "")
    if next_url:
        session["oauth_next"] = next_url

    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid email profile",
        "state":         state,
        "access_type":   "online",
        "prompt":        "select_account",
    }
    auth_url = GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)
    return redirect(auth_url)


@app.route("/auth/google/callback")
def google_callback():
    """Handle the OAuth2 callback from Google."""
    # --- CSRF state check ---
    state_in_session = session.pop("oauth_state", None)
    state_from_google = request.args.get("state")
    if not state_in_session or state_in_session != state_from_google:
        flash("Authentication session expired or invalid state. Please click 'Continue with Google' again.", "error")
        return redirect(url_for("login"))

    # --- Check for error from Google ---
    error = request.args.get("error")
    if error:
        flash(f"Google Sign-In was cancelled or failed: {error}", "error")
        return redirect(url_for("login"))

    code = request.args.get("code")
    if not code:
        flash("Google Sign-In failed: no authorization code received.", "error")
        return redirect(url_for("login"))

    # --- Exchange code for tokens ---
    try:
        token_resp = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "code":          code,
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri":  GOOGLE_REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
    except Exception as e:
        flash("Google Sign-In failed: could not exchange authorization code.", "error")
        return redirect(url_for("login"))

    access_token = token_data.get("access_token")
    if not access_token:
        flash("Google Sign-In failed: no access token received.", "error")
        return redirect(url_for("login"))

    # --- Fetch user info from Google ---
    try:
        userinfo_resp = requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        userinfo_resp.raise_for_status()
        userinfo = userinfo_resp.json()
    except Exception:
        flash("Google Sign-In failed: could not retrieve user information.", "error")
        return redirect(url_for("login"))

    google_id    = userinfo.get("id")
    email        = userinfo.get("email")
    google_name  = userinfo.get("name", "")
    avatar_url   = userinfo.get("picture", "")
    email_verified = userinfo.get("verified_email", False)

    if not google_id or not email:
        flash("Google Sign-In failed: incomplete user information received.", "error")
        return redirect(url_for("login"))

    if not email_verified:
        flash("Your Google account email is not verified. Please verify it and try again.", "error")
        return redirect(url_for("login"))

    # --- Look up or create the user ---
    import random

    try:
        # 1. Find by google_id (fastest path — returning Google user)
        user = User.query.filter_by(google_id=google_id).first()

        if user is None:
            # 2. Find by email — link Google to an existing email/password account
            user = User.query.filter_by(email=email).first()
            if user is not None:
                # Link the Google ID to the existing account
                user.google_id = google_id
                if avatar_url and not user.avatar_url:
                    user.avatar_url = avatar_url
                db.session.commit()
                flash(f"Your Google account has been linked to your existing DreamShelf account. Welcome back, {user.username}!", "success")
            else:
                # 3. Brand-new user — create an account automatically
                base_username = (google_name or email.split("@")[0]).replace(" ", "").lower()
                base_username = "".join(c for c in base_username if c.isalnum() or c == "_")[:30] or "user"
                username = base_username
                suffix = 1
                while User.query.filter_by(username=username).first():
                    username = f"{base_username}{suffix}"
                    suffix += 1

                color = random.choice(AVATAR_COLORS)
                user = User(
                    username=username,
                    email=email,
                    password_hash=None,   # No password for Google-only accounts
                    google_id=google_id,
                    avatar_color=color,
                    avatar_url=avatar_url or None,
                )
                db.session.add(user)
                db.session.commit()
                flash(f"Welcome to DreamShelf, {user.username}! Your account has been created via Google.", "success")

        login_user(user)
    except Exception as e:
        db.session.rollback()
        flash("An error occurred while setting up your account. Please try again.", "error")
        return redirect(url_for("login"))

    next_url = session.pop("oauth_next", None)
    return redirect(next_url or url_for("dashboard"))

class SettingsForm(FlaskForm):
    bio = TextAreaField("Bio", validators=[Length(max=500)])
    avatar_url = StringField("Avatar URL", validators=[Length(max=500)])
    submit = SubmitField("Save Settings")

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    form = SettingsForm(obj=current_user)
    if form.validate_on_submit():
        current_user.bio = form.bio.data
        current_user.avatar_url = form.avatar_url.data
        db.session.commit()
        flash("Settings saved successfully.", "success")
        return redirect(url_for("public_collection", username=current_user.username))
    return render_template("settings.html", form=form)

# =====================
# --- Social Routes ---
# =====================

@app.route("/follow/<username>")
@login_required
def follow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash(f"User {username} not found.", "error")
        return redirect(url_for("landing"))
    if user == current_user:
        flash("You cannot follow yourself!", "error")
        return redirect(url_for("public_collection", username=username))
    if user not in current_user.followed:
        current_user.followed.append(user)
        db.session.commit()
        flash(f"You followed {username}.", "success")
    return redirect(url_for("public_collection", username=username))

@app.route("/unfollow/<username>")
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash(f"User {username} not found.", "error")
        return redirect(url_for("landing"))
    if user in current_user.followed:
        current_user.followed.remove(user)
        db.session.commit()
        flash(f"You stopped following {username}.", "info")
    return redirect(url_for("public_collection", username=username))

@app.route("/import", methods=["GET", "POST"])
@login_required
def import_csv():
    if request.method == "POST":
        if 'csv_file' not in request.files:
            flash("No file part", "error")
            return redirect(request.url)
        file = request.files['csv_file']
        if file.filename == '':
            flash("No selected file", "error")
            return redirect(request.url)
        if file and file.filename.endswith('.csv'):
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_input = csv.DictReader(stream)
            count = 0
            for row in csv_input:
                title = row.get("Title") or row.get("Name")
                year = row.get("Year")
                if not title:
                    continue
                try:
                    params = {"api_key": TMDB_API_KEY, "query": title}
                    if year:
                        params["year"] = year
                    r = requests.get("https://api.themoviedb.org/3/search/movie", params=params, timeout=6)
                    data = r.json()
                    if data["results"]:
                        d = data["results"][0]
                        tmdb_id = d["id"]
                        
                        existing = Movie.query.filter_by(user_id=current_user.id, tmdb_id=str(tmdb_id)).first()
                        if not existing:
                            r2 = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}", params={"api_key": TMDB_API_KEY}, timeout=6)
                            d2 = r2.json()
                            genres = ", ".join([g["name"] for g in d2.get("genres", [])])
                            
                            rating_val = float(row.get("Rating", 0))
                            if rating_val <= 5.0 and rating_val > 0.0:
                                rating_val *= 2  # Convert letterboxd out-of-5 to out-of-10
                            
                            new_movie = Movie(
                                user_id=current_user.id,
                                tmdb_id=str(tmdb_id),
                                title=d2.get("title", "Unknown"),
                                year=(d2.get("release_date") or "")[:4],
                                rating=rating_val,
                                description=(d2.get("overview") or "")[:1000],
                                genre=genres,
                                img_url=f"https://image.tmdb.org/t/p/w500{d2.get('poster_path', '')}",
                                status="watched",
                                date_watched=date.today(),
                            )
                            db.session.add(new_movie)
                            count += 1
                except:
                    pass
            db.session.commit()
            flash(f"Successfully imported {count} movies!", "success")
            return redirect(url_for("collection"))
    return render_template("import.html")


@app.route("/feed")
@login_required
def feed():
    followed_users = current_user.followed.all()
    feed_items = []
    for u in followed_users:
        for m in u.movies:
            feed_items.append({"action": "added the movie", "item": m, "user": u, "date": m.date_added})
            if m.status == "watched" and m.date_watched:
                if m.rating and m.rating > 0:
                    feed_items.append({"action": f"watched and rated ⭐ {m.rating}", "item": m, "user": u, "date": m.date_watched})
                else:
                    feed_items.append({"action": "watched", "item": m, "user": u, "date": m.date_watched})
        for b in u.books:
            feed_items.append({"action": "added the book", "item": b, "user": u, "date": b.date_added})
            if b.status == "read" and b.date_read:
                if b.rating and b.rating > 0:
                    feed_items.append({"action": f"read and rated ⭐ {b.rating}", "item": b, "user": u, "date": b.date_read})
                else:
                    feed_items.append({"action": "read", "item": b, "user": u, "date": b.date_read})
    
    feed_items.sort(key=lambda x: x["date"] or date.min, reverse=True)
    return render_template("feed.html", feed_items=feed_items[:50])


@app.route("/view/movie/<int:item_id>")
def view_movie(item_id):
    movie = Movie.query.get_or_404(item_id)
    response = {}
    trailer_key = None
    cast = []
    director = None
    backdrop_url = movie.img_url

    if movie.tmdb_id:
        try:
            tmdb_url = f"https://api.themoviedb.org/3/movie/{movie.tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits,videos"
            r = requests.get(tmdb_url, timeout=3)
            if r.status_code == 200:
                response = r.json()
                if "videos" in response and "results" in response["videos"]:
                    for video in response["videos"]["results"]:
                        if video["type"] == "Trailer" and video["site"] == "YouTube":
                            trailer_key = video["key"]
                            break
                if "credits" in response and "cast" in response["credits"]:
                    cast = response["credits"]["cast"][:6]
                if "credits" in response and "crew" in response["credits"]:
                    for crew_member in response["credits"]["crew"]:
                        if crew_member["job"] == "Director":
                            director = crew_member["name"]
                            break
                backdrop_path = response.get("backdrop_path")
                if backdrop_path:
                    backdrop_url = f"https://image.tmdb.org/t/p/original{backdrop_path}"
        except Exception:
            pass

    return render_template("detail.html", item=movie, trailer_key=trailer_key, cast=cast, director=director, backdrop_url=backdrop_url, item_type="movie")

@app.route("/view/book/<int:item_id>")
def view_book(item_id):
    book = Book.query.get_or_404(item_id)
    return render_template("detail.html", item=book, trailer_key=None, cast=[], director=book.author, backdrop_url=book.img_url, item_type="book")

# =====================
# --- Core Routes ---
# =====================

@app.route("/")
def landing():
    return render_template("index.html")


@app.route("/dashboard")
@login_required
def dashboard():
    movies = Movie.query.filter_by(user_id=current_user.id).all()
    books = Book.query.filter_by(user_id=current_user.id).all()
    watched = [m for m in movies if m.status == "watched"]
    to_watch = [m for m in movies if m.status == "to_watch"]
    read_books = [b for b in books if b.status == "read"]
    to_read = [b for b in books if b.status == "to_read"]

    today = date.today()

    # --- Monthly stats (current month) ---
    movies_this_month = [m for m in watched if m.date_watched and
                         m.date_watched.month == today.month and m.date_watched.year == today.year]
    books_this_month = [b for b in read_books if b.date_read and
                        b.date_read.month == today.month and b.date_read.year == today.year]

    # --- Streak (consecutive days with activity) ---
    activity_dates = set()
    for m in watched:
        if m.date_watched:
            activity_dates.add(m.date_watched)
    for b in read_books:
        if b.date_read:
            activity_dates.add(b.date_read)
    streak = 0
    check_date = today
    while check_date in activity_dates:
        streak += 1
        check_date -= timedelta(days=1)

    # --- Recent activity ---
    all_items = []
    for m in movies:
        all_items.append({"type": "movie", "item": m, "date": m.date_added})
    for b in books:
        all_items.append({"type": "book", "item": b, "date": b.date_added})
    all_items.sort(key=lambda x: x["date"] or date.min, reverse=True)
    recent = all_items[:6]

    # --- Average rating (strictly exclude unrated items where rating is 0 or None) ---
    rated_movies = [m for m in watched if m.rating is not None and m.rating > 0]
    avg_movie_rating = round(sum(m.rating for m in rated_movies) / len(rated_movies), 1) if rated_movies else 0.0

    # --- Up Next queue (first 4 items from watchlist) ---
    up_next_movies = to_watch[:4]

    # --- Rating distribution (1 to 10 stars) ---
    rating_counts = {i: 0 for i in range(1, 11)}
    for m in rated_movies:
        r = int(round(m.rating))
        if 1 <= r <= 10:
            rating_counts[r] += 1
    max_rating_freq = max(rating_counts.values()) if any(rating_counts.values()) else 1

    return render_template("dashboard.html",
        watched_count=len(watched),
        to_watch_count=len(to_watch),
        read_count=len(read_books),
        to_read_count=len(to_read),
        movies_this_month=len(movies_this_month),
        books_this_month=len(books_this_month),
        recent=recent,
        avg_movie_rating=avg_movie_rating,
        streak=streak,
        up_next=up_next_movies,
        rating_counts=rating_counts,
        max_rating_freq=max_rating_freq
    )

@app.route("/analytics")
@login_required
def analytics():
    movies = current_user.movies
    books = current_user.books
    watched = [m for m in movies if m.status == "watched"]
    to_watch = [m for m in movies if m.status == "to_watch"]
    read_books = [b for b in books if b.status == "read"]
    
    today = date.today()

    # --- Weekly activity (last 7 days) ---
    week_labels = []
    week_movies = []
    week_books = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        week_labels.append(d.strftime("%a"))
        week_movies.append(sum(1 for m in watched if m.date_watched == d))
        week_books.append(sum(1 for b in read_books if b.date_read == d))

    # --- Monthly chart (this year) ---
    month_labels = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    month_movies = [0]*12
    month_books = [0]*12
    for m in watched:
        if m.date_watched and m.date_watched.year == today.year:
            month_movies[m.date_watched.month - 1] += 1
    for b in read_books:
        if b.date_read and b.date_read.year == today.year:
            month_books[b.date_read.month - 1] += 1

    # --- Genre breakdown ---
    genre_counts = Counter()
    for m in watched:
        if m.genre:
            for g in m.genre.split(","):
                genre_counts[g.strip()] += 1
    for b in read_books:
        if b.genre:
            for g in b.genre.split(","):
                genre_counts[g.strip()] += 1
    top_genres = genre_counts.most_common(6)

    # --- Completion rate ---
    total_movies = len(movies)
    completion_pct = round(len(watched) / total_movies * 100) if total_movies else 0

    week_max = max((week_movies[i] + week_books[i] for i in range(7)), default=0) or 1
    month_max = max((month_movies[i] + month_books[i] for i in range(12)), default=0) or 1
    
    # --- Advanced Analytics ---
    rating_counts = [0] * 10
    for item in watched + read_books:
        r = item.rating
        if r and r > 0:
            idx = min(int(r) - 1, 9)
            rating_counts[idx] += 1
            
    era_counts = Counter()
    for item in watched + read_books:
        year = item.year
        if year and year.isdigit():
            decade = (int(year) // 10) * 10
            if decade > 1900:
                era_counts[f"{decade}s"] += 1
    era_labels = list(era_counts.keys())
    era_data = list(era_counts.values())
    
    rated_items = [x for x in (watched + read_books) if x.rating is not None and x.rating > 0]
    top_items = sorted(rated_items, key=lambda x: x.rating, reverse=True)[:5]

    return render_template("analytics.html",
        watched_count=len(watched),
        to_watch_count=len(to_watch),
        week_labels=week_labels,
        week_movies=week_movies,
        week_books=week_books,
        week_max=week_max,
        month_labels=month_labels,
        month_movies=month_movies,
        month_books=month_books,
        month_max=month_max,
        top_genres=top_genres,
        completion_pct=completion_pct,
        rating_counts=rating_counts,
        era_labels=era_labels,
        era_data=era_data,
        top_items=top_items
    )


@app.route("/collection")
@login_required
def collection():
    tab = request.args.get("tab", "movies")
    status = request.args.get("status", "all")
    sort = request.args.get("sort", "newest")
    tag_filter = request.args.get("tag")
    media_type_filter = request.args.get("media_type")
    book_category_filter = request.args.get("category") or (request.args.get("media_type") if tab == "books" else None) or (request.args.get("type") if tab == "books" else None)

    movie_q = Movie.query.filter_by(user_id=current_user.id)
    book_q = Book.query.filter_by(user_id=current_user.id)

    if status == "watched":
        movie_q = movie_q.filter_by(status="watched")
    elif status == "to_watch":
        movie_q = movie_q.filter_by(status="to_watch")
    if status == "read":
        book_q = book_q.filter_by(status="read")
    elif status == "to_read":
        book_q = book_q.filter_by(status="to_read")

    if media_type_filter and media_type_filter != "all":
        movie_q = movie_q.filter_by(media_type=media_type_filter)

    if book_category_filter and book_category_filter != "all":
        book_q = book_q.filter_by(category=book_category_filter)

    if sort == "rating":
        movie_q = movie_q.order_by(Movie.rating.desc())
        book_q = book_q.order_by(Book.rating.desc())
    elif sort == "title":
        movie_q = movie_q.order_by(Movie.title)
        book_q = book_q.order_by(Book.title)
    else:  # newest
        movie_q = movie_q.order_by(Movie.date_added.desc())
        book_q = book_q.order_by(Book.date_added.desc())

    movies = movie_q.all()
    books = book_q.all()

    # Counts for collection summary and filter badges
    watched_count = Movie.query.filter_by(user_id=current_user.id, status="watched").count()
    to_watch_count = Movie.query.filter_by(user_id=current_user.id, status="to_watch").count()
    total_movies_count = watched_count + to_watch_count

    read_count = Book.query.filter_by(user_id=current_user.id, status="read").count()
    to_read_count = Book.query.filter_by(user_id=current_user.id, status="to_read").count()
    total_books_count = read_count + to_read_count

    # Media type counts with watched/total breakdown (from full collection)
    movie_type_counts = {
        "movie": {
            "total": Movie.query.filter_by(user_id=current_user.id, media_type="movie").count(),
            "watched": Movie.query.filter_by(user_id=current_user.id, media_type="movie", status="watched").count(),
            "to_watch": Movie.query.filter_by(user_id=current_user.id, media_type="movie", status="to_watch").count(),
        },
        "series": {
            "total": Movie.query.filter_by(user_id=current_user.id, media_type="series").count(),
            "watched": Movie.query.filter_by(user_id=current_user.id, media_type="series", status="watched").count(),
            "to_watch": Movie.query.filter_by(user_id=current_user.id, media_type="series", status="to_watch").count(),
        },
        "animation": {
            "total": Movie.query.filter_by(user_id=current_user.id, media_type="animation").count(),
            "watched": Movie.query.filter_by(user_id=current_user.id, media_type="animation", status="watched").count(),
            "to_watch": Movie.query.filter_by(user_id=current_user.id, media_type="animation", status="to_watch").count(),
        },
        "anime": {
            "total": Movie.query.filter_by(user_id=current_user.id, media_type="anime").count(),
            "watched": Movie.query.filter_by(user_id=current_user.id, media_type="anime", status="watched").count(),
            "to_watch": Movie.query.filter_by(user_id=current_user.id, media_type="anime", status="to_watch").count(),
        },
    }

    # Book category counts with read/total breakdown (from full collection)
    book_category_counts = {
        "fiction": {
            "label": "Fiction & Literature",
            "emoji": "📖",
            "total": Book.query.filter_by(user_id=current_user.id, category="fiction").count(),
            "read": Book.query.filter_by(user_id=current_user.id, category="fiction", status="read").count(),
            "to_read": Book.query.filter_by(user_id=current_user.id, category="fiction", status="to_read").count(),
        },
        "philosophy": {
            "label": "Philosophy",
            "emoji": "🧠",
            "total": Book.query.filter_by(user_id=current_user.id, category="philosophy").count(),
            "read": Book.query.filter_by(user_id=current_user.id, category="philosophy", status="read").count(),
            "to_read": Book.query.filter_by(user_id=current_user.id, category="philosophy", status="to_read").count(),
        },
        "self_help": {
            "label": "Self-Help",
            "emoji": "🌱",
            "total": Book.query.filter_by(user_id=current_user.id, category="self_help").count(),
            "read": Book.query.filter_by(user_id=current_user.id, category="self_help", status="read").count(),
            "to_read": Book.query.filter_by(user_id=current_user.id, category="self_help", status="to_read").count(),
        },
        "business": {
            "label": "Business & Finance",
            "emoji": "💼",
            "total": Book.query.filter_by(user_id=current_user.id, category="business").count(),
            "read": Book.query.filter_by(user_id=current_user.id, category="business", status="read").count(),
            "to_read": Book.query.filter_by(user_id=current_user.id, category="business", status="to_read").count(),
        },
        "non_fiction": {
            "label": "Non-Fiction",
            "emoji": "🌍",
            "total": Book.query.filter_by(user_id=current_user.id, category="non_fiction").count(),
            "read": Book.query.filter_by(user_id=current_user.id, category="non_fiction", status="read").count(),
            "to_read": Book.query.filter_by(user_id=current_user.id, category="non_fiction", status="to_read").count(),
        },
    }

    # Tag Processing
    all_tags = set()
    for m in movies:
        if m.custom_tags:
            all_tags.update([t.strip() for t in m.custom_tags.split(",") if t.strip()])
    for b in books:
        if b.custom_tags:
            all_tags.update([t.strip() for t in b.custom_tags.split(",") if t.strip()])
    all_tags = sorted(list(all_tags))

    if tag_filter:
        movies = [m for m in movies if m.custom_tags and tag_filter in [t.strip() for t in m.custom_tags.split(",")]]
        books = [b for b in books if b.custom_tags and tag_filter in [t.strip() for t in b.custom_tags.split(",")]]

    return render_template("collection.html", movies=movies, books=books,
                           tab=tab, status=status, sort=sort, all_tags=all_tags, current_tag=tag_filter,
                           watched_count=watched_count, to_watch_count=to_watch_count, total_movies_count=total_movies_count,
                           read_count=read_count, to_read_count=to_read_count, total_books_count=total_books_count,
                           movie_type_counts=movie_type_counts, current_media_type=media_type_filter,
                           book_category_counts=book_category_counts, current_book_category=book_category_filter)

@app.route("/u/<username>")
def public_collection(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("landing"))
        
    tab = request.args.get("tab", "movies")
    status = request.args.get("status", "all")
    sort = request.args.get("sort", "newest")
    media_type_filter = request.args.get("media_type")
    book_category_filter = request.args.get("category") or (request.args.get("media_type") if tab == "books" else None) or (request.args.get("type") if tab == "books" else None)

    movie_q = Movie.query.filter_by(user_id=user.id)
    book_q = Book.query.filter_by(user_id=user.id)

    if status == "watched":
        movie_q = movie_q.filter_by(status="watched")
    elif status == "to_watch":
        movie_q = movie_q.filter_by(status="to_watch")
    if status == "read":
        book_q = book_q.filter_by(status="read")
    elif status == "to_read":
        book_q = book_q.filter_by(status="to_read")

    if media_type_filter and media_type_filter != "all":
        movie_q = movie_q.filter_by(media_type=media_type_filter)

    if book_category_filter and book_category_filter != "all":
        book_q = book_q.filter_by(category=book_category_filter)

    if sort == "rating":
        movie_q = movie_q.order_by(Movie.rating.desc())
        book_q = book_q.order_by(Book.rating.desc())
    elif sort == "title":
        movie_q = movie_q.order_by(Movie.title)
        book_q = book_q.order_by(Book.title)
    else:  # newest
        movie_q = movie_q.order_by(Movie.date_added.desc())
        book_q = book_q.order_by(Book.date_added.desc())

    movies = movie_q.all()
    books = book_q.all()
    
    watched_count = Movie.query.filter_by(user_id=user.id, status="watched").count()
    to_watch_count = Movie.query.filter_by(user_id=user.id, status="to_watch").count()
    total_movies_count = watched_count + to_watch_count

    read_count = Book.query.filter_by(user_id=user.id, status="read").count()
    to_read_count = Book.query.filter_by(user_id=user.id, status="to_read").count()
    total_books_count = read_count + to_read_count

    movie_type_counts = {
        "movie": {
            "total": Movie.query.filter_by(user_id=user.id, media_type="movie").count(),
            "watched": Movie.query.filter_by(user_id=user.id, media_type="movie", status="watched").count(),
            "to_watch": Movie.query.filter_by(user_id=user.id, media_type="movie", status="to_watch").count(),
        },
        "series": {
            "total": Movie.query.filter_by(user_id=user.id, media_type="series").count(),
            "watched": Movie.query.filter_by(user_id=user.id, media_type="series", status="watched").count(),
            "to_watch": Movie.query.filter_by(user_id=user.id, media_type="series", status="to_watch").count(),
        },
        "animation": {
            "total": Movie.query.filter_by(user_id=user.id, media_type="animation").count(),
            "watched": Movie.query.filter_by(user_id=user.id, media_type="animation", status="watched").count(),
            "to_watch": Movie.query.filter_by(user_id=user.id, media_type="animation", status="to_watch").count(),
        },
        "anime": {
            "total": Movie.query.filter_by(user_id=user.id, media_type="anime").count(),
            "watched": Movie.query.filter_by(user_id=user.id, media_type="anime", status="watched").count(),
            "to_watch": Movie.query.filter_by(user_id=user.id, media_type="anime", status="to_watch").count(),
        },
    }

    book_category_counts = {
        "fiction": {
            "label": "Fiction & Literature",
            "emoji": "📖",
            "total": Book.query.filter_by(user_id=user.id, category="fiction").count(),
            "read": Book.query.filter_by(user_id=user.id, category="fiction", status="read").count(),
            "to_read": Book.query.filter_by(user_id=user.id, category="fiction", status="to_read").count(),
        },
        "philosophy": {
            "label": "Philosophy",
            "emoji": "🧠",
            "total": Book.query.filter_by(user_id=user.id, category="philosophy").count(),
            "read": Book.query.filter_by(user_id=user.id, category="philosophy", status="read").count(),
            "to_read": Book.query.filter_by(user_id=user.id, category="philosophy", status="to_read").count(),
        },
        "self_help": {
            "label": "Self-Help",
            "emoji": "🌱",
            "total": Book.query.filter_by(user_id=user.id, category="self_help").count(),
            "read": Book.query.filter_by(user_id=user.id, category="self_help", status="read").count(),
            "to_read": Book.query.filter_by(user_id=user.id, category="self_help", status="to_read").count(),
        },
        "business": {
            "label": "Business & Finance",
            "emoji": "💼",
            "total": Book.query.filter_by(user_id=user.id, category="business").count(),
            "read": Book.query.filter_by(user_id=user.id, category="business", status="read").count(),
            "to_read": Book.query.filter_by(user_id=user.id, category="business", status="to_read").count(),
        },
        "non_fiction": {
            "label": "Non-Fiction",
            "emoji": "🌍",
            "total": Book.query.filter_by(user_id=user.id, category="non_fiction").count(),
            "read": Book.query.filter_by(user_id=user.id, category="non_fiction", status="read").count(),
            "to_read": Book.query.filter_by(user_id=user.id, category="non_fiction", status="to_read").count(),
        },
    }

    return render_template("public_collection.html", 
                           profile_user=user, 
                           movies=movies, books=books,
                           tab=tab, status=status, sort=sort,
                           watched_count=watched_count, to_watch_count=to_watch_count, total_movies_count=total_movies_count,
                           read_count=read_count, to_read_count=to_read_count, total_books_count=total_books_count,
                           movie_type_counts=movie_type_counts, current_media_type=media_type_filter,
                           book_category_counts=book_category_counts, current_book_category=book_category_filter)



# =====================
# --- Discover (Personalized + Filtered) ---
# =====================

CURATED_BOOKS = [
    {
        "google_id": "OL17930368W",
        "title": "Atomic Habits",
        "author": "James Clear",
        "year": "2018",
        "genre": "Self-Help, Psychology, Productivity",
        "img_url": "https://covers.openlibrary.org/b/id/12539702-M.jpg",
        "overview": "No matter your goals, Atomic Habits offers a proven framework for improving every day. James Clear reveals practical strategies to form good habits and break bad ones."
    },
    {
        "google_id": "OL17364145W",
        "title": "The Subtle Art of Not Giving a F*ck",
        "author": "Mark Manson",
        "year": "2016",
        "genre": "Self-Help, Philosophy",
        "img_url": "https://covers.openlibrary.org/b/id/8231990-M.jpg",
        "overview": "A generation-defining self-help guide that shows how to stop trying to be 'positive' all the time and instead become better at handling adversity."
    },
    {
        "google_id": "OL27178342W",
        "title": "The Courage to Be Disliked",
        "author": "Ichiro Kishimi, Fumitake Koga",
        "year": "2013",
        "genre": "Philosophy, Psychology, Self-Help",
        "img_url": "https://covers.openlibrary.org/b/id/10543210-M.jpg",
        "overview": "The Japanese phenomenon demonstrating how to free yourself, change your life, and achieve real happiness through the philosophy of Alfred Adler."
    },
    {
        "google_id": "OL17860775W",
        "title": "Deep Work",
        "author": "Cal Newport",
        "year": "2016",
        "genre": "Self-Help, Productivity, Business",
        "img_url": "https://covers.openlibrary.org/b/id/8235111-M.jpg",
        "overview": "Deep work is the ability to focus without distraction on a demanding cognitive task. A guide for focused success in a distracted world."
    },
    {
        "google_id": "OL20862660W",
        "title": "The Psychology of Money",
        "author": "Morgan Housel",
        "year": "2020",
        "genre": "Finance, Psychology, Business",
        "img_url": "https://covers.openlibrary.org/b/id/10574768-M.jpg",
        "overview": "Doing well with money isn't just about what you know—it's about how you behave. Timeless lessons on wealth, greed, and happiness."
    },
    {
        "google_id": "OL61565W",
        "title": "Meditations",
        "author": "Marcus Aurelius",
        "year": "2002",
        "genre": "Philosophy, Stoicism, Classics",
        "img_url": "https://covers.openlibrary.org/b/id/8774136-M.jpg",
        "overview": "The personal writings of the Roman Emperor Marcus Aurelius, recording private reflections on Stoic philosophy, duty, and life."
    },
    {
        "google_id": "OL24198165W",
        "title": "Man's Search for Meaning",
        "author": "Viktor E. Frankl",
        "year": "1946",
        "genre": "Psychology, Philosophy, Memoir",
        "img_url": "https://covers.openlibrary.org/b/id/8231856-M.jpg",
        "overview": "Psychiatrist Viktor Frankl explores his experiences in concentration camps and the fundamental human drive to find purpose and meaning."
    },
    {
        "google_id": "OL15849841W",
        "title": "Thinking, Fast and Slow",
        "author": "Daniel Kahneman",
        "year": "2011",
        "genre": "Psychology, Behavioral Economics, Science",
        "img_url": "https://covers.openlibrary.org/b/id/7266155-M.jpg",
        "overview": "Nobel laureate Daniel Kahneman takes us on a groundbreaking tour of the mind, explaining the two systems that drive how we think and decide."
    },
    {
        "google_id": "OL331168W",
        "title": "The 48 Laws of Power",
        "author": "Robert Greene",
        "year": "1998",
        "genre": "Philosophy, Psychology, Strategy",
        "img_url": "https://covers.openlibrary.org/b/id/6424160-M.jpg",
        "overview": "Amoral, cunning, and instructive—a synthesis of three thousand years of history distilled into forty-eight essential laws of power."
    },
    {
        "google_id": "OL27178343W",
        "title": "The Alchemist",
        "author": "Paulo Coelho",
        "year": "1988",
        "genre": "Fiction, Fantasy, Philosophy",
        "img_url": "https://covers.openlibrary.org/b/id/8231992-M.jpg",
        "overview": "The enchanting story of Santiago, an Andalusian shepherd boy who journeys across the desert in pursuit of his personal legend."
    },
    {
        "google_id": "OL20862661W",
        "title": "The Midnight Library",
        "author": "Matt Haig",
        "year": "2020",
        "genre": "Fiction, Fantasy, Magical Realism",
        "img_url": "https://covers.openlibrary.org/b/id/10313767-M.jpg",
        "overview": "Between life and death stands a library with infinite books—each one an opportunity to live out a different path you could have taken."
    },
    {
        "google_id": "OL1168007W",
        "title": "1984",
        "author": "George Orwell",
        "year": "1949",
        "genre": "Fiction, Dystopian, Classics",
        "img_url": "https://covers.openlibrary.org/b/id/7222246-M.jpg",
        "overview": "A dystopian masterpiece exploring ubiquitous surveillance, truth manipulation, and individual liberty in a totalitarian world."
    },
    {
        "google_id": "OL3298910W",
        "title": "To Kill a Mockingbird",
        "author": "Harper Lee",
        "year": "1960",
        "genre": "Fiction, Classics, Literature",
        "img_url": "https://covers.openlibrary.org/b/id/8226191-M.jpg",
        "overview": "A compassionate and deeply moving story of innocence, moral growth, and empathy amidst racial injustice in the American South."
    },
    {
        "google_id": "OL123456W",
        "title": "Dune",
        "author": "Frank Herbert",
        "year": "1965",
        "genre": "Sci-Fi, Fantasy, Classics",
        "img_url": "https://covers.openlibrary.org/b/id/8235123-M.jpg",
        "overview": "Set on the desert planet Arrakis, Dune is the grand epic of young Paul Atreides, destiny, ecology, and planetary power."
    },
    {
        "google_id": "OL24198166W",
        "title": "Project Hail Mary",
        "author": "Andy Weir",
        "year": "2021",
        "genre": "Sci-Fi, Space, Adventure",
        "img_url": "https://covers.openlibrary.org/b/id/10543211-M.jpg",
        "overview": "A lone astronaut awakens with amnesia on a desperate last-chance interstellar mission to save humanity from impending extinction."
    },
    {
        "google_id": "OL17364146W",
        "title": "Sapiens: A Brief History of Humankind",
        "author": "Yuval Noah Harari",
        "year": "2014",
        "genre": "History, Science, Anthropology",
        "img_url": "https://covers.openlibrary.org/b/id/8231991-M.jpg",
        "overview": "A provocative narrative tracing the evolutionary history of Homo sapiens from the Stone Age to modern global society."
    },
    {
        "google_id": "OL8315603W",
        "title": "Rich Dad Poor Dad",
        "author": "Robert T. Kiyosaki",
        "year": "1997",
        "genre": "Finance, Personal Growth, Business",
        "img_url": "https://covers.openlibrary.org/b/id/8315603-M.jpg",
        "overview": "What the rich teach their kids about money that the poor and middle class do not—an iconic guide on financial independence."
    },
    {
        "google_id": "OL19747970W",
        "title": "Can't Hurt Me",
        "author": "David Goggins",
        "year": "2018",
        "genre": "Biography, Self-Help, Motivation",
        "img_url": "https://covers.openlibrary.org/b/id/8739161-M.jpg",
        "overview": "The remarkable story of how mental toughness, disciplined habits, and self-belief turned hardship into legendary achievement."
    },
    {
        "google_id": "OL1234567W",
        "title": "The Great Gatsby",
        "author": "F. Scott Fitzgerald",
        "year": "1925",
        "genre": "Fiction, Classics, Literature",
        "img_url": "https://covers.openlibrary.org/b/id/7222161-M.jpg",
        "overview": "The evocative story of Jay Gatsby's pursuit of love and wealth on Long Island during the glittering roaring twenties."
    },
    {
        "google_id": "OL151817W",
        "title": "Beyond Good and Evil",
        "author": "Friedrich Nietzsche",
        "year": "1886",
        "genre": "Philosophy, Classics",
        "img_url": "https://covers.openlibrary.org/b/id/8235222-M.jpg",
        "overview": "Nietzsche's incisive philosophical critique dissecting conventional morality, dogmatism, and the will to power."
    }
]

MOVIE_GENRE_CATEGORIES = {
    "scifi_fantasy": [878, 14],            # Science Fiction, Fantasy
    "action_adventure": [28, 12],          # Action, Adventure
    "crime_thriller_mystery": [80, 53, 9648], # Crime, Thriller, Mystery
    "animation_family": [16, 10751],       # Animation, Family
    "drama_romance": [18, 10749],          # Drama, Romance
    "comedy": [35],                        # Comedy
}

BOOK_BUCKETS = {
    "philosophy": ["philosophy", "stoicism", "wisdom", "ethics", "mind", "morality"],
    "fiction_scifi": ["fiction", "fantasy", "sci-fi", "dystopian", "classics", "literature", "adventure", "magical"],
    "self_help": ["self-help", "habits", "productivity", "growth", "motivation", "success", "happiness", "discipline"],
    "psychology_finance": ["psychology", "finance", "money", "business", "strategy", "economics", "history", "biography"],
}

def _get_user_collection_ids():
    movie_tmdb_ids = {m.tmdb_id for m in Movie.query.filter_by(user_id=current_user.id).all() if m.tmdb_id}
    book_google_ids = {b.google_id for b in Book.query.filter_by(user_id=current_user.id).all() if b.google_id}
    return movie_tmdb_ids, book_google_ids


def detect_media_type(d, explicit_type=None):
    if explicit_type in ["movie", "series", "animation", "anime"]:
        return explicit_type
    
    genres_raw = d.get("genres", [])
    if isinstance(genres_raw, list):
        genres_names = [g.get("name", "") if isinstance(g, dict) else str(g) for g in genres_raw]
    else:
        genres_names = [str(genres_raw)]
    genres_str = " ".join(genres_names).lower()
    
    orig_lang = (d.get("original_language") or "").lower()
    title_str = (d.get("title") or d.get("name") or "").lower()
    overview_str = (d.get("overview") or "").lower()
    
    is_animation = "animation" in genres_str
    anime_keywords = ["anime", "solo leveling", "my hero academia", "one piece", "attack on titan", "detective conan", "spirited away", "naruto", "bleach", "demon slayer", "dragon ball", "jujutsu"]
    is_anime = is_animation and (orig_lang == "ja" or any(k in overview_str or k in title_str for k in anime_keywords))
    is_tv = "first_air_date" in d or d.get("media_type") == "tv"
    
    if is_anime:
        return "anime"
    elif is_animation:
        return "animation"
    elif is_tv:
        return "series"
    else:
        return "movie"


def get_diverse_movie_recommendations(user_movies, movie_in_collection, page=1, category="all"):
    import random
    if not user_movies:
        return []

    seen_ids = set(movie_in_collection)
    results = []

    if category == "series":
        try:
            params = {
                "api_key": TMDB_API_KEY,
                "sort_by": "popularity.desc",
                "vote_count.gte": 80,
                "page": page
            }
            r = requests.get("https://api.themoviedb.org/3/discover/tv", params=params, timeout=5)
            for item in r.json().get("results", []):
                tid = str(item["id"])
                if tid in seen_ids:
                    continue
                if item.get("poster_path"):
                    seen_ids.add(tid)
                    results.append({
                        "tmdb_id": tid,
                        "title": item.get("name") or item.get("original_name") or "",
                        "year": (item.get("first_air_date") or "")[:4],
                        "img_url": f"https://image.tmdb.org/t/p/w300{item['poster_path']}",
                        "rating": round(item.get("vote_average", 0), 1),
                        "overview": (item.get("overview") or "")[:200],
                        "media_type": "series"
                    })
                if len(results) >= 12:
                    break
        except Exception:
            pass
        return results

    elif category == "anime":
        try:
            params = {
                "api_key": TMDB_API_KEY,
                "with_genres": "16",
                "with_original_language": "ja",
                "sort_by": "popularity.desc",
                "vote_count.gte": 30,
                "page": page
            }
            r = requests.get("https://api.themoviedb.org/3/discover/movie", params=params, timeout=5)
            for item in r.json().get("results", []):
                tid = str(item["id"])
                if tid in seen_ids:
                    continue
                if item.get("poster_path"):
                    seen_ids.add(tid)
                    results.append({
                        "tmdb_id": tid,
                        "title": item.get("title", ""),
                        "year": (item.get("release_date") or "")[:4],
                        "img_url": f"https://image.tmdb.org/t/p/w300{item['poster_path']}",
                        "rating": round(item.get("vote_average", 0), 1),
                        "overview": (item.get("overview") or "")[:200],
                        "media_type": "anime"
                    })
                if len(results) >= 12:
                    break
        except Exception:
            pass
        return results

    elif category == "animation":
        try:
            params = {
                "api_key": TMDB_API_KEY,
                "with_genres": "16",
                "without_original_language": "ja",
                "sort_by": "popularity.desc",
                "vote_count.gte": 80,
                "page": page
            }
            r = requests.get("https://api.themoviedb.org/3/discover/movie", params=params, timeout=5)
            for item in r.json().get("results", []):
                tid = str(item["id"])
                if tid in seen_ids:
                    continue
                if item.get("poster_path"):
                    seen_ids.add(tid)
                    results.append({
                        "tmdb_id": tid,
                        "title": item.get("title", ""),
                        "year": (item.get("release_date") or "")[:4],
                        "img_url": f"https://image.tmdb.org/t/p/w300{item['poster_path']}",
                        "rating": round(item.get("vote_average", 0), 1),
                        "overview": (item.get("overview") or "")[:200],
                        "media_type": "animation"
                    })
                if len(results) >= 12:
                    break
        except Exception:
            pass
        return results

    elif category == "movie":
        # Feature movies, excluding animation
        active_categories = set()
        for m in user_movies:
            if m.media_type != "movie" and m.media_type:
                continue
            mg = (m.genre or "").lower()
            if any(term in mg for term in ["science fiction", "sci-fi", "fantasy"]):
                active_categories.add("scifi_fantasy")
            if any(term in mg for term in ["action", "adventure"]):
                active_categories.add("action_adventure")
            if any(term in mg for term in ["crime", "thriller", "mystery"]):
                active_categories.add("crime_thriller_mystery")
            if any(term in mg for term in ["drama", "romance"]):
                active_categories.add("drama_romance")
            if "comedy" in mg:
                active_categories.add("comedy")
        if not active_categories:
            active_categories = {"scifi_fantasy", "action_adventure", "crime_thriller_mystery"}

        active_cat_list = list(active_categories)
        rng = random.Random(page * 7919)
        rng.shuffle(active_cat_list)
        category_results = {}
        for cat_key in active_cat_list:
            gids = MOVIE_GENRE_CATEGORIES.get(cat_key, [28])
            gid_str = "|".join(str(g) for g in gids)
            try:
                params = {
                    "api_key": TMDB_API_KEY,
                    "with_genres": gid_str,
                    "without_genres": "16",
                    "sort_by": "popularity.desc",
                    "vote_count.gte": 150,
                    "page": page
                }
                r = requests.get("https://api.themoviedb.org/3/discover/movie", params=params, timeout=5)
                cat_movies = []
                for item in r.json().get("results", []):
                    tid = str(item["id"])
                    if tid in seen_ids:
                        continue
                    if item.get("poster_path"):
                        seen_ids.add(tid)
                        cat_movies.append({
                            "tmdb_id": tid,
                            "title": item.get("title", ""),
                            "year": (item.get("release_date") or "")[:4],
                            "img_url": f"https://image.tmdb.org/t/p/w300{item['poster_path']}",
                            "rating": round(item.get("vote_average", 0), 1),
                            "overview": (item.get("overview") or "")[:200],
                            "media_type": "movie"
                        })
                    if len(cat_movies) >= 6:
                        break
                category_results[cat_key] = cat_movies
            except Exception:
                category_results[cat_key] = []
        blended = []
        max_count = max((len(lst) for lst in category_results.values()), default=0)
        for i in range(max_count):
            for cat_key in active_cat_list:
                lst = category_results.get(cat_key, [])
                if i < len(lst) and len(blended) < 12:
                    blended.append(lst[i])
        return blended

    else:
        # category == "all": blended across genres
        active_categories = set()
        for m in user_movies:
            mg = (m.genre or "").lower()
            if any(term in mg for term in ["science fiction", "sci-fi", "fantasy"]):
                active_categories.add("scifi_fantasy")
            if any(term in mg for term in ["action", "adventure"]):
                active_categories.add("action_adventure")
            if any(term in mg for term in ["crime", "thriller", "mystery"]):
                active_categories.add("crime_thriller_mystery")
            if any(term in mg for term in ["animation", "family"]):
                active_categories.add("animation_family")
            if any(term in mg for term in ["drama", "romance"]):
                active_categories.add("drama_romance")
            if "comedy" in mg:
                active_categories.add("comedy")

        if not active_categories:
            active_categories = {"scifi_fantasy", "action_adventure", "crime_thriller_mystery", "animation_family"}

        active_cat_list = list(active_categories)
        rng = random.Random(page * 7919)
        rng.shuffle(active_cat_list)

        category_results = {}
        for cat_key in active_cat_list:
            gids = MOVIE_GENRE_CATEGORIES.get(cat_key, [28])
            gid_str = "|".join(str(g) for g in gids)
            try:
                params = {
                    "api_key": TMDB_API_KEY,
                    "with_genres": gid_str,
                    "sort_by": "popularity.desc",
                    "vote_count.gte": 150,
                    "page": page
                }
                r = requests.get("https://api.themoviedb.org/3/discover/movie", params=params, timeout=5)
                cat_movies = []
                for item in r.json().get("results", []):
                    tid = str(item["id"])
                    if tid in seen_ids:
                        continue
                    if item.get("poster_path"):
                        seen_ids.add(tid)
                        m_type = "animation" if cat_key == "animation_family" else "movie"
                        cat_movies.append({
                            "tmdb_id": tid,
                            "title": item.get("title", ""),
                            "year": (item.get("release_date") or "")[:4],
                            "img_url": f"https://image.tmdb.org/t/p/w300{item['poster_path']}",
                            "rating": round(item.get("vote_average", 0), 1),
                            "overview": (item.get("overview") or "")[:200],
                            "media_type": m_type
                        })
                    if len(cat_movies) >= 6:
                        break
                category_results[cat_key] = cat_movies
            except Exception:
                category_results[cat_key] = []

        blended = []
        max_count = max((len(lst) for lst in category_results.values()), default=0)
        for i in range(max_count):
            for cat_key in active_cat_list:
                lst = category_results.get(cat_key, [])
                if i < len(lst) and len(blended) < 12:
                    blended.append(lst[i])

        return blended


def get_trending_movies(movie_in_collection, page=1, category="all"):
    trending = []
    seen_ids = set(movie_in_collection)
    try:
        if category == "series":
            params = {"api_key": TMDB_API_KEY, "sort_by": "popularity.desc", "page": page}
            r = requests.get("https://api.themoviedb.org/3/discover/tv", params=params, timeout=5)
            for item in r.json().get("results", []):
                tid = str(item["id"])
                if tid in seen_ids:
                    continue
                if item.get("poster_path"):
                    seen_ids.add(tid)
                    trending.append({
                        "tmdb_id": tid,
                        "title": item.get("name") or item.get("original_name") or "",
                        "year": (item.get("first_air_date") or "")[:4],
                        "img_url": f"https://image.tmdb.org/t/p/w300{item['poster_path']}",
                        "rating": round(item.get("vote_average", 0), 1),
                        "overview": (item.get("overview") or "")[:200],
                        "media_type": "series"
                    })
                if len(trending) >= 12:
                    break
        elif category == "anime":
            params = {"api_key": TMDB_API_KEY, "with_genres": "16", "with_original_language": "ja", "sort_by": "popularity.desc", "page": page}
            r = requests.get("https://api.themoviedb.org/3/discover/movie", params=params, timeout=5)
            for item in r.json().get("results", []):
                tid = str(item["id"])
                if tid in seen_ids:
                    continue
                if item.get("poster_path"):
                    seen_ids.add(tid)
                    trending.append({
                        "tmdb_id": tid,
                        "title": item.get("title", ""),
                        "year": (item.get("release_date") or "")[:4],
                        "img_url": f"https://image.tmdb.org/t/p/w300{item['poster_path']}",
                        "rating": round(item.get("vote_average", 0), 1),
                        "overview": (item.get("overview") or "")[:200],
                        "media_type": "anime"
                    })
                if len(trending) >= 12:
                    break
        elif category == "animation":
            params = {"api_key": TMDB_API_KEY, "with_genres": "16", "without_original_language": "ja", "sort_by": "popularity.desc", "page": page}
            r = requests.get("https://api.themoviedb.org/3/discover/movie", params=params, timeout=5)
            for item in r.json().get("results", []):
                tid = str(item["id"])
                if tid in seen_ids:
                    continue
                if item.get("poster_path"):
                    seen_ids.add(tid)
                    trending.append({
                        "tmdb_id": tid,
                        "title": item.get("title", ""),
                        "year": (item.get("release_date") or "")[:4],
                        "img_url": f"https://image.tmdb.org/t/p/w300{item['poster_path']}",
                        "rating": round(item.get("vote_average", 0), 1),
                        "overview": (item.get("overview") or "")[:200],
                        "media_type": "animation"
                    })
                if len(trending) >= 12:
                    break
        elif category == "movie":
            params = {"api_key": TMDB_API_KEY, "without_genres": "16", "sort_by": "popularity.desc", "page": page}
            r = requests.get("https://api.themoviedb.org/3/discover/movie", params=params, timeout=5)
            for item in r.json().get("results", []):
                tid = str(item["id"])
                if tid in seen_ids:
                    continue
                if item.get("poster_path"):
                    seen_ids.add(tid)
                    trending.append({
                        "tmdb_id": tid,
                        "title": item.get("title", ""),
                        "year": (item.get("release_date") or "")[:4],
                        "img_url": f"https://image.tmdb.org/t/p/w300{item['poster_path']}",
                        "rating": round(item.get("vote_average", 0), 1),
                        "overview": (item.get("overview") or "")[:200],
                        "media_type": "movie"
                    })
                if len(trending) >= 12:
                    break
        else:
            params = {"api_key": TMDB_API_KEY, "sort_by": "popularity.desc", "page": page}
            r = requests.get("https://api.themoviedb.org/3/discover/movie", params=params, timeout=5)
            for item in r.json().get("results", []):
                tid = str(item["id"])
                if tid in seen_ids:
                    continue
                if item.get("poster_path"):
                    seen_ids.add(tid)
                    trending.append({
                        "tmdb_id": tid,
                        "title": item.get("title", ""),
                        "year": (item.get("release_date") or "")[:4],
                        "img_url": f"https://image.tmdb.org/t/p/w300{item['poster_path']}",
                        "rating": round(item.get("vote_average", 0), 1),
                        "overview": (item.get("overview") or "")[:200],
                        "media_type": "movie"
                    })
                if len(trending) >= 12:
                    break
    except Exception:
        pass
    return trending


def get_diverse_book_recommendations(user_books, book_in_collection, book_titles_in_collection, seed=0, category="all"):
    import random
    if not user_books:
        return []

    rng = random.Random(seed) if seed else random.Random()

    if category and category != "all":
        matching = []
        for b in CURATED_BOOKS:
            title_clean = b["title"].lower().strip()
            if title_clean in book_titles_in_collection or b["google_id"] in book_in_collection:
                continue
            cat = b.get("category") or detect_book_category(b["title"], b["genre"], b["overview"])
            if cat == category:
                matching.append(b)
        rng.shuffle(matching)
        return matching[:12]

    # Bucket candidate books by theme
    buckets = {
        "philosophy": [],
        "fiction": [],
        "self_help": [],
        "business": [],
        "non_fiction": []
    }

    for b in CURATED_BOOKS:
        title_clean = b["title"].lower().strip()
        if title_clean in book_titles_in_collection or b["google_id"] in book_in_collection:
            continue

        cat = b.get("category") or detect_book_category(b["title"], b["genre"], b["overview"])
        if cat in buckets:
            buckets[cat].append(b)
        else:
            buckets["fiction"].append(b)

    # Shuffle each bucket using seed
    for k in buckets:
        rng.shuffle(buckets[k])

    # Interleave across categories so the list contains a balanced blend
    bucket_keys = ["philosophy", "fiction", "self_help", "business", "non_fiction"]
    if seed:
        shift = seed % len(bucket_keys)
        bucket_keys = bucket_keys[shift:] + bucket_keys[:shift]

    blended = []
    max_len = max((len(buckets[k]) for k in bucket_keys), default=0)
    for i in range(max_len):
        for k in bucket_keys:
            if i < len(buckets[k]) and len(blended) < 12:
                blended.append(buckets[k][i])

    return blended


def get_trending_books(book_in_collection, book_titles_in_collection, seed=0, category="all"):
    import random
    rng = random.Random(seed) if seed else random.Random()

    pool = []
    for b in CURATED_BOOKS:
        if b["title"].lower().strip() in book_titles_in_collection or b["google_id"] in book_in_collection:
            continue
        if category and category != "all":
            cat = b.get("category") or detect_book_category(b["title"], b["genre"], b["overview"])
            if cat != category:
                continue
        pool.append(b)

    rng.shuffle(pool)

    # Also try to fetch daily trending from Open Library
    live_books = []
    try:
        r = requests.get("https://openlibrary.org/trending/daily.json", params={"limit": 15}, timeout=4)
        for w in r.json().get("works", []):
            w_title = w.get("title", "").strip()
            if not w_title or w_title.lower() in book_titles_in_collection:
                continue
            w_key = w.get("key", "").replace("/works/", "")
            if w_key in book_in_collection:
                continue
            cover_i = w.get("cover_i")
            thumb = f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg" if cover_i else ""
            if not thumb:
                continue
            authors = w.get("author_name", ["Unknown"])
            author_str = ", ".join(authors[:2]) if isinstance(authors, list) else str(authors)
            subjects = ", ".join(w.get("subject", [])[:5]) if "subject" in w else ""
            detected_cat = detect_book_category(w_title, subjects)
            if category and category != "all" and detected_cat != category:
                continue
            live_books.append({
                "google_id": w_key,
                "title": w_title,
                "author": author_str,
                "year": str(w.get("first_publish_year", "")),
                "img_url": thumb,
                "overview": "",
                "category": detected_cat
            })
    except Exception:
        pass

    combined = live_books + pool
    seen = set()
    result = []
    for b in combined:
        tl = b["title"].lower().strip()
        if tl not in seen:
            seen.add(tl)
            result.append(b)
        if len(result) >= 12:
            break
    return result


@app.route("/discover")
@login_required
def discover():
    tab = request.args.get("tab", "movies")
    category = request.args.get("category", "all")
    rec_page = request.args.get("rec_page", type=int, default=1)
    trend_page = request.args.get("trend_page", type=int, default=1)

    movie_in_collection, book_in_collection = _get_user_collection_ids()
    book_titles_in_collection = {b.title.lower().strip() for b in Book.query.filter_by(user_id=current_user.id).all() if b.title}

    recommended_movies = []
    trending_movies = []
    is_personalized_movies = False

    recommended_books = []
    trending_books = []
    is_personalized_books = False

    if tab == "movies":
        user_movies = Movie.query.filter_by(user_id=current_user.id).all()
        is_personalized_movies = bool(user_movies)
        if is_personalized_movies:
            recommended_movies = get_diverse_movie_recommendations(user_movies, movie_in_collection, page=rec_page, category=category)
        trending_movies = get_trending_movies(movie_in_collection, page=trend_page, category=category)
    else:
        user_books = Book.query.filter_by(user_id=current_user.id).all()
        is_personalized_books = bool(user_books)
        if is_personalized_books:
            recommended_books = get_diverse_book_recommendations(user_books, book_in_collection, book_titles_in_collection, seed=rec_page, category=category)
        trending_books = get_trending_books(book_in_collection, book_titles_in_collection, seed=trend_page, category=category)

    return render_template("discover.html",
        tab=tab,
        current_category=category,
        recommended_movies=recommended_movies,
        trending_movies=trending_movies,
        recommended_books=recommended_books,
        trending_books=trending_books,
        is_personalized_movies=is_personalized_movies,
        is_personalized_books=is_personalized_books,
    )


@app.route("/api/discover_section")
@login_required
def api_discover_section():
    tab = request.args.get("tab", "movies")
    section = request.args.get("section", "recommended")
    category = request.args.get("category", "all")
    page = request.args.get("page", type=int, default=1)
    seed = request.args.get("seed", type=int, default=1)

    movie_in_collection, book_in_collection = _get_user_collection_ids()
    book_titles_in_collection = {b.title.lower().strip() for b in Book.query.filter_by(user_id=current_user.id).all() if b.title}

    if tab == "movies":
        if section == "recommended":
            user_movies = Movie.query.filter_by(user_id=current_user.id).all()
            items = get_diverse_movie_recommendations(user_movies, movie_in_collection, page=page, category=category)
        else:
            items = get_trending_movies(movie_in_collection, page=page, category=category)
    else:
        if section == "recommended":
            user_books = Book.query.filter_by(user_id=current_user.id).all()
            items = get_diverse_book_recommendations(user_books, book_in_collection, book_titles_in_collection, seed=seed, category=category)
        else:
            items = get_trending_books(book_in_collection, book_titles_in_collection, seed=seed, category=category)

    return jsonify({"success": True, "items": items, "tab": tab, "section": section, "category": category})


# =====================
# --- Preview Routes (JSON) ---
# =====================

@app.route("/movie_preview/<int:tmdb_id>")
@login_required
def movie_preview(tmdb_id):
    try:
        r = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}",
                         params={"api_key": TMDB_API_KEY, "append_to_response": "credits"}, timeout=6)
        d = r.json()
        cast = [c["name"] for c in d.get("credits", {}).get("cast", [])[:5]]
        genres = [g["name"] for g in d.get("genres", [])]
        return jsonify({
            "title": d.get("title", ""),
            "year": (d.get("release_date") or "")[:4],
            "overview": d.get("overview", ""),
            "poster": f"https://image.tmdb.org/t/p/w300{d.get('poster_path', '')}",
            "rating": round(d.get("vote_average", 0), 1),
            "genres": ", ".join(genres),
            "cast": ", ".join(cast),
            "runtime": d.get("runtime", ""),
            "tmdb_id": tmdb_id,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/book_preview/<book_id>")
@login_required
def book_preview(book_id):
    # 1. Check curated bank first (instant response)
    for b in CURATED_BOOKS:
        if b["google_id"] == book_id:
            return jsonify({
                "title": b["title"],
                "author": b["author"],
                "year": b["year"],
                "overview": b["overview"],
                "poster": b["img_url"],
                "genres": b["genre"],
                "pages": "",
                "google_id": book_id,
            })

    # 2. If Open Library work key
    if book_id.startswith("OL"):
        try:
            r = requests.get(f"https://openlibrary.org/works/{book_id}.json", timeout=5)
            if r.status_code == 200:
                d = r.json()
                desc = d.get("description", "")
                if isinstance(desc, dict):
                    desc = desc.get("value", "")
                covers = d.get("covers", [])
                cover_id = covers[0] if covers else None
                poster = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else ""
                genres = ", ".join(d.get("subjects", [])[:4])
                return jsonify({
                    "title": d.get("title", ""),
                    "author": request.args.get("author", "Unknown"),
                    "year": (d.get("first_publish_date") or "")[:4],
                    "overview": desc[:600] if desc else "No description available.",
                    "poster": poster,
                    "genres": genres,
                    "pages": "",
                    "google_id": book_id,
                })
        except Exception:
            pass

    # 3. Google Books API
    try:
        r = requests.get(f"https://www.googleapis.com/books/v1/volumes/{book_id}", timeout=5)
        data = r.json()
        vol = data.get("volumeInfo", {})
        thumb = ""
        if "imageLinks" in vol:
            thumb = vol["imageLinks"].get("thumbnail", "").replace("http://", "https://")
        return jsonify({
            "title": vol.get("title", ""),
            "author": ", ".join(vol.get("authors", ["Unknown"])),
            "year": (vol.get("publishedDate") or "")[:4],
            "overview": (vol.get("description") or "")[:600],
            "poster": thumb,
            "genres": ", ".join(vol.get("categories", [])),
            "pages": vol.get("pageCount", ""),
            "google_id": book_id,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =====================
# --- Quick Add Routes ---
# =====================

@app.route("/quick_add_movie")
@login_required
def quick_add_movie():
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("ajax") == "1"
    tmdb_id = request.args.get("id")
    status = request.args.get("status", "to_watch")
    req_type = request.args.get("media_type")
    if not tmdb_id:
        if is_ajax:
            return jsonify({"success": False, "message": "Missing movie ID"}), 400
        return redirect(request.args.get("return_url") or request.referrer or url_for("discover", tab="movies"))

    # Don't add duplicates
    existing = Movie.query.filter_by(user_id=current_user.id, tmdb_id=str(tmdb_id)).first()
    if existing:
        if is_ajax:
            return jsonify({"success": False, "already_exists": True, "message": f'"{existing.title}" is already in your collection.'})
        flash(f'"{existing.title}" is already in your collection.', "error")
        return redirect(request.args.get("return_url") or request.referrer or url_for("discover", tab="movies"))

    try:
        is_tv = req_type == "series"
        d = None
        if not is_tv:
            r = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}",
                             params={"api_key": TMDB_API_KEY}, timeout=6)
            if r.status_code == 200:
                d = r.json()
        if not d:
            r_tv = requests.get(f"https://api.themoviedb.org/3/tv/{tmdb_id}",
                                params={"api_key": TMDB_API_KEY}, timeout=6)
            if r_tv.status_code == 200:
                d = r_tv.json()
                is_tv = True

        if not d:
            raise Exception("Item not found on TMDB")

        genres_list = [g.get("name", "") for g in d.get("genres", []) if g.get("name")]
        genres = ", ".join(genres_list)
        title = d.get("title") or d.get("name") or "Unknown"
        rel_date = d.get("release_date") or d.get("first_air_date") or ""
        year = rel_date[:4] if rel_date else ""
        media_type = detect_media_type(d, explicit_type=req_type)

        new_movie = Movie(
            user_id=current_user.id,
            tmdb_id=str(tmdb_id),
            title=title,
            year=year,
            rating=0.0,
            description=(d.get("overview") or "")[:1000],
            genre=genres,
            img_url=f"https://image.tmdb.org/t/p/w500{d.get('poster_path', '')}" if d.get('poster_path') else "",
            status=status,
            media_type=media_type,
            date_watched=date.today() if status == "watched" else None,
        )
        db.session.add(new_movie)
        db.session.commit()
        if is_ajax:
            return jsonify({
                "success": True,
                "title": new_movie.title,
                "status": status,
                "media_type": media_type,
                "message": f'"{new_movie.title}" added to your collection!'
            })
        flash(f'"{new_movie.title}" added to your collection!', "success")
    except Exception as e:
        if is_ajax:
            return jsonify({"success": False, "message": str(e)}), 500
        flash(f"Could not add movie: {str(e)}", "error")

    return redirect(request.args.get("return_url") or request.referrer or url_for("discover", tab="movies"))


@app.route("/quick_add_book")
@login_required
def quick_add_book():
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("ajax") == "1"
    google_id = request.args.get("id")
    status = request.args.get("status", "to_read")
    title = request.args.get("title")
    author = request.args.get("author")
    img_url = request.args.get("img_url")
    year = request.args.get("year", "")
    genre = request.args.get("genre", "")
    overview = request.args.get("overview", "")

    if not google_id and not title:
        if is_ajax:
            return jsonify({"success": False, "message": "Missing book ID or title"}), 400
        return redirect(request.args.get("return_url") or request.referrer or url_for("discover", tab="books"))

    # Check duplicates by id or title
    existing = None
    if google_id:
        existing = Book.query.filter_by(user_id=current_user.id, google_id=google_id).first()
    if not existing and title:
        existing = Book.query.filter_by(user_id=current_user.id, title=title).first()

    if existing:
        if is_ajax:
            return jsonify({"success": False, "already_exists": True, "message": f'"{existing.title}" is already in your collection.'})
        flash(f'"{existing.title}" is already in your collection.', "error")
        return redirect(request.args.get("return_url") or request.referrer or url_for("discover", tab="books"))

    # If parameters passed directly from card, add immediately
    if title and author and img_url:
        cat = request.args.get("category") or detect_book_category(title, genre, overview)
        new_book = Book(
            user_id=current_user.id,
            google_id=google_id or f"book_{secrets.token_hex(6)}",
            title=title,
            author=author,
            year=year,
            rating=0.0,
            description=overview[:1000] if overview else "",
            genre=genre,
            img_url=img_url,
            category=cat,
            status=status,
            date_read=date.today() if status == "read" else None,
        )
        db.session.add(new_book)
        db.session.commit()
        if is_ajax:
            return jsonify({
                "success": True,
                "title": new_book.title,
                "status": status,
                "message": f'"{new_book.title}" added to your collection!'
            })
        flash(f'"{new_book.title}" added to your collection!', "success")
        return redirect(request.args.get("return_url") or request.referrer or url_for("discover", tab="books"))

    # If in curated bank, use curated details
    for b in CURATED_BOOKS:
        if b["google_id"] == google_id:
            cat = b.get("category") or detect_book_category(b["title"], b["genre"], b["overview"])
            new_book = Book(
                user_id=current_user.id,
                google_id=google_id,
                title=b["title"],
                author=b["author"],
                year=b["year"],
                rating=0.0,
                description=b["overview"],
                genre=b["genre"],
                img_url=b["img_url"],
                category=cat,
                status=status,
                date_read=date.today() if status == "read" else None,
            )
            db.session.add(new_book)
            db.session.commit()
            if is_ajax:
                return jsonify({
                    "success": True,
                    "title": new_book.title,
                    "status": status,
                    "message": f'"{new_book.title}" added to your collection!'
                })
            flash(f'"{new_book.title}" added to your collection!', "success")
            return redirect(request.args.get("return_url") or request.referrer or url_for("discover", tab="books"))

    # Otherwise fetch from Open Library or Google Books
    try:
        if google_id and google_id.startswith("OL"):
            r = requests.get(f"https://openlibrary.org/works/{google_id}.json", timeout=6)
            data = r.json()
            b_title = data.get("title", "Unknown")
            desc = data.get("description", "")
            if isinstance(desc, dict):
                desc = desc.get("value", "")
            covers = data.get("covers", [])
            cover_id = covers[0] if covers else None
            thumb = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else ""
            genres = ", ".join(data.get("subjects", [])[:3])
            cat = detect_book_category(b_title, genres, desc)
            new_book = Book(
                user_id=current_user.id,
                google_id=google_id,
                title=b_title,
                author=author or "Unknown",
                year=year or (data.get("first_publish_date") or "")[:4],
                rating=0.0,
                description=desc[:1000] if desc else "",
                genre=genres,
                img_url=thumb,
                category=cat,
                status=status,
                date_read=date.today() if status == "read" else None,
            )
        else:
            r = requests.get(f"https://www.googleapis.com/books/v1/volumes/{google_id}", timeout=6)
            data = r.json()
            vol = data.get("volumeInfo", {})
            thumb = ""
            if "imageLinks" in vol:
                thumb = vol["imageLinks"].get("thumbnail", "").replace("http://", "https://")
            vol_genre = ", ".join(vol.get("categories", []))
            vol_title = vol.get("title", "Unknown")
            vol_desc = (vol.get("description") or "")[:1000]
            cat = detect_book_category(vol_title, vol_genre, vol_desc)
            new_book = Book(
                user_id=current_user.id,
                google_id=google_id,
                title=vol_title,
                author=", ".join(vol.get("authors", ["Unknown"])),
                year=(vol.get("publishedDate") or "")[:4],
                rating=0.0,
                description=vol_desc,
                genre=vol_genre,
                img_url=thumb,
                category=cat,
                status=status,
                date_read=date.today() if status == "read" else None,
            )
        db.session.add(new_book)
        db.session.commit()
        if is_ajax:
            return jsonify({
                "success": True,
                "title": new_book.title,
                "status": status,
                "message": f'"{new_book.title}" added to your collection!'
            })
        flash(f'"{new_book.title}" added to your collection!', "success")
    except Exception as e:
        if is_ajax:
            return jsonify({"success": False, "message": str(e)}), 500
        flash(f"Could not add book: {str(e)}", "error")

    return redirect(request.args.get("return_url") or request.referrer or url_for("discover", tab="books"))


# =====================
# --- Movie Routes ---
# =====================

@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    class AddForm(FlaskForm):
        title = StringField("Movie Title", validators=[DataRequired()])
        submit = SubmitField("Search Movie")
    form = AddForm()
    if form.validate_on_submit():
        return redirect(url_for("find", title=form.title.data))
    return render_template("add.html", form=form, item_type="Movie")


@app.route("/find")
@login_required
def find():
    title = request.args.get("title")
    if not title:
        return redirect(url_for("add"))
    r = requests.get("https://api.themoviedb.org/3/search/movie",
                     params={"api_key": TMDB_API_KEY, "query": title})
    data = r.json()
    return render_template("select.html", items=data.get("results", []), item_type="Movie", query=title)


@app.route("/select")
@login_required
def select():
    tmdb_id = request.args.get("id")
    status = request.args.get("status", "to_watch")
    req_type = request.args.get("media_type")
    if not tmdb_id:
        return redirect(url_for("add"))

    existing = Movie.query.filter_by(user_id=current_user.id, tmdb_id=str(tmdb_id)).first()
    if existing:
        flash(f'"{existing.title}" is already in your collection.', "error")
        return redirect(request.args.get("return_url") or request.referrer or url_for("collection", tab="movies"))

    is_tv = req_type == "series"
    d = None
    if not is_tv:
        r = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}",
                         params={"api_key": TMDB_API_KEY})
        if r.status_code == 200:
            d = r.json()
    if not d:
        r_tv = requests.get(f"https://api.themoviedb.org/3/tv/{tmdb_id}",
                            params={"api_key": TMDB_API_KEY})
        if r_tv.status_code == 200:
            d = r_tv.json()
            is_tv = True

    if not d:
        flash("Could not fetch details from TMDB.", "error")
        return redirect(url_for("add"))

    genres = ", ".join([g.get("name", "") for g in d.get("genres", []) if g.get("name")])
    title = d.get("title") or d.get("name") or "Unknown"
    rel_date = d.get("release_date") or d.get("first_air_date") or ""
    year = rel_date[:4] if rel_date else ""
    media_type = detect_media_type(d, explicit_type=req_type)

    new_movie = Movie(
        user_id=current_user.id,
        tmdb_id=str(tmdb_id),
        title=title,
        year=year,
        rating=0.0,
        description=(d.get("overview") or "")[:1000],
        genre=genres,
        img_url=f"https://image.tmdb.org/t/p/w500{d.get('poster_path', '')}" if d.get('poster_path') else "",
        status=status,
        media_type=media_type,
        date_watched=date.today() if status == "watched" else None,
    )
    db.session.add(new_movie)
    db.session.commit()
    if status == "to_watch":
        flash(f'"{new_movie.title}" added to your watchlist!', "success")
        return redirect(request.args.get("return_url") or url_for("collection", tab="movies", status="to_watch"))
    return redirect(request.args.get("return_url") or url_for("edit", movie_id=new_movie.id))


@app.route("/edit/<int:movie_id>", methods=["GET", "POST"])
@login_required
def edit(movie_id):
    movie = db.session.get(Movie, movie_id)
    if not movie or movie.user_id != current_user.id:
        return redirect(url_for("collection"))
    class EditForm(FlaskForm):
        title = StringField("Title", validators=[DataRequired()])
        media_type = SelectField("Category", choices=[
            ("movie", "🎬 Normal Movie"),
            ("series", "📺 Series / TV Show"),
            ("animation", "🎨 Animation"),
            ("anime", "⛩️ Anime")
        ], default="movie")
        rating = StringField("Your Rating (0–10)")
        custom_tags = StringField("Custom Tags (comma separated)")
        review = TextAreaField("Your Review")
        description = TextAreaField("Synopsis")
        status = SelectField("Status", choices=[("to_watch", "🕐 To Watch"), ("watched", "✅ Watched")])
        submit = SubmitField("Save")
    form = EditForm()
    if form.validate_on_submit():
        movie.title = form.title.data
        movie.media_type = form.media_type.data or "movie"
        try:
            movie.rating = float(form.rating.data or 0)
        except ValueError:
            movie.rating = 0.0
        movie.custom_tags = form.custom_tags.data
        movie.review = form.review.data
        movie.description = form.description.data
        movie.status = form.status.data
        if form.status.data == "watched" and not movie.date_watched:
            movie.date_watched = date.today()
        db.session.commit()
        flash("Saved!", "success")
        return redirect(url_for("collection", tab="movies"))
    form.title.data = movie.title
    form.media_type.data = movie.media_type or "movie"
    form.rating.data = str(movie.rating)
    form.custom_tags.data = movie.custom_tags
    form.review.data = movie.review
    form.description.data = movie.description
    form.status.data = movie.status
    return render_template("edit.html", item=movie, form=form, item_type="Movie")


@app.route("/delete/<int:movie_id>", methods=["GET", "POST", "DELETE"])
@login_required
def delete(movie_id):
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("ajax") == "1"
    movie = db.session.get(Movie, movie_id)
    if movie and movie.user_id == current_user.id:
        title = movie.title
        db.session.delete(movie)
        db.session.commit()
        if is_ajax:
            return jsonify({
                "success": True,
                "item_id": movie_id,
                "item_type": "movie",
                "message": f'"{title}" removed from collection.',
                "watched_count": Movie.query.filter_by(user_id=current_user.id, status="watched").count(),
                "to_watch_count": Movie.query.filter_by(user_id=current_user.id, status="to_watch").count(),
                "total_count": Movie.query.filter_by(user_id=current_user.id).count(),
            })
        flash(f'"{title}" removed.', "success")
    else:
        if is_ajax:
            return jsonify({"success": False, "error": "Movie not found"}), 404
        flash("Movie not found.", "error")

    return_url = request.args.get("return_url") or request.referrer
    if return_url:
        return redirect(return_url)
    return redirect(url_for("collection", tab="movies"))


@app.route("/toggle_status/<string:item_type>/<int:item_id>", methods=["GET", "POST"])
@login_required
def toggle_status(item_type, item_id):
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("ajax") == "1"

    if item_type == "movie":
        movie = db.session.get(Movie, item_id)
        if not movie or movie.user_id != current_user.id:
            if is_ajax:
                return jsonify({"success": False, "error": "Movie not found"}), 404
            flash("Movie not found.", "error")
            return redirect(url_for("collection", tab="movies"))

        new_status = "to_watch" if movie.status == "watched" else "watched"
        movie.status = new_status
        if new_status == "watched":
            if not movie.date_watched:
                movie.date_watched = date.today()
        else:
            movie.date_watched = None
        db.session.commit()

        if is_ajax:
            return jsonify({
                "success": True,
                "item_type": "movie",
                "item_id": item_id,
                "new_status": new_status,
                "label": "Watched" if new_status == "watched" else "To Watch",
                "icon": "fa-check" if new_status == "watched" else "fa-clock",
                "toggle_title": "Mark as To Watch" if new_status == "watched" else "Mark as Watched",
                "message": f'Marked "{movie.title}" as {"Watched" if new_status == "watched" else "To Watch"}',
                "watched_count": Movie.query.filter_by(user_id=current_user.id, status="watched").count(),
                "to_watch_count": Movie.query.filter_by(user_id=current_user.id, status="to_watch").count(),
                "total_count": Movie.query.filter_by(user_id=current_user.id).count(),
            })
        flash(f'Marked "{movie.title}" as {"Watched" if new_status == "watched" else "To Watch"}.', "success")

    elif item_type == "book":
        book = db.session.get(Book, item_id)
        if not book or book.user_id != current_user.id:
            if is_ajax:
                return jsonify({"success": False, "error": "Book not found"}), 404
            flash("Book not found.", "error")
            return redirect(url_for("collection", tab="books"))

        new_status = "to_read" if book.status == "read" else "read"
        book.status = new_status
        if new_status == "read":
            if not book.date_read:
                book.date_read = date.today()
        else:
            book.date_read = None
        db.session.commit()

        if is_ajax:
            return jsonify({
                "success": True,
                "item_type": "book",
                "item_id": item_id,
                "new_status": new_status,
                "label": "Read" if new_status == "read" else "To Read",
                "icon": "fa-check" if new_status == "read" else "fa-bookmark",
                "toggle_title": "Mark as To Read" if new_status == "read" else "Mark as Read",
                "message": f'Marked "{book.title}" as {"Read" if new_status == "read" else "To Read"}',
                "read_count": Book.query.filter_by(user_id=current_user.id, status="read").count(),
                "to_read_count": Book.query.filter_by(user_id=current_user.id, status="to_read").count(),
                "total_count": Book.query.filter_by(user_id=current_user.id).count(),
            })
        flash(f'Marked "{book.title}" as {"Read" if new_status == "read" else "To Read"}.', "success")
    else:
        if is_ajax:
            return jsonify({"success": False, "error": "Invalid item type"}), 400
        return redirect(url_for("collection"))

    return_url = request.args.get("return_url") or request.referrer
    if return_url:
        return redirect(return_url)
    return redirect(url_for("collection", tab="movies" if item_type == "movie" else "books"))


# =====================
# --- Book Routes ---
# =====================

@app.route("/add_book", methods=["GET", "POST"])
@login_required
def add_book():
    class AddBookForm(FlaskForm):
        title = StringField("Book Title", validators=[DataRequired()])
        submit = SubmitField("Search Book")
    form = AddBookForm()
    if form.validate_on_submit():
        return redirect(url_for("find_book", title=form.title.data))
    return render_template("add.html", form=form, item_type="Book")


@app.route("/find_book")
@login_required
def find_book():
    title = request.args.get("title")
    if not title:
        return redirect(url_for("add_book"))

    items = []
    # 1. Try Google Books API
    try:
        r = requests.get("https://www.googleapis.com/books/v1/volumes",
                         params={"q": title, "maxResults": 12}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            for item in data.get("items", []):
                vol = item.get("volumeInfo", {})
                thumb = ""
                if "imageLinks" in vol:
                    thumb = vol["imageLinks"].get("thumbnail", "").replace("http://", "https://")
                items.append({
                    "id": item.get("id"),
                    "title": vol.get("title", "Unknown"),
                    "release_date": vol.get("publishedDate", ""),
                    "poster_path": None,
                    "thumb": thumb,
                    "author": ", ".join(vol.get("authors", ["Unknown"])),
                })
    except Exception:
        pass

    # 2. Try Open Library if Google gave 0 results
    if not items:
        try:
            r = requests.get("https://openlibrary.org/search.json", params={"q": title, "limit": 12}, timeout=6)
            if r.status_code == 200:
                for doc in r.json().get("docs", []):
                    cover_i = doc.get("cover_i")
                    thumb = f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg" if cover_i else ""
                    key = doc.get("key", "").replace("/works/", "")
                    authors = doc.get("author_name", ["Unknown"])
                    items.append({
                        "id": key,
                        "title": doc.get("title", "Unknown"),
                        "release_date": str(doc.get("first_publish_year", "")),
                        "poster_path": None,
                        "thumb": thumb,
                        "author": ", ".join(authors[:2]) if isinstance(authors, list) else str(authors),
                    })
        except Exception:
            pass

    # 3. Match from CURATED_BOOKS
    if not items:
        q_lower = title.lower()
        for b in CURATED_BOOKS:
            if q_lower in b["title"].lower() or q_lower in b["author"].lower() or q_lower in b["genre"].lower():
                items.append({
                    "id": b["google_id"],
                    "title": b["title"],
                    "release_date": b["year"],
                    "poster_path": None,
                    "thumb": b["img_url"],
                    "author": b["author"],
                })

    if not items:
        flash("Could not find books matching that query. Please try another search term.", "error")
        return redirect(url_for("add_book"))

    return render_template("select.html", items=items, item_type="Book", query=title)


@app.route("/select_book")
@login_required
def select_book():
    book_id = request.args.get("id")
    status = request.args.get("status", "to_read")
    if not book_id:
        return redirect(url_for("add_book"))

    existing = Book.query.filter_by(user_id=current_user.id, google_id=book_id).first()
    if existing:
        flash(f'"{existing.title}" is already in your collection.', "error")
        return redirect(request.args.get("return_url") or request.referrer or url_for("collection", tab="books"))

    # 1. Check curated bank
    for b in CURATED_BOOKS:
        if b["google_id"] == book_id:
            cat = b.get("category") or detect_book_category(b["title"], b["genre"], b["overview"])
            new_book = Book(
                user_id=current_user.id,
                google_id=book_id,
                title=b["title"],
                author=b["author"],
                year=b["year"],
                rating=0.0,
                description=b["overview"],
                genre=b["genre"],
                img_url=b["img_url"],
                category=cat,
                status=status,
                date_read=date.today() if status == "read" else None,
            )
            db.session.add(new_book)
            db.session.commit()
            if status == "to_read":
                flash(f'"{new_book.title}" added to your reading list!', "success")
                return redirect(request.args.get("return_url") or url_for("collection", tab="books", status="to_read"))
            return redirect(request.args.get("return_url") or url_for("edit_book", book_id=new_book.id))

    # 2. Check Open Library
    if book_id.startswith("OL"):
        try:
            r = requests.get(f"https://openlibrary.org/works/{book_id}.json", timeout=6)
            data = r.json()
            b_title = data.get("title", "Unknown")
            desc = data.get("description", "")
            if isinstance(desc, dict):
                desc = desc.get("value", "")
            covers = data.get("covers", [])
            cover_id = covers[0] if covers else None
            thumb = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else ""
            genres = ", ".join(data.get("subjects", [])[:3])
            cat = detect_book_category(b_title, genres, desc)
            new_book = Book(
                user_id=current_user.id,
                google_id=book_id,
                title=b_title,
                author=request.args.get("author", "Unknown"),
                year=(data.get("first_publish_date") or "")[:4],
                rating=0.0,
                description=desc[:1000] if desc else "",
                genre=genres,
                img_url=thumb,
                category=cat,
                status=status,
                date_read=date.today() if status == "read" else None,
            )
            db.session.add(new_book)
            db.session.commit()
            if status == "to_read":
                flash(f'"{new_book.title}" added to your reading list!', "success")
                return redirect(request.args.get("return_url") or url_for("collection", tab="books", status="to_read"))
            return redirect(request.args.get("return_url") or url_for("edit_book", book_id=new_book.id))
        except Exception:
            pass

    # 3. Check Google Books
    try:
        r = requests.get(f"https://www.googleapis.com/books/v1/volumes/{book_id}", timeout=8)
        data = r.json()
        vol = data.get("volumeInfo", {})
        if not vol:
            flash("Book details could not be retrieved.", "error")
            return redirect(url_for("add_book"))

        year = (vol.get("publishedDate") or "")[:4]
        authors = ", ".join(vol.get("authors", ["Unknown"]))
        thumb = ""
        if "imageLinks" in vol:
            thumb = vol["imageLinks"].get("thumbnail", "").replace("http://", "https://")
        categories = ", ".join(vol.get("categories", []))
        vol_title = vol.get("title", "Unknown")
        vol_desc = (vol.get("description") or "")[:1000]
        cat = detect_book_category(vol_title, categories, vol_desc)

        new_book = Book(
            user_id=current_user.id,
            google_id=book_id,
            title=vol_title,
            author=authors,
            year=year,
            rating=0.0,
            description=vol_desc,
            genre=categories,
            img_url=thumb,
            category=cat,
            status=status,
            date_read=date.today() if status == "read" else None,
        )
        db.session.add(new_book)
        db.session.commit()

        if status == "to_read":
            flash(f'"{new_book.title}" added to your reading list!', "success")
            return redirect(request.args.get("return_url") or url_for("collection", tab="books", status="to_read"))
        return redirect(request.args.get("return_url") or url_for("edit_book", book_id=new_book.id))
    except Exception as e:
        flash(f"Could not fetch book details: {str(e)}", "error")
        return redirect(url_for("add_book"))


@app.route("/edit_book/<int:book_id>", methods=["GET", "POST"])
@login_required
def edit_book(book_id):
    book = db.session.get(Book, book_id)
    if not book or book.user_id != current_user.id:
        return redirect(url_for("collection"))
    class EditForm(FlaskForm):
        title = StringField("Title", validators=[DataRequired()])
        category = SelectField("Category", choices=[
            ("fiction", "📖 Fiction & Literature"),
            ("philosophy", "🧠 Philosophy & Ethics"),
            ("self_help", "🌱 Self-Help & Growth"),
            ("business", "💼 Business & Finance"),
            ("non_fiction", "🌍 Non-Fiction & Science"),
        ])
        rating = StringField("Your Rating (0–10)")
        custom_tags = StringField("Custom Tags (comma separated)")
        review = TextAreaField("Your Review")
        description = TextAreaField("Synopsis")
        status = SelectField("Status", choices=[("to_read", "📖 To Read"), ("read", "✅ Read")])
        submit = SubmitField("Save")
    form = EditForm()
    if form.validate_on_submit():
        book.title = form.title.data
        book.category = form.category.data
        try:
            book.rating = float(form.rating.data or 0)
        except ValueError:
            book.rating = 0.0
        book.custom_tags = form.custom_tags.data
        book.review = form.review.data
        book.description = form.description.data
        book.status = form.status.data
        if form.status.data == "read" and not book.date_read:
            book.date_read = date.today()
        db.session.commit()
        flash("Saved!", "success")
        return redirect(url_for("collection", tab="books"))
    form.title.data = book.title
    form.category.data = book.category or "fiction"
    form.rating.data = str(book.rating)
    form.custom_tags.data = book.custom_tags
    form.review.data = book.review
    form.description.data = book.description
    form.status.data = book.status
    return render_template("edit.html", item=book, form=form, item_type="Book")


@app.route("/delete_book/<int:book_id>", methods=["GET", "POST", "DELETE"])
@login_required
def delete_book(book_id):
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("ajax") == "1"
    book = db.session.get(Book, book_id)
    if book and book.user_id == current_user.id:
        title = book.title
        db.session.delete(book)
        db.session.commit()
        if is_ajax:
            return jsonify({
                "success": True,
                "item_id": book_id,
                "item_type": "book",
                "message": f'"{title}" removed from collection.',
                "read_count": Book.query.filter_by(user_id=current_user.id, status="read").count(),
                "to_read_count": Book.query.filter_by(user_id=current_user.id, status="to_read").count(),
                "total_count": Book.query.filter_by(user_id=current_user.id).count(),
            })
        flash(f'"{title}" removed.', "success")
    else:
        if is_ajax:
            return jsonify({"success": False, "error": "Book not found"}), 404
        flash("Book not found.", "error")

    return_url = request.args.get("return_url") or request.referrer
    if return_url:
        return redirect(return_url)
    return redirect(url_for("collection", tab="books"))

@app.route("/api/search_movie")
@login_required
def api_search_movie():
    query = request.args.get("q", "")
    if not query:
        return jsonify([])
    try:
        r = requests.get("https://api.themoviedb.org/3/search/movie",
                         params={"api_key": TMDB_API_KEY, "query": query}, timeout=3)
        results = [{"id": i["id"], "title": i.get("title", ""), "year": (i.get("release_date") or "")[:4]}
                   for i in r.json().get("results", [])[:5]]
        return jsonify(results)
    except:
        return jsonify([])

@app.route("/api/search_book")
@login_required
def api_search_book():
    query = request.args.get("q", "")
    if not query:
        return jsonify([])
    try:
        r = requests.get("https://www.googleapis.com/books/v1/volumes",
                         params={"q": query, "maxResults": 5}, timeout=3)
        results = [{"id": i.get("id"), "title": i.get("volumeInfo", {}).get("title", ""),
                    "year": (i.get("volumeInfo", {}).get("publishedDate") or "")[:4]}
                   for i in r.json().get("items", [])]
        return jsonify(results)
    except:
        return jsonify([])

if __name__ == "__main__":
    app.run(debug=True)
