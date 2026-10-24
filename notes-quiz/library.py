"""Saving, opening and deleting a user's lessons, reviewers, quizzes and scores.
Every query filters by the logged-in user, so nobody can open another user's data by changing a number in the URL."""
import re

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user
from sqlalchemy import func
from werkzeug.security import check_password_hash

from extensions import db, limiter
from models import Attempt, Lesson, Quiz, Reviewer, User

bp = Blueprint("library", __name__)

MAX_ITEMS = 200          # per user, to protect the free database size
MAX_ATTEMPTS = 2000
TYPES = {"multiple_choice", "true_false", "identification", "enumeration", "fill_in_the_blanks"}


def clip(value, limit):
    return str(value or "").strip()[:limit]


def notes_title(notes):
    line = next((l for l in notes.splitlines() if l.strip()), "Untitled lesson")
    line = re.sub(r"\s+", " ", line).strip()
    return line if len(line) <= 60 else line[:57] + "..."


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


# ---------------------------------------------------------------- input checks (only known fields are kept)

def clean_topics(raw):
    if not isinstance(raw, list) or len(raw) > 200:
        raise ValueError("Invalid reviewer data.")
    out = []
    for t in raw:
        if not isinstance(t, dict):
            raise ValueError("Invalid reviewer data.")
        topic, definition = clip(t.get("topic"), 200), clip(t.get("definition"), 2000)
        if topic and definition:
            out.append({"topic": topic, "definition": definition, "example": clip(t.get("example"), 2000)})
    if not out:
        raise ValueError("Invalid reviewer data.")
    return out


def clean_questions(raw):
    if not isinstance(raw, list) or not raw or len(raw) > 100:
        raise ValueError("Invalid quiz data.")
    out = []
    for q in raw:
        if not isinstance(q, dict) or q.get("type") not in TYPES:
            raise ValueError("Invalid quiz data.")
        item = {"type": q["type"], "question": clip(q.get("question"), 1000), "answer": clip(q.get("answer"), 1000),
                "explanation": clip(q.get("explanation"), 1000), "evidence": clip(q.get("evidence"), 600)}
        if not item["question"] or not item["answer"]:
            raise ValueError("Invalid quiz data.")
        options = q.get("options")
        if isinstance(options, list) and options:
            if len(options) > 8 or not is_int(q.get("correct")) or not 0 <= q["correct"] < len(options):
                raise ValueError("Invalid quiz data.")
            item["options"] = [clip(o, 500) for o in options]
            item["correct"] = q["correct"]
        elif q["type"] in ("multiple_choice", "true_false"):
            raise ValueError("Invalid quiz data.")
        if q["type"] == "enumeration":
            items = q.get("items")
            if not isinstance(items, list) or not items:
                raise ValueError("Invalid quiz data.")
            item["items"] = [clip(i, 300) for i in items[:20]]
        out.append(item)
    return out


def clean_attempt(data, total):
    score, answers = data.get("score"), data.get("answers")
    if not is_int(score) or not 0 <= score <= total:
        raise ValueError("Invalid score.")
    if not isinstance(answers, list) or len(answers) != total:
        raise ValueError("Invalid answers.")
    cleaned = []
    for a in answers:
        if a is None or is_int(a):
            cleaned.append(a)
        elif isinstance(a, str):
            cleaned.append(a[:600])
        else:
            raise ValueError("Invalid answers.")
    return score, cleaned


def lesson_for(data):
    """Find the user's lesson (by id) or create one from the notes. Returns (lesson, error)."""
    lesson_id = data.get("lesson_id")
    if lesson_id is not None:
        lesson = Lesson.query.filter_by(id=lesson_id, user_id=current_user.id).first() if is_int(lesson_id) else None
        return (lesson, None) if lesson else (None, "That lesson was not found.")
    notes = str(data.get("notes") or "").strip()
    if not 40 <= len(notes) <= current_app.config["MAX_NOTES_CHARS"]:
        return None, "The notes are missing or too long to save."
    if Lesson.query.filter_by(user_id=current_user.id).count() >= MAX_ITEMS:
        return None, "Your library is full. Delete something first."
    lesson = Lesson(user_id=current_user.id, title=notes_title(notes), notes_text=notes)
    db.session.add(lesson)
    db.session.flush()
    return lesson, None


