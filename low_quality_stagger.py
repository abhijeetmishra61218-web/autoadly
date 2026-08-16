# low_quality_stagger.py
"""
AutoAdly - Staggered sweet-spot scheduler for low-quality marketplaces.

Totally separate script from low_quality_engine.py's adaptive per-marketplace
ladder (that module is left on disk untouched, but engine.start_engine() now
launches this one instead — see the note at the bottom of this file).

How it works:

  1. DISCOVERY / STAGGERED START
     Low-quality marketplaces are queued per ad in discovery order. The 1st
     one starts testing right away, the 2nd one 5 minutes later, the 3rd one
     5 minutes after that (10 min from the start), the 4th 15 min in, and so
     on — so their first attempts land spread out instead of all firing at
     once.

  2. FIXED TEST INTERVAL PER SLOT
     Each marketplace's queue position also sets the interval it's tested
     at, for its whole life in that slot — it does not adapt up/down like
     low_quality_engine.py did:
         slot 0 -> 5 min    slot 3 -> 20 min   slot 6 -> 1h
         slot 1 -> 10 min   slot 4 -> 30 min   slot 7 -> 1.5h
         slot 2 -> 15 min   slot 5 -> 45 min   slot 8+ -> 2h

  3. GRADUATING ("suits")
     Once a marketplace's post survives GRADUATION_STREAK times in a row at
     its assigned interval, it "suits" that timing. It's removed from the
     testing queue and added to a real marketplace list (visible in the
     normal list UI, same marketplace_lists table everything else uses)
     named for that interval, e.g. "Ad #12 Sweet Spot 5min". From then on a
     separate loop keeps posting to it forever at exactly that interval.

  4. FALLING OUT OF A SWEET SPOT
     If a graduated marketplace's post ever gets buried, it's pulled off
     that sweet-spot list and dropped back into the testing queue with a
     brand-new (later) slot, since the interval it graduated at clearly
     isn't stable for it anymore.

Like low_quality_engine.py, this never touches engine.py's main loop or its
index — it only reads engine's shared helpers (get_client, the core post
function, is_still_visible). A bug or slowdown in here cannot affect normal
posting.
"""
import asyncio
import logging
import random
import time

import database as db
import engine

logger = logging.getLogger("low_quality_stagger")

# 5m, 10m, 15m, 20m, 30m, 45m, 1h, 1.5h, 2h — same ladder low_quality_engine.py
# used, just assigned by queue position now instead of adapted per-post.
INTERVAL_LADDER = [300, 600, 900, 1200, 1800, 2700, 3600, 5400, 7200]

STAGGER_STEP_SECONDS = 300   # each new marketplace's first attempt starts 5 min after the previous one's
GRADUATION_STREAK = 3        # consecutive still-visible posts at the assigned interval before it "suits"
VISIBILITY_CHECK_DELAY_SECONDS = 90  # kept in step with engine.VISIBILITY_CHECK_DELAY_SECONDS
DISCOVERY_INTERVAL_SECONDS = 30

_testing_running = set()    # (ad_id, marketplace_id) with a testing task alive
_graduated_running = set()  # (ad_id, marketplace_id) with a fixed-interval task alive


def _slot_interval(slot_index):
    return INTERVAL_LADDER[min(slot_index, len(INTERVAL_LADDER) - 1)]


def _sweet_spot_list_name(ad_id, interval_seconds):
    minutes = interval_seconds // 60
    if minutes < 60:
        label = f"{minutes}min"
    else:
        hours, rem = divmod(minutes, 60)
        label = f"{hours}h" + (f"{rem}m" if rem else "")
    return f"Ad #{ad_id} Sweet Spot {label}"


async def _get_or_create_sweet_spot_list(ad_id, interval_seconds):
    name = _sweet_spot_list_name(ad_id, interval_seconds)
    return await db.get_or_create_list(name, category="Sweet Spot")


