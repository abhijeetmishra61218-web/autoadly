# database.py
import aiosqlite
import time

DB_PATH = "ad_bot.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS ad_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT UNIQUE,
    session_string TEXT,
    status TEXT DEFAULT 'free'
);

CREATE TABLE IF NOT EXISTS marketplaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT,
    chat_id INTEGER,
    chat_username TEXT,
    is_forum INTEGER DEFAULT 0,
    quality_tier TEXT DEFAULT 'standard'
);

CREATE TABLE IF NOT EXISTS forum_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marketplace_id INTEGER,
    topic_name TEXT,
    topic_id INTEGER,
    FOREIGN KEY(marketplace_id) REFERENCES marketplaces(id)
);

CREATE TABLE IF NOT EXISTS marketplace_visibility (
    marketplace_id INTEGER PRIMARY KEY,
    checks INTEGER DEFAULT 0,
    buried_count INTEGER DEFAULT 0,
    last_checked REAL,
    FOREIGN KEY(marketplace_id) REFERENCES marketplaces(id)
);

CREATE TABLE IF NOT EXISTS marketplace_lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    list_type TEXT,
    category TEXT,
    owner_customer_id INTEGER
);

CREATE TABLE IF NOT EXISTS marketplace_list_items (
    list_id INTEGER,
    marketplace_id INTEGER,
    FOREIGN KEY(list_id) REFERENCES marketplace_lists(id),
    FOREIGN KEY(marketplace_id) REFERENCES marketplaces(id)
);

CREATE TABLE IF NOT EXISTS advertisements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_account_id INTEGER,
    source_chat_id INTEGER,
    source_message_id INTEGER,
    category TEXT,
    marketplace_list_id INTEGER,
    status TEXT DEFAULT 'active',
    current_index INTEGER DEFAULT 0,
    FOREIGN KEY(ad_account_id) REFERENCES ad_accounts(id)
);

CREATE TABLE IF NOT EXISTS post_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_account_id INTEGER,
    marketplace_id INTEGER,
    posted_at REAL,
    message_link TEXT
);
"""

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

async def get_list_marketplaces(list_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT m.* FROM marketplaces m
            JOIN marketplace_list_items i ON i.marketplace_id = m.id
            WHERE i.list_id = ?
        """, (list_id,))
        return await cursor.fetchall()

async def get_marketplace_list_by_id(list_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM marketplace_lists WHERE id = ?", (list_id,))
        return await cursor.fetchone()

async def delete_custom_list(list_id: int):
    """Deletes a customer's custom marketplace LIST (the collection itself and
       its membership rows) — but never touches the shared `marketplaces` table,
       since those chats are also referenced by the global preset lists and
       possibly other customers' lists."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM marketplace_list_items WHERE list_id = ?", (list_id,))
        await db.execute("DELETE FROM marketplace_lists WHERE id = ?", (list_id,))
        await db.commit()

# ---- Automatic marketplace visibility/quality tracking ----
# After a post, the engine periodically checks back whether the message is
# still visible in a marketplace (not deleted, not buried under a flood of
# newer messages). Marketplaces that consistently bury posts get their
# quality_tier auto-downgraded to 'low', and the posting rotation skips them.

VISIBILITY_MIN_CHECKS = 5       # need at least this many samples before judging
VISIBILITY_BURIED_THRESHOLD = 0.6   # 60%+ buried => auto-demote
VISIBILITY_CHECK_COOLDOWN_SECONDS = 6 * 60 * 60  # only re-check a given marketplace this often

async def should_check_visibility(marketplace_id: int) -> bool:
    """Whether it's worth scheduling a visibility check for this marketplace
       right now (keeps overhead low — samples over time instead of every post)."""
    import time as _time
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT last_checked FROM marketplace_visibility WHERE marketplace_id = ?", (marketplace_id,))
        row = await cursor.fetchone()
    if not row or not row["last_checked"]:
        return True
    return (_time.time() - row["last_checked"]) >= VISIBILITY_CHECK_COOLDOWN_SECONDS

async def record_visibility_check(marketplace_id: int, buried: bool):
    """Logs one visibility sample and auto-demotes the marketplace's quality_tier
       to 'low' if it's consistently burying posts."""
    import time as _time
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT INTO marketplace_visibility (marketplace_id, checks, buried_count, last_checked) VALUES (?, 1, ?, ?) "
            "ON CONFLICT(marketplace_id) DO UPDATE SET checks = checks + 1, buried_count = buried_count + ?, last_checked = ?",
            (marketplace_id, 1 if buried else 0, _time.time(), 1 if buried else 0, _time.time())
        )
        await db.commit()
        cursor = await db.execute("SELECT checks, buried_count FROM marketplace_visibility WHERE marketplace_id = ?", (marketplace_id,))
        row = await cursor.fetchone()
        if row and row["checks"] >= VISIBILITY_MIN_CHECKS:
            ratio = row["buried_count"] / row["checks"]
            if ratio >= VISIBILITY_BURIED_THRESHOLD:
                await db.execute("UPDATE marketplaces SET quality_tier = 'low' WHERE id = ?", (marketplace_id,))
                await db.commit()
                return True  # newly (or still) demoted
    return False

