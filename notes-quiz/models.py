"""Database tables. Every saved item belongs to a user, and deleting a user deletes everything they own."""
from flask_login import UserMixin
from sqlalchemy import CheckConstraint, Index, func
from sqlalchemy.dialects.postgresql import JSONB

from extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), nullable=False, unique=True)      # stored in lowercase
    password_hash = db.Column(db.String(255), nullable=False)           # never the real password
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())


class Lesson(db.Model):
    """The notes a user pasted or uploaded. Reviewers and quizzes are made from a lesson."""
    __tablename__ = "lessons"
    __table_args__ = (Index("ix_lessons_user_created", "user_id", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    notes_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())


class Reviewer(db.Model):
    __tablename__ = "reviewers"
    __table_args__ = (Index("ix_reviewers_user_created", "user_id", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    topics = db.Column(JSONB, nullable=False)                           # [{topic, definition, example}]
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())


class Quiz(db.Model):
    __tablename__ = "quizzes"
    __table_args__ = (Index("ix_quizzes_user_created", "user_id", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    questions = db.Column(JSONB, nullable=False)
    question_count = db.Column(db.Integer, nullable=False)              # so the library list needs no JSON
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())


class Attempt(db.Model):
    """One time a user took a quiz."""
    __tablename__ = "attempts"
    __table_args__ = (
        CheckConstraint("total > 0 AND score >= 0 AND score <= total", name="ck_attempts_score_range"),
        Index("ix_attempts_user_created", "user_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Integer, nullable=False)
    answers = db.Column(JSONB, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
