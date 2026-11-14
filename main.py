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
    date_added: Mapped[date] = mapped_column(Date, default=date.today)
    date_read: Mapped[date] = mapped_column(Date, nullable=True)
    owner: Mapped["User"] = relationship("User", back_populates="books")

with app.app_context():
    db.create_all()
    # --- Schema migration: ensure google_id exists and password_hash is nullable ---
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    existing_cols = {c["name"]: c for c in inspector.get_columns("user")}
    
    if "google_id" not in existing_cols:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE user ADD COLUMN google_id VARCHAR(100)"))
            conn.commit()

    # In SQLite, if password_hash was originally NOT NULL, recreate table to make it nullable
    if "password_hash" in existing_cols and not existing_cols["password_hash"].get("nullable", True):
        with db.engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            conn.execute(text("""
                CREATE TABLE user_new (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    email VARCHAR(150) NOT NULL UNIQUE,
                    password_hash VARCHAR(256),
                    avatar_color VARCHAR(20) NOT NULL,
                    created_at DATETIME NOT NULL,
                    bio VARCHAR(500),
                    avatar_url VARCHAR(500),
                    google_id VARCHAR(100) UNIQUE
                )
            """))
            conn.execute(text("""
                INSERT INTO user_new (id, username, email, password_hash, avatar_color, created_at, bio, avatar_url, google_id)
                SELECT id, username, email, password_hash, avatar_color, created_at, bio, avatar_url, google_id FROM user
            """))
            conn.execute(text("DROP TABLE user"))
            conn.execute(text("ALTER TABLE user_new RENAME TO user"))
            conn.execute(text("PRAGMA foreign_keys=ON"))
            conn.commit()


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
                flash(f"Your Google account has been linked to your existing CineShelf account. Welcome back, {user.username}!", "success")
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
                flash(f"Welcome to CineShelf, {user.username}! Your account has been created via Google.", "success")

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
                feed_items.append({"action": f"watched and rated ⭐ {m.rating}", "item": m, "user": u, "date": m.date_watched})
        for b in u.books:
            feed_items.append({"action": "added the book", "item": b, "user": u, "date": b.date_added})
            if b.status == "read" and b.date_read:
                feed_items.append({"action": f"read and rated ⭐ {b.rating}", "item": b, "user": u, "date": b.date_read})
    
    feed_items.sort(key=lambda x: x["date"] or date.min, reverse=True)
    return render_template("feed.html", feed_items=feed_items[:50])


@app.route("/view/movie/<int:item_id>")
def view_movie(item_id):
    movie = Movie.query.get_or_404(item_id)
    tmdb_url = f"https://api.themoviedb.org/3/movie/{movie.tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits,videos"
    response = requests.get(tmdb_url).json()
    
    trailer_key = None
    if "videos" in response and "results" in response["videos"]:
        for video in response["videos"]["results"]:
            if video["type"] == "Trailer" and video["site"] == "YouTube":
                trailer_key = video["key"]
                break
                
    cast = []
    if "credits" in response and "cast" in response["credits"]:
        cast = response["credits"]["cast"][:6]
        
    director = None
    if "credits" in response and "crew" in response["credits"]:
        for crew_member in response["credits"]["crew"]:
            if crew_member["job"] == "Director":
                director = crew_member["name"]
                break

    backdrop_path = response.get("backdrop_path")
    backdrop_url = f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else movie.img_url

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

    return render_template("dashboard.html",
        watched_count=len(watched),
        to_watch_count=len(to_watch),
        read_count=len(read_books),
        to_read_count=len(to_read),
        movies_this_month=len(movies_this_month),
        books_this_month=len(books_this_month),
        recent=recent,
        avg_movie_rating=round(sum(m.rating for m in watched if m.rating) / max(len(watched), 1), 1),
        streak=streak
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
    
    top_items = sorted(watched + read_books, key=lambda x: x.rating or 0, reverse=True)[:5]

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
                           tab=tab, status=status, sort=sort, all_tags=all_tags, current_tag=tag_filter)

@app.route("/u/<username>")
def public_collection(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("landing"))
        
    tab = request.args.get("tab", "movies")
    status = request.args.get("status", "all")
    sort = request.args.get("sort", "newest")

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
    
    return render_template("public_collection.html", 
                           profile_user=user, 
                           movies=movies, books=books,
                           tab=tab, status=status, sort=sort)



# =====================
# --- Discover (Personalized + Filtered) ---
# =====================

def _get_user_collection_ids():
    movie_tmdb_ids = {m.tmdb_id for m in Movie.query.filter_by(user_id=current_user.id).all() if m.tmdb_id}
    book_google_ids = {b.google_id for b in Book.query.filter_by(user_id=current_user.id).all() if b.google_id}
    return movie_tmdb_ids, book_google_ids