def prune_lesson(lesson_id):
    """Remove a lesson once it has no reviewer or quiz left."""
    if not Reviewer.query.filter_by(lesson_id=lesson_id).first() and not Quiz.query.filter_by(lesson_id=lesson_id).first():
        Lesson.query.filter_by(id=lesson_id).delete()


# ---------------------------------------------------------------- save and open (JSON API)

@bp.post("/api/save/reviewer")
@login_required
@limiter.limit("30 per minute")
def save_reviewer():
    data = request.get_json(silent=True) or {}
    try:
        topics = clean_topics(data.get("topics"))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if Reviewer.query.filter_by(user_id=current_user.id).count() >= MAX_ITEMS:
        return jsonify(error="Your library is full. Delete something first."), 400
    lesson, error = lesson_for(data)
    if error:
        return jsonify(error=error), 400
    reviewer = Reviewer(lesson_id=lesson.id, user_id=current_user.id, title=clip(data.get("title"), 120) or lesson.title, topics=topics)
    db.session.add(reviewer)
    db.session.commit()
    return jsonify(id=reviewer.id, lesson_id=lesson.id)


@bp.post("/api/save/quiz")
@login_required
@limiter.limit("30 per minute")
def save_quiz():
    data = request.get_json(silent=True) or {}
    try:
        questions = clean_questions(data.get("questions"))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if Quiz.query.filter_by(user_id=current_user.id).count() >= MAX_ITEMS:
        return jsonify(error="Your library is full. Delete something first."), 400
    lesson, error = lesson_for(data)
    if error:
        return jsonify(error=error), 400
    quiz = Quiz(lesson_id=lesson.id, user_id=current_user.id, title=clip(data.get("title"), 120) or lesson.title,
                questions=questions, question_count=len(questions))
    db.session.add(quiz)
    db.session.commit()
    return jsonify(id=quiz.id, lesson_id=lesson.id)


@bp.get("/api/quizzes/<int:quiz_id>")
@login_required
def get_quiz(quiz_id):
    row = (db.session.query(Quiz, Lesson.notes_text).join(Lesson, Quiz.lesson_id == Lesson.id)
           .filter(Quiz.id == quiz_id, Quiz.user_id == current_user.id).first())
    if not row:
        return jsonify(error="Quiz not found."), 404
    quiz, notes = row
    return jsonify(id=quiz.id, lesson_id=quiz.lesson_id, title=quiz.title, questions=quiz.questions, notes=notes)


@bp.get("/api/reviewers/<int:reviewer_id>")
@login_required
def get_reviewer(reviewer_id):
    row = (db.session.query(Reviewer, Lesson.notes_text).join(Lesson, Reviewer.lesson_id == Lesson.id)
           .filter(Reviewer.id == reviewer_id, Reviewer.user_id == current_user.id).first())
    if not row:
        return jsonify(error="Reviewer not found."), 404
    reviewer, notes = row
    return jsonify(id=reviewer.id, lesson_id=reviewer.lesson_id, title=reviewer.title, topics=reviewer.topics, notes=notes)


@bp.post("/api/quizzes/<int:quiz_id>/attempts")
@login_required
@limiter.limit("30 per minute")
def add_attempt(quiz_id):
    quiz = Quiz.query.filter_by(id=quiz_id, user_id=current_user.id).first()
    if not quiz:
        return jsonify(error="Quiz not found."), 404
    if Attempt.query.filter_by(user_id=current_user.id).count() >= MAX_ATTEMPTS:
        return jsonify(error="Too many saved scores. Delete some quizzes first."), 400
    try:
        score, answers = clean_attempt(request.get_json(silent=True) or {}, quiz.question_count)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    attempt = Attempt(quiz_id=quiz.id, user_id=current_user.id, score=score, total=quiz.question_count, answers=answers)
    db.session.add(attempt)
    db.session.commit()
    return jsonify(id=attempt.id)


