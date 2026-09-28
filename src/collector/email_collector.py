import os
import re
import json
import logging
import email
from email import policy
from email.utils import parseaddr, parsedate_to_datetime
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from imapclient import IMAPClient
import html2text
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from src import config
from src.storage.db import Database

logger = logging.getLogger(__name__)

# Noise keywords in sender or subject
NOISE_SENDER_PATTERNS = [
    r"no[-_]?reply",
    r"bounce",
    r"promo",
    r"newsletter",
    r"notification@",
    r"mailer-daemon",
    r"marketing",
    r"adv@",
    r"inform@",
]

NOISE_SUBJECT_PATTERNS = [
    r"скидк[аи]",
    r"акци[яи]",
    r"распродаж[ае]",
    r"кассовый чек",
    r"электронный чек",
    r"код подтверждения",
    r"пароль для входа",
    r"ваш заказ",
    r"доставка заказа",
    r"специальное предложение",
    r"black friday",
]

STUDENT_GROUP_PATTERNS = [
    r"\b[1-4]\d{3}[а-яa-z]?\b",  # e.g. 2815, 4118, 1121, 2033
    r"групп[аы]",
    r"старост",
    r"лабораторн",
    r"отчет",
    r"допуск",
    r"практик",
    r"курсов",
    r"физик[ае]",
    r"опд",
]

DEPT_PATTERNS = [
    r"кафедр",
    r"деканат",
    r"дирекц",
    r"ректорат",
    r"ученый совет",
    r"приказ",
    r"совещани",
    r"положение",
    r"эффективн.*контракт",
]

MONTHS_RU = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "мая": 5,
    "июн": 6, "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}


def get_user_emails() -> list[str]:
    """Return normalized list of Dmitry's active email addresses."""
    candidates = [config.MAILRU_EMAIL, config.GUAP_EMAIL, config.GMAIL_EMAIL]
    return [e.lower().strip() for e in candidates if e and e.strip()]