@app.route("/discover")
@login_required
def discover():
    import random
    movie_in_collection, book_in_collection = _get_user_collection_ids()
    refresh = request.args.get('refresh', type=int, default=0)
    page_offset = random.randint(1, 4) if refresh else 1

    # -- Personalized movie recommendations --
    user_movies = Movie.query.filter_by(user_id=current_user.id, status="watched").all()
    genre_ids = set()
    for m in user_movies:
        if m.tmdb_id:
            try:
                r = requests.get(f"https://api.themoviedb.org/3/movie/{m.tmdb_id}",
                                 params={"api_key": TMDB_API_KEY}, timeout=4)
                for g in r.json().get("genres", []):
                    genre_ids.add(str(g["id"]))
                if len(genre_ids) >= 6:
                    break
            except Exception:
                pass

    if genre_ids and refresh:
        genre_ids = set(random.sample(list(genre_ids), min(3, len(genre_ids))))

    recommended_movies = []
    is_personalized_movies = bool(genre_ids)
    if is_personalized_movies:
        try:
            params = {"api_key": TMDB_API_KEY, "sort_by": "popularity.desc", "page": page_offset}
            params["with_genres"] = ",".join(list(genre_ids)[:3])
            r = requests.get("https://api.themoviedb.org/3/discover/movie", params=params, timeout=6)
            for item in r.json().get("results", []):
                tid = str(item["id"])
                if tid in movie_in_collection: continue
                if item.get("poster_path"):
                    recommended_movies.append({
                        "tmdb_id": tid, "title": item.get("title", ""),
                        "year": (item.get("release_date") or "")[:4],
                        "img_url": f"https://image.tmdb.org/t/p/w300{item['poster_path']}",
                        "rating": round(item.get("vote_average", 0), 1),
                        "overview": (item.get("overview") or "")[:200]
                    })
                if len(recommended_movies) >= 12: break
        except Exception: pass

    trending_movies = []
    try:
        tparams = {"api_key": TMDB_API_KEY, "sort_by": "popularity.desc", "page": page_offset}
        r = requests.get("https://api.themoviedb.org/3/discover/movie", params=tparams, timeout=6)
        for item in r.json().get("results", []):
            tid = str(item["id"])
            if tid in movie_in_collection: continue
            if item.get("poster_path"):
                trending_movies.append({
                    "tmdb_id": tid, "title": item.get("title", ""),
                    "year": (item.get("release_date") or "")[:4],
                    "img_url": f"https://image.tmdb.org/t/p/w300{item['poster_path']}",
                    "rating": round(item.get("vote_average", 0), 1),
                    "overview": (item.get("overview") or "")[:200]
                })
            if len(trending_movies) >= 12: break
    except Exception: pass

    # -- Personalized book recommendations --
    user_books = Book.query.filter_by(user_id=current_user.id, status="read").all()
    book_subjects = []
    for b in user_books:
        if b.genre:
            book_subjects += [g.strip().lower() for g in b.genre.split(",") if g.strip()]
    if book_subjects and refresh:
        random.shuffle(book_subjects)
        
    book_query = "+".join(book_subjects[:2]) if book_subjects else ""
    is_personalized_books = bool(book_query)

    recommended_books = []
    if is_personalized_books:
        try:
            r = requests.get("https://www.googleapis.com/books/v1/volumes",
                             params={"q": f"subject:{book_query}", "maxResults": 20,
                                     "orderBy": "relevance", "printType": "books", "startIndex": (page_offset-1)*15}, timeout=6)
            for item in r.json().get("items", []):
                gid = item.get("id")
                if gid in book_in_collection: continue
                vol = item.get("volumeInfo", {})
                thumb = vol.get("imageLinks", {}).get("thumbnail", "").replace("http://", "https://")
                if not thumb: continue
                recommended_books.append({
                    "google_id": gid, "title": vol.get("title", ""),
                    "author": ", ".join(vol.get("authors", ["Unknown"])),
                    "year": (vol.get("publishedDate") or "")[:4],
                    "img_url": thumb, "overview": (vol.get("description") or "")[:200]
                })
                if len(recommended_books) >= 12: break
        except Exception: pass

    trending_books = []
    try:
        tr = requests.get("https://www.googleapis.com/books/v1/volumes",
                         params={"q": "subject:fiction", "maxResults": 20,
                                 "orderBy": "newest", "printType": "books", "startIndex": (page_offset-1)*15}, timeout=6)
        for item in tr.json().get("items", []):
            gid = item.get("id")
            if gid in book_in_collection: continue
            vol = item.get("volumeInfo", {})
            thumb = vol.get("imageLinks", {}).get("thumbnail", "").replace("http://", "https://")
            if not thumb: continue
            trending_books.append({
                "google_id": gid, "title": vol.get("title", ""),
                "author": ", ".join(vol.get("authors", ["Unknown"])),
                "year": (vol.get("publishedDate") or "")[:4],
                "img_url": thumb, "overview": (vol.get("description") or "")[:200]
            })
            if len(trending_books) >= 12: break
    except Exception: pass

    return render_template("discover.html",
        recommended_movies=recommended_movies,
        trending_movies=trending_movies,
        recommended_books=recommended_books,
        trending_books=trending_books,
        is_personalized_movies=is_personalized_movies,
        is_personalized_books=is_personalized_books,
    )


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
    try:
        r = requests.get(f"https://www.googleapis.com/books/v1/volumes/{book_id}", timeout=6)
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
    tmdb_id = request.args.get("id")
    status = request.args.get("status", "to_watch")
    if not tmdb_id:
        return redirect(url_for("discover"))

    # Don't add duplicates
    existing = Movie.query.filter_by(user_id=current_user.id, tmdb_id=str(tmdb_id)).first()
    if existing:
        flash(f'"{existing.title}" is already in your collection.', "error")
        return redirect(url_for("discover"))

    try:
        r = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}",
                         params={"api_key": TMDB_API_KEY}, timeout=6)
        d = r.json()
        genres = ", ".join([g["name"] for g in d.get("genres", [])])
        new_movie = Movie(
            user_id=current_user.id,
            tmdb_id=str(tmdb_id),
            title=d.get("title", "Unknown"),
            year=(d.get("release_date") or "")[:4],
            rating=0.0,
            description=(d.get("overview") or "")[:1000],
            genre=genres,
            img_url=f"https://image.tmdb.org/t/p/w500{d.get('poster_path', '')}",
            status=status,
            date_watched=date.today() if status == "watched" else None,
        )
        db.session.add(new_movie)
        db.session.commit()
        flash(f'"{new_movie.title}" added to your collection!', "success")
    except Exception as e:
        flash(f"Could not add movie: {str(e)}", "error")

    return redirect(url_for("discover"))


