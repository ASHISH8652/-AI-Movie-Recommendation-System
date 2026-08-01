# CineMatch — Personalized Movie / TV / Anime / K-Drama Recommender

A real, deployable recommendation app:
- **Live data** from TMDB (latest releases through classics, any language, anime, K-drama, series)
- **Email + OTP login** (no passwords) — each person gets their own account
- **A real trained ML model per user** (scikit-learn `GradientBoostingClassifier`) learning from:
  1. Explicit 👍/👎 and 1–5 star ratings
  2. Implicit behavior (what you click into)
  3. TMDB's public signals (genres, rating, popularity, language, release era)
- Runs locally with zero config (SQLite), or deploys to the real internet with Postgres

---

## 1. Run it locally

Requires Python 3.10+.

```bash
cd cinematch_app
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Set up email login (Gmail App Password)

1. Turn on 2-Step Verification: https://myaccount.google.com/security
2. Create an App Password: https://myaccount.google.com/apppasswords — choose "Mail", any device name
3. Google gives you a 16-character password. Open `.env` and set:
   ```
   SMTP_EMAIL=your_gmail_address@gmail.com
   SMTP_APP_PASSWORD=the_16_char_app_password   (no spaces)
   ```
   (`TMDB_API_KEY` and `SESSION_SECRET` are already filled in for you.)

### Run

```bash
uvicorn app:app --reload --port 8000
```

Open **http://localhost:8000** — you'll land on a login screen, enter your email, get a code, and you're in.

---

## 2. Train your model

The app works immediately with a content-popularity baseline score. To unlock real personalization:

1. Open a few titles (logs a weak "interested" signal automatically).
2. Use 👍 / 👎 or the star rating — these are strong signals.
3. Once **you** have 8+ rated titles with a mix of likes/dislikes, your model trains automatically (and retrains every 5 new ratings after that). Each person's model is separate — your ratings never affect anyone else's recommendations.
4. Force a retrain any time with **"Retrain now"** under "Your Model."

---

## 3. Deploy it for real (Render)

Render's free tier is the simplest path for a FastAPI app like this.

### Option A — one-click Blueprint (fastest)

1. Push this folder to a GitHub repo.
2. Go to https://dashboard.render.com/blueprints → **New Blueprint Instance** → connect your repo. Render reads `render.yaml` and creates both the web service and a free Postgres database automatically.
3. When prompted, fill in the env vars it asks for: `TMDB_API_KEY`, `SMTP_EMAIL`, `SMTP_APP_PASSWORD`. (`SESSION_SECRET` and `DATABASE_URL` are generated/wired automatically.)
4. Click **Apply** — Render builds and deploys. You'll get a URL like `https://cinematch.onrender.com`.

### Option B — manual dashboard setup

1. **Database first:** Dashboard → **New** → **PostgreSQL** → name it `cinematch-db`, free plan → **Create Database**. Copy the **Internal Database URL** once it's ready.
2. **Web service:** Dashboard → **New** → **Web Service** → connect your GitHub repo.
   - Runtime: Python 3
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - Plan: Free
3. Under **Environment**, add:
   - `TMDB_API_KEY` = your TMDB key
   - `SMTP_EMAIL` = your Gmail address
   - `SMTP_APP_PASSWORD` = your 16-char App Password
   - `SESSION_SECRET` = any long random string (or click "Generate")
   - `DATABASE_URL` = the Internal Database URL from step 1
4. **Create Web Service.** First deploy takes a few minutes; after that you have a live URL.

### One honest caveat

Render's **free** web service disk is not persistent across restarts/redeploys — your Postgres data (users, ratings, history) is completely safe since it lives in the database, but a trained model file (`models/user_X_model.joblib`) can get wiped on a redeploy. If that happens, just hit **"Retrain now"** once — it rebuilds instantly from your ratings, which are all still in Postgres. A paid Render instance with a persistent disk (or writing the model bytes into Postgres instead of disk) removes this caveat entirely if it ever bothers you.

---

## Project structure

```
cinematch_app/
├── app.py              FastAPI backend — routes, auth, TMDB proxying, scoring
├── auth.py              OTP generation/verification + signed session cookies
├── tmdb_client.py        TMDB API wrapper (key never reaches the browser)
├── db.py                  SQLAlchemy models: users, OTP codes, per-user feedback
├── recommender.py          Feature engineering + per-user model training/scoring
├── static/index.html        Frontend — login gate + the app
├── data/                     SQLite file when running locally (gitignored)
├── models/                    Per-user trained models + metadata (gitignored)
├── requirements.txt
├── render.yaml                Render Blueprint (web service + Postgres)
├── Procfile                    For Railway/Heroku-style platforms
├── .env                          Your local secrets (gitignored, never commit)
└── .env.example
```
