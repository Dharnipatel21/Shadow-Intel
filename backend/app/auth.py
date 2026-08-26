"""Email/password + Google OAuth authentication for ShadowIntel."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import smtplib, ssl, secrets, uuid
from email.message import EmailMessage

import jwt
import bcrypt
from fastapi import HTTPException

from . import config, store


def init_auth():
    c = store.conn()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS users(
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            password_hash TEXT,
            name TEXT,
            provider TEXT DEFAULT 'password',
            is_verified INTEGER DEFAULT 0,
            verify_token TEXT,
            otp_code TEXT,
            otp_expires TEXT,
            created_at TEXT
        );
        """
    )
    for column in ("otp_code TEXT", "otp_expires TEXT"):
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {column}")
        except Exception:
            pass
    c.commit()
    c.close()


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()

def verify_password(p: str, hashed: str) -> bool:
    return bcrypt.checkpw(p.encode(), hashed.encode())


def create_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=config.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")


def get_user_by_email(email: str):
    return store.one("SELECT * FROM users WHERE email=?", email)


def generate_otp() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def create_user(email: str, password: str | None, name: str, provider: str = "password"):
    uid = f"U-{uuid.uuid4().hex[:10]}"
    verify_token = secrets.token_urlsafe(24)
    otp_code = generate_otp()
    otp_expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    c = store.conn()
    c.execute(
        "INSERT INTO users VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            uid, email,
            hash_password(password) if password else None,
            name, provider,
            0 if provider == "password" else 1,
            verify_token, otp_code, otp_expires, store.now(),
        ),
    )
    c.commit()
    c.close()
    return uid, verify_token, otp_code


def send_verification_email(to_email: str, token: str):
    if not config.smtp_enabled():
        raise HTTPException(501, "SMTP is not configured (SMTP_USER/SMTP_PASSWORD missing).")
    link = f"{config.FRONTEND_BASE_URL}/verify?token={token}"
    msg = EmailMessage()
    msg["Subject"] = "Verify your ShadowIntel account"
    msg["From"] = config.SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg.set_content(f"Click to verify your ShadowIntel account:\n\n{link}")
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)


def send_otp_email(to_email: str, code: str):
    if not config.smtp_enabled():
        raise HTTPException(501, "SMTP is not configured (SMTP_USER/SMTP_PASSWORD missing).")
    msg = EmailMessage()
    msg["Subject"] = "Your ShadowIntel verification code"
    msg["From"] = config.SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg.set_content(f"Your ShadowIntel verification code is: {code}\n\nThis code expires in 10 minutes.")
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)


def verify_otp(email: str, code: str):
    user = get_user_by_email(email)
    if not user:
        raise HTTPException(404, "No account found for this email.")
    if user["is_verified"]:
        return user
    if not user["otp_code"] or user["otp_code"] != code:
        raise HTTPException(400, "Invalid verification code.")
    if not user["otp_expires"] or datetime.fromisoformat(user["otp_expires"]) < datetime.now(timezone.utc):
        raise HTTPException(400, "Verification code expired. Request a new one.")
    c = store.conn()
    c.execute("UPDATE users SET is_verified=1, otp_code=NULL, otp_expires=NULL WHERE email=?", (email,))
    c.commit()
    c.close()
    return get_user_by_email(email)


def regenerate_otp(email: str):
    user = get_user_by_email(email)
    if not user:
        raise HTTPException(404, "No account found for this email.")
    code = generate_otp()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    c = store.conn()
    c.execute("UPDATE users SET otp_code=?, otp_expires=? WHERE email=?", (code, expires, email))
    c.commit()
    c.close()
    return code


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

def google_login_url(state: str) -> str:
    if not config.google_oauth_enabled():
        raise HTTPException(501, "Google OAuth is not configured.")
    import urllib.parse
    params = {
        "client_id": config.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": config.GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

def google_exchange_code(code: str) -> dict:
    import httpx
    data = {
        "code": code,
        "client_id": config.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": config.GOOGLE_OAUTH_CLIENT_SECRET,
        "redirect_uri": config.GOOGLE_OAUTH_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    r = httpx.post(GOOGLE_TOKEN_URL, data=data, timeout=10)
    if r.status_code != 200:
        raise HTTPException(401, f"Google token exchange failed: {r.text}")
    access_token = r.json()["access_token"]
    userinfo = httpx.get(
        GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=10
    ).json()
    return userinfo