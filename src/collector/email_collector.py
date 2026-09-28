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
                            fetch_data = client.fetch(chunk, ["RFC822"])

                            for uid, data in fetch_data.items():
                                stats["checked"] += 1
                                raw_bytes = data.get(b"RFC822")
                                if not raw_bytes:
                                    continue

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

                                # Classification
                                category, is_noise = self.classify_email(sender_email, subject, msg)
                                requires_action = (category in ("guap_student", "guap_dept")) and not is_noise

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

                # Simple body extraction from payload
                body_plain = snippet
                has_attachments = False

                category, is_noise = self.classify_email(sender_email, subject, headers_map)
                requires_action = (category in ("guap_student", "guap_dept")) and not is_noise

                inserted = await self.db.upsert_email_message(
                    message_id=message_id,
                    account_id=account_id,
                    folder="INBOX",
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
        """Sync all connected accounts and return aggregated statistics."""
        await self.db.init_db()
        results = {}

        # 1. Sync Mail.ru (INBOX and ГУАП folders)
        mailru_folders = ["INBOX", "ГУАП"]
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

        # 2. Sync GUAP Corporate direct IMAP
        logger.info("Starting GUAP direct IMAP ingestion for last %d days...", days)
        results["guap"] = await self.ingest_imap_account(
            account_id="guap",
            host=config.GUAP_IMAP_SERVER,
            port=config.GUAP_IMAP_PORT,
            username=config.GUAP_EMAIL,
            password=config.GUAP_PASSWORD,
            folders=["INBOX"],
            days=days,
        )

        # 3. Sync Gmail API
        logger.info("Starting Gmail API ingestion for last %d days...", days)
        results["gmail"] = await self.ingest_gmail_account(
            account_id="gmail",
            days=days,
        )

        # Aggregated stats from DB
        db_stats = await self.db.get_email_stats()
        results["db_totals"] = db_stats
        return results
