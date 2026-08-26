"""Central place that reads optional environment variables."""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name, default)
    return v if v not in (None, "") else None

# --- LLM (Groq) ---
GROQ_API_KEY = _env("GROQ_API_KEY")
GROQ_MODEL = _env("GROQ_MODEL", "llama-3.3-70b-versatile")

# --- Auth / JWT ---
JWT_SECRET_KEY = _env("JWT_SECRET_KEY", "dev-insecure-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(_env("JWT_EXPIRE_MINUTES", "1440"))

# --- Explainable hybrid anomaly scoring ---
HYBRID_RISK_RULE_WEIGHT = float(_env("HYBRID_RISK_RULE_WEIGHT", "0.50"))
HYBRID_RISK_ML_WEIGHT = float(_env("HYBRID_RISK_ML_WEIGHT", "0.25"))
HYBRID_RISK_GRAPH_WEIGHT = float(_env("HYBRID_RISK_GRAPH_WEIGHT", "0.25"))

# --- Google OAuth ---
GOOGLE_OAUTH_CLIENT_ID = _env("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_OAUTH_CLIENT_SECRET = _env("GOOGLE_OAUTH_CLIENT_SECRET")
GOOGLE_OAUTH_REDIRECT_URI = _env(
    "GOOGLE_OAUTH_REDIRECT_URI", "http://127.0.0.1:8010/api/auth/google/callback"
)
FRONTEND_BASE_URL = _env("FRONTEND_BASE_URL", "http://localhost:3000")

# --- SMTP (email verification) ---
SMTP_HOST = _env("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(_env("SMTP_PORT", "587"))
SMTP_USER = _env("SMTP_USER")
SMTP_PASSWORD = _env("SMTP_PASSWORD")
SMTP_FROM_EMAIL = _env("SMTP_FROM_EMAIL", SMTP_USER)

def groq_enabled() -> bool:
    return GROQ_API_KEY is not None

def google_oauth_enabled() -> bool:
    return GOOGLE_OAUTH_CLIENT_ID is not None and GOOGLE_OAUTH_CLIENT_SECRET is not None

def smtp_enabled() -> bool:
    return SMTP_USER is not None and SMTP_PASSWORD is not None