@app.route("/quick_add_book")
@login_required
def quick_add_book():
    google_id = request.args.get("id")
    status = request.args.get("status", "to_read")
    if not google_id:
        return redirect(url_for("discover"))

    existing = Book.query.filter_by(user_id=current_user.id, google_id=google_id).first()
    if existing:
        flash(f'"{existing.title}" is already in your collection.', "error")
        return redirect(url_for("discover"))

    try:
        r = requests.get(f"https://www.googleapis.com/books/v1/volumes/{google_id}", timeout=6)
        data = r.json()
        vol = data.get("volumeInfo", {})
        thumb = ""
        if "imageLinks" in vol:
            thumb = vol["imageLinks"].get("thumbnail", "").replace("http://", "https://")
        new_book = Book(
            user_id=current_user.id,
            google_id=google_id,
            title=vol.get("title", "Unknown"),
            author=", ".join(vol.get("authors", ["Unknown"])),
            year=(vol.get("publishedDate") or "")[:4],
            rating=0.0,
            description=(vol.get("description") or "")[:1000],
            genre=", ".join(vol.get("categories", [])),
            img_url=thumb,
            status=status,
            date_read=date.today() if status == "read" else None,
        )
        db.session.add(new_book)
        db.session.commit()
        flash(f'"{new_book.title}" added to your collection!', "success")
    except Exception as e:
        flash(f"Could not add book: {str(e)}", "error")

    return redirect(url_for("discover"))


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
    if not tmdb_id:
        return redirect(url_for("add"))

    existing = Movie.query.filter_by(user_id=current_user.id, tmdb_id=str(tmdb_id)).first()
    if existing:
        flash(f'"{existing.title}" is already in your collection.', "error")
        return redirect(url_for("collection", tab="movies"))

    r = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}",
                     params={"api_key": TMDB_API_KEY})
    d = r.json()
    genres = ", ".join([g["name"] for g in d.get("genres", [])])
    new_movie = Movie(
        user_id=current_user.id,
        tmdb_id=str(tmdb_id),
        title=d.get("title", "Unknown"),
        year=(d.get("release_date") or "")[:4],
        rating=0.0,
        description=(d.get("overview") or "")[:1000],
        genre=genres,
        img_url=f"https://image.tmdb.org/t/p/w500{d.get('poster_path', '')}",
        status=status,
        date_watched=date.today() if status == "watched" else None,
    )
    db.session.add(new_movie)
    db.session.commit()
    if status == "to_watch":
        flash(f'"{new_movie.title}" added to your watchlist!', "success")
        return redirect(url_for("collection", tab="movies"))
    return redirect(url_for("edit", movie_id=new_movie.id))


