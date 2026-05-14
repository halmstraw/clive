#!/usr/bin/env python3
"""One-time interactive helper to generate a Telegram session string.

Run this once on any machine where you can receive your Telegram login code.
Copy the printed TELEGRAM_SESSION_STRING into your environment (or GitHub Secrets).
After that, d106_e2e.py runs without any interactive prompts.

Usage:
  TELEGRAM_API_ID=12345 TELEGRAM_API_HASH=abc123 python tests/e2e/generate_session.py
"""

from __future__ import annotations

import asyncio
import os

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]

    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        await client.start()
        session_string = client.session.save()

    print("\n" + "=" * 60)
    print("TELEGRAM_SESSION_STRING=")
    print(session_string)
    print("=" * 60)
    print("\nStore this in your environment or GitHub Secrets.")
    print("Do not commit it to the repo.")


if __name__ == "__main__":
    asyncio.run(main())
