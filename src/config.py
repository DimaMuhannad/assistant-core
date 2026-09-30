import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file with override
load_dotenv(BASE_DIR / ".env", override=True)

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
_RAW_KEYS = os.getenv("GEMINI_API_KEYS", "")
GEMINI_API_KEYS = [k.strip() for k in _RAW_KEYS.split(",") if k.strip()]
if not GEMINI_API_KEYS and GEMINI_API_KEY:
    GEMINI_API_KEYS = [GEMINI_API_KEY]
if not GEMINI_API_KEY and GEMINI_API_KEYS:
    GEMINI_API_KEY = GEMINI_API_KEYS[0]

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Speech-to-Text (STT) Settings
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_CPU_THREADS = int(os.getenv("WHISPER_CPU_THREADS", "2"))

# Notion Second Brain Settings
NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
NOTION_TASKS_DB_ID = os.getenv("NOTION_TASKS_DB_ID", "")
NOTION_PROJECTS_DB_ID = os.getenv("NOTION_PROJECTS_DB_ID", "")
NOTION_WAITING_DB_ID = os.getenv("NOTION_WAITING_DB_ID", "")
NOTION_JOURNAL_DB_ID = os.getenv("NOTION_JOURNAL_DB_ID", "")

# Mailbox 1: Mail.ru (Personal & University)
MAILRU_EMAIL = os.getenv("MAILRU_EMAIL", "")
MAILRU_PASSWORD = os.getenv("MAILRU_PASSWORD", "")
MAILRU_IMAP_SERVER = os.getenv("MAILRU_IMAP_SERVER", "imap.mail.ru")
MAILRU_IMAP_PORT = int(os.getenv("MAILRU_IMAP_PORT", "993"))
MAILRU_SMTP_SERVER = os.getenv("MAILRU_SMTP_SERVER", "smtp.mail.ru")
MAILRU_SMTP_PORT = int(os.getenv("MAILRU_SMTP_PORT", "587"))

# Mailbox 2: Gmail.com (Services & Personal)
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL", "")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD", "")
GMAIL_IMAP_SERVER = os.getenv("GMAIL_IMAP_SERVER", "imap.gmail.com")
GMAIL_IMAP_PORT = int(os.getenv("GMAIL_IMAP_PORT", "993"))
GMAIL_SMTP_SERVER = os.getenv("GMAIL_SMTP_SERVER", "smtp.gmail.com")
GMAIL_SMTP_PORT = int(os.getenv("GMAIL_SMTP_PORT", "587"))

# Mailbox 3: GUAP Corporate (guap.ru) & LMS pro.guap.ru
GUAP_EMAIL = os.getenv("GUAP_EMAIL", "")
GUAP_PASSWORD = os.getenv("GUAP_PASSWORD", "")
GUAP_LK_PASSWORD = os.getenv("GUAP_LK_PASSWORD", "")
GUAP_IMAP_SERVER = os.getenv("GUAP_IMAP_SERVER", "mail.guap.ru")
GUAP_IMAP_PORT = int(os.getenv("GUAP_IMAP_PORT", "993"))
GUAP_SMTP_SERVER = os.getenv("GUAP_SMTP_SERVER", "mail.guap.ru")
GUAP_SMTP_PORT = int(os.getenv("GUAP_SMTP_PORT", "587"))