async def get_low_quality_marketplaces():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT m.id, m.chat_username, m.chat_id, v.checks, v.buried_count
            FROM marketplaces m
            JOIN marketplace_visibility v ON v.marketplace_id = m.id
            WHERE m.quality_tier = 'low'
            ORDER BY v.buried_count DESC
        """)
        return await cursor.fetchall()

async def reset_marketplace_quality(marketplace_id: int):
    """Gives a demoted marketplace a fresh chance — clears its stats and restores it to 'standard'."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE marketplaces SET quality_tier = 'standard' WHERE id = ?", (marketplace_id,))
        await db.execute("DELETE FROM marketplace_visibility WHERE marketplace_id = ?", (marketplace_id,))
        await db.commit()

async def get_forum_topic(marketplace_id: int, category: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM forum_topics
            WHERE marketplace_id = ? AND LOWER(topic_name) = LOWER(?)
        """, (marketplace_id, category))
        row = await cursor.fetchone()
        if row:
            return row["topic_id"]
        cursor = await db.execute("""
            SELECT topic_id FROM forum_topics
            WHERE marketplace_id = ? AND LOWER(topic_name) IN ('general', 'main')
        """, (marketplace_id,))
        row = await cursor.fetchone()
        return row["topic_id"] if row else None

async def log_success(ad_account_id: int, marketplace_id: int, message_link: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO post_logs (ad_account_id, marketplace_id, posted_at, message_link) VALUES (?, ?, ?, ?)",
            (ad_account_id, marketplace_id, time.time(), message_link)
        )
        await db.commit()

async def cleanup_old_logs():
    cutoff = time.time() - 900
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM post_logs WHERE posted_at < ?", (cutoff,))
        await db.commit()

async def update_ad_index(ad_id: int, new_index: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE advertisements SET current_index = ? WHERE id = ?", (new_index, ad_id))
        await db.commit()

async def get_active_advertisements():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM advertisements WHERE status = 'active'")
        return await cursor.fetchall()

async def get_ad_account_session(ad_account_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM ad_accounts WHERE id = ?", (ad_account_id,))
        return await cursor.fetchone()
CATEGORY_SYNONYMS = {
    "Telegram": ["telegram", "tg"],
    "Discord": ["discord"],
    "TikTok": ["tiktok", "tik tok"],
    "Instagram": ["instagram", "insta", "ig"],
    "X (Twitter)": ["x", "twitter"],
    "Exchange": ["exchange", "trade", "swap", "sfs", "trade/swap/sfs"],
    "YouTube": ["youtube", "yt"],
    "WhatsApp": ["whatsapp", "wa"],
    "Facebook": ["facebook", "fb"],
    "Others": ["others", "general", "misc"],
}

async def get_all_ad_accounts():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM ad_accounts")
        return await cursor.fetchall()

async def get_marketplace_by_chat_id(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM marketplaces WHERE chat_id = ?", (chat_id,))
        return await cursor.fetchone()

async def upsert_marketplace(chat_id: int, chat_username: str, is_forum: bool, category: str = "General", quality_tier: str = "standard"):
    existing = await get_marketplace_by_chat_id(chat_id)
    if existing:
        return existing["id"]
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO marketplaces (category, chat_id, chat_username, is_forum, quality_tier) VALUES (?, ?, ?, ?, ?)",
            (category, chat_id, chat_username, 1 if is_forum else 0, quality_tier)
        )
        await db.commit()
        return cursor.lastrowid

async def upsert_forum_topic(marketplace_id: int, topic_name: str, topic_id: int, closed: bool = False):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id FROM forum_topics WHERE marketplace_id = ? AND topic_id = ?",
            (marketplace_id, topic_id)
        )
        row = await cursor.fetchone()
        if row:
            await db.execute(
                "UPDATE forum_topics SET topic_name = ?, closed = ? WHERE id = ?",
                (topic_name, 1 if closed else 0, row["id"])
            )
        else:
            await db.execute(
                "INSERT INTO forum_topics (marketplace_id, topic_name, topic_id, closed) VALUES (?, ?, ?, ?)",
                (marketplace_id, topic_name, topic_id, 1 if closed else 0)
            )
        await db.commit()

async def add_marketplace_to_all_lists(marketplace_id: int, list_id: int = 1):
    """Adds a marketplace to the default 'All Groups & Forums' list (list_id=1) if not already present."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT 1 FROM marketplace_list_items WHERE list_id = ? AND marketplace_id = ?",
            (list_id, marketplace_id)
        )
        if not await cursor.fetchone():
            await db.execute(
                "INSERT INTO marketplace_list_items (list_id, marketplace_id) VALUES (?, ?)",
                (list_id, marketplace_id)
            )
            await db.commit()

