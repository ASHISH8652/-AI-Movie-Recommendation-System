# CineMatch — Personalized Movie / TV / Anime / K-Drama Recommender

<div align="center">

# 🎬 CineMatch
### AI-Powered Personalized Movie, TV, Anime & K-Drama Recommender

<img src="https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python"/>
<img src="https://img.shields.io/badge/FastAPI-0.115-green?style=for-the-badge&logo=fastapi"/>
<img src="https://img.shields.io/badge/Scikit--Learn-ML-orange?style=for-the-badge&logo=scikitlearn"/>
<img src="https://img.shields.io/badge/TMDB-API-01B4E4?style=for-the-badge"/>
<img src="https://img.shields.io/badge/PostgreSQL-Database-blue?style=for-the-badge&logo=postgresql"/>
<img src="https://img.shields.io/badge/Render-Deployed-46E3B7?style=for-the-badge&logo=render&logoColor=black"/>

**A real, self-hosted recommendation engine — not a demo with sample data. Live TMDB data, per-user trained ML models, email OTP login, and it's actually deployed.**

**[🔴 Live App → cinematch-0tab.onrender.com](https://cinematch-0tab.onrender.com)**

</div>

---

## 📌 Features

* ✅ Personalized recommendations from a **real, per-user trained ML model**
* ✅ Email + OTP login — no passwords
* ✅ Live TMDB data — latest releases through classics
* ✅ Movies · TV Shows · Anime · Korean Dramas
* ✅ 25+ languages, including regional Indian languages (Hindi, Odia, Tamil, Telugu, Bengali, Marathi, Gujarati, Kannada, Malayalam, Urdu, Assamese, Punjabi)
* ✅ Mood-based discovery — comedy, action, horror, emotional, thriller, sci-fi, and more
* ✅ Trending-this-week feed
* ✅ Search by title across movies + TV
* ✅ 👍 / 👎 and 1–5 star rating feedback
* ✅ Implicit behavior tracking (what you click into)
* ✅ Automatic model retraining as feedback accumulates
* ✅ Weekly "vibe" breakdown of your own taste patterns
* ✅ SQLite locally, PostgreSQL in production — zero code changes between them

---

## 🧠 How the recommendation engine works

```
                     User Login (Email + OTP)
                              │
                              ▼
                  Browse Movies, TV, Anime, K-Drama
                              │
                              ▼
              Like • Dislike • Star Rating • Click signals
                              │
                              ▼
                Feature Engineering (genre, language,
                 popularity, rating, era, media type)
                              │
                              ▼
          Gradient Boosting Classifier — trained PER USER
                              │
                              ▼
              Personalized Score (0–100) per title
                              │
                              ▼
                  Ranked, Personalized Results
```

Each user's model is completely independent — one person's ratings never influence another person's recommendations. The model retrains automatically once you have 8+ rated titles (with a mix of likes and dislikes), and again every 5 new ratings after that.

---

## 🚀 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Uvicorn |
| Machine Learning | scikit-learn (Gradient Boosting Classifier) |
| Database | SQLAlchemy — SQLite (local) / PostgreSQL (production) |
| Auth | Email + OTP, signed session cookies (`itsdangerous`) |
| Email delivery | Resend HTTP API |
| Movie/TV data | TMDB API |
| Frontend | HTML, vanilla JavaScript, CSS |
| Deployment | Render (Blueprint: web service + managed Postgres) |

---

## 📂 Project Structure

```
.
├── app.py                FastAPI backend — routes, auth, TMDB proxying, scoring
├── auth.py                OTP generation/verification + Resend email + session cookies
├── tmdb_client.py          TMDB API wrapper (key never reaches the browser)
├── db.py                    SQLAlchemy models — users, OTP codes, per-user feedback
├── recommender.py            Feature engineering + per-user model training/scoring
├── static/
│   └── index.html               Frontend — login gate + the app
├── data/                          SQLite file when running locally (gitignored)
├── models/                         Per-user trained models + metadata (gitignored)
├── requirements.txt
├── render.yaml                      Render Blueprint (web service + Postgres)
├── Procfile                          For Railway/Heroku-style platforms
├── .env.example
└── .env                                Local secrets (gitignored, never committed)
```

---

## ⚙️ Run it locally

Requires Python 3.10+.

```bash
git clone https://github.com/ASHISH8652/-AI-Movie-Recommendation-System.git
cd -AI-Movie-Recommendation-System

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Environment variables

Create a `.env` file in the project root:

```env
TMDB_API_KEY=your_tmdb_api_key
SESSION_SECRET=any_long_random_string

# Email OTP delivery (Resend — https://resend.com)
RESEND_API_KEY=your_resend_api_key
RESEND_FROM=CineMatch <onboarding@resend.dev>

# Leave unset locally — defaults to a SQLite file in ./data/
# DATABASE_URL=
```

> Why Resend instead of Gmail SMTP? Most free-tier hosts (Render included) block outbound SMTP ports entirely — Resend's HTTP API runs over standard HTTPS, which is never blocked, so it works identically in local dev and in production.

### Run

```bash
uvicorn app:app --reload --port 8000
```

Open **http://localhost:8000** → enter your email → get a code → you're in.

---

## 🎯 Train your model

1. Open a few titles — this alone logs a weak "interested" signal.
2. Use 👍 / 👎 or the star rating — these are strong signals.
3. Once you have **8+ rated titles** with a mix of likes/dislikes, your personal model trains automatically. It retrains every 5 new ratings after that.
4. Force a retrain any time with **"Retrain now"** under "Your Model" in the app.

---

## 🌐 Deployment (Render)

This repo ships with a `render.yaml` Blueprint — Render reads it and provisions both the web service and a free PostgreSQL database in one step.

1. Push this repo to GitHub.
2. **Render Dashboard → Blueprints → New Blueprint Instance** → connect this repo.
3. Fill in the requested secrets: `TMDB_API_KEY`, `RESEND_API_KEY`. (`SESSION_SECRET` and `DATABASE_URL` are generated/wired automatically.)
4. Click **Apply** — Render builds and deploys automatically on every push to `main`.

**Build command:** `pip install -r requirements.txt`
**Start command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`

### Honest caveat

Render's free web service disk isn't persistent across redeploys — your Postgres data (users, ratings, full history) is completely safe since it lives in the database, but a trained model file can get wiped on a redeploy. If that happens, one click on **"Retrain now"** rebuilds it instantly from your ratings, which are always safe in Postgres.

---

## 📊 Roadmap

- [ ] Verified sending domain (let any user receive OTPs, not just the account owner)
- [ ] Collaborative filtering across users, on top of the per-user model
- [ ] Watchlist / saved-for-later
- [ ] "Why this was recommended" explanation per title
- [ ] Social login (Google/GitHub)
- [ ] PWA / mobile wrapper

---
---

# 📊 Future Improvements

- Deep Learning Recommendation Engine
- Collaborative Filtering
- Hybrid Recommendation System
- Movie Trailer Integration
- Voice Search
- Watchlist
- Recommendation Explanation
- Social Login
- Mobile App

---
## 🌐 Live Demo

**Live Application:** [https://your-app.onrender.com](https://cinematch-0tab.onrender.com/)
## 👨‍💻 Developer

**Ashish Kumar Prusty**
AI & Machine Learning Engineer · 
📍 Odisha, India

[GitHub](https://github.com/ASHISH8652) · [LinkedIn](https://www.linkedin.com/in/ashish-kumar-prusty-7947ba263/)

---

## 📄 License

MIT License.

<div align="center">



### ⭐ If you found this project useful, please consider giving it a Star ⭐

Made with ❤️ by **Ashish Kumar Prusty**

</div>


