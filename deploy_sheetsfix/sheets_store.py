"""
Google Sheets-backed live data store for users.json and subscriptions.json.
This is the "Sheets = data, GitHub = code only" piece of the RDP-migration
plan: these two datasets live in a shared Google Sheet so a new RDP can pull
them straight from Sheets instead of needing a JSON backup restored.

Every function here mirrors the shape of the equivalent function in
content_store.py exactly (same dict/key structure) so it's a drop-in swap.

If Sheets is unreachable (no service account file, bad key, network issue),
every function raises SheetsUnavailableError. content_store.py catches this
and falls back to the local JSON file, so a Sheets outage never breaks the
bot - it just temporarily stops syncing.
"""

import os
import time

import gspread
from google.oauth2.service_account import Credentials

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, "sheets_service_account.json")
# Set SHEETS_SHEET_ID as an env var (or edit the default below) - it's the
# long id in your Sheet's URL between /d/ and /edit.
SHEET_ID = os.environ.get(
    "SHEETS_SHEET_ID",
    "1XLiOBQ-zPKhQlyR5EyYkjXiJ4kMKuy39j_X6X6Khcgs",
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_client = None
_spreadsheet = None


class SheetsUnavailableError(Exception):
    """Raised whenever Sheets can't be reached - callers fall back to local JSON."""


def _get_spreadsheet():
    global _client, _spreadsheet
    if _spreadsheet is not None:
        return _spreadsheet
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise SheetsUnavailableError(
            f"Service account key not found at {SERVICE_ACCOUNT_FILE}"
        )
    try:
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        _client = gspread.authorize(creds)
        _spreadsheet = _client.open_by_key(SHEET_ID)
    except Exception as e:
        raise SheetsUnavailableError(f"Could not connect to Google Sheets: {e}") from e
    return _spreadsheet


def _get_or_create_worksheet(name, header):
    spreadsheet = _get_spreadsheet()
    try:
        ws = spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=name, rows=2000, cols=len(header))
        ws.append_row(header)
    return ws


# ---- Users (mirrors content_store.py's users.json: {uid_str: {"username": str}}) ----

USERS_HEADER = ["user_id", "username"]


def load_users():
    ws = _get_or_create_worksheet("Users", USERS_HEADER)
    rows = ws.get_all_records()
    return {
        str(r["user_id"]): {"username": r.get("username", "") or ""}
        for r in rows
        if r.get("user_id") not in (None, "")
    }


def save_users(data):
    ws = _get_or_create_worksheet("Users", USERS_HEADER)
    rows = [USERS_HEADER] + [
        [uid, info.get("username", "") or ""] for uid, info in data.items()
    ]
    ws.clear()
    ws.update(rows)


# ---- Subscriptions (mirrors subscriptions.json) ----

SUBS_HEADER = [
    "user_id", "plan_id", "purchase_date", "expiry",
    "months", "notified_soon", "reclaimed",
]


def load_subscriptions():
    ws = _get_or_create_worksheet("Subscriptions", SUBS_HEADER)
    rows = ws.get_all_records()
    out = {}
    for r in rows:
        uid = str(r.get("user_id") or "")
        if not uid:
            continue
        out[uid] = {
            "plan_id": r.get("plan_id") or None,
            "purchase_date": float(r.get("purchase_date") or 0),
            "expiry": float(r.get("expiry") or 0),
            "months": int(r.get("months") or 1),
            "notified_soon": str(r.get("notified_soon")).strip().upper() == "TRUE",
            "reclaimed": str(r.get("reclaimed")).strip().upper() == "TRUE",
        }
    return out


def save_subscriptions(data):
    ws = _get_or_create_worksheet("Subscriptions", SUBS_HEADER)
    rows = [SUBS_HEADER]
    for uid, sub in data.items():
        rows.append([
            uid,
            sub.get("plan_id"),
            sub.get("purchase_date"),
            sub.get("expiry"),
            sub.get("months"),
            bool(sub.get("notified_soon", False)),
            bool(sub.get("reclaimed", False)),
        ])
    ws.clear()
    ws.update(rows)


# ---- Post logs (ad-posting activity, synced from ad_bot.db every 15 min) ----

POST_LOGS_HEADER = ["posted_at", "ad_account_id", "marketplace_id", "chat_username", "message_link"]


def append_post_logs(rows):
    """rows: list of dicts with posted_at/ad_account_id/marketplace_id/chat_username/message_link."""
    if not rows:
        return
    ws = _get_or_create_worksheet("PostLogs", POST_LOGS_HEADER)
    values = [
        [r.get("posted_at"), r.get("ad_account_id"), r.get("marketplace_id"),
         r.get("chat_username") or "", r.get("message_link") or ""]
        for r in rows
    ]
    ws.append_rows(values, value_input_option="RAW")


def get_post_logs(since_hours=6):
    """Rows from the last `since_hours`, newest first. Used by /alog."""
    ws = _get_or_create_worksheet("PostLogs", POST_LOGS_HEADER)
    rows = ws.get_all_records()
    cutoff = time.time() - since_hours * 3600
    out = []
    for r in rows:
        try:
            posted_at = float(r.get("posted_at") or 0)
        except (TypeError, ValueError):
            continue
        if posted_at >= cutoff:
            out.append({
                "posted_at": posted_at,
                "ad_account_id": r.get("ad_account_id"),
                "marketplace_id": r.get("marketplace_id"),
                "chat_username": r.get("chat_username"),
                "message_link": r.get("message_link"),
            })
    out.sort(key=lambda r: r["posted_at"], reverse=True)
    return out


def trim_post_logs(retention_hours):
    """Rewrites the PostLogs tab keeping only rows within retention_hours -
       run every 6h with retention_hours=7 so /alog's 6h window is always
       fully covered even mid-trim, while the Sheet stays a bounded size."""
    ws = _get_or_create_worksheet("PostLogs", POST_LOGS_HEADER)
    rows = ws.get_all_records()
    cutoff = time.time() - retention_hours * 3600
    kept = []
    for r in rows:
        try:
            posted_at = float(r.get("posted_at") or 0)
        except (TypeError, ValueError):
            continue
        if posted_at >= cutoff:
            kept.append([r.get("posted_at"), r.get("ad_account_id"), r.get("marketplace_id"),
                         r.get("chat_username") or "", r.get("message_link") or ""])
    ws.clear()
    ws.update([POST_LOGS_HEADER] + kept)