def extract_deadline(text: str, default_year: int = 2026) -> datetime | None:
    """Extract explicit deadline date from text if mentioned (e.g. 'до 24.09.26', 'к 15 октября')."""
    if not text:
        return None
    # Pattern 1: до 24.09.26 or до 24.09.2026 or до 24.09
    m = re.search(r"(?:до|к|срок(?:ом)?(?:\s+до)?)\s+(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?", text, re.IGNORECASE)
    if m:
        day, month, year_str = int(m.group(1)), int(m.group(2)), m.group(3)
        if year_str:
            year = int(year_str)
            if year < 100:
                year += 2000
        else:
            year = default_year
        try:
            return datetime(year, month, day, 23, 59, 59, tzinfo=timezone.utc)
        except Exception:
            pass

    # Pattern 2: до 24 сентября
    m2 = re.search(r"(?:до|к|срок(?:ом)?(?:\s+до)?)\s+(\d{1,2})\s+([а-яё]{3,8})(?:\s+(\d{4}))?", text, re.IGNORECASE)
    if m2:
        day = int(m2.group(1))
        m_str = m2.group(2).lower()[:3]
        year = int(m2.group(3)) if m2.group(3) else default_year
        if m_str in MONTHS_RU:
            try:
                return datetime(year, MONTHS_RU[m_str], day, 23, 59, 59, tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def calculate_relevance(date_sent: datetime, deadline: datetime | None, now: datetime | None = None) -> tuple[float, bool]:
    """Calculate date relevance score and expiration status.
    
    Returns: (relevance_score, is_expired)
    """
    now = now or datetime.now(timezone.utc)
    if date_sent.tzinfo is None:
        date_sent = date_sent.replace(tzinfo=timezone.utc)

    if deadline:
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if deadline < now:
            return 0.05, True
        days_left = (deadline - now).total_seconds() / 86400.0
        if days_left <= 1:
            return 1.5, False
        if days_left <= 3:
            return 1.3, False
        return 1.1, False

    age_days = (now - date_sent).total_seconds() / 86400.0
    if age_days <= 1:
        return 1.0, False
    if age_days <= 3:
        return 0.9, False
    if age_days <= 7:
        return 0.75, False
    if age_days <= 14:
        return 0.5, False
    if age_days <= 30:
        return 0.25, False
    return 0.05, True


class EmailCollector:
    """Multi-account email collector and ingestion engine."""

    def __init__(self, db: Database | None = None):
        self.db = db or Database(config.SQLITE_DB_PATH)
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = True
        self.html_converter.body_width = 0

    def clean_subject_for_thread(self, subject: str | None) -> str:
        """Normalize subject to compute thread identifier."""
        if not subject:
            return "no_subject"
        cleaned = re.sub(r"^(re|fwd|fw|на|re\[\d+\]):\s*", "", subject, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s+", " ", cleaned).lower()
        return cleaned

    def classify_email(self, sender_email: str, subject: str, raw_msg: Any | None = None) -> tuple[str, bool]:
        """Classify email into category and determine if it's noise.
        
        Returns: (category, is_noise)
        """
        sender_lower = (sender_email or "").lower()
        subject_lower = (subject or "").lower()

        # 1. Noise check
        for pattern in NOISE_SENDER_PATTERNS:
            if re.search(pattern, sender_lower):
                return "noise", True
        for pattern in NOISE_SUBJECT_PATTERNS:
            if re.search(pattern, subject_lower):
                return "noise", True

        # Check list-unsubscribe header
        if raw_msg and hasattr(raw_msg, "get") and raw_msg.get("List-Unsubscribe"):
            return "newsletter", True

        # 2. Service check (prioritize known technical services over keywords)
        if any(s in sender_lower for s in ["github.com", "google.com", "spacecore", "hetzner", "yandex.ru", "telegram", "gitlab"]):
            if "nov-jliana" in sender_lower:
                return "guap_dept", False
            return "service", False

        # 3. GUAP Student check
        if "@stud.guap.ru" in sender_lower:
            return "guap_student", False
        for pattern in STUDENT_GROUP_PATTERNS:
            if re.search(pattern, subject_lower, re.IGNORECASE):
                return "guap_student", False

        # 4. GUAP Department check
        if "@guap.ru" in sender_lower or "@aanet.ru" in sender_lower or "nov-jliana" in sender_lower:
            return "guap_dept", False
        for pattern in DEPT_PATTERNS:
            if re.search(pattern, subject_lower, re.IGNORECASE):
                return "guap_dept", False

        # 5. Default
        return "personal", False


    def extract_body_and_snippet(self, msg: email.message.EmailMessage) -> tuple[str, str, str]:
        """Extract plain text, html body, and a clean short snippet."""
        body_plain = ""
        body_html = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                if "attachment" in content_disposition:
                    continue

                try:
                    payload = part.get_content()
                    if content_type == "text/plain" and not body_plain:
                        body_plain = payload if isinstance(payload, str) else payload.decode(errors="ignore")
                    elif content_type == "text/html" and not body_html:
                        body_html = payload if isinstance(payload, str) else payload.decode(errors="ignore")
                except Exception as e:
                    logger.debug("Failed to extract part content: %s", e)
        else:
            try:
                payload = msg.get_content()
                ct = msg.get_content_type()
                if ct == "text/html":
                    body_html = payload if isinstance(payload, str) else payload.decode(errors="ignore")
                else:
                    body_plain = payload if isinstance(payload, str) else payload.decode(errors="ignore")
            except Exception as e:
                logger.debug("Failed to extract direct payload: %s", e)

        # If no plain body, convert HTML
        if not body_plain and body_html:
            try:
                body_plain = self.html_converter.handle(body_html)
            except Exception:
                body_plain = ""

        # Clean snippet
        snippet_source = body_plain or body_html or ""
        clean_text = re.sub(r"\s+", " ", snippet_source).strip()
        snippet = clean_text[:200]

        return body_plain[:50000], body_html[:50000], snippet

    async def ingest_imap_account(
        self,
        account_id: str,
        host: str,
        port: int,
        username: str,
        password: str,
        folders: list[str] | None = None,
        days: int = 60,
        max_messages: int = 200,
    ) -> dict[str, Any]:
        """Fetch and ingest messages from an IMAP account."""
        if not username or not password:
            logger.warning("Account %s credentials missing, skipping.", account_id)
            return {"account": account_id, "status": "skipped_no_creds"}

        folders = folders or ["INBOX"]
        since_date = datetime.now(timezone.utc).date() - timedelta(days=days)
        stats = {
            "account": account_id,
            "checked": 0,
            "inserted": 0,
            "duplicates": 0,
            "categories": {},
        }

        try:
            with IMAPClient(host, port=port, ssl=True, timeout=15) as client:
                client.login(username, password)
                logger.info("[%s] IMAP connected to %s:%d as %s", account_id, host, port, username)

                for folder in folders:
                    try:
                        select_info = client.select_folder(folder, readonly=True)
                        total_in_folder = select_info.get(b"EXISTS", 0)
                        logger.info("[%s] Folder '%s': total %d messages", account_id, folder, total_in_folder)

                        # Search messages since date
                        msg_uids = client.search(["SINCE", since_date])
                        logger.info("[%s] Folder '%s': %d messages found since %s", account_id, folder, len(msg_uids), since_date)

                        if not msg_uids:
                            continue

                        # Limit to latest max_messages
                        if len(msg_uids) > max_messages:
                            msg_uids = msg_uids[-max_messages:]

                        # Fetch in chunks
                        chunk_size = 25
                        for i in range(0, len(msg_uids), chunk_size):
                            chunk = msg_uids[i : i + chunk_size]
                            fetch_data = client.fetch(chunk, ["RFC822", "FLAGS"])

                            for uid, data in fetch_data.items():
                                stats["checked"] += 1
                                raw_bytes = data.get(b"RFC822")
                                if not raw_bytes:
                                    continue

                                raw_flags = data.get(b"FLAGS", ())
                                flags_list = [f.decode("utf-8", errors="ignore") if isinstance(f, bytes) else str(f) for f in raw_flags]
                                flags_json = json.dumps(flags_list, ensure_ascii=False)
                                has_answered_flag = any("answered" in f.lower() for f in flags_list)
                                has_seen_flag = any("seen" in f.lower() for f in flags_list)

                                msg = email.message_from_bytes(raw_bytes, policy=policy.default)
                                message_id = str(msg.get("Message-ID", "")).strip() or f"gen-{account_id}-{folder}-{uid}"
                                subject = str(msg.get("Subject", "")).strip()
                                sender_raw = str(msg.get("From", ""))
                                sender_name, sender_email = parseaddr(sender_raw)
                                if not sender_email:
                                    sender_email = sender_raw

                                # Date parsing
                                date_str = str(msg.get("Date", ""))
                                try:
                                    date_sent = parsedate_to_datetime(date_str)
                                    if date_sent.tzinfo is None:
                                        date_sent = date_sent.replace(tzinfo=timezone.utc)
                                except Exception:
                                    date_sent = datetime.now(timezone.utc)

                                recipients = [str(msg.get("To", ""))]
                                if msg.get("Cc"):
                                    recipients.append(str(msg.get("Cc", "")))

                                in_reply_to = str(msg.get("In-Reply-To", "")).strip() or None
                                references_text = str(msg.get("References", "")).strip() or None

                                # Thread ID calculation
                                clean_subj = self.clean_subject_for_thread(subject)
                                thread_root = (in_reply_to or references_text or "").split()[0] if (in_reply_to or references_text) else None
                                thread_id = thread_root or f"th-{clean_subj[:32]}"

                                # Body extraction
                                body_plain, body_html, snippet = self.extract_body_and_snippet(msg)

                                # Check attachments
                                attachments = []
                                for part in msg.iter_attachments():
                                    fname = part.get_filename() or "attachment"
                                    attachments.append(fname)
                                has_attachments = len(attachments) > 0

                                # Check if outgoing from user
                                user_emails = get_user_emails()
                                is_from_me = (sender_email.lower().strip() in user_emails) or (folder in ("Отправленные", "Sent"))

                                if is_from_me:
                                    category = "outgoing"
                                    is_noise = False
                                    requires_action = False
                                    is_answered = True
                                    is_expired = False
                                    deadline = None
                                    relevance_score = 1.0
                                else:
                                    category, is_noise = self.classify_email(sender_email, subject, msg)
                                    deadline = extract_deadline(f"{subject} {snippet}")
                                    relevance_score, is_expired = calculate_relevance(date_sent, deadline)
                                    is_answered = has_answered_flag
                                    requires_action = (category in ("guap_student", "guap_dept")) and not is_noise and not is_answered and not is_expired

                                # Persist
                                inserted = await self.db.upsert_email_message(
                                    message_id=message_id,
                                    account_id=account_id,
                                    folder=folder,
                                    sender_name=sender_name,
                                    sender_email=sender_email,
                                    recipients_json=json.dumps(recipients, ensure_ascii=False),
                                    subject=subject,
                                    date_sent=date_sent,
                                    body_plain=body_plain,
                                    body_html=body_html,
                                    snippet=snippet,
                                    has_attachments=has_attachments,
                                    attachments_json=json.dumps(attachments, ensure_ascii=False) if attachments else None,
                                    in_reply_to=in_reply_to,
                                    references_text=references_text,
                                    thread_id=thread_id,
                                    category=category,
                                    is_noise=is_noise,
                                    requires_action=requires_action,
                                    is_read=has_seen_flag,
                                    is_answered=is_answered,
                                    flags_json=flags_json,
                                    is_expired=is_expired,
                                    deadline_at=deadline,
                                    relevance_score=relevance_score,
                                )

                                if inserted:
                                    stats["inserted"] += 1
                                    stats["categories"][category] = stats["categories"].get(category, 0) + 1
                                else:
                                    stats["duplicates"] += 1

                    except Exception as fe:
                        logger.error("[%s] Error processing folder '%s': %s", account_id, folder, fe)

        except Exception as e:
            logger.error("[%s] Failed to connect/ingest IMAP: %s", account_id, e)
            stats["error"] = str(e)

        return stats

    async def ingest_gmail_account(
        self,
        account_id: str = "gmail",
        days: int = 60,
        max_messages: int = 150,
    ) -> dict[str, Any]:
        """Fetch and ingest messages from Gmail using Gmail API and OAuth2 token."""
        token_path = Path(config.GOOGLE_TOKEN_FILE)
        if not token_path.is_absolute():
            token_path = config.BASE_DIR / token_path

        if not token_path.exists():
            logger.warning("Gmail token file %s does not exist, skipping Gmail.", token_path)
            return {"account": account_id, "status": "skipped_no_token"}

        stats = {
            "account": account_id,
            "checked": 0,
            "inserted": 0,
            "duplicates": 0,
            "categories": {},
        }

        try:
            creds = Credentials.from_authorized_user_file(str(token_path))
            service = build("gmail", "v1", credentials=creds)

            # Query messages from last N days
            query = f"newer_than:{days}d"
            res = service.users().messages().list(userId="me", q=query, maxResults=max_messages).execute()
            messages_meta = res.get("messages", [])
            logger.info("[gmail] Gmail API returned %d messages for query '%s'", len(messages_meta), query)

            for item in messages_meta:
                stats["checked"] += 1
                msg_id = item["id"]
                try:
                    detail = service.users().messages().get(
                        userId="me",
                        id=msg_id,
                        format="metadata",
                        metadataHeaders=["Message-ID", "Subject", "From", "To", "Cc", "Date", "In-Reply-To", "References"]
                    ).execute()
                except Exception as get_err:
                    logger.debug("Failed to get gmail msg %s: %s", msg_id, get_err)
                    continue

                label_ids = detail.get("labelIds", [])
                payload = detail.get("payload", {})
                headers_list = payload.get("headers", [])
                headers_map = {h["name"].lower(): h["value"] for h in headers_list}

                message_id = headers_map.get("message-id", f"gmail-{msg_id}").strip()
                subject = headers_map.get("subject", "")
                sender_raw = headers_map.get("from", "")
                sender_name, sender_email = parseaddr(sender_raw)
                if not sender_email:
                    sender_email = sender_raw

                # Date parsing
                internal_date_ms = int(detail.get("internalDate", "0"))
                if internal_date_ms:
                    date_sent = datetime.fromtimestamp(internal_date_ms / 1000.0, tz=timezone.utc)
                else:
                    date_sent = datetime.now(timezone.utc)

                recipients = [headers_map.get("to", "")]
                if "cc" in headers_map:
                    recipients.append(headers_map["cc"])

                in_reply_to = headers_map.get("in-reply-to")
                references_text = headers_map.get("references")
                thread_root = (in_reply_to or references_text or "").split()[0] if (in_reply_to or references_text) else None
                clean_subj = self.clean_subject_for_thread(subject)
                thread_id = thread_root or detail.get("threadId") or f"th-{clean_subj[:32]}"

                # Snippet
                snippet = detail.get("snippet", "")

                body_plain = snippet
                has_attachments = False

                user_emails = get_user_emails()
                is_from_me = ("SENT" in label_ids) or (sender_email.lower().strip() in user_emails)

                if is_from_me:
                    category = "outgoing"
                    is_noise = False
                    requires_action = False
                    is_answered = True
                    is_expired = False
                    deadline = None
                    relevance_score = 1.0
                else:
                    category, is_noise = self.classify_email(sender_email, subject, headers_map)
                    deadline = extract_deadline(f"{subject} {snippet}")
                    relevance_score, is_expired = calculate_relevance(date_sent, deadline)
                    is_answered = False
                    requires_action = (category in ("guap_student", "guap_dept")) and not is_noise and not is_answered and not is_expired

                flags_list = list(label_ids)
                has_seen = "UNREAD" not in label_ids

                inserted = await self.db.upsert_email_message(
                    message_id=message_id,
                    account_id=account_id,
                    folder="INBOX" if not is_from_me else "SENT",
                    sender_name=sender_name,
                    sender_email=sender_email,
                    recipients_json=json.dumps(recipients, ensure_ascii=False),
                    subject=subject,
                    date_sent=date_sent,
                    body_plain=body_plain,
                    body_html=None,
                    snippet=snippet,
                    has_attachments=has_attachments,
                    attachments_json=None,
                    in_reply_to=in_reply_to,
                    references_text=references_text,
                    thread_id=thread_id,
                    category=category,
                    is_noise=is_noise,
                    requires_action=requires_action,
                    is_read=has_seen,
                    is_answered=is_answered,
                    flags_json=json.dumps(flags_list, ensure_ascii=False),
                    is_expired=is_expired,
                    deadline_at=deadline,
                    relevance_score=relevance_score,
                )

                if inserted:
                    stats["inserted"] += 1
                    stats["categories"][category] = stats["categories"].get(category, 0) + 1
                else:
                    stats["duplicates"] += 1

        except Exception as e:
            logger.error("[gmail] Error fetching Gmail messages: %s", e)
            stats["error"] = str(e)

        return stats

    async def sync_all_accounts(self, days: int = 60) -> dict[str, Any]:
        """Sync all connected accounts, reconcile replies, and update date relevance."""
        await self.db.init_db()
        results = {}

        # 1. Sync Mail.ru (INBOX, ГУАП, and Отправленные)
        mailru_folders = ["INBOX", "ГУАП", "Отправленные"]
        logger.info("Starting Mail.ru ingestion for last %d days...", days)
        results["mailru"] = await self.ingest_imap_account(
            account_id="mailru",
            host=config.MAILRU_IMAP_SERVER,
            port=config.MAILRU_IMAP_PORT,
            username=config.MAILRU_EMAIL,
            password=config.MAILRU_PASSWORD,
            folders=mailru_folders,
            days=days,
        )

        # 2. Sync GUAP Corporate direct IMAP (INBOX and Sent)
        logger.info("Starting GUAP direct IMAP ingestion for last %d days...", days)
        results["guap"] = await self.ingest_imap_account(
            account_id="guap",
            host=config.GUAP_IMAP_SERVER,
            port=config.GUAP_IMAP_PORT,
            username=config.GUAP_EMAIL,
            password=config.GUAP_PASSWORD,
            folders=["INBOX", "Sent"],
            days=days,
        )

        # 3. Sync Gmail API
        logger.info("Starting Gmail API ingestion for last %d days...", days)
        results["gmail"] = await self.ingest_gmail_account(
            account_id="gmail",
            days=days,
        )

        # 4. Reconcile outgoing replies and thread statuses
        user_emails = get_user_emails()
        logger.info("Reconciling replies and thread statuses for %s...", user_emails)
        reconcile_stats = await self.db.reconcile_replies_and_threads(user_emails)
        results["reconciliation"] = reconcile_stats

        # 5. Recalculate date relevance and aging
        logger.info("Updating date relevance and expiration...")
        aging_stats = await self.db.update_date_relevance()
        results["aging"] = aging_stats

        # 6. Aggregated stats from DB
        db_stats = await self.db.get_email_stats()
        results["db_totals"] = db_stats

        actionable = await self.db.list_actionable_emails()
        results["active_actionable_count"] = len(actionable)
        logger.info("Sync finished. Active actionable emails remaining: %d", len(actionable))
        return results
