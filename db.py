"""
SQLAlchemy models for users, OTP codes, and per-user feedback.
Uses SQLite by default (zero config, local dev) and Postgres in production
when DATABASE_URL is set (e.g. by Render/Railway).
"""
import os
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
)
from sqlalchemy.orm import declarative_base, sessionmaker

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(DATA_DIR, 'cinematch.db')}")
# Some hosts (Render/Heroku) hand out "postgres://" — SQLAlchemy 2.x wants "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class OtpCode(Base):
    __tablename__ = "otp_codes"
    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False, index=True)
    code_hash = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    consumed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tmdb_id = Column(Integer, nullable=False)
    media_type = Column(String, nullable=False)
    title = Column(String)
    genre_ids = Column(Text)               # JSON-encoded list[int]
    original_language = Column(String)
    vote_average = Column(Float)
    popularity = Column(Float)
    release_year = Column(Integer)
    runtime = Column(Integer)
    signal = Column(String, nullable=False)  # click | like | dislike | rating
    rating_value = Column(Float)
    mood_context = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session():
    return SessionLocal()


# ---------- users ----------

def get_or_create_user(email: str) -> User:
    s = get_session()
    try:
        user = s.query(User).filter_by(email=email).first()
        if not user:
            user = User(email=email)
            s.add(user)
            s.commit()
            s.refresh(user)
        return user
    finally:
        s.close()


# ---------- otp ----------

def create_otp(email: str, code_hash: str, expires_at: datetime) -> None:
    s = get_session()
    try:
        s.add(OtpCode(email=email, code_hash=code_hash, expires_at=expires_at))
        s.commit()
    finally:
        s.close()


def latest_otp(email: str):
    s = get_session()
    try:
        row = (
            s.query(OtpCode)
            .filter_by(email=email, consumed=False)
            .order_by(OtpCode.created_at.desc())
            .first()
        )
        if row:
            s.expunge(row)
        return row
    finally:
        s.close()


def mark_otp_consumed(otp_id: int) -> None:
    s = get_session()
    try:
        row = s.get(OtpCode, otp_id)
        if row:
            row.consumed = True
            s.commit()
    finally:
        s.close()


# ---------- feedback ----------

def insert_feedback(user_id: int, row: dict) -> int:
    s = get_session()
    try:
        s.add(Feedback(user_id=user_id, **row))
        s.commit()
        total = s.query(Feedback).filter_by(user_id=user_id).count()
        return total
    finally:
        s.close()


def all_feedback(user_id: int) -> list[dict]:
    s = get_session()
    try:
        rows = (
            s.query(Feedback)
            .filter_by(user_id=user_id)
            .order_by(Feedback.created_at.asc())
            .all()
        )
        return [
            {
                "tmdb_id": r.tmdb_id, "media_type": r.media_type, "title": r.title,
                "genre_ids": r.genre_ids, "original_language": r.original_language,
                "vote_average": r.vote_average, "popularity": r.popularity,
                "release_year": r.release_year, "runtime": r.runtime,
                "signal": r.signal, "rating_value": r.rating_value,
                "mood_context": r.mood_context,
            }
            for r in rows
        ]
    finally:
        s.close()


def weekly_vibe(user_id: int, week_start: datetime) -> list[dict]:
    s = get_session()
    try:
        rows = (
            s.query(Feedback.mood_context, Feedback.id)
            .filter(
                Feedback.user_id == user_id,
                Feedback.mood_context.isnot(None),
                Feedback.mood_context != "",
                Feedback.created_at >= week_start,
            )
            .all()
        )
        counts: dict[str, int] = {}
        for mood, _id in rows:
            counts[mood] = counts.get(mood, 0) + 1
        return [{"mood_context": k, "c": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]
    finally:
        s.close()
