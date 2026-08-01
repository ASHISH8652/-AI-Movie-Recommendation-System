"""
Email + OTP authentication.
- OTP codes are 6 digits, hashed before storage (never stored in plaintext), expire in 10 minutes.
- Sessions are a signed cookie (itsdangerous) — no server-side session store needed.
- Sending uses Gmail SMTP with an App Password (never your real Gmail password).
"""
import hashlib
import os
import random
import smtplib
import socket
import ssl
from email.message import EmailMessage

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
    smtp_email = os.getenv("SMTP_EMAIL")
    smtp_app_password = os.getenv("SMTP_APP_PASSWORD")
    if not smtp_email or not smtp_app_password:
        raise RuntimeError("SMTP_EMAIL / SMTP_APP_PASSWORD are not set in .env")

    msg = EmailMessage()
    msg["Subject"] = f"{code} is your CineMatch verification code"
    msg["From"] = smtp_email
    msg["To"] = to_email
    msg.set_content(
        f"Your CineMatch verification code is: {code}\n\n"
        f"It expires in {OTP_TTL_MINUTES} minutes. If you didn't request this, you can ignore this email."
    )

    context = ssl.create_default_context()

    # Some hosts (Render free tier included) have no outbound IPv6 route.
    # smtp.gmail.com resolves to both A and AAAA records, and smtplib may pick
    # the IPv6 one and fail with "Network is unreachable". Force IPv4 resolution
    # for the duration of this call only; TLS still verifies against the hostname.
    original_getaddrinfo = socket.getaddrinfo

    def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = _ipv4_only_getaddrinfo
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.starttls(context=context)
            server.login(smtp_email, smtp_app_password)
            server.send_message(msg)
    finally:
        socket.getaddrinfo = original_getaddrinfo


def make_session_token(user_id: int, email: str) -> str:
    return _serializer.dumps({"uid": user_id, "email": email})


def read_session_token(token: str):
    try:
        return _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None