"""Register, log in and log out."""
import re

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db, limiter
from models import User

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD, MAX_PASSWORD = 10, 128
DUMMY_HASH = generate_password_hash("not-a-real-password")   # makes unknown emails take as long as real ones


def safe_next(target):
    """Only allow redirects to pages on this site."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return None


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    nxt = safe_next(request.values.get("next"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        error = None
        if not EMAIL_RE.match(email) or len(email) > 254:
            error = "Enter a valid email address."
        elif len(password) < MIN_PASSWORD:
            error = f"Use a password with at least {MIN_PASSWORD} characters."
        elif len(password) > MAX_PASSWORD:
            error = f"Use a password with at most {MAX_PASSWORD} characters."
        elif password != (request.form.get("confirm") or ""):
            error = "The two passwords do not match."
        elif User.query.filter_by(email=email).first():
            error = "That email is already registered. Try logging in."
        if not error:
            user = User(email=email, password_hash=generate_password_hash(password))
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:           # two sign-ups at the same moment
                db.session.rollback()
                error = "That email is already registered. Try logging in."
            else:
                login_user(user)
                return redirect(nxt or url_for("index"))
        flash(error, "error")
        return render_template("register.html", email=email, next=nxt), 400
    return render_template("register.html", next=nxt)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    nxt = safe_next(request.values.get("next"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        ok = check_password_hash(user.password_hash if user else DUMMY_HASH, password[:MAX_PASSWORD])
        if user and ok:
            login_user(user, remember=bool(request.form.get("remember")))
            return redirect(nxt or url_for("index"))
        flash("Wrong email or password.", "error")      # same message for both, so emails cannot be guessed
        return render_template("login.html", email=email, next=nxt), 401
    return render_template("login.html", next=nxt)


@bp.post("/logout")
def logout():
    logout_user()
    return redirect(url_for("index"))
