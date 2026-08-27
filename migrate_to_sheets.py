"""
One-time migration: pushes the current (confirmed-correct) local
users.json and subscriptions.json into Google Sheets, then reads back
from Sheets to verify the counts match before declaring success.

Run this once, manually, after confirming local data is correct.
Does NOT change how the bot reads data - content_store.py still reads
locally (see the emergency revert). This just makes Sheets an accurate
mirror for future reference / RDP migration, per the original plan.
"""

import json

import sheets_store

print("Loading local files...")
with open("users.json") as f:
    local_users = json.load(f)
with open("subscriptions.json") as f:
    local_subs = json.load(f)

print(f"Local: {len(local_users)} users, {len(local_subs)} subscriptions")

print("Pushing users to Sheets...")
sheets_store.save_users(local_users)

print("Pushing subscriptions to Sheets...")
sheets_store.save_subscriptions(local_subs)

print("Reading back from Sheets to verify...")
sheet_users = sheets_store.load_users()
sheet_subs = sheets_store.load_subscriptions()

print(f"Sheets now has: {len(sheet_users)} users, {len(sheet_subs)} subscriptions")

users_ok = sheet_users == local_users
subs_match_ids = set(sheet_subs.keys()) == set(local_subs.keys())

if users_ok and len(sheet_users) == len(local_users):
    print("USERS: verified match OK")
else:
    print("USERS: MISMATCH - do not trust Sheets Users tab yet, investigate before relying on it")

if subs_match_ids and len(sheet_subs) == len(local_subs):
    print("SUBSCRIPTIONS: verified match OK")
else:
    print("SUBSCRIPTIONS: MISMATCH - do not trust Sheets Subscriptions tab yet, investigate before relying on it")

if users_ok and subs_match_ids:
    print("\nMigration verified successful. Sheets now accurately mirrors local data.")
else:
    print("\nMigration completed but verification found a mismatch - check the details above before trusting Sheets.")
