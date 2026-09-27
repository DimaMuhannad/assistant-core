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

SCHEDULE_URL = os.getenv("SCHEDULE_URL", "https://rasp.guap.ru/")
SCHEDULE_TARGET_ID = os.getenv("SCHEDULE_TARGET_ID", "1234")
SCHEDULE_POLL_INTERVAL_HOURS = int(os.getenv("SCHEDULE_POLL_INTERVAL_HOURS", "2"))
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
