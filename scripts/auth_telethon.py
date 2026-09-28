#!/usr/bin/env python3
"""Interactive Telegram MTProto authentication script for Telethon Userbot.

Run this script once to create the persistent session file:
    ./.venv/bin/python scripts/auth_telethon.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from src.config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION_PATH


async def authenticate() -> None:
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        print("[!] Error: TELEGRAM_API_ID or TELEGRAM_API_HASH is not set in .env")
        sys.exit(1)

    session_path = Path(TELEGRAM_SESSION_PATH)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    # Telethon automatically appends .session if not present or handles file stem
    session_file_stem = str(session_path).removesuffix(".session")

    print(f"[*] Initializing Telethon client with session: {session_file_stem}.session")
    print(f"[*] API ID: {TELEGRAM_API_ID}")

    client = TelegramClient(session_file_stem, TELEGRAM_API_ID, TELEGRAM_API_HASH)

    await client.connect()

    if not await client.is_user_authorized():
        print("[*] Authentication required.")
        phone = input("Enter your phone number (e.g. +79123456789): ").strip()
        await client.send_code_request(phone)

        code = input("Enter the login code sent to your Telegram app: ").strip()
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            print("[*] Two-Step Verification (2FA) is enabled on this account.")
            password = input("Enter your Telegram 2FA cloud password: ").strip()
            await client.sign_in(password=password)

    me = await client.get_me()
    print("\n[+] SUCCESS! Authenticated as:")
    print(f"    Name: {me.first_name} {me.last_name or ''}".strip())
    print(f"    Username: @{me.username}" if me.username else "    Username: (none)")
    print(f"    User ID: {me.id}")
    print(f"    Phone: +{me.phone}")
    print(f"    Session saved at: {session_file_stem}.session")

    print("\n[*] Fetching top 15 recent dialogs (chats/channels) for reference:")
    dialogs = await client.get_dialogs(limit=15)
    for idx, d in enumerate(dialogs, start=1):
        entity_type = "Channel" if d.is_channel else ("Group" if d.is_group else "User")
        username_str = f"@{d.entity.username}" if getattr(d.entity, "username", None) else "private"
        print(f"  {idx:2d}. [{entity_type:7s}] {d.name[:35]:35s} (ID: {d.id}, {username_str})")

    await client.disconnect()
    print("\n[+] Telethon Userbot session is ready for autonomous collection!")


if __name__ == "__main__":
    asyncio.run(authenticate())
