"""Runtime configuration. Secrets come from environment variables (or backend/.env), never from the frontend."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("QCHAIN_DATABASE_URL", f"sqlite:///{(BASE_DIR / 'qchain.db').as_posix()}")
MODEL_PATH = Path(os.getenv("QCHAIN_MODEL_PATH", str(BASE_DIR / "app" / "ml" / "shelf_life_model.joblib")))

# Signing secret for session tokens. The default is for local demo use only.
AUTH_SECRET = os.getenv("QCHAIN_AUTH_SECRET", "dev-only-change-me")
TOKEN_TTL_HOURS = int(os.getenv("QCHAIN_TOKEN_TTL_HOURS", "12"))

# Key that simulated IoT gateways use to push readings to /api/sensors/ingest.
DEVICE_API_KEY = os.getenv("QCHAIN_DEVICE_API_KEY", "demo-device-key")

# LLM explanation layer (optional). Without a key the deterministic template explainer is used.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AGENT_MODEL = os.getenv("QCHAIN_AGENT_MODEL", "claude-opus-5")

CORS_ORIGINS = [o.strip() for o in os.getenv("QCHAIN_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]

# The demo runs on a fixed simulation clock so every figure is reproducible (Asia/Qatar local time, UTC+3).
DEMO_NOW = datetime.fromisoformat(os.getenv("QCHAIN_DEMO_NOW", "2026-09-25T14:00:00"))
FLEET_SIZE = int(os.getenv("QCHAIN_FLEET_SIZE", "1284"))
RANDOM_SEED = int(os.getenv("QCHAIN_SEED", "4821"))

DEMO_USERS = {
    # username: (password, role, display name)
    "admin": (os.getenv("QCHAIN_ADMIN_PASSWORD", "admin123"), "admin", "Platform Admin"),
    "warehouse": (os.getenv("QCHAIN_WAREHOUSE_PASSWORD", "warehouse123"), "warehouse_manager", "Warehouse Manager"),
    "distributor": (os.getenv("QCHAIN_DISTRIBUTOR_PASSWORD", "distributor123"), "distributor", "Distribution Planner"),
    "retailer": (os.getenv("QCHAIN_RETAILER_PASSWORD", "retailer123"), "retailer", "Retail Buyer"),
}
