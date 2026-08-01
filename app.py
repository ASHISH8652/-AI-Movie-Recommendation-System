import json
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

import auth
import db as dbmod
import recommender as rec
import tmdb_client as tmdb

dbmod.init_db()

app = FastAPI(title="CineMatch", description="Personalized movie/TV/anime/K-drama recommender")

BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, "static")
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

MOOD_GENRES = {
    "comedy": {"movie": 35, "tv": 35},
    "action": {"movie": 28, "tv": 10759},
    "fighting": {"movie": 28, "tv": 10759},
    "horror": {"movie": 27, "tv": 9648},
    "emotional": {"movie": 18, "tv": 18},
    "romance": {"movie": 10749, "tv": 10749},
    "thriller": {"movie": 53, "tv": 9648},
    "scifi": {"movie": 878, "tv": 10765},
    "fantasy": {"movie": 14, "tv": 10765},
    "family": {"movie": 10751, "tv": 10751},
    "documentary": {"movie": 99, "tv": 99},
}


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ---------- auth ----------

def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("session")
    if not token:
        return None
    return auth.read_session_token(token)


def require_user(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


class OtpRequest(BaseModel):
    email: str


class OtpVerify(BaseModel):
    email: str
    code: str


@app.post("/api/auth/request-otp")
def request_otp(payload: OtpRequest):
    email = payload.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "Enter a valid email address.")
    code = auth.generate_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=auth.OTP_TTL_MINUTES)
    dbmod.create_otp(email, auth.hash_code(code), expires_at)
    try:
        auth.send_otp_email(email, code)
    except Exception as e:
        # Temporary local fallback: if SMTP isn't configured/working yet, surface the
        # code directly instead of blocking sign-in entirely. Disable by removing
        # DEV_SHOW_OTP from .env once real email sending works.
        if os.getenv("DEV_SHOW_OTP", "").lower() == "true":
            return {"sent": False, "dev_code": code, "email_error": str(e)}
        raise HTTPException(502, f"Could not send the code: {e}")
    return {"sent": True}


@app.post("/api/auth/verify-otp")
def verify_otp(payload: OtpVerify, response: Response):
    email = payload.email.strip().lower()
    otp = dbmod.latest_otp(email)
    if not otp:
        raise HTTPException(400, "No pending code for this email — request a new one.")
    expires_at = otp.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(400, "That code expired — request a new one.")
    if auth.hash_code(payload.code) != otp.code_hash:
        raise HTTPException(400, "Incorrect code.")
    dbmod.mark_otp_consumed(otp.id)
    user = dbmod.get_or_create_user(email)
    token = auth.make_session_token(user.id, user.email)
    response.set_cookie("session", token, httponly=True, samesite="lax", max_age=auth.SESSION_MAX_AGE)
    return {"authenticated": True, "email": user.email}


@app.get("/api/auth/me")
def me(request: Request):
    user = get_current_user(request)
    return {"authenticated": user is not None, "email": user["email"] if user else None}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie("session")
    return {"logged_out": True}


# ---------- movie data + personalization ----------

def era_params(media_type: str, era: str) -> dict:
    date_field = "first_air_date" if media_type == "tv" else "primary_release_date"
    today = datetime.now()
    if era == "latest":
        frm = today.replace(year=today.year - 2)
        return {f"{date_field}.gte": frm.strftime("%Y-%m-%d"), "sort_by": "popularity.desc", "vote_count.gte": 20}
    if era == "classic":
        return {f"{date_field}.lte": "1999-12-31", "sort_by": "vote_average.desc", "vote_count.gte": 150}
    return {"sort_by": "popularity.desc", "vote_count.gte": 30}


@app.get("/api/genres")
def get_genres():
    try:
        return tmdb.genres()
    except Exception as e:
        raise HTTPException(502, f"TMDB request failed: {e}")