async def _cleanup_state(ad_id, marketplace_id, list_id=None):
    if list_id:
        try:
            await db.remove_marketplace_from_list(list_id, marketplace_id)
        except Exception:
            pass
    await db.delete_sweet_spot_state(ad_id, marketplace_id)


async def _requeue_after_burial(ad_id, marketplace_id, old_list_id):
    """A graduated marketplace got buried — its old interval wasn't actually
       stable. Drop it from that sweet-spot list and put it back at the END
       of the testing queue with a fresh slot (it may land on a longer
       interval this time around)."""
    if old_list_id:
        try:
            await db.remove_marketplace_from_list(old_list_id, marketplace_id)
        except Exception:
            pass
    await db.delete_sweet_spot_state(ad_id, marketplace_id)
    slot_index = await db.count_sweet_spot_slots(ad_id)
    interval = _slot_interval(slot_index)
    next_run_at = time.time() + slot_index * STAGGER_STEP_SECONDS
    await db.create_sweet_spot_state(ad_id, marketplace_id, slot_index, interval, next_run_at)


async def _run_testing(ad_cache, ad_id, marketplace_id):
    """Tests one (ad, marketplace) pair at its assigned fixed interval until
       it either graduates, gets promoted/removed, or the ad stops."""
    key = (ad_id, marketplace_id)
    try:
        while True:
            state = await db.get_sweet_spot_state(ad_id, marketplace_id)
            if not state or state["state"] != "testing":
                break

            delay = max(0.0, state["next_run_at"] - time.time())
            await asyncio.sleep(delay + random.uniform(0, 20))

            ad = ad_cache.get(ad_id)
            if ad is None:
                await _cleanup_state(ad_id, marketplace_id)
                break  # ad no longer active

            marketplace = await db.get_marketplace_by_id(marketplace_id)
            if not marketplace or marketplace["quality_tier"] != "low":
                await _cleanup_state(ad_id, marketplace_id)
                break  # promoted back to standard (or deleted) — main rotation owns it now

            list_marketplace_ids = {m["id"] for m in await db.get_list_marketplaces(ad["marketplace_list_id"])}
            if marketplace_id not in list_marketplace_ids:
                await _cleanup_state(ad_id, marketplace_id)
                break  # no longer part of this ad's marketplace list

            interval = state["interval_seconds"]
            try:
                client = await engine.get_client(ad["ad_account_id"])
                link, msg_id, target = await engine._post_to_marketplace_core(client, ad, marketplace)
            except Exception as e:
                logger.info(f"low_quality_stagger: test post failed for marketplace {marketplace_id}: {e}")
                link, msg_id, target = None, None, None

            if not link:
                await db.update_sweet_spot_progress(ad_id, marketplace_id, time.time() + interval, 0)
                continue

            await db.log_success(ad["ad_account_id"], marketplace_id, link)
            logger.info(f"low_quality_stagger: test-posted to {marketplace['chat_username']} (slot interval={interval}s)")

            visible = True
            if msg_id:
                await asyncio.sleep(VISIBILITY_CHECK_DELAY_SECONDS)
                try:
                    visible = await engine.is_still_visible(client, target, msg_id)
                except Exception:
                    visible = True  # couldn't confirm either way — don't punish for a check failure

            if not visible:
                await db.update_sweet_spot_progress(ad_id, marketplace_id, time.time() + interval, 0)
                continue

            streak = state["streak"] + 1
            if streak >= GRADUATION_STREAK:
                list_id = await _get_or_create_sweet_spot_list(ad_id, interval)
                await db.add_marketplace_to_all_lists(marketplace_id, list_id=list_id)  # generic "add to list" helper, despite the name
                await db.graduate_sweet_spot_state(ad_id, marketplace_id, list_id)
                logger.info(f"low_quality_stagger: {marketplace['chat_username']} suits {interval}s — graduated to a fixed schedule")
                break  # the discovery loop below picks this up and starts _run_graduated for it
            else:
                await db.update_sweet_spot_progress(ad_id, marketplace_id, time.time() + interval, streak)
    finally:
        _testing_running.discard(key)


