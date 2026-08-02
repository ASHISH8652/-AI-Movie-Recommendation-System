"""
Email + OTP authentication.
- OTP codes are 6 digits, hashed before storage (never stored in plaintext), expire in 10 minutes.
- Sessions are a signed cookie (itsdangerous) -- no server-side session store needed.
- Sending uses Resend's HTTP API (https://resend.com) instead of raw SMTP, because
  most free-tier cloud hosts (Render included) block outbound SMTP ports entirely.
  HTTP over 443 is never blocked, which is why this approach is reliable in production.
"""
import hashlib
import os
import random

import requests
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me-in-production")
_serializer = URLSafeTimedSerializer(SESSION_SECRET)
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

OTP_TTL_MINUTES = 10


def generate_otp() -> str:
    return f"{random.randint(0, 999999):06d}"


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode()).hexdigest()


def send_otp_email(to_email: str, code: str) -> None:
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not set in .env")

    sender = os.getenv("RESEND_FROM", "CineMatch <onboarding@resend.dev>")

    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "from": sender,
            "to": [to_email],
            "subject": f"{code} is your CineMatch verification code",
            "text": (
                f"Your CineMatch verification code is: {code}\n\n"
                f"It expires in {OTP_TTL_MINUTES} minutes. If you didn't request this, ignore this email."
            ),
        },
        timeout=15,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Resend API error ({resp.status_code}): {resp.text}")


def make_session_token(user_id: int, email: str) -> str:
    return _serializer.dumps({"uid": user_id, "email": email})


def read_session_token(token: str):
    try:
        return _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None