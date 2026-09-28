import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(BASE_DIR / ".env")

TZ = os.getenv("TZ", "Europe/Moscow")
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/assistant.db")
# If DATABASE_URL uses sqlite+aiosqlite:/// or sqlite:/// extract relative or absolute file path
SQLITE_DB_PATH = DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
if not os.path.isabs(SQLITE_DB_PATH):
    SQLITE_DB_PATH = str(BASE_DIR / SQLITE_DB_PATH)

SCHEDULE_URL = os.getenv("SCHEDULE_URL", "https://guap.ru/rasp")
SCHEDULE_TARGET_ID = os.getenv("SCHEDULE_TARGET_ID", "2903")
SCHEDULE_PARAM_NAME = os.getenv("SCHEDULE_PARAM_NAME", "pr")
SCHEDULE_POLL_INTERVAL_HOURS = int(os.getenv("SCHEDULE_POLL_INTERVAL_HOURS", "2"))
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "./credentials.json")
GOOGLE_TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "./token.json")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID", "")
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0")) if os.getenv("TELEGRAM_API_ID") else None
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION_PATH = os.getenv("TELEGRAM_SESSION_PATH", "./data/assistant_worker.session")
if not os.path.isabs(TELEGRAM_SESSION_PATH):
    TELEGRAM_SESSION_PATH = str(BASE_DIR / TELEGRAM_SESSION_PATH)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")