async def get_ranked_topics(marketplace_id: int, category: str):
    """Returns topic_ids in preference order: exact category match, synonym match, any other open topic. Closed topics excluded."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM forum_topics WHERE marketplace_id = ? AND (closed IS NULL OR closed = 0)",
            (marketplace_id,)
        )
        topics = await cursor.fetchall()

    if not topics:
        return []

    exact, synonym, rest = [], [], []
    cat_lower = category.lower()
    synonyms = [s.lower() for s in CATEGORY_SYNONYMS.get(category, [])]

    for t in topics:
        name = (t["topic_name"] or "").lower()
        if name == cat_lower:
            exact.append(t["topic_id"])
        elif any(s in name or name in s for s in synonyms):
            synonym.append(t["topic_id"])
        else:
            rest.append(t["topic_id"])

    ordered = exact + synonym + rest
    seen = set()
    result = []
    for tid in ordered:
        if tid not in seen:
            seen.add(tid)
            result.append(tid)
    return result

async def get_free_ad_account():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM ad_accounts WHERE status = 'free' LIMIT 1")
        return await cursor.fetchone()

async def mark_ad_account_status(account_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE ad_accounts SET status = ? WHERE id = ?", (status, account_id))
        await db.commit()
    if status == "free":
        try:
            import content_store as _store
            import myadbot

            kind, uid, payload = _store.get_oldest_pending_fulfillment()
            if kind == "replacement":
                await myadbot.fulfill_replacement(uid, payload["index"], account_id, payload["ad_config"])
                _store.remove_pending_replacement(uid, payload["index"])
            elif kind == "request":
                await myadbot._assign_account(uid, None, uid, account_id, send_new=True)
                _store.remove_pending_account_request(uid)
                remaining_empty = sum(1 for s in _store.get_customer_adbots(uid) if s.get("ad_account_id") is None)
                if remaining_empty > 0:
                    _store.queue_pending_account_request(uid, created_at=payload)
        except Exception as e:
            print(f"[mark_ad_account_status] auto-fulfillment failed: {e}")

async def get_ad_account_by_id(account_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM ad_accounts WHERE id = ?", (account_id,))
        return await cursor.fetchone()

async def get_active_ad_for_account(ad_account_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM advertisements WHERE ad_account_id = ? AND status = 'active'",
            (ad_account_id,)
        )
        return await cursor.fetchone()

async def stop_advertisement(ad_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE advertisements SET status = 'stopped' WHERE id = ?", (ad_id,))
        await db.commit()

async def create_advertisement(ad_account_id: int, source_chat_id: int, source_message_id: int, category: str, marketplace_list_id: int, source_username: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        # Safety net: an account must never have more than one active ad at once.
        # Stopping any other active ad for this account here (inside the same
        # connection/transaction as the insert) closes the race where two
        # near-simultaneous calls (e.g. a fast double-tap) both see "no active
        # ad" and both create one, leaving two posting loops running in parallel.
        await db.execute("UPDATE advertisements SET status = 'stopped' WHERE ad_account_id = ? AND status = 'active'", (ad_account_id,))
        cursor = await db.execute(
            "INSERT INTO advertisements (ad_account_id, source_chat_id, source_message_id, category, marketplace_list_id, status, current_index, source_username) VALUES (?, ?, ?, ?, ?, 'active', 0, ?)",
            (ad_account_id, source_chat_id, source_message_id, category, marketplace_list_id, source_username)
        )
        await db.commit()
        return cursor.lastrowid

async def get_or_create_list(name: str, category: str = "All", owner_customer_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id FROM marketplace_lists WHERE name = ? AND (owner_customer_id IS ? )",
            (name, owner_customer_id)
        )
        row = await cursor.fetchone()
        if row:
            return row["id"]
        cursor = await db.execute(
            "INSERT INTO marketplace_lists (name, list_type, category, owner_customer_id) VALUES (?, 'preset', ?, ?)",
            (name, category, owner_customer_id)
        )
        await db.commit()
        return cursor.lastrowid

async def get_preset_lists():
    """Returns the 4 standard preset lists, creating them if they don't exist yet."""
    presets = ["All Groups & Forums", "Only High Quality Groups", "Only High Quality Forums"]
    result = []
    for name in presets:
        list_id = await get_or_create_list(name)
        result.append({"id": list_id, "name": name})
    return result

