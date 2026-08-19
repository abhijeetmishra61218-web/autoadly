"""
AutoAdly - Crypto Payments admin panel (aiogram, using our existing raw_api pattern)
"""

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message

import raw_api
import content_store as store
import payments_engine as pe

router = Router()

PAY_PENDING = {}

def _admin_home_rows():
    cryptos = pe.all_cryptos()
    rows = []
    for c in cryptos:
        state = "ON" if c.get("enabled") else "OFF"
        emoji_tag = " (emoji set)" if c.get("emoji_id") else ""
        rows.append([{"text": f"{c['name']}{emoji_tag} [{state}]", "callback_data": f"payadmin:c:{c['id']}"}])
    rows.append([{"text": "Test Transaction", "callback_data": "payadmin:test"}])
    rows.append([{"text": "Close", "callback_data": "payadmin:close"}])
    return rows

def _admin_home_text():
    cryptos = pe.all_cryptos()
    lines = ["<b>CRYPTO PAYMENTS</b>", ""]
    for c in cryptos:
        state = "ON" if c.get("enabled") else "OFF"
        addr = c.get("address") or "(no address set)"
        lines.append(f"<b>{c['name']}</b>  [{state}]")
        lines.append(f"  {pe.chain_label(c.get('chain'))}")
        lines.append(f"  {addr}")
        lines.append("")
    return "\n".join(lines)

def _crypto_panel_rows(cid):
    c = pe.get_crypto(cid)
    toggle = "Disable" if c.get("enabled") else "Enable"
    return [
        [{"text": "Edit Address", "callback_data": f"payadmin:addr:{cid}"}],
        [{"text": "Edit Min Confirmations", "callback_data": f"payadmin:conf:{cid}"}],
        [{"text": "Set Emoji", "callback_data": f"payadmin:emoji:{cid}"}],
        [{"text": toggle, "callback_data": f"payadmin:tgl:{cid}"}],
        [{"text": "Test This Crypto", "callback_data": f"payadmin:testc:{cid}"}],
        [{"text": "Back", "callback_data": "payadmin:home"}],
    ]

def _crypto_panel_text(cid):
    c = pe.get_crypto(cid)
    addr = c.get("address") or "(no address set)"
    return (
        f"<b>{c['name']}</b>\n"
        f"Chain: {pe.chain_label(c.get('chain'))}\n"
        f"Status: {'Enabled' if c.get('enabled') else 'Disabled'}\n"
        f"Min confirmations: {c.get('min_conf', 1)}\n"
        f"Emoji: {'Set' if c.get('emoji_id') else 'Not set'}\n\n"
        f"Address:\n{addr}"
    )

