import aiohttp

from config import TG_API

def build_keyboard(rows_spec):
    raw_rows = []
    for row in rows_spec:
        raw_row = []
        for btn in row:
            raw_btn = {"text": btn["text"]}
            if "url" in btn:
                raw_btn["url"] = btn["url"]
            else:
                raw_btn["callback_data"] = btn["callback_data"]
            if btn.get("emoji_id"):
                raw_btn["icon_custom_emoji_id"] = btn["emoji_id"]
            raw_row.append(raw_btn)
        raw_rows.append(raw_row)
    return {"inline_keyboard": raw_rows}

def _strip_tags(text):
    import re
    return re.sub(r"</?[a-zA-Z][^>]*>", "", text)

async def _post(session, url, payload):
    async with session.post(url, json=payload) as r:
        data = await r.json()
        if not data.get("ok") and "can't parse entities" in str(data.get("description", "")):
            payload = dict(payload)
            payload.pop("parse_mode", None)
            if "text" in payload:
                payload["text"] = _strip_tags(payload["text"])
            if "caption" in payload:
                payload["caption"] = _strip_tags(payload["caption"])
            async with session.post(url, json=payload) as r2:
                return await r2.json()
        return data

async def send_message(chat_id, text, rows_spec, photo=None, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id,
        "parse_mode": parse_mode,
        "reply_markup": build_keyboard(rows_spec),
    }
    async with aiohttp.ClientSession() as session:
        if photo:
            payload["photo"] = photo
            payload["caption"] = text
            return await _post(session, f"{TG_API}/sendPhoto", payload)
        else:
            payload["text"] = text
            return await _post(session, f"{TG_API}/sendMessage", payload)

async def get_chat(chat_id):
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{TG_API}/getChat", json={"chat_id": chat_id}) as r:
            data = await r.json()
            return data.get("result") if data.get("ok") else None

async def delete_message(chat_id, message_id):
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{TG_API}/deleteMessage", json={"chat_id": chat_id, "message_id": message_id}) as r:
            return await r.json()

async def render(chat_id, old_message_id, text, rows_spec, photo=None, parse_mode="HTML"):
    """Replaces a message: deletes the old one and sends a fresh one.
       Avoids all editMessageText/editMessageMedia type-mismatch issues entirely.
       Returns the raw Telegram response — callers MUST read result['result']['message_id']
       and store it, since the old message_id is no longer valid after this call."""
    if old_message_id:
        try:
            await delete_message(chat_id, old_message_id)
        except Exception:
            pass
    return await send_message(chat_id, text, rows_spec, photo=photo, parse_mode=parse_mode)

def new_message_id(render_result):
    """Helper to safely pull the new message_id out of render()'s return value."""
    if isinstance(render_result, dict) and render_result.get("ok"):
        return render_result["result"]["message_id"]
    return None


async def edit_message(chat_id, message_id, text, rows_spec, parse_mode="HTML"):
    """Lightweight text-only edit — use only when you know the message has no photo.
       For messages that might have a photo, use render() instead."""
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
        "reply_markup": build_keyboard(rows_spec),
    }
    async with aiohttp.ClientSession() as session:
        return await _post(session, f"{TG_API}/editMessageText", payload)