@app.get("/api/discover")
def discover(type: str = "movie", mood: str = "", era: str = "latest", lang: str = "", query: str = "",
             user=Depends(require_user)):
    model = rec.load_model(user["uid"])
    try:
        if query:
            data = tmdb.search_multi(query)
            items = [it for it in data.get("results", []) if it.get("media_type") in ("movie", "tv")]

        elif type == "anime":
            extra_tv = {"with_genres": "16", "with_origin_country": "JP"}
            extra_movie = {"with_genres": "16", "with_origin_country": "JP"}
            if mood in MOOD_GENRES:
                extra_tv["with_genres"] += f",{MOOD_GENRES[mood]['tv']}"
            params_tv = {**era_params("tv", era), **extra_tv}
            params_movie = {**era_params("movie", era), **extra_movie}
            if lang:
                params_tv["with_original_language"] = lang
                params_movie["with_original_language"] = lang
            tv_items = [dict(it, media_type="tv") for it in tmdb.discover("tv", params_tv).get("results", [])]
            movie_items = [dict(it, media_type="movie") for it in tmdb.discover("movie", params_movie).get("results", [])]
            items = sorted(tv_items + movie_items, key=lambda x: x.get("popularity", 0), reverse=True)

        elif type == "kdrama":
            params = {**era_params("tv", era), "with_origin_country": "KR"}
            if mood in MOOD_GENRES:
                params["with_genres"] = MOOD_GENRES[mood]["tv"]
            if lang:
                params["with_original_language"] = lang
            items = [dict(it, media_type="tv") for it in tmdb.discover("tv", params).get("results", [])]

        else:
            media_type = "tv" if type == "tv" else "movie"
            params = era_params(media_type, era)
            if mood in MOOD_GENRES:
                params["with_genres"] = MOOD_GENRES[mood][media_type]
            if lang:
                params["with_original_language"] = lang
            items = [dict(it, media_type=media_type) for it in tmdb.discover(media_type, params).get("results", [])]

    except Exception as e:
        raise HTTPException(502, f"TMDB request failed: {e}")

    results = [{**it, **rec.score_item(it, model)} for it in items[:30]]
    if model is not None:
        results.sort(key=lambda r: r.get("personalized_score") or r["entertainment_score"], reverse=True)
    return {"results": results, "personalized": model is not None}


@app.get("/api/trending")
def trending(user=Depends(require_user)):
    model = rec.load_model(user["uid"])
    try:
        data = tmdb.trending()
    except Exception as e:
        raise HTTPException(502, f"TMDB request failed: {e}")
    items = [it for it in data.get("results", []) if it.get("media_type") in ("movie", "tv")]
    results = [{**it, **rec.score_item(it, model)} for it in items[:24]]
    return {"results": results, "personalized": model is not None}


@app.get("/api/details")
def get_details(media_type: str, id: int, user=Depends(require_user)):
    try:
        return tmdb.details(media_type, id)
    except Exception as e:
        raise HTTPException(502, f"TMDB request failed: {e}")


class Feedback(BaseModel):
    tmdb_id: int
    media_type: str
    title: Optional[str] = ""
    genre_ids: Optional[List[int]] = []
    original_language: Optional[str] = ""
    vote_average: Optional[float] = 0
    popularity: Optional[float] = 0
    release_year: Optional[int] = None
    runtime: Optional[int] = None
    signal: str  # click | like | dislike | rating
    rating_value: Optional[float] = None
    mood_context: Optional[str] = ""


@app.post("/api/feedback")
def post_feedback(fb: Feedback, user=Depends(require_user)):
    row = fb.dict()
    row["genre_ids"] = json.dumps(row["genre_ids"] or [])
    total = dbmod.insert_feedback(user["uid"], row)
    retrain_result = None
    if total >= rec.MIN_SAMPLES and total % 5 == 0:
        retrain_result = rec.train(user["uid"])
    return {"stored": True, "total_feedback": total, "retrain_result": retrain_result}


@app.post("/api/model/retrain")
def retrain(user=Depends(require_user)):
    return rec.train(user["uid"])


@app.get("/api/model/status")
def model_status(user=Depends(require_user)):
    return rec.status(user["uid"])


@app.get("/api/vibe")
def vibe(user=Depends(require_user)):
    today = datetime.now(timezone.utc)
    monday = today - timedelta(days=today.weekday())
    week_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return {"counts": dbmod.weekly_vibe(user["uid"], week_start)}
