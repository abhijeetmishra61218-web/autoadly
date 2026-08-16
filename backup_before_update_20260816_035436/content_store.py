# content_store.py


import json
import os
import re

def normalize_phone(raw: str) -> str:
    """Strips spaces/dashes/parens/etc out of a phone number, keeping a single
       leading '+' if present. Used both when a phone number is first entered
       (so it's stored clean) and whenever one is displayed (so any number
       already in the system with stray spaces shows clean immediately too,
       with no migration needed)."""
    if not raw:
        return raw
    raw = raw.strip()
    has_plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    return ("+" + digits) if has_plus else digits

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLANS_FILE = os.path.join(BASE_DIR, "plans.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
ACTION_EMOJI_FILE = os.path.join(BASE_DIR, "action_emojis.json")
ADMINS_FILE = os.path.join(BASE_DIR, "admins.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")

DEFAULT_PLANS = [
    {"id": "bronze", "name": "Bronze", "price": "$29/mo", "ad_accounts": 1,
     "supported_groups": "All standard groups", "custom_groups": 0, "simultaneous_ads": 1,
     "features": "1 Ad Account, Standard marketplaces only", "image": None},
    {"id": "silver", "name": "Silver", "price": "$59/mo", "ad_accounts": 2,
     "supported_groups": "All standard + high quality", "custom_groups": 3, "simultaneous_ads": 2,
     "features": "2 Ad Accounts, High Quality access, 3 custom lists", "image": None},
    {"id": "gold", "name": "Gold", "price": "$99/mo", "ad_accounts": 4,
     "supported_groups": "All including OFM", "custom_groups": 10, "simultaneous_ads": 4,
     "features": "4 Ad Accounts, OFM access, 10 custom lists", "image": None},
    {"id": "platinum", "name": "Platinum", "price": "$179/mo", "ad_accounts": 8,
     "supported_groups": "All marketplaces, priority", "custom_groups": -1, "simultaneous_ads": 8,
     "features": "8 Ad Accounts, unlimited custom lists, priority support", "image": None},
]

DEFAULT_SETTINGS = {
    "welcome_text": "<b>Welcome {name} to AutoAdly</b>\n\n\nAutoAdly — Your Business Growth Partner.\nPromote your business across hundreds of Telegram marketplaces automatically—even while you sleep. Simple, reliable, and effortless.",
    "welcome_image": None,
    "terms_text": "Terms & Conditions:\n\n1. Subscriptions are non-refundable once activated.\n2. Banned ad accounts are replaced free while your subscription is active.\n3. You are responsible for the content you advertise.",
    "button_labels": {
        "buy": "Buy Ad Bot",
        "support": "Support",
        "terms": "Terms & Conditions",
    },
}

DEFAULT_ACTION_EMOJIS = {"buy_now": None, "back_button": None, "support": None, "terms": None, "buy_ad_bot_home": None, "plan_button": None}
DEFAULT_ADMINS = {"owner_id": None, "cofounders": []}

def _load(path, default):
    if not os.path.exists(path):
        _save(path, default)
        return json.loads(json.dumps(default))
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                _save(path, default)
                return json.loads(json.dumps(default))
            return json.loads(content)
    except json.JSONDecodeError:
        _save(path, default)
        return json.loads(json.dumps(default))

def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---- plans ----
def load_plans():
    return _load(PLANS_FILE, DEFAULT_PLANS)

def save_plans(data):
    _save(PLANS_FILE, data)

def get_plan(plan_id):
    for p in load_plans():
        if p["id"] == plan_id:
            return p
    return None

# ---- settings ----
def load_settings():
    return _load(SETTINGS_FILE, DEFAULT_SETTINGS)

def save_settings(data):
    _save(SETTINGS_FILE, data)

def set_button_label(key, new_label):
    s = load_settings()
    s.setdefault("button_labels", dict(DEFAULT_SETTINGS["button_labels"]))
    s["button_labels"][key] = new_label
    save_settings(s)

# ---- action emojis ----
def load_action_emojis():
    return _load(ACTION_EMOJI_FILE, DEFAULT_ACTION_EMOJIS)

def get_action_emoji(key):
    return load_action_emojis().get(key)

# ---- admins ----
def load_admins():
    return _load(ADMINS_FILE, DEFAULT_ADMINS)

def save_admins(data):
    _save(ADMINS_FILE, data)

def ensure_owner(user_id):
    admins = load_admins()
    if admins["owner_id"] is None:
        admins["owner_id"] = user_id
        save_admins(admins)
    return admins

def is_admin(user_id):
    admins = load_admins()
    return user_id == admins.get("owner_id") or user_id in admins.get("cofounders", [])

def add_cofounder(user_id):
    admins = load_admins()
    if user_id not in admins["cofounders"]:
        admins["cofounders"].append(user_id)
        save_admins(admins)

# ---- users ----
def register_user(user_id, username=None):
    users = _load(USERS_FILE, {})
    users[str(user_id)] = {"username": (username or "").lower().lstrip("@")}
    _save(USERS_FILE, users)

def get_uid_by_username(username):
    username = username.lower().lstrip("@")
    users = _load(USERS_FILE, {})
    for uid, info in users.items():
        if info.get("username") == username:
            return int(uid)
    return None

def get_username_by_uid(user_id):
    users = _load(USERS_FILE, {})
    info = users.get(str(user_id))
    username = info.get("username") if info else None
    return username or None

def free_customer_slots(user_id):
    """Clears ad_account_id on every filled slot for this customer (so the
       accounts can be reassigned elsewhere) while PRESERVING each slot's
       name/bio/photo_file_id. This means if the customer resubscribes later,
       whatever new account fills 'Adbot #1' again automatically gets the same
       identity as before, since _assign_account reads name/bio/photo straight
       from the slot it's filling."""
    data = load_customer_adbots()
    key = str(user_id)
    slots = data.get(key, [])
    for slot in slots:
        slot["ad_account_id"] = None
    data[key] = slots
    save_customer_adbots(data)

def save_action_emojis(data):
    _save(ACTION_EMOJI_FILE, data)

def set_action_emoji(key, emoji_id):
    e = load_action_emojis()
    e[key] = emoji_id
    save_action_emojis(e)


def update_plan(plan_id, **fields):
    plans = load_plans()
    for p in plans:
        if p["id"] == plan_id:
            p.update(fields)
            break
    save_plans(plans)

SUBSCRIPTIONS_FILE = os.path.join(BASE_DIR, "subscriptions.json")

def load_subscriptions():
    return _load(SUBSCRIPTIONS_FILE, {})

def save_subscriptions(data):
    _save(SUBSCRIPTIONS_FILE, data)

def get_subscription(user_id):
    subs = load_subscriptions()
    return subs.get(str(user_id))

def activate_subscription(user_id, plan_id, months=1, days=None):
    import time as _time
    subs = load_subscriptions()
    key = str(user_id)
    now = _time.time()
    existing = subs.get(key)
    start = now
    if existing and existing.get("expiry", 0) > now:
        start = existing["expiry"]  # renewing before expiry extends from current expiry, not from now
    if days is not None:
        duration_seconds = days * 24 * 60 * 60
    else:
        duration_seconds = months * 30 * 24 * 60 * 60
    expiry = start + duration_seconds
    subs[key] = {
        "plan_id": plan_id,
        "purchase_date": now,
        "expiry": expiry,
        "months": months if days is None else None,
        "days": days,
        "notified_soon": False,
        "reclaimed": False,
    }
    save_subscriptions(subs)
    return subs[key]

CUSTOMER_ADBOTS_FILE = os.path.join(BASE_DIR, "customer_adbots.json")

def load_customer_adbots():
    return _load(CUSTOMER_ADBOTS_FILE, {})

def save_customer_adbots(data):
    _save(CUSTOMER_ADBOTS_FILE, data)

def get_customer_adbots(user_id):
    data = load_customer_adbots()
    return data.get(str(user_id), [])

def ensure_customer_slots(user_id, quota):
    """Grows the customer's slot list up to `quota` empty slots if it's shorter.
       Never shrinks or touches existing slots."""
    data = load_customer_adbots()
    key = str(user_id)
    data.setdefault(key, [])
    while len(data[key]) < quota:
        data[key].append({"name": None, "ad_account_id": None, "bio": None, "photo_file_id": None})
    save_customer_adbots(data)

def get_next_empty_slot_index(user_id):
    data = load_customer_adbots()
    slots = data.get(str(user_id), [])
    for i, slot in enumerate(slots):
        if slot.get("ad_account_id") is None:
            return i
    return None

def fill_slot_with_account(user_id, index, ad_account_id):
    data = load_customer_adbots()
    key = str(user_id)
    if key in data and 0 <= index < len(data[key]):
        data[key][index]["ad_account_id"] = ad_account_id
        save_customer_adbots(data)

def add_customer_adbot(user_id, name, ad_account_id):
    data = load_customer_adbots()
    key = str(user_id)
    data.setdefault(key, [])
    for slot in data[key]:
        if slot.get("ad_account_id") is None:
            slot["ad_account_id"] = ad_account_id
            if name:
                slot["name"] = name
            save_customer_adbots(data)
            return
    data[key].append({"name": name, "ad_account_id": ad_account_id, "bio": None, "photo_file_id": None})
    save_customer_adbots(data)

def rename_customer_adbot(user_id, index, new_name):
    data = load_customer_adbots()
    key = str(user_id)
    if key in data and 0 <= index < len(data[key]):
        data[key][index]["name"] = new_name
        save_customer_adbots(data)

def set_slot_bio(user_id, index, bio):
    data = load_customer_adbots()
    key = str(user_id)
    if key in data and 0 <= index < len(data[key]):
        data[key][index]["bio"] = bio
        save_customer_adbots(data)

def set_slot_photo(user_id, index, photo_file_id):
    data = load_customer_adbots()
    key = str(user_id)
    if key in data and 0 <= index < len(data[key]):
        data[key][index]["photo_file_id"] = photo_file_id
        save_customer_adbots(data)
def set_slot_cached_photo(user_id, index, photo_bytes):
    """Persist a raw Telegram profile photo for this slot."""
    cache_dir = os.path.join(BASE_DIR, "profile_photo_cache")
    os.makedirs(cache_dir, exist_ok=True)

    path = os.path.join(
        cache_dir,
        f"{int(user_id)}_{int(index)}.jpg",
    )

    if photo_bytes:
        with open(path, "wb") as f:
            f.write(photo_bytes)
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def get_slot_cached_photo(user_id, index):
    """Return the cached raw profile photo, if available."""
    path = os.path.join(
        BASE_DIR,
        "profile_photo_cache",
        f"{int(user_id)}_{int(index)}.jpg",
    )

    if not os.path.exists(path):
        return None

    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        print(f"[content_store] cached photo read failed: {e}")
        return None

def slot_display_name(slot, index):
    base = slot.get("name") or "Adbot"
    return f"{base} #{index + 1}"

def get_marketplace_folder_link():
    s = load_settings()
    return s.get("marketplace_folder_link")

def set_marketplace_folder_link(link):
    s = load_settings()
    s["marketplace_folder_link"] = link
    save_settings(s)

def get_dashboard_image():
    s = load_settings()
    return s.get("dashboard_image")

def set_dashboard_image(file_id):
    s = load_settings()
    s["dashboard_image"] = file_id
    save_settings(s)

def get_category_emoji(category):
    e = load_action_emojis()
    return e.get(f"cat_emoji_{category}")

def set_category_emoji(category, emoji_id):
    e = load_action_emojis()
    e[f"cat_emoji_{category}"] = emoji_id
    save_action_emojis(e)

def get_list_emoji(list_name):
    e = load_action_emojis()
    return e.get(f"list_emoji_{list_name}")

def set_list_emoji(list_name, emoji_id):
    e = load_action_emojis()
    e[f"list_emoji_{list_name}"] = emoji_id
    save_action_emojis(e)

BANNED_FILE = os.path.join(BASE_DIR, "banned.json")

def load_all_users():
    return _load(USERS_FILE, {})

def load_banned():
    return _load(BANNED_FILE, {})

def save_banned(data):
    _save(BANNED_FILE, data)

def is_banned(user_id):
    banned = load_banned()
    return str(user_id) in banned

def ban_user(user_id):
    banned = load_banned()
    banned[str(user_id)] = True
    save_banned(banned)

def unban_user(user_id):
    banned = load_banned()
    banned.pop(str(user_id), None)
    save_banned(banned)

PENDING_SETUPS_FILE = os.path.join(BASE_DIR, "pending_setups.json")

def load_pending_setups():
    return _load(PENDING_SETUPS_FILE, {})

def save_pending_setups(data):
    _save(PENDING_SETUPS_FILE, data)

def queue_pending_setup(user_id, profile, ad_request):
    import time as _time
    data = load_pending_setups()
    data[str(user_id)] = {"profile": profile, "ad_request": ad_request, "created_at": _time.time()}
    save_pending_setups(data)

def get_oldest_pending_setup():
    data = load_pending_setups()
    if not data:
        return None, None
    oldest_uid = min(data.keys(), key=lambda k: data[k]["created_at"])
    return int(oldest_uid), data[oldest_uid]

def remove_pending_setup(user_id):
    data = load_pending_setups()
    data.pop(str(user_id), None)
    save_pending_setups(data)

PENDING_ACCOUNT_REQUESTS_FILE = os.path.join(BASE_DIR, "pending_account_requests.json")

def load_pending_account_requests():
    return _load(PENDING_ACCOUNT_REQUESTS_FILE, {})

def save_pending_account_requests(data):
    _save(PENDING_ACCOUNT_REQUESTS_FILE, data)

def get_pending_account_request(user_id):
    data = load_pending_account_requests()
    return data.get(str(user_id))

def queue_pending_account_request(user_id, created_at=None):
    """Adds/re-queues a customer waiting for a new account. Always preserves
       their EARLIEST known queue position: if they're already queued and no
       explicit created_at is given, keeps their original timestamp instead of
       resetting it to now. This guarantees re-checking or re-triggering a
       customer's request (e.g. an admin looking them up) can never silently
       bump them behind someone who queued more recently."""
    import time as _time
    data = load_pending_account_requests()
    key = str(user_id)
    if created_at is None:
        existing = data.get(key)
        created_at = existing["created_at"] if existing else _time.time()
    data[key] = {"created_at": created_at}
    save_pending_account_requests(data)

def get_oldest_pending_account_request():
    """Returns (user_id, created_at) or (None, None) if the queue is empty."""
    data = load_pending_account_requests()
    if not data:
        return None, None
    oldest_uid = min(data.keys(), key=lambda k: data[k]["created_at"])
    return int(oldest_uid), data[oldest_uid]["created_at"]

def remove_pending_account_request(user_id):
    data = load_pending_account_requests()
    data.pop(str(user_id), None)
    save_pending_account_requests(data)

def is_priority_request(entry):
    """created_at == 0 is how /priority and the direct-assign fallback mark
       someone as jumped to the very front of the queue (see
       queue_pending_account_request's docstring)."""
    return entry is not None and entry.get("created_at") == 0

def list_pending_account_requests_sorted():
    """Returns the account-request queue as a list of
       (user_id, created_at, is_priority), priority entries first (in the
       order they were prioritized), then everyone else oldest-first."""
    data = load_pending_account_requests()
    entries = [(int(uid), e["created_at"], is_priority_request(e)) for uid, e in data.items()]
    entries.sort(key=lambda e: (not e[2], e[1]))
    return entries

def remove_priority(user_id):
    """Un-prioritizes a customer previously jumped to the front via /priority
       (created_at forced to 0), restoring them to their fair queue position —
       their subscription's purchase_date if known, otherwise now. Returns
       False if they weren't in the queue or weren't currently prioritized."""
    import time as _time
    data = load_pending_account_requests()
    key = str(user_id)
    entry = data.get(key)
    if not is_priority_request(entry):
        return False
    sub = get_subscription(user_id)
    restored_at = sub.get("purchase_date") if sub else None
    data[key] = {"created_at": restored_at if restored_at is not None else _time.time()}
    save_pending_account_requests(data)
    return True

PENDING_REPLACEMENTS_FILE = os.path.join(BASE_DIR, "pending_replacements.json")

def load_pending_replacements():
    return _load(PENDING_REPLACEMENTS_FILE, {})

def save_pending_replacements(data):
    _save(PENDING_REPLACEMENTS_FILE, data)

def queue_pending_replacement(user_id, index, ad_config):
    """Supports MULTIPLE pending replacements per customer (e.g. two restricted
       accounts on the same account). Stores a list per user, keyed by index."""
    import time as _time
    data = load_pending_replacements()
    key = str(user_id)
    data.setdefault(key, [])
    # avoid duplicate entries for the same index (e.g. re-triggered detection)
    data[key] = [e for e in data[key] if e["index"] != index]
    data[key].append({"index": index, "ad_config": ad_config, "created_at": _time.time()})
    save_pending_replacements(data)

def get_oldest_pending_replacement():
    data = load_pending_replacements()
    best_uid, best_entry, best_time = None, None, None
    for uid, entries in data.items():
        for entry in entries:
            if best_time is None or entry["created_at"] < best_time:
                best_time = entry["created_at"]
                best_uid = int(uid)
                best_entry = entry
    if best_uid is None:
        return None, None
    return best_uid, best_entry

def remove_pending_replacement(user_id, index=None):
    """If index is given, removes only that one slot's entry. Otherwise removes all
       entries for this user (backward-compatible with old call sites)."""
    data = load_pending_replacements()
    key = str(user_id)
    if key not in data:
        return
    if index is None:
        data.pop(key, None)
    else:
        data[key] = [e for e in data[key] if e["index"] != index]
        if not data[key]:
            data.pop(key, None)
    save_pending_replacements(data)

def set_customer_adbot_account(user_id, index, new_account_id):
    data = load_customer_adbots()
    key = str(user_id)
    if key in data and 0 <= index < len(data[key]):
        data[key][index]["ad_account_id"] = new_account_id
        save_customer_adbots(data)

def mark_subscription_flag(user_id, flag_name, value=True):
    subs = load_subscriptions()
    key = str(user_id)
    if key in subs:
        subs[key][flag_name] = value
        save_subscriptions(subs)

PRESTOCK_PROFILES_FILE = os.path.join(BASE_DIR, "prestock_profiles.json")

def load_prestock_profiles():
    return _load(PRESTOCK_PROFILES_FILE, {})

def save_prestock_profiles(data):
    _save(PRESTOCK_PROFILES_FILE, data)

def set_prestock_profile(user_id, profile):
    data = load_prestock_profiles()
    data[str(user_id)] = profile
    save_prestock_profiles(data)

def get_prestock_profile(user_id):
    return load_prestock_profiles().get(str(user_id))

def get_master_account_id():
    s = load_settings()
    return s.get("master_account_id")

def set_master_account_id(account_id):
    s = load_settings()
    s["master_account_id"] = account_id
    save_settings(s)

def get_oldest_pending_fulfillment():
    """Compares the replacement queue and the new-account-request queue and
       returns whichever is genuinely oldest, as ('replacement', uid, entry) or
       ('request', uid, created_at). Returns (None, None, None) if both empty.
       This guarantees true first-come-first-served across BOTH queue types,
       instead of always favoring one over the other."""
    replace_uid, replace_entry = get_oldest_pending_replacement()
    request_uid, request_created_at = get_oldest_pending_account_request()

    replace_time = replace_entry["created_at"] if replace_entry else None
    request_time = request_created_at

    if replace_time is None and request_time is None:
        return None, None, None
    if replace_time is None:
        return "request", request_uid, request_time
    if request_time is None:
        return "replacement", replace_uid, replace_entry
    if replace_time <= request_time:
        return "replacement", replace_uid, replace_entry
    return "request", request_uid, request_time

def reconcile_account_request_queue():
    """Safety net: finds any customer whose filled Ad Bot Accounts are below
       their plan quota but who isn't waiting in EITHER the replacement queue
       or the new-account-request queue — i.e. they were silently dropped and
       would otherwise never get their remaining accounts. Re-queues each one
       found, using their original purchase_date as a fair timestamp (so they
       land in the correct first-come-first-served position, not at the back).
       Returns a list of (user_id, missing_count) that were fixed."""
    subs = load_subscriptions()
    adbots = load_customer_adbots()
    requests = load_pending_account_requests()
    replacements = load_pending_replacements()

    fixed = []
    for uid, sub in subs.items():
        if sub.get("reclaimed"):
            continue  # subscription already expired/reclaimed, not owed anything
        plan = get_plan(sub.get("plan_id"))
        quota = plan.get("max_ad_accounts", 0) if plan else 0
        slots = adbots.get(uid, [])
        missing = quota - sum(1 for s in slots if s.get("ad_account_id") is not None)
        if missing <= 0:
            continue
        already_in_replacement_queue = uid in replacements and len(replacements[uid]) > 0
        already_in_request_queue = uid in requests
        if already_in_replacement_queue or already_in_request_queue:
            continue
        queue_pending_account_request(uid, created_at=sub.get("purchase_date"))
        fixed.append((int(uid), missing))
    return fixed
