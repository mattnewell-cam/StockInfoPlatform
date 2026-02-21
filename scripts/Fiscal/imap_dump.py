"""Dump recent IMAP emails to files for inspection."""
import imaplib
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = (BASE_DIR / ".." / "..").resolve()
load_dotenv(PROJECT_ROOT / ".env")

IMAP_HOST = os.getenv("FISCAL_MAGIC_IMAP_HOST", "")
IMAP_PORT = int(os.getenv("FISCAL_MAGIC_IMAP_PORT", "993"))
IMAP_USER = os.getenv("FISCAL_MAGIC_IMAP_USER", "")
IMAP_PASSWORD = os.getenv("FISCAL_MAGIC_IMAP_PASSWORD", "")
IMAP_MAILBOX = os.getenv("FISCAL_MAGIC_IMAP_MAILBOX", "INBOX")

OUT_DIR = BASE_DIR / "pages" / "imap_dump"
OUT_DIR.mkdir(parents=True, exist_ok=True)

with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as client:
    client.login(IMAP_USER, IMAP_PASSWORD)
    client.select(IMAP_MAILBOX, readonly=True)

    status, data = client.search(None, "ALL")
    msg_ids = data[0].split()
    recent = msg_ids[-10:]  # last 10 emails

    print(f"Fetching {len(recent)} most recent emails from {IMAP_MAILBOX}...")

    for msg_id in reversed(recent):
        status, fetched = client.fetch(msg_id, "(RFC822)")
        raw = next(
            (bytes(item[1]) for item in fetched if isinstance(item, tuple) and isinstance(item[1], (bytes, bytearray))),
            b"",
        )
        out_path = OUT_DIR / f"email_{msg_id.decode()}.eml"
        out_path.write_bytes(raw)
        print(f"  Saved {out_path.name} ({len(raw)} bytes)")

print(f"\nDone. Files in: {OUT_DIR}")
