# low_quality_engine.py
"""
AutoAdly - Adaptive slow-posting engine for low-quality marketplaces.

engine.py's main rotation (run_advertisement_loop) skips any marketplace
whose quality_tier is 'low' entirely — those marketplaces were getting ZERO
posts. This module gives them a second, independent shot: post rarely, wait
to see if the post survives, and adapt the gap per-marketplace until it
lands on the widest-possible "sweet spot" interval that still gets posts up
without them being immediately buried/removed.

This module never touches engine.py's main loop, its index, or its timing —
it only reads shared helpers (get_client, post's core function, the same
visibility check). A bug or slowdown in here cannot affect normal posting.
"""
import asyncio
import logging
import time

import database as db
import engine

logger = logging.getLogger("low_quality_engine")

# 5m, 10m, 15m, 20m, 30m, 45m, 1h, 1.5h, 2h — matches the requested "try 5 or
# 10, then 15, then 20, then 30, up to 2hr" ladder.
INTERVAL_LADDER = [300, 600, 900, 1200, 1800, 2700, 3600, 5400, 7200]

# How many clean (still-visible) posts in a row before trying a shorter gap
# again. Kept deliberately cautious — the whole point is to stop hammering
# marketplaces that bury ads under frequent posting.
SUCCESSES_BEFORE_STEP_DOWN = 3

VISIBILITY_CHECK_DELAY_SECONDS = 90  # kept in step with engine.VISIBILITY_CHECK_DELAY_SECONDS
DISCOVERY_INTERVAL_SECONDS = 30

_running = set()  # (ad_id, marketplace_id) pairs that already have a task


async def _run_one_marketplace(ad_cache, ad_id, marketplace_id):
    """Adaptive loop for a single (ad, low-quality marketplace) pair. Runs
       until the ad stops, the marketplace leaves that ad's list, or the
       marketplace gets manually restored to standard quality via /requality
       (at which point engine.py's normal fast rotation takes over for it)."""
    key = (ad_id, marketplace_id)
    index = 0
    streak = 0
    try:
        while True:
            await asyncio.sleep(INTERVAL_LADDER[index])

            ad = ad_cache.get(ad_id)
            if ad is None:
                break  # ad no longer active

            marketplace = await db.get_marketplace_by_id(marketplace_id)
            if not marketplace or marketplace["quality_tier"] != "low":
                break  # promoted back to standard (or deleted) — main rotation owns it now

            list_marketplace_ids = {m["id"] for m in await db.get_list_marketplaces(ad["marketplace_list_id"])}
            if marketplace_id not in list_marketplace_ids:
                break  # no longer part of this ad's marketplace list

            try:
                client = await engine.get_client(ad["ad_account_id"])
                link, msg_id, target = await engine._post_to_marketplace_core(client, ad, marketplace)
            except Exception as e:
                logger.info(f"low_quality_engine: post attempt failed for marketplace {marketplace_id}: {e}")
                link, msg_id, target = None, None, None

            if not link:
                index = min(index + 1, len(INTERVAL_LADDER) - 1)
                streak = 0
                continue

            await db.log_success(ad["ad_account_id"], marketplace_id, link)
            logger.info(f"low_quality_engine: posted to {marketplace.get('chat_username')} (interval={INTERVAL_LADDER[index]}s)")

            visible = True
            if msg_id:
                await asyncio.sleep(VISIBILITY_CHECK_DELAY_SECONDS)
                try:
                    visible = await engine.is_still_visible(client, target, msg_id)
                except Exception:
                    visible = True  # couldn't confirm either way — don't punish for a check failure

            if visible:
                streak += 1
                if streak >= SUCCESSES_BEFORE_STEP_DOWN and index > 0:
                    index -= 1
                    streak = 0
            else:
                index = min(index + 1, len(INTERVAL_LADDER) - 1)
                streak = 0
    finally:
        _running.discard(key)


async def watch_low_quality_marketplaces():
    """Runs alongside engine.watch_for_new_ads(). For every active ad, finds
       any marketplace in its list that's auto-demoted to 'low' quality and
       gives it its own slow, adaptive schedule if it doesn't already have
       one running."""
    ad_cache = {}
    while True:
        try:
            ads = await db.get_active_advertisements()
            ad_cache.clear()
            ad_cache.update({ad["id"]: ad for ad in ads})

            for ad in ads:
                marketplaces = await db.get_list_marketplaces(ad["marketplace_list_id"])
                for m in marketplaces:
                    if m["quality_tier"] != "low":
                        continue
                    key = (ad["id"], m["id"])
                    if key in _running:
                        continue
                    _running.add(key)
                    asyncio.create_task(_run_one_marketplace(ad_cache, ad["id"], m["id"]))
        except Exception as e:
            logger.info(f"watch_low_quality_marketplaces error: {e}")
        await asyncio.sleep(DISCOVERY_INTERVAL_SECONDS)
