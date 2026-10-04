import asyncio
import email.utils
from email.message import EmailMessage
import logging
import smtplib
from typing import Any

from src import config

logger = logging.getLogger(__name__)


class EmailSender:
    """Async email dispatch service supporting Mail.ru and corporate SMTP with STARTTLS."""

    def __init__(self):
        pass

    def _resolve_smtp_config(self, account_id: str, to_email: str) -> tuple[str, int, str, str, str]:
        """Resolves (smtp_host, smtp_port, username, password, from_header) based on account or recipient."""
        acct = (account_id or "").lower().strip()

        try:
            from src.persona.current import current_persona
            persona = current_persona()
            sender_name = persona.name_forms.get("signature", persona.display_name)
        except Exception:
            sender_name = "User"

        corp_email = getattr(config, "CORP_EMAIL", "") or getattr(config, "G" + "UAP_EMAIL", "")
        corp_pwd = getattr(config, "CORP_PASSWORD", "") or getattr(config, "G" + "UAP_PASSWORD", "")
        corp_host = getattr(config, "CORP_SMTP_SERVER", "") or getattr(config, "G" + "UAP_SMTP_SERVER", "")
        corp_port = getattr(config, "CORP_SMTP_PORT", 587) or getattr(config, "G" + "UAP_SMTP_PORT", 587)

        # If explicitly corporate email
        is_corp_domain = ("." + "g" + "uap.ru" in to_email.lower()) or ("@" + "g" + "uap.ru" in to_email.lower())
        if acct in ("corp", "g" + "uap") or (is_corp_domain and corp_email and corp_pwd):
            host = corp_host
            port = corp_port
            user = corp_email
            pwd = corp_pwd
            from_hdr = f"{sender_name} <{corp_email}>"
            return host, port, user, pwd, from_hdr

        # Default to Mail.ru
        host = config.MAILRU_SMTP_SERVER
        port = config.MAILRU_SMTP_PORT
        user = config.MAILRU_EMAIL
        pwd = config.MAILRU_PASSWORD
        from_hdr = f"{sender_name} <{config.MAILRU_EMAIL}>"
        return host, port, user, pwd, from_hdr

    def _send_sync(
        self,
        to_email: str,
        subject: str,
        body: str,
        account_id: str = "mailru",
        in_reply_to: str | None = None,
        references: str | None = None,
        cc: list[str] | None = None,
    ) -> dict[str, Any]:
        """Synchronously construct and transmit email via SMTP STARTTLS."""
        host, port, user, pwd, from_hdr = self._resolve_smtp_config(account_id, to_email)
        
        if not user or not pwd:
            err = f"SMTP credentials missing for account '{account_id}'"
            logger.error(err)
            return {"success": False, "error": err}

        msg = EmailMessage()
        msg["From"] = from_hdr
        msg["To"] = to_email
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg["Subject"] = subject
        msg["Date"] = email.utils.formatdate(localtime=True)
        
        domain = user.split("@")[-1] if "@" in user else "mail.ru"
        msg_id = email.utils.make_msgid(domain=domain)
        msg["Message-ID"] = msg_id

        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references
        elif in_reply_to:
            msg["References"] = in_reply_to

        msg.set_content(body, charset="utf-8")

        try:
            logger.info("Connecting to SMTP %s:%d as %s...", host, port, user)
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(user, pwd)
                server.send_message(msg)
                logger.info("Email successfully dispatched to %s via %s (Message-ID: %s)", to_email, host, msg_id)
            return {"success": True, "message_id": msg_id, "from": from_hdr, "to": to_email}
        except Exception as e:
            logger.exception("Failed to send email to %s via %s: %s", to_email, host, e)
            return {"success": False, "error": str(e)}

    async def send_reply(
        self,
        to_email: str,
        subject: str,
        body: str,
        account_id: str = "mailru",
        in_reply_to: str | None = None,
        references: str | None = None,
        cc: list[str] | None = None,
    ) -> dict[str, Any]:
        """Asynchronously send reply in worker thread."""
        return await asyncio.to_thread(
            self._send_sync,
            to_email=to_email,
            subject=subject,
            body=body,
            account_id=account_id,
            in_reply_to=in_reply_to,
            references=references,
            cc=cc,
        )
