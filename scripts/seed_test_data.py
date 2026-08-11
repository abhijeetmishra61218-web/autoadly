# seed_test_data.py
import asyncio
import database as db
import aiosqlite

async def seed():
    await db.init_db()
    async with aiosqlite.connect(db.DB_PATH) as conn:
        # Dummy ad account
        await conn.execute(
            "INSERT INTO ad_accounts (phone, session_string, status) VALUES (?, ?, 'occupied')",
            ("+10000000000", "1BVtsOLgBu2d_09lXu56BaCW9SOynMKCovdHXtzpsh1S39_T1RzIErXmEY9z0eudm_iMXM6fT2JNxdreAcZspLsRZ10g2sTAiu61XQy2IuGuiZF6bFluGxmKLv5Wbw1bEPkqwS1jlFZh_fAbQqAC0o314GQCNXo060L1YNrCA9aK9QCbRtKePiQSLYtpNr4ouCGu9298Ctx3FCQoVTY9kYP-EWsPkc3t1e8AqHoE7sNj0TZKnb-KOudCTaNEYGoHtkXETfPXYzOPJa-mWTvpRj06OaftbYklkYhkJdZHTKrQWPiUYMoAJ3eHV_80sBmPpG08nCqXG4hHky5PoDdhbLqsbUOKgI8c=")
        )
        cursor = await conn.execute("SELECT last_insert_rowid()")
        ad_account_id = (await cursor.fetchone())[0]

        # Anvesana Marketplace (normal group)
        await conn.execute(
            "INSERT INTO marketplaces (category, chat_id, chat_username, is_forum, quality_tier) VALUES (?, ?, ?, 0, 'standard')",
            ("Telegram", -1001945309702, "anvesana_marketplace")
        )
        cursor = await conn.execute("SELECT last_insert_rowid()")
        group_a_id = (await cursor.fetchone())[0]

        # quick Market (forum)
        await conn.execute(
            "INSERT INTO marketplaces (category, chat_id, chat_username, is_forum, quality_tier) VALUES (?, ?, ?, 1, 'standard')",
            ("Telegram", -1001676369027, "quick_market")
        )
        cursor = await conn.execute("SELECT last_insert_rowid()")
        forum_id = (await cursor.fetchone())[0]

        # Forum topic mapping: "telegram" topic -> topic_id 120084
        await conn.execute(
            "INSERT INTO forum_topics (marketplace_id, topic_name, topic_id) VALUES (?, 'Telegram', ?)",
            (forum_id, 120084)
        )

        # A marketplace list containing both
        await conn.execute(
            "INSERT INTO marketplace_lists (name, list_type, category) VALUES ('Test List', 'preset', 'Telegram')"
        )
        cursor = await conn.execute("SELECT last_insert_rowid()")
        list_id = (await cursor.fetchone())[0]
        await conn.execute("INSERT INTO marketplace_list_items (list_id, marketplace_id) VALUES (?, ?)", (list_id, group_a_id))
        await conn.execute("INSERT INTO marketplace_list_items (list_id, marketplace_id) VALUES (?, ?)", (list_id, forum_id))

        # TODO: replace these two with a real chat_id + message_id the dummy account can see
        SOURCE_CHAT_ID = -1001945309702   # e.g. reuse Anvesana Marketplace, post a test ad message there first
        SOURCE_MESSAGE_ID = 1             # the message_id of that test ad message

        await conn.execute(
            "INSERT INTO advertisements (ad_account_id, source_chat_id, source_message_id, category, marketplace_list_id, status) VALUES (?, ?, ?, 'Telegram', ?, 'active')",
            (ad_account_id, SOURCE_CHAT_ID, SOURCE_MESSAGE_ID, list_id)
        )

        await conn.commit()
    print("Test data seeded.")

asyncio.run(seed())