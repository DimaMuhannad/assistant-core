#!/usr/bin/env python3
"""Telegram MTProto authentication script for Telethon Userbot.

Supports both interactive terminal input and non-interactive CLI flags
(useful when running commands through an IDE runner where stdin is closed).

Usage:
  1) Interactive (in a real terminal):
     ./.venv/bin/python scripts/auth_telethon.py

  2) Two-step CLI (works everywhere, including non-interactive runners):
     Step 1: ./.venv/bin/python scripts/auth_telethon.py --phone +79123456789
     Step 2: ./.venv/bin/python scripts/auth_telethon.py --code 12345 [--password YOUR_2FA]
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from src.config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION_PATH

STATE_FILE = Path(__file__).resolve().parent.parent / "data" / ".tg_login_pending.json"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Authenticate Telethon Userbot")
    parser.add_argument("--phone", type=str, help="Phone number with country code, e.g. +79123456789")
    parser.add_argument("--code", type=str, help="Telegram login code received in the Telegram app")
    parser.add_argument("--password", type=str, help="Telegram 2FA cloud password (if enabled)")
    args = parser.parse_args()

    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        print("[!] Error: TELEGRAM_API_ID or TELEGRAM_API_HASH is not set in .env")
        sys.exit(1)

    session_path = Path(TELEGRAM_SESSION_PATH)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_file_stem = str(session_path).removesuffix(".session")

    print(f"[*] Initializing Telethon client with session: {session_file_stem}.session")
    print(f"[*] API ID: {TELEGRAM_API_ID}")

    client = TelegramClient(session_file_stem, TELEGRAM_API_ID, TELEGRAM_API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print("\n[+] ALREADY AUTHORIZED!")
        print(f"    Name: {me.first_name} {me.last_name or ''}".strip())
        print(f"    Username: @{me.username}" if me.username else "    Username: (none)")
        print(f"    User ID: {me.id}")
        await print_dialogs(client)
        await client.disconnect()
        return

    # Check if this is Step 2: entering code
    if args.code:
        if not STATE_FILE.exists():
            print("[!] Error: No pending login request found. Please run Step 1 first with --phone.")
            sys.exit(1)

        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            phone = state["phone"]
            phone_code_hash = state["phone_code_hash"]
        except Exception as e:
            print(f"[!] Failed to read login state: {e}")
            sys.exit(1)

        print(f"[*] Submitting code '{args.code}' for phone: {phone}...")
        try:
            await client.sign_in(phone=phone, code=args.code.strip(), phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if args.password:
                print("[*] Submitting 2FA cloud password...")
                await client.sign_in(password=args.password.strip())
            else:
                print("\n[!] 2FA (Two-Step Verification) is enabled on this account.")
                print("    Please run again with your 2FA password:")
                print(f"    ./.venv/bin/python scripts/auth_telethon.py --code {args.code} --password ВАШ_ПАРОЛЬ")
                await client.disconnect()
                return

        # Success! Clean up state file
        if STATE_FILE.exists():
            STATE_FILE.unlink()

        me = await client.get_me()
        print("\n[+] SUCCESS! Authenticated as:")
        print(f"    Name: {me.first_name} {me.last_name or ''}".strip())
        print(f"    Username: @{me.username}" if me.username else "    Username: (none)")
        print(f"    User ID: {me.id}")
        print(f"    Phone: +{me.phone}")
        print(f"    Session saved at: {session_file_stem}.session")
        await print_dialogs(client)
        await client.disconnect()
        return

    # Step 1: phone provided via argument
    if args.phone:
        phone = args.phone.strip()
        print(f"[*] Requesting Telegram login code for {phone}...")
        sent_code = await client.send_code_request(phone)
        STATE_FILE.write_text(
            json.dumps({"phone": phone, "phone_code_hash": sent_code.phone_code_hash}),
            encoding="utf-8",
        )
        print("\n[+] Login code requested successfully!")
        print(f"[+] Telegram has sent a login code to your app on phone: {phone}")
        print("\nNow run the next command with your code:")
        print("    ./.venv/bin/python scripts/auth_telethon.py --code ВАШ_КОД")
        print("    (или с паролем, если включен 2FA: --code ВАШ_КОД --password ВАШ_ПАРОЛЬ)")
        await client.disconnect()
        return

    # If no arguments given, check if stdin is interactive (a real terminal)
    if sys.stdin.isatty():
        print("[*] Interactive terminal detected.")
        phone = input("Enter your phone number (e.g. +79123456789): ").strip()
        sent_code = await client.send_code_request(phone)
        code = input("Enter the login code sent to your Telegram app: ").strip()
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=sent_code.phone_code_hash)
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
        await print_dialogs(client)
        await client.disconnect()
        return

    # Non-interactive without arguments
    print("\n[!] Stdin is not a terminal (command was executed non-interactively).")
    print("Please use the two-step command arguments:")
    print("  Шаг 1: ./.venv/bin/python scripts/auth_telethon.py --phone +79XXXXXXXXX")
    print("  Шаг 2: ./.venv/bin/python scripts/auth_telethon.py --code ВАШ_КОД")
    await client.disconnect()


async def print_dialogs(client: TelegramClient) -> None:
    print("\n[*] Fetching top 15 recent dialogs (chats/channels) for reference:")
    dialogs = await client.get_dialogs(limit=15)
    for idx, d in enumerate(dialogs, start=1):
        entity_type = "Channel" if d.is_channel else ("Group" if d.is_group else "User")
        username_str = f"@{d.entity.username}" if getattr(d.entity, "username", None) else "private"
        print(f"  {idx:2d}. [{entity_type:7s}] {d.name[:35]:35s} (ID: {d.id}, {username_str})")


if __name__ == "__main__":
    asyncio.run(main())
