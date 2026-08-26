"""
One-time backfill: pushes your EXISTING local users.json / subscriptions.json
into the Google Sheet. This never ran when the Sheets integration first went
live, which is why the Sheet only has whatever's been written since (a
handful of rows) instead of your real 26 users / 12 subscriptions.

Safe to run more than once - it overwrites the Sheet's Users/Subscriptions
tabs with whatever's currently in your local JSON files, which is always the
complete, correct picture (local is authoritative; see content_store.py).

Run once:
    python3 backfill_sheets.py
"""

import content_store as store
import sheets_store

def main():
    users = store.load_all_users()
    subs = store.load_subscriptions()

    print(f"Local users.json: {len(users)} users")
    print(f"Local subscriptions.json: {len(subs)} subscriptions")

    try:
        sheets_store.save_users(users)
        print(f"Pushed {len(users)} users to the 'Users' Sheet tab.")
    except sheets_store.SheetsUnavailableError as e:
        print(f"Could not reach Sheets for users backfill: {e}")
        return

    try:
        sheets_store.save_subscriptions(subs)
        print(f"Pushed {len(subs)} subscriptions to the 'Subscriptions' Sheet tab.")
    except sheets_store.SheetsUnavailableError as e:
        print(f"Could not reach Sheets for subscriptions backfill: {e}")
        return

    print("Backfill complete. Check your Google Sheet now.")

if __name__ == "__main__":
    main()
