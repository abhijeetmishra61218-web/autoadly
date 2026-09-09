"""
One-time fix for the "only my first adbot ever posts" bug.

Root cause (see database.create_advertisement for the full writeup): every ad
used to start at current_index = 0 and walks its marketplace list in lockstep
with every other ad on the same list, advancing by 1 position per cycle
through the identical [60,120,180,240]s interval sequence. Two accounts on
the same list therefore hit the same marketplace at times separated by a
CONSTANT offset (whatever their start times differed by) for their entire
lifetime. If that offset is under engine.py's 90s cross-account cooldown
(MIN_GLOBAL_MARKETPLACE_GAP_SECONDS), the later-started account is
permanently a few seconds behind at every single marketplace and never wins
the cooldown -- it just silently never posts, forever.

create_advertisement now staggers the starting index for any NEW ad, but
ads that were already created and are still 'active' were stuck with
whatever index they happened to have. This script re-staggers those
existing active ads (grouped by marketplace_list_id, since only ads sharing
a list can collide with each other) so already-running adbots pick up the
fix without the customer needing to recreate their ad.

Run once, from the bot_project_clean folder, with the engine stopped (or at
least accept that in-flight loops will pick up the new current_index on
their next DB read inside the while loop, since run_advertisement_loop
re-fetches nothing about current_index mid-loop other than what it itself
writes -- safest to restart the engine process right after running this):

    python3 scripts/fix_stagger_active_ads.py
"""
import asyncio
import sqlite3

DB_PATH = "ad_bot.db"
STAGGER_PRIME = 2039  # must match database.create_advertisement


def main():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute("SELECT id, ad_account_id, marketplace_list_id, current_index FROM advertisements WHERE status='active'")
    active_ads = cur.fetchall()

    if not active_ads:
        print("No active ads found -- nothing to do.")
        return

    # Cache list lengths so we don't re-query per ad.
    list_lengths = {}

    updated = 0
    for ad in active_ads:
        list_id = ad["marketplace_list_id"]
        if list_id not in list_lengths:
            cur.execute("SELECT COUNT(*) FROM marketplace_list_items WHERE list_id = ?", (list_id,))
            list_lengths[list_id] = cur.fetchone()[0]
        list_len = list_lengths[list_id]
        if not list_len:
            continue

        new_index = (ad["ad_account_id"] * STAGGER_PRIME) % list_len
        if new_index == ad["current_index"]:
            continue

        cur.execute("UPDATE advertisements SET current_index = ? WHERE id = ?", (new_index, ad["id"]))
        print(f"ad id={ad['id']} account={ad['ad_account_id']} list={list_id}: "
              f"current_index {ad['current_index']} -> {new_index}")
        updated += 1

    con.commit()
    con.close()
    print(f"\nDone. Re-staggered {updated}/{len(active_ads)} active ads.")
    print("Restart the engine process (main.py / run_forever.sh) now so the running")
    print("asyncio loops pick up the new starting positions.")


if __name__ == "__main__":
    main()