@router.message(F.text.regexp(r"^/payments"))
async def cmd_payments(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    await raw_api.send_message(message.chat.id, _admin_home_text(), _admin_home_rows())

@router.callback_query(F.data == "payadmin:home")
async def cb_payadmin_home(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    await raw_api.render(callback.message.chat.id, callback.message.message_id, _admin_home_text(), _admin_home_rows())
    await callback.answer()

@router.callback_query(F.data == "payadmin:close")
async def cb_payadmin_close(callback: CallbackQuery):
    try:
        await raw_api.delete_message(callback.message.chat.id, callback.message.message_id)
    except Exception:
        pass
    await callback.answer()

@router.callback_query(F.data.startswith("payadmin:c:"))
async def cb_payadmin_crypto(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    cid = callback.data.split(":", 2)[2]
    if not pe.get_crypto(cid):
        await callback.answer("Not found.", show_alert=True)
        return
    await raw_api.render(callback.message.chat.id, callback.message.message_id, _crypto_panel_text(cid), _crypto_panel_rows(cid))
    await callback.answer()

@router.callback_query(F.data.startswith("payadmin:tgl:"))
async def cb_payadmin_toggle(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    cid = callback.data.split(":", 2)[2]
    c = pe.get_crypto(cid)
    if c:
        c["enabled"] = not bool(c.get("enabled"))
        pe.save_crypto(c)
    await raw_api.render(callback.message.chat.id, callback.message.message_id, _crypto_panel_text(cid), _crypto_panel_rows(cid))
    await callback.answer("Updated.")

@router.callback_query(F.data.startswith("payadmin:addr:"))
async def cb_payadmin_addr(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    cid = callback.data.split(":", 2)[2]
    PAY_PENDING[callback.from_user.id] = {"action": "edit_addr", "id": cid}
    c = pe.get_crypto(cid)
    await callback.message.answer(f"Send the deposit address for {c['name']}:")
    await callback.answer()

@router.callback_query(F.data.startswith("payadmin:conf:"))
async def cb_payadmin_conf(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    cid = callback.data.split(":", 2)[2]
    PAY_PENDING[callback.from_user.id] = {"action": "edit_conf", "id": cid}
    await callback.message.answer("Send the minimum confirmations required (whole number, e.g. 2):")
    await callback.answer()

@router.callback_query(F.data.startswith("payadmin:emoji:"))
async def cb_payadmin_emoji(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    cid = callback.data.split(":", 2)[2]
    PAY_PENDING[callback.from_user.id] = {"action": "edit_emoji", "id": cid}
    await callback.message.answer("Send the custom emoji's document_id (use /getemojiid), or send 0 to remove it:")
    await callback.answer()

@router.callback_query(F.data == "payadmin:test")
async def cb_payadmin_test(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    rows = [[{"text": c["name"], "callback_data": f"payadmin:testc:{c['id']}"}] for c in pe.all_cryptos()]
    rows.append([{"text": "Back", "callback_data": "payadmin:home"}])
    await raw_api.render(callback.message.chat.id, callback.message.message_id, "Pick which crypto to test, then send the hash:", rows)
    await callback.answer()

@router.callback_query(F.data.startswith("payadmin:testc:"))
async def cb_payadmin_testc(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    cid = callback.data.split(":", 2)[2]
    PAY_PENDING[callback.from_user.id] = {"action": "test_hash", "id": cid}
    c = pe.get_crypto(cid)
    await callback.message.answer(f"Send the transaction hash to test against {c['name']}:")
    await callback.answer()

def _format_test_result(crypto, txhash, res):
    lines = [f"<b>TEST RESULT - {crypto['name']}</b>", pe.chain_label(crypto.get("chain")), "", f"Hash: {txhash}", ""]
    if not res.get("ok"):
        lines.append(f"Could not query the blockchain. Error: {res.get('error')}")
        return "\n".join(lines)
    if not res.get("found"):
        lines.append("Transaction not found on this chain.")
        if res.get("error"):
            lines.append(str(res.get("error")))
        return "\n".join(lines)
    dec = int(crypto.get("decimals", 8))
    amount = res.get("amount", 0.0)
    amount_str = pe.fmt_crypto(amount, dec)
    if crypto.get("is_usd_stable"):
        usd_str = pe.fmt_money(amount)
    else:
        price = pe.get_usd_price(crypto.get("coingecko_id"))
        usd_str = pe.fmt_money(amount * price) if price else "price unavailable"
    lines.append(f"Amount: {amount_str} {crypto['name']} (approx {usd_str})")
    lines.append(f"From: {res.get('from_address') or 'unknown'}")
    lines.append(f"To: {res.get('to_address') or 'unknown'}")
    lines.append(f"Confirmations: {res.get('confirmations', 0)}")
    lines.append(f"Confirmed: {'Yes' if res.get('confirmed') else 'No'}")
    target = crypto.get("address")
    if target:
        matches = pe.addr_match(res.get("to_address"), target)
        lines.append(f"Matches your address: {'Yes' if matches else 'No'}")
    return "\n".join(lines)

@router.message(F.text, ~F.text.startswith("/"), F.from_user.id.in_(PAY_PENDING.keys()))
async def on_payadmin_text(message: Message):
    print(f"[DEBUG] on_payadmin_text caught message from {message.from_user.id}: {message.text[:50]!r}")
    pending = PAY_PENDING.get(message.from_user.id)
    if not pending or not store.is_admin(message.from_user.id):
        return
    action = pending["action"]
    cid = pending.get("id")
    c = pe.get_crypto(cid) if cid else None

    if action == "edit_addr" and c:
        c["address"] = message.text.strip()
        if c["address"]:
            c["enabled"] = True
        pe.save_crypto(c)
        await message.reply("Address saved and crypto enabled.")
        PAY_PENDING.pop(message.from_user.id, None)

    elif action == "edit_conf" and c:
        if not message.text.strip().isdigit():
            await message.reply("Please send a whole number (e.g. 2).")
            return
        c["min_conf"] = int(message.text.strip())
        pe.save_crypto(c)
        await message.reply("Min confirmations updated.")
        PAY_PENDING.pop(message.from_user.id, None)

    elif action == "edit_emoji" and c:
        val = message.text.strip()
        c["emoji_id"] = None if val == "0" else val
        pe.save_crypto(c)
        await message.reply("Emoji updated." if c["emoji_id"] else "Emoji removed.")
        PAY_PENDING.pop(message.from_user.id, None)

    elif action == "test_hash" and c:
        PAY_PENDING.pop(message.from_user.id, None)
        wait_msg = await message.reply("Looking up the transaction, please wait...")
        res = await pe.verify_tx(c, message.text.strip())
        out = _format_test_result(c, message.text.strip(), res)
        try:
            await wait_msg.edit_text(out)
        except Exception:
            await message.reply(out)
