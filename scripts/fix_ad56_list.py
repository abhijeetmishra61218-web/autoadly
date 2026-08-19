"""
One-off fix: move @CyberGod's ad (id=56, phone +573237027833) off the empty
"Only High Quality Groups" list (id=3, 0 groups) onto "All Groups & Forums"
(48 groups, fully populated), so it starts posting without the client
re-doing anything in the wizard.

Run from the project root on the VM:
    (.venv) $ python3 scripts/fix_ad56_list.py

Safe to run more than once (it's idempotent).
"""
import asyncio
import database as db


AD_ID = 56
SAFE_LIST_NAME = "All Groups & Forums"


async def main():
    await db.init_db()
    safe_list_id = await db.get_or_create_list(SAFE_LIST_NAME)

    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM advertisements WHERE id = ?", (AD_ID,))
        before = await cur.fetchone()
        if not before:
            print(f"No advertisement with id={AD_ID} found.")
            return
        print("Before:", dict(before))

        await conn.execute(
            "UPDATE advertisements SET marketplace_list_id = ? WHERE id = ?",
            (safe_list_id, AD_ID),
        )
        await conn.commit()

        cur = await conn.execute("SELECT * FROM advertisements WHERE id = ?", (AD_ID,))
        after = await cur.fetchone()
        print("After: ", dict(after))

    groups = await db.get_list_marketplaces(safe_list_id)
    print(f"\nAd {AD_ID} now points at list_id={safe_list_id} ('{SAFE_LIST_NAME}'), "
          f"which has {len(groups)} groups linked.")
    print("The running bot will pick this up automatically within ~10s "
          "(watch_for_new_ads poll) once engine.py's _running_ad_ids fix is deployed "
          "and the process has been restarted at least once after that.")


if __name__ == "__main__":
    asyncio.run(main())