@bp.patch("/api/attempts/<int:attempt_id>")
@login_required
@limiter.limit("60 per minute")
def update_attempt(attempt_id):
    attempt = Attempt.query.filter_by(id=attempt_id, user_id=current_user.id).first()
    if not attempt:
        return jsonify(error="Score not found."), 404
    try:
        attempt.score, attempt.answers = clean_attempt(request.get_json(silent=True) or {}, attempt.total)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    db.session.commit()
    return jsonify(id=attempt.id)


# ---------------------------------------------------------------- library page, deleting, account

@bp.get("/library")
@login_required
def library():
    uid = current_user.id
    quizzes = (db.session.query(Quiz.id, Quiz.title, Quiz.question_count, Quiz.created_at,
                                func.count(Attempt.id), func.max(Attempt.score * 100.0 / Attempt.total))
               .outerjoin(Attempt, Attempt.quiz_id == Quiz.id).filter(Quiz.user_id == uid)
               .group_by(Quiz.id).order_by(Quiz.created_at.desc()).all())
    reviewers = (db.session.query(Reviewer.id, Reviewer.title, Reviewer.created_at, func.jsonb_array_length(Reviewer.topics))
                 .filter(Reviewer.user_id == uid).order_by(Reviewer.created_at.desc()).all())
    recent = (db.session.query(Attempt.score, Attempt.total, Attempt.created_at, Quiz.title)
              .join(Quiz, Attempt.quiz_id == Quiz.id).filter(Attempt.user_id == uid)
              .order_by(Attempt.created_at.desc()).limit(10).all())
    return render_template("library.html", quizzes=quizzes, reviewers=reviewers, recent=recent)


@bp.get("/library/quiz/<int:quiz_id>")
@login_required
def view_quiz(quiz_id):
    """Read-only page: the saved notes, the questions, and the answers (hidden until you ask)."""
    row = (db.session.query(Quiz, Lesson.notes_text).join(Lesson, Quiz.lesson_id == Lesson.id)
           .filter(Quiz.id == quiz_id, Quiz.user_id == current_user.id).first())
    if not row:
        abort(404)
    quiz, notes = row
    attempts = (Attempt.query.filter_by(quiz_id=quiz.id, user_id=current_user.id)
                .order_by(Attempt.created_at.desc()).limit(10).all())
    return render_template("quiz_view.html", quiz=quiz, notes=notes, attempts=attempts)


@bp.post("/library/quiz/<int:quiz_id>/delete")
@login_required
def delete_quiz(quiz_id):
    quiz = Quiz.query.filter_by(id=quiz_id, user_id=current_user.id).first_or_404()
    lesson_id = quiz.lesson_id
    db.session.delete(quiz)
    db.session.flush()
    prune_lesson(lesson_id)
    db.session.commit()
    flash("Quiz deleted.", "ok")
    return redirect(url_for("library.library"))


@bp.post("/library/reviewer/<int:reviewer_id>/delete")
@login_required
def delete_reviewer(reviewer_id):
    reviewer = Reviewer.query.filter_by(id=reviewer_id, user_id=current_user.id).first_or_404()
    lesson_id = reviewer.lesson_id
    db.session.delete(reviewer)
    db.session.flush()
    prune_lesson(lesson_id)
    db.session.commit()
    flash("Reviewer deleted.", "ok")
    return redirect(url_for("library.library"))


@bp.post("/account/delete")
@login_required
@limiter.limit("5 per hour")
def delete_account():
    if not check_password_hash(current_user.password_hash, request.form.get("password") or ""):
        flash("That password is wrong, so nothing was deleted.", "error")
        return redirect(url_for("library.library"))
    user = db.session.get(User, current_user.id)
    logout_user()
    db.session.delete(user)          # the database removes everything this user owns
    db.session.commit()
    flash("Your account and all saved data were deleted.", "ok")
    return redirect(url_for("auth.login"))
