import asyncio
import email.utils
from email.message import EmailMessage
import logging
import smtplib
from typing import Any

from src import config

logger = logging.getLogger(__name__)


class EmailSender:
    """Async email dispatch service supporting Mail.ru and GUAP SMTP with STARTTLS."""

    def __init__(self):
        pass

    def _resolve_smtp_config(self, account_id: str, to_email: str) -> tuple[str, int, str, str, str]:
        """Resolves (host, port, username, password, from_header) based on account or recipient.
        
        Returns:
            tuple: (smtp_host, smtp_port, username, password, from_header)
        """
        acct = (account_id or "").lower().strip()
        
        # If explicitly guap or corporate email
        if acct == "guap" or ("guap.ru" in to_email.lower() and config.GUAP_EMAIL and config.GUAP_PASSWORD):
            host = config.GUAP_SMTP_SERVER
            port = config.GUAP_SMTP_PORT
            user = config.GUAP_EMAIL
            pwd = config.GUAP_PASSWORD
            from_hdr = f"Дмитрий Александрович Попов <{config.GUAP_EMAIL}>"
            return host, port, user, pwd, from_hdr

        # Default to Mail.ru (scipopov@mail.ru)
        host = config.MAILRU_SMTP_SERVER
        port = config.MAILRU_SMTP_PORT
        user = config.MAILRU_EMAIL
        pwd = config.MAILRU_PASSWORD
        from_hdr = f"Дмитрий Александрович Попов <{config.MAILRU_EMAIL}>"
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