async def _run_graduated(ad_cache, ad_id, marketplace_id):
    """Keeps posting forever at the fixed interval a marketplace graduated
       at. Never adapts — if it stops working, it's demoted back into the
       testing queue for a fresh slot instead of adjusted here."""
    key = (ad_id, marketplace_id)
    try:
        while True:
            state = await db.get_sweet_spot_state(ad_id, marketplace_id)
            if not state or state["state"] != "graduated":
                break
            interval = state["interval_seconds"]
            list_id = state["list_id"]

            await asyncio.sleep(interval + random.uniform(0, 30))

            ad = ad_cache.get(ad_id)
            if ad is None:
                await _cleanup_state(ad_id, marketplace_id, list_id)
                break  # ad no longer active

            marketplace = await db.get_marketplace_by_id(marketplace_id)
            if not marketplace or marketplace["quality_tier"] != "low":
                await _cleanup_state(ad_id, marketplace_id, list_id)
                break  # promoted back to standard (or deleted) — main rotation owns it now

            list_marketplace_ids = {m["id"] for m in await db.get_list_marketplaces(ad["marketplace_list_id"])}
            if marketplace_id not in list_marketplace_ids:
                await _cleanup_state(ad_id, marketplace_id, list_id)
                break  # no longer part of this ad's marketplace list

            try:
                client = await engine.get_client(ad["ad_account_id"])
                link, msg_id, target = await engine._post_to_marketplace_core(client, ad, marketplace)
            except Exception as e:
                logger.info(f"low_quality_stagger: fixed-schedule post failed for marketplace {marketplace_id}: {e}")
                link, msg_id, target = None, None, None

            if not link:
                await _requeue_after_burial(ad_id, marketplace_id, list_id)
                break

            await db.log_success(ad["ad_account_id"], marketplace_id, link)
            logger.info(f"low_quality_stagger: posted to {marketplace['chat_username']} (fixed interval={interval}s)")

            if msg_id:
                await asyncio.sleep(VISIBILITY_CHECK_DELAY_SECONDS)
                try:
                    visible = await engine.is_still_visible(client, target, msg_id)
                except Exception:
                    visible = True
                if not visible:
                    await _requeue_after_burial(ad_id, marketplace_id, list_id)
                    break
    finally:
        _graduated_running.discard(key)


async def watch_low_quality_marketplaces():
    """Runs alongside engine.watch_for_new_ads(). Discovers newly low-quality
       marketplaces and gives each a staggered testing slot; also makes sure
       every already-graduated marketplace has its fixed-schedule task
       running."""
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

                    state = await db.get_sweet_spot_state(ad["id"], m["id"])
                    if state is None:
                        slot_index = await db.count_sweet_spot_slots(ad["id"])
                        interval = _slot_interval(slot_index)
                        next_run_at = time.time() + slot_index * STAGGER_STEP_SECONDS
                        await db.create_sweet_spot_state(ad["id"], m["id"], slot_index, interval, next_run_at)
                        state = await db.get_sweet_spot_state(ad["id"], m["id"])

                    if state["state"] == "testing" and key not in _testing_running:
                        _testing_running.add(key)
                        asyncio.create_task(_run_testing(ad_cache, ad["id"], m["id"]))
                    elif state["state"] == "graduated" and key not in _graduated_running:
                        _graduated_running.add(key)
                        asyncio.create_task(_run_graduated(ad_cache, ad["id"], m["id"]))
        except Exception as e:
            logger.info(f"watch_low_quality_marketplaces error: {e}")
        await asyncio.sleep(DISCOVERY_INTERVAL_SECONDS)

# NOTE: engine.start_engine() imports and starts THIS module now instead of
# low_quality_engine.py. low_quality_engine.py is left on disk (untouched)
# in case you ever want to switch back — just don't run both at once, or
# the same low-quality marketplace would get posted to twice on overlapping
# schedules.
