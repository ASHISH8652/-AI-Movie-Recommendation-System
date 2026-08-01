"""
Trains a real scikit-learn model PER USER on their own feedback:
  - explicit likes / dislikes (weight 1.0)
  - explicit 1-5 star ratings (>=4 -> positive, <=2 -> negative, 3 -> skipped)
  - implicit "opened this title" clicks (weight 0.35, weak positive)
combined with TMDB's public signals (genres, rating, popularity, language, era)
as the feature set. Retrains automatically as feedback accumulates.

Until a given user has enough data (>=8 labeled examples with both classes present),
that user falls back to a plain content-popularity score.
"""
import json
import math
import os
from datetime import datetime, timezone

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

import db as dbmod

# Fixed, deterministic genre vocabulary so feature vectors are stable across retrains.
GENRE_VOCAB = [
    28, 12, 16, 35, 80, 99, 18, 10751, 14, 36, 27, 10402, 9648, 10749, 878,
    10770, 53, 10752, 37, 10759, 10762, 10763, 10764, 10765, 10766, 10767, 10768,
]

# Expanded language vocabulary — major world + Indian regional languages.
LANG_VOCAB = [
    "en", "hi", "ko", "ja", "es", "ta", "te", "zh", "fr", "de", "pa", "bn",
    "it", "pt", "or", "mr", "gu", "kn", "ml", "ur", "as", "ar", "ru", "th", "vi", "id",
]

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODEL_DIR, exist_ok=True)

MIN_SAMPLES = 8


def _paths(user_id: int):
    return (
        os.path.join(MODEL_DIR, f"user_{user_id}_model.joblib"),
        os.path.join(MODEL_DIR, f"user_{user_id}_meta.json"),
    )


def featurize(genre_ids, original_language, vote_average, popularity, release_year, media_type) -> np.ndarray:
    genre_ids = genre_ids or []
    g = [1.0 if gid in genre_ids else 0.0 for gid in GENRE_VOCAB]
    lang = original_language if original_language in LANG_VOCAB else None
    l = [1.0 if lang == code else 0.0 for code in LANG_VOCAB]
    l.append(1.0 if lang is None else 0.0)  # "other language" bucket
    vote = (vote_average or 0.0) / 10.0
    pop = min(math.log1p(popularity or 0.0) / 8.0, 1.0)
    year = release_year or 2015
    year_norm = min(max((year - 1950) / (2026 - 1950), 0.0), 1.0)
    media_flag = 1.0 if media_type == "tv" else 0.0
    return np.array(g + l + [vote, pop, year_norm, media_flag], dtype=float)


def _label_and_weight(row: dict):
    signal = row["signal"]
    if signal == "like":
        return 1, 1.0
    if signal == "dislike":
        return 0, 1.0
    if signal == "rating":
        rv = row["rating_value"] or 3
        if rv >= 4:
            return 1, 1.0
        if rv <= 2:
            return 0, 1.0
        return None, None
    if signal == "click":
        return 1, 0.35
    return None, None


def build_training_set(user_id: int):
    rows = dbmod.all_feedback(user_id)
    X, y, w = [], [], []
    for row in rows:
        label, weight = _label_and_weight(row)
        if label is None:
            continue
        genre_ids = json.loads(row["genre_ids"]) if row["genre_ids"] else []
        feat = featurize(
            genre_ids, row["original_language"], row["vote_average"],
            row["popularity"], row["release_year"], row["media_type"],
        )
        X.append(feat)
        y.append(label)
        w.append(weight)
    return np.array(X), np.array(y), np.array(w)


def train(user_id: int) -> dict:
    model_path, meta_path = _paths(user_id)
    X, y, w = build_training_set(user_id)

    if len(y) < MIN_SAMPLES or len(set(y.tolist())) < 2:
        meta = {
            "trained": False,
            "n_samples": int(len(y)),
            "reason": f"Need at least {MIN_SAMPLES} labeled titles (likes/dislikes/ratings), with a mix of both.",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f)
        return meta

    model = GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.08)
    model.fit(X, y, sample_weight=w)
    joblib.dump(model, model_path)

    importances = model.feature_importances_
    top_idx = np.argsort(importances[: len(GENRE_VOCAB)])[::-1][:5]
    meta = {
        "trained": True,
        "n_samples": int(len(y)),
        "top_genre_ids": [GENRE_VOCAB[i] for i in top_idx],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f)
    return meta


def load_model(user_id: int):
    model_path, _ = _paths(user_id)
    if not os.path.exists(model_path):
        return None
    return joblib.load(model_path)


def status(user_id: int) -> dict:
    _, meta_path = _paths(user_id)
    if not os.path.exists(meta_path):
        return {"trained": False, "n_samples": 0, "reason": "No feedback yet — like, dislike, or rate a few titles."}
    with open(meta_path) as f:
        return json.load(f)


def score_item(item: dict, model=None) -> dict:
    vote = item.get("vote_average", 0) or 0
    pop = item.get("popularity", 0) or 0
    pop_score = min(pop / 300, 1.0) * 100
    base = vote * 10 * 0.7 + pop_score * 0.3
    base = max(1, min(round(base), 100))

    if model is None:
        return {"entertainment_score": base, "personalized_score": None}

    year = None
    date_str = item.get("release_date") or item.get("first_air_date")
    if date_str:
        try:
            year = int(date_str[:4])
        except (ValueError, TypeError):
            year = None

    feat = featurize(
        item.get("genre_ids", []), item.get("original_language"),
        vote, pop, year, item.get("media_type", "movie"),
    )
    proba = model.predict_proba(feat.reshape(1, -1))[0][1]
    return {"entertainment_score": base, "personalized_score": round(float(proba) * 100)}