async def get_customer_custom_lists(customer_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM marketplace_lists WHERE owner_customer_id = ?", (customer_id,)
        )
        return await cursor.fetchall()

async def populate_preset_list_all():
    """Ensures 'All Groups & Forums' (list_id from get_preset_lists) contains every marketplace.
       Call this once at startup / after seeding new marketplaces."""
    presets = await get_preset_lists()
    all_list_id = presets[0]["id"]
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT id, quality_tier FROM marketplaces")
        marketplaces = await cursor.fetchall()
        for m in marketplaces:
            await add_marketplace_to_all_lists(m["id"], list_id=all_list_id)
    return all_list_id

async def save_list_name(list_id: int, new_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE marketplace_lists SET name = ? WHERE id = ?", (new_name, list_id))
        await db.commit()

async def get_recent_logs_for_customer(user_id, minutes: int = 15):
    """Returns post_logs joined with marketplace names, for all ad accounts owned by this customer,
       limited to the last N minutes."""
    import content_store as store
    import time as _time
    adbots = store.get_customer_adbots(user_id)
    account_ids = [b["ad_account_id"] for b in adbots]
    if not account_ids:
        return []
    cutoff = _time.time() - (minutes * 60)
    placeholders = ",".join("?" for _ in account_ids)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = f'''
            SELECT p.*, m.chat_username FROM post_logs p
            JOIN marketplaces m ON m.id = p.marketplace_id
            WHERE p.ad_account_id IN ({placeholders}) AND p.posted_at >= ?
            ORDER BY p.posted_at DESC
            LIMIT 50
        '''
        cursor = await db.execute(query, account_ids + [cutoff])
        return await cursor.fetchall()

async def add_ad_account(phone: str, session_string: str, status: str = "free"):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO ad_accounts (phone, session_string, status) VALUES (?, ?, ?)",
            (phone, session_string, status)
        )
        await db.commit()
        return cursor.lastrowid

async def get_all_marketplace_usernames():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT chat_username FROM marketplaces WHERE chat_username IS NOT NULL")
        rows = await cursor.fetchall()
        return [r["chat_username"] for r in rows if r["chat_username"]]

async def has_active_ad(ad_account_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM advertisements WHERE ad_account_id = ? AND status = 'active'", (ad_account_id,))
        return (await cursor.fetchone()) is not None

async def get_recent_logs_for_account(ad_account_id, minutes: int = 15):
    import time as _time
    cutoff = _time.time() - (minutes * 60)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT p.*, m.chat_username FROM post_logs p
            JOIN marketplaces m ON m.id = p.marketplace_id
            WHERE p.ad_account_id = ? AND p.posted_at >= ?
            ORDER BY p.posted_at DESC
            LIMIT 50
        ''', (ad_account_id, cutoff))
        return await cursor.fetchall()

async def mark_ad_account_status_no_fulfill(account_id: int, status: str):
    """Same as mark_ad_account_status but never triggers auto-fulfillment.
       Use when the caller is already handling assignment itself (e.g. immediate manual assignment)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE ad_accounts SET status = ? WHERE id = ?", (status, account_id))
        await db.commit()

async def delete_ad_account(account_id: int):
    """Permanently removes an Ad Bot Account from the system. To use that
       phone number again later, it must be logged in fresh via /login —
       nothing about it is preserved."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM ad_accounts WHERE id = ?", (account_id,))
        await db.commit()

async def get_ad_account_by_phone(phone: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM ad_accounts WHERE phone = ?", (phone,))
        return await cursor.fetchone()

async def refresh_ad_account_session(account_id: int, session_string: str, status: str = "free"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE ad_accounts SET session_string = ?, status = ? WHERE id = ?",
            (session_string, status, account_id)
        )
        await db.commit()

async def save_two_step_password(account_id: int, password: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE ad_accounts SET two_step_password = ? WHERE id = ?", (password, account_id))
        await db.commit()

async def mark_marketplaces_synced(account_id: int, synced: bool = True):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE ad_accounts SET marketplaces_synced = ? WHERE id = ?", (1 if synced else 0, account_id))
        await db.commit()

async def get_unsynced_accounts():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM ad_accounts WHERE marketplaces_synced = 0 OR marketplaces_synced IS NULL")
        return await cursor.fetchall()