@app.route("/edit/<int:movie_id>", methods=["GET", "POST"])
@login_required
def edit(movie_id):
    movie = db.session.get(Movie, movie_id)
    if not movie or movie.user_id != current_user.id:
        return redirect(url_for("collection"))
    class EditForm(FlaskForm):
        title = StringField("Title", validators=[DataRequired()])
        rating = StringField("Your Rating (0–10)")
        custom_tags = StringField("Custom Tags (comma separated)")
        review = TextAreaField("Your Review")
        description = TextAreaField("Synopsis")
        status = SelectField("Status", choices=[("to_watch", "🕐 To Watch"), ("watched", "✅ Watched")])
        submit = SubmitField("Save")
    form = EditForm()
    if form.validate_on_submit():
        movie.title = form.title.data
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
    form.rating.data = str(movie.rating)
    form.custom_tags.data = movie.custom_tags
    form.review.data = movie.review
    form.description.data = movie.description
    form.status.data = movie.status
    return render_template("edit.html", item=movie, form=form, item_type="Movie")


@app.route("/delete/<int:movie_id>")
@login_required
def delete(movie_id):
    movie = db.session.get(Movie, movie_id)
    if movie and movie.user_id == current_user.id:
        db.session.delete(movie)
        db.session.commit()
        flash("Movie removed.", "success")
    return redirect(url_for("collection", tab="movies"))


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
    try:
        r = requests.get("https://www.googleapis.com/books/v1/volumes",
                         params={"q": title, "maxResults": 12}, timeout=8)
        data = r.json()
    except Exception:
        flash("Could not reach Google Books API. Please try again.", "error")
        return redirect(url_for("add_book"))

    items = []
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
        return redirect(url_for("collection", tab="books"))

    try:
        r = requests.get(f"https://www.googleapis.com/books/v1/volumes/{book_id}", timeout=8)
        data = r.json()
    except Exception:
        flash("Could not fetch book details. Please try again.", "error")
        return redirect(url_for("add_book"))

    vol = data.get("volumeInfo", {})
    if not vol:
        flash("Book not found. Please try again.", "error")
        return redirect(url_for("add_book"))

    year = (vol.get("publishedDate") or "")[:4]
    authors = ", ".join(vol.get("authors", ["Unknown"]))
    thumb = ""
    if "imageLinks" in vol:
        thumb = vol["imageLinks"].get("thumbnail", "").replace("http://", "https://")
    categories = ", ".join(vol.get("categories", []))

    new_book = Book(
        user_id=current_user.id,
        google_id=book_id,
        title=vol.get("title", "Unknown"),
        author=authors,
        year=year,
        rating=0.0,
        description=(vol.get("description") or "")[:1000],
        genre=categories,
        img_url=thumb,
        status=status,
        date_read=date.today() if status == "read" else None,
    )
    db.session.add(new_book)
    db.session.commit()

    if status == "to_read":
        flash(f'"{new_book.title}" added to your reading list!', "success")
        return redirect(url_for("collection", tab="books"))
    return redirect(url_for("edit_book", book_id=new_book.id))


@app.route("/edit_book/<int:book_id>", methods=["GET", "POST"])
@login_required
def edit_book(book_id):
    book = db.session.get(Book, book_id)
    if not book or book.user_id != current_user.id:
        return redirect(url_for("collection"))
    class EditForm(FlaskForm):
        title = StringField("Title", validators=[DataRequired()])
        rating = StringField("Your Rating (0–10)")
        custom_tags = StringField("Custom Tags (comma separated)")
        review = TextAreaField("Your Review")
        description = TextAreaField("Synopsis")
        status = SelectField("Status", choices=[("to_read", "📖 To Read"), ("read", "✅ Read")])
        submit = SubmitField("Save")
    form = EditForm()
    if form.validate_on_submit():
        book.title = form.title.data
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
    form.rating.data = str(book.rating)
    form.custom_tags.data = book.custom_tags
    form.review.data = book.review
    form.description.data = book.description
    form.status.data = book.status
    return render_template("edit.html", item=book, form=form, item_type="Book")


@app.route("/delete_book/<int:book_id>")
@login_required
def delete_book(book_id):
    book = db.session.get(Book, book_id)
    if book and book.user_id == current_user.id:
        db.session.delete(book)
        db.session.commit()
        flash("Book removed.", "success")
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
