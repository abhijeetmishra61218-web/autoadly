"""
AutoAdly - Crypto Payments Engine
Ported from Premium Villa Bot, framework-agnostic (works with any bot library).
"""

import os
import json
import time
import urllib.request
import urllib.error
import asyncio

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PAY_FILE = os.path.join(BASE_DIR, "cryptos.json")
USED_HASHES_FILE = os.path.join(BASE_DIR, "used_hashes.json")

TX_TIME_GRACE = 300
PAY_AMOUNT_TOLERANCE = 0.99

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

ESPLORA_BTC = "https://blockstream.info/api"
ESPLORA_LTC = "https://litecoinspace.org/api"
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
TRONSCAN_TX = "https://apilist.tronscanapi.com/api/transaction-info?hash="
BSC_RPCS = [
    "https://bsc-dataseed1.binance.org/",
    "https://bsc-dataseed2.binance.org/",
    "https://bsc-dataseed3.binance.org/",
    "https://bsc-dataseed4.binance.org/",
]
ETH_RPCS = [
    "https://eth.llamarpc.com",
    "https://rpc.ankr.com/eth",
    "https://ethereum.publicnode.com",
]
BSCSCAN_API = "https://api.etherscan.io/v2/api"
ETHERSCAN_API = "https://api.etherscan.io/v2/api"
COINGECKO_PRICE = "https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"

BSCSCAN_API_KEY = "3EVGFMHJTRURZZRSK9FCP7BD8AZ6D7QCZ4"
ETHERSCAN_API_KEY = "3EVGFMHJTRURZZRSK9FCP7BD8AZ6D7QCZ4"  # etherscan v2 API is shared across chains via chainid param

USDT_BEP20_CONTRACT = "0x55d398326f99059fF775485246999027B3197955"
USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
USDC_ERC20_CONTRACT = "0xA0b86991c6218b36C1D19D4a2e9Eb0cE3606eB48"
USDC_SOL_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

SUPPORTED_CHAINS = {
    "btc":        {"label": "Bitcoin (BTC)",           "decimals": 8,  "coingecko": "bitcoin",  "stable": False, "token": None},
    "ltc":        {"label": "Litecoin (LTC)",          "decimals": 8,  "coingecko": "litecoin", "stable": False, "token": None},
    "sol":        {"label": "Solana (SOL)",            "decimals": 9,  "coingecko": "solana",   "stable": False, "token": None},
    "trc20":      {"label": "USDT - Tron (TRC20)",     "decimals": 6,  "coingecko": "tether",   "stable": True,  "token": USDT_TRC20_CONTRACT},
    "bep20":      {"label": "USDT - BSC (BEP20)",      "decimals": 18, "coingecko": "tether",   "stable": True,  "token": USDT_BEP20_CONTRACT},
    "eth":        {"label": "Ethereum (ETH)",          "decimals": 18, "coingecko": "ethereum", "stable": False, "token": None},
    "erc20_usdc": {"label": "USDC - Ethereum (ERC20)", "decimals": 6,  "coingecko": "usd-coin", "stable": True,  "token": USDC_ERC20_CONTRACT},
    "spl_usdc":   {"label": "USDC - Solana (SPL)",     "decimals": 6,  "coingecko": "usd-coin", "stable": True,  "token": USDC_SOL_MINT},
}

def _default_cryptos():
    return {
        "cryptos": [
            {"id": "btc", "name": "BTC", "chain": "btc", "address": "",
             "coingecko_id": "bitcoin", "decimals": 8, "enabled": False,
             "min_conf": 1, "is_usd_stable": False, "token_contract": None, "emoji_id": None},
            {"id": "ltc", "name": "LTC", "chain": "ltc", "address": "",
             "coingecko_id": "litecoin", "decimals": 8, "enabled": False,
             "min_conf": 2, "is_usd_stable": False, "token_contract": None, "emoji_id": None},
            {"id": "sol", "name": "SOL", "chain": "sol", "address": "",
             "coingecko_id": "solana", "decimals": 9, "enabled": False,
             "min_conf": 1, "is_usd_stable": False, "token_contract": None, "emoji_id": None},
            {"id": "usdt_trc20", "name": "USDT(Trc20)", "chain": "trc20", "address": "",
             "coingecko_id": "tether", "decimals": 6, "enabled": False,
             "min_conf": 20, "is_usd_stable": True, "token_contract": USDT_TRC20_CONTRACT, "emoji_id": None},
            {"id": "usdt_bep20", "name": "USDT(Bep20)", "chain": "bep20", "address": "",
             "coingecko_id": "tether", "decimals": 18, "enabled": False,
             "min_conf": 12, "is_usd_stable": True, "token_contract": USDT_BEP20_CONTRACT, "emoji_id": None},
            {"id": "eth", "name": "ETH", "chain": "eth", "address": "",
             "coingecko_id": "ethereum", "decimals": 18, "enabled": False,
             "min_conf": 12, "is_usd_stable": False, "token_contract": None, "emoji_id": None},
            {"id": "usdc_erc20", "name": "USDC(Erc20)", "chain": "erc20_usdc", "address": "",
             "coingecko_id": "usd-coin", "decimals": 6, "enabled": False,
             "min_conf": 12, "is_usd_stable": True, "token_contract": USDC_ERC20_CONTRACT, "emoji_id": None},
            {"id": "usdc_sol", "name": "USDC(Sol)", "chain": "spl_usdc", "address": "",
             "coingecko_id": "usd-coin", "decimals": 6, "enabled": False,
             "min_conf": 1, "is_usd_stable": True, "token_contract": USDC_SOL_MINT, "emoji_id": None},
        ]
    }

# ========================= storage =========================
def load_cryptos():
    if not os.path.exists(PAY_FILE):
        save_cryptos(_default_cryptos())
    try:
        with open(PAY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = _default_cryptos()
        save_cryptos(data)
    if not isinstance(data, dict) or not isinstance(data.get("cryptos"), list):
        data = _default_cryptos()
        save_cryptos(data)
    return data

def save_cryptos(data):
    with open(PAY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def all_cryptos():
    return load_cryptos()["cryptos"]

def enabled_cryptos():
    return [c for c in all_cryptos() if c.get("enabled") and c.get("address")]

def get_crypto(cid):
    for c in all_cryptos():
        if c["id"] == cid:
            return c
    return None

def save_crypto(updated):
    data = load_cryptos()
    for i, c in enumerate(data["cryptos"]):
        if c["id"] == updated["id"]:
            data["cryptos"][i] = updated
            break
    save_cryptos(data)

def chain_label(chain):
    info = SUPPORTED_CHAINS.get(chain)
    return info["label"] if info else chain

# ========================= used-hash tracking =========================
def _load_used_hashes():
    try:
        with open(USED_HASHES_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def hash_used(h):
    if not h:
        return False
    return h.strip().lower() in _load_used_hashes()

def mark_hash_used(h):
    if not h:
        return
    used = _load_used_hashes()
    used.add(h.strip().lower())
    try:
        with open(USED_HASHES_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(used), f)
    except Exception:
        pass

# ========================= formatting =========================
def fmt_money(value):
    try:
        v = float(value)
    except Exception:
        return "$0"
    if abs(v - round(v)) < 0.005:
        return "$" + str(int(round(v)))
    return "$" + ("%.2f" % v)

def fmt_crypto(amount, decimals=8):
    try:
        v = float(amount)
    except Exception:
        return str(amount)
    s = ("%." + str(min(decimals, 8)) + "f") % v
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"

# ========================= HTTP helpers =========================
def _http_get(url, timeout=15, as_json=True):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8").strip()
    return json.loads(raw) if as_json else raw

def _http_post_json(url, payload, timeout=15):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

# ========================= price conversion =========================
_PRICE_CACHE = {}
_PRICE_TTL = 60

def get_usd_price(coingecko_id):
    if not coingecko_id:
        return None
    now = time.time()
    cached = _PRICE_CACHE.get(coingecko_id)
    if cached and (now - cached[0]) < _PRICE_TTL:
        return cached[1]
    try:
        data = _http_get(COINGECKO_PRICE.format(ids=coingecko_id))
        price = float(data[coingecko_id]["usd"])
        _PRICE_CACHE[coingecko_id] = (now, price)
        return price
    except Exception:
        return cached[1] if cached else None

def usd_to_crypto(usd_amount, crypto):
    if crypto.get("is_usd_stable"):
        return float(usd_amount), 1.0
    price = get_usd_price(crypto.get("coingecko_id"))
    if not price or price <= 0:
        return None, None
    return float(usd_amount) / price, price

# ========================= result builder =========================
def _result(ok=True, found=False, amount=0.0, to_address=None, from_address=None,
            confirmations=0, confirmed=False, status_ok=True, all_to=None, error=None,
            timestamp=None):
    return {
        "ok": ok, "found": found, "amount": float(amount),
        "to_address": to_address, "from_address": from_address,
        "confirmations": int(confirmations), "confirmed": bool(confirmed),
        "status_ok": bool(status_ok), "all_to": all_to or [], "error": error,
        "timestamp": timestamp,
    }

# ----- BTC / LTC -----
def _verify_esplora(base, txid, target, decimals):
    tx = _http_get(base + "/tx/" + txid)
    vout = tx.get("vout", []) or []
    all_to = []
    amount_to_target = 0
    for o in vout:
        addr = o.get("scriptpubkey_address")
        val = int(o.get("value", 0) or 0)
        if addr:
            all_to.append(addr)
        if target and addr == target:
            amount_to_target += val
    total_out = sum(int(o.get("value", 0) or 0) for o in vout)
    from_addr = None
    vin = tx.get("vin", []) or []
    if vin:
        prevout = vin[0].get("prevout") or {}
        from_addr = prevout.get("scriptpubkey_address")
    status = tx.get("status", {}) or {}
    confirmed_in_block = bool(status.get("confirmed"))
    confs = 0
    if confirmed_in_block and status.get("block_height") is not None:
        try:
            tip = int(_http_get(base + "/blocks/tip/height", as_json=False))
            confs = max(0, tip - int(status["block_height"]) + 1)
        except Exception:
            confs = 1
    sats = amount_to_target if target else total_out
    amount = sats / float(10 ** decimals)
    primary_to = target if (target and amount_to_target > 0) else (all_to[0] if all_to else None)
    ts = status.get("block_time")
    return _result(ok=True, found=True, amount=amount, to_address=primary_to,
                   from_address=from_addr, confirmations=confs, confirmed=confirmed_in_block,
                   status_ok=True, all_to=all_to, timestamp=ts)

# ----- Solana native SOL -----
def _verify_sol(sig, target, decimals=9):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
        "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0,
                         "commitment": "finalized"}],
    }
    res = _http_post_json(SOLANA_RPC, payload)
    r = res.get("result")
    if not r:
        return _result(ok=True, found=False, error="Transaction not found / not finalized yet")
    meta = r.get("meta") or {}
    msg = (r.get("transaction") or {}).get("message") or {}
    raw_keys = msg.get("accountKeys") or []
    accounts = []
    for k in raw_keys:
        accounts.append(k.get("pubkey") if isinstance(k, dict) else k)
    pre = meta.get("preBalances") or []
    post = meta.get("postBalances") or []
    amount = 0.0
    if target and target in accounts:
        idx = accounts.index(target)
        if idx < len(pre) and idx < len(post):
            amount = (post[idx] - pre[idx]) / float(10 ** decimals)
    from_addr = accounts[0] if accounts else None
    err = meta.get("err")
    confirmed = err is None
    ts = r.get("blockTime")
    return _result(ok=True, found=True, amount=amount, to_address=target,
                   from_address=from_addr, confirmations=(1 if confirmed else 0),
                   confirmed=confirmed, status_ok=confirmed, all_to=accounts[:6], timestamp=ts)

# ----- Solana SPL token (USDC-SOL) -----
def _verify_spl(sig, target_owner, mint, decimals=6):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
        "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0,
                         "commitment": "finalized"}],
    }
    res = _http_post_json(SOLANA_RPC, payload)
    r = res.get("result")
    if not r:
        return _result(ok=True, found=False, error="Transaction not found / not finalized yet")
    meta = r.get("meta") or {}
    err = meta.get("err")
    confirmed = err is None
    pre_bal = meta.get("preTokenBalances") or []
    post_bal = meta.get("postTokenBalances") or []

    def _bal_map(entries):
        out = {}
        for e in entries:
            if e.get("mint") != mint:
                continue
            owner = e.get("owner")
            amt = float(((e.get("uiTokenAmount") or {}).get("uiAmountString")) or 0)
            out[owner] = amt
        return out

    pre_map = _bal_map(pre_bal)
    post_map = _bal_map(post_bal)
    amount = 0.0
    to_owner = None
    if target_owner:
        delta = post_map.get(target_owner, 0.0) - pre_map.get(target_owner, 0.0)
        if delta > 0:
            amount = delta
            to_owner = target_owner
    else:
        for owner, post_amt in post_map.items():
            delta = post_amt - pre_map.get(owner, 0.0)
            if delta > 0:
                amount = delta
                to_owner = owner
                break
    from_owner = None
    for owner, pre_amt in pre_map.items():
        if post_map.get(owner, 0.0) < pre_amt:
            from_owner = owner
            break
    ts = r.get("blockTime")
    return _result(ok=True, found=True, amount=amount, to_address=to_owner,
                   from_address=from_owner, confirmations=(1 if confirmed else 0),
                   confirmed=confirmed, status_ok=confirmed, all_to=list(post_map.keys()), timestamp=ts)

# ----- USDT TRC20 -----
def _verify_trc20(txhash, target, contract, decimals=6):
    data = _http_get(TRONSCAN_TX + txhash)
    if not data or (not data.get("hash") and not data.get("trc20TransferInfo")):
        return _result(ok=True, found=False, error="Transaction not found on Tronscan")
    transfers = data.get("trc20TransferInfo") or []
    confirmed_flag = bool(data.get("confirmed"))
    contract_ret = data.get("contractRet") or "SUCCESS"
    confs = int(data.get("confirmations") or (1 if confirmed_flag else 0))
    amount = 0.0
    to_addr = None
    from_addr = None
    all_to = []
    for t in transfers:
        ca = t.get("contract_address") or ""
        if contract and ca and ca.lower() != contract.lower():
            continue
        dec = int(t.get("decimals", decimals) or decimals)
        try:
            val = float(t.get("amount_str", "0")) / float(10 ** dec)
        except Exception:
            val = 0.0
        t_to = t.get("to_address")
        t_from = t.get("from_address")
        if t_to:
            all_to.append(t_to)
        if target and t_to == target:
            amount += val
            to_addr = t_to
            from_addr = t_from
        elif not target:
            amount += val
            to_addr = t_to
            from_addr = t_from
    if to_addr is None and transfers:
        t = transfers[0]
        to_addr = t.get("to_address")
        from_addr = t.get("from_address")
    ts = data.get("timestamp")
    try:
        ts = (float(ts) / 1000.0) if ts else None
    except Exception:
        ts = None
    return _result(ok=True, found=True, amount=amount, to_address=to_addr, from_address=from_addr,
                   confirmations=confs, confirmed=(confirmed_flag and contract_ret == "SUCCESS"),
                   status_ok=(contract_ret == "SUCCESS"), all_to=all_to, timestamp=ts)

# ----- generic EVM helpers (shared by BEP20 and ETH/ERC20) -----
def _evm_rpc(method, params, rpc_urls):
    for url in rpc_urls:
        try:
            result = _http_post_json(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            if result and "result" in result:
                return result
        except Exception:
            continue
    return {}

def _verify_evm_token(txhash, target, contract, decimals, rpc_urls):
    rcpt = (_evm_rpc("eth_getTransactionReceipt", [txhash], rpc_urls) or {}).get("result")
    if not rcpt:
        return _result(ok=True, found=False, error="Transaction receipt not found")
    status_ok = str(rcpt.get("status")) == "0x1"
    logs = rcpt.get("logs") or []
    amount = 0.0
    to_addr = None
    from_addr = None
    all_to = []
    for lg in logs:
        if contract and (lg.get("address", "").lower() != contract.lower()):
            continue
        topics = lg.get("topics") or []
        if not topics or topics[0].lower() != TRANSFER_TOPIC:
            continue
        if len(topics) < 3:
            continue
        t_from = "0x" + topics[1][-40:]
        t_to = "0x" + topics[2][-40:]
        try:
            val = int(lg.get("data", "0x0"), 16) / float(10 ** decimals)
        except Exception:
            val = 0.0
        all_to.append(t_to)
        if target and t_to.lower() == target.lower():
            amount += val
            to_addr = t_to
            from_addr = t_from
        elif not target:
            amount += val
            to_addr = t_to
            from_addr = t_from
    if to_addr is None and all_to:
        to_addr = all_to[0]
    confs = 0
    ts = None
    try:
        tx_block = int(rcpt.get("blockNumber"), 16)
        tip_res = _evm_rpc("eth_blockNumber", [], rpc_urls)
        tip = int(tip_res.get("result"), 16)
        confs = max(0, tip - tx_block + 1)
        blk = (_evm_rpc("eth_getBlockByNumber", [hex(tx_block), False], rpc_urls) or {}).get("result") or {}
        if blk.get("timestamp"):
            ts = int(blk["timestamp"], 16)
    except Exception:
        confs = 1 if status_ok else 0
    return _result(ok=True, found=True, amount=amount, to_address=to_addr, from_address=from_addr,
                   confirmations=confs, confirmed=(status_ok and confs >= 1), status_ok=status_ok,
                   all_to=all_to, timestamp=ts)

def _verify_bep20(txhash, target, contract, decimals=18):
    return _verify_evm_token(txhash, target, contract, decimals, BSC_RPCS)

def _verify_erc20_usdc(txhash, target, contract, decimals=6):
    return _verify_evm_token(txhash, target, contract, decimals, ETH_RPCS)

# ----- native ETH transfer -----
def _verify_eth_native(txhash, target, decimals=18):
    rcpt = (_evm_rpc("eth_getTransactionReceipt", [txhash], ETH_RPCS) or {}).get("result")
    if not rcpt:
        return _result(ok=True, found=False, error="Transaction receipt not found")
    status_ok = str(rcpt.get("status")) == "0x1"
    tx = (_evm_rpc("eth_getTransactionByHash", [txhash], ETH_RPCS) or {}).get("result")
    if not tx:
        return _result(ok=True, found=False, error="Transaction not found")
    to_addr = tx.get("to")
    from_addr = tx.get("from")
    try:
        amount = int(tx.get("value", "0x0"), 16) / float(10 ** decimals)
    except Exception:
        amount = 0.0
    confs = 0
    ts = None
    try:
        tx_block = int(rcpt.get("blockNumber"), 16)
        tip_res = _evm_rpc("eth_blockNumber", [], ETH_RPCS)
        tip = int(tip_res.get("result"), 16)
        confs = max(0, tip - tx_block + 1)
        blk = (_evm_rpc("eth_getBlockByNumber", [hex(tx_block), False], ETH_RPCS) or {}).get("result") or {}
        if blk.get("timestamp"):
            ts = int(blk["timestamp"], 16)
    except Exception:
        confs = 1 if status_ok else 0
    matches = bool(target) and bool(to_addr) and to_addr.lower() == target.lower()
    return _result(ok=True, found=True, amount=amount if matches or not target else 0.0,
                   to_address=to_addr, from_address=from_addr, confirmations=confs,
                   confirmed=(status_ok and confs >= 1), status_ok=status_ok, all_to=[to_addr], timestamp=ts)

# ========================= verify dispatcher =========================
def _verify_blocking(crypto, txhash):
    chain = crypto.get("chain")
    target = crypto.get("address") or None
    dec = int(crypto.get("decimals", 8))
    try:
        if chain == "btc":
            return _verify_esplora(ESPLORA_BTC, txhash, target, dec)
        if chain == "ltc":
            return _verify_esplora(ESPLORA_LTC, txhash, target, dec)
        if chain == "sol":
            return _verify_sol(txhash, target, dec)
        if chain == "trc20":
            return _verify_trc20(txhash, target, crypto.get("token_contract"), dec)
        if chain == "bep20":
            return _verify_bep20(txhash, target, crypto.get("token_contract"), dec)
        if chain == "eth":
            return _verify_eth_native(txhash, target, dec)
        if chain == "erc20_usdc":
            return _verify_erc20_usdc(txhash, target, crypto.get("token_contract"), dec)
        if chain == "spl_usdc":
            return _verify_spl(txhash, target, crypto.get("token_contract"), dec)
        return _result(ok=False, found=False, error="No detector for chain '%s'" % chain)
    except urllib.error.HTTPError as e:
        return _result(ok=False, found=False, error="HTTP %s from blockchain API" % e.code)
    except Exception as e:
        return _result(ok=False, found=False, error=str(e))

async def verify_tx(crypto, txhash):
    return await asyncio.to_thread(_verify_blocking, crypto, txhash)

# ========================= address scanners (for auto-detection) =========================
def _scan_esplora_addr(base, target, decimals):
    out = []
    try:
        txs = []
        try:
            txs += _http_get(base + "/address/" + target + "/txs", timeout=15) or []
        except Exception:
            pass
        try:
            txs += _http_get(base + "/address/" + target + "/txs/mempool", timeout=15) or []
        except Exception:
            pass
        for tx in txs:
            amt = 0
            for o in tx.get("vout", []) or []:
                if o.get("scriptpubkey_address") == target:
                    amt += int(o.get("value", 0) or 0)
            if amt <= 0:
                continue
            out.append({"hash": tx.get("txid"), "amount": amt / float(10 ** decimals)})
    except Exception as e:
        print(f"[scan_esplora] Error: {e}")
    return out

def _scan_sol_addr(target, decimals):
    out = []
    try:
        res = _http_post_json(SOLANA_RPC, {
            "jsonrpc": "2.0", "id": 1,
            "method": "getSignaturesForAddress",
            "params": [target, {"limit": 15}]
        })
        sigs = res.get("result") or []
        for s in sigs:
            sig = s.get("signature")
            if sig:
                out.append({"hash": sig, "amount": None})
    except Exception as e:
        print(f"[scan_sol] Error: {e}")
    return out

def _scan_trc20_addr(target, contract, decimals):
    out = []
    try:
        url = (
            "https://apilist.tronscanapi.com/api/token_trc20/transfers"
            "?limit=25&start=0&direction=2&relatedAddress=" + target
            + "&contractAddress=" + (contract or "")
        )
        data = _http_get(url, timeout=15)
        transfers = data.get("token_transfers") or data.get("data") or []
        for t in transfers:
            to_a = t.get("to_address") or t.get("toAddress") or ""
            if to_a.lower() != target.lower():
                continue
            h = t.get("transaction_id") or t.get("hash") or t.get("transactionHash")
            if h:
                out.append({"hash": h, "amount": None})
    except Exception as e:
        print(f"[scan_trc20] Error: {e}")
    return out

def _scan_bep20_addr(target, contract, decimals):
    out = []
    try:
        params = {
            "chainid": "56", "module": "account", "action": "tokentx",
            "contractaddress": contract, "address": target,
            "sort": "desc", "offset": "10", "page": "1",
        }
        if BSCSCAN_API_KEY:
            params["apikey"] = BSCSCAN_API_KEY
        url = BSCSCAN_API + "?" + "&".join(f"{k}={v}" for k, v in params.items())
        data = _http_get(url, timeout=15)
        if data.get("status") == "1" and data.get("result"):
            for tx in data["result"]:
                to_addr = tx.get("to", "").lower()
                if target and to_addr != target.lower():
                    continue
                h = tx.get("hash")
                if h:
                    out.append({"hash": h, "amount": None})
    except Exception as e:
        print(f"[scan_bep20] Error: {e}")
    return out

def _scan_erc20_addr(target, contract, decimals):
    out = []
    try:
        params = {
            "chainid": "1", "module": "account", "action": "tokentx",
            "contractaddress": contract, "address": target,
            "sort": "desc", "offset": "10", "page": "1",
        }
        if ETHERSCAN_API_KEY:
            params["apikey"] = ETHERSCAN_API_KEY
        url = ETHERSCAN_API + "?" + "&".join(f"{k}={v}" for k, v in params.items())
        data = _http_get(url, timeout=15)
        if data.get("status") == "1" and data.get("result"):
            for tx in data["result"]:
                to_addr = tx.get("to", "").lower()
                if target and to_addr != target.lower():
                    continue
                h = tx.get("hash")
                if h:
                    out.append({"hash": h, "amount": None})
    except Exception as e:
        print(f"[scan_erc20] Error: {e}")
    return out

def _scan_eth_native_addr(target, decimals):
    out = []
    try:
        params = {
            "chainid": "1", "module": "account", "action": "txlist",
            "address": target, "sort": "desc", "offset": "10", "page": "1",
        }
        if ETHERSCAN_API_KEY:
            params["apikey"] = ETHERSCAN_API_KEY
        url = ETHERSCAN_API + "?" + "&".join(f"{k}={v}" for k, v in params.items())
        data = _http_get(url, timeout=15)
        if data.get("status") == "1" and data.get("result"):
            for tx in data["result"]:
                to_addr = (tx.get("to") or "").lower()
                if target and to_addr != target.lower():
                    continue
                h = tx.get("hash")
                if h:
                    out.append({"hash": h, "amount": None})
    except Exception as e:
        print(f"[scan_eth] Error: {e}")
    return out

def _scan_spl_addr(target, mint, decimals):
    out = []
    try:
        res = _http_post_json(SOLANA_RPC, {
            "jsonrpc": "2.0", "id": 1,
            "method": "getSignaturesForAddress",
            "params": [target, {"limit": 15}]
        })
        sigs = res.get("result") or []
        for s in sigs:
            sig = s.get("signature")
            if sig:
                out.append({"hash": sig, "amount": None})
    except Exception as e:
        print(f"[scan_spl] Error: {e}")
    return out

def _scan_blocking(crypto):
    chain = crypto.get("chain")
    target = crypto.get("address") or None
    dec = int(crypto.get("decimals", 8))
    if not target:
        return []
    try:
        if chain == "btc":
            return _scan_esplora_addr(ESPLORA_BTC, target, dec)
        if chain == "ltc":
            return _scan_esplora_addr(ESPLORA_LTC, target, dec)
        if chain == "sol":
            return _scan_sol_addr(target, dec)
        if chain == "trc20":
            return _scan_trc20_addr(target, crypto.get("token_contract"), dec)
        if chain == "bep20":
            return _scan_bep20_addr(target, crypto.get("token_contract"), dec)
        if chain == "eth":
            return _scan_eth_native_addr(target, dec)
        if chain == "erc20_usdc":
            return _scan_erc20_addr(target, crypto.get("token_contract"), dec)
        if chain == "spl_usdc":
            return _scan_spl_addr(target, crypto.get("token_contract"), dec)
    except Exception:
        return []
    return []

async def scan_address(crypto):
    return await asyncio.to_thread(_scan_blocking, crypto)

# ========================= validation helpers =========================
def amount_ok(received, required):
    try:
        r = float(received)
        req = float(required)
        return r + 1e-12 >= req * PAY_AMOUNT_TOLERANCE and r <= req * 1.10
    except Exception:
        return False

def addr_match(a, b):
    return bool(a) and bool(b) and str(a).strip().lower() == str(b).strip().lower()

def time_ok(started_at, res):
    ts = res.get("timestamp")
    if not started_at or ts is None:
        return True
    try:
        return float(ts) >= (float(started_at) - TX_TIME_GRACE)
    except Exception:
        return True

import re as _re

_EXPLORER_HASH_PATTERNS = [
    r"bscscan\.com/tx/([0-9a-fA-Fx]+)",
    r"etherscan\.io/tx/([0-9a-fA-Fx]+)",
    r"blockstream\.info/tx/([0-9a-fA-F]+)",
    r"litecoinspace\.org/tx/([0-9a-fA-F]+)",
    r"tronscan\.org/#/transaction/([0-9a-fA-F]+)",
    r"solscan\.io/tx/([1-9A-HJ-NP-Za-km-z]+)",
    r"explorer\.solana\.com/tx/([1-9A-HJ-NP-Za-km-z]+)",
]

def extract_hash(raw_text):
    """Accepts either a raw hash or a full blockchain explorer URL, returns just the hash/signature."""
    raw_text = raw_text.strip()
    for pattern in _EXPLORER_HASH_PATTERNS:
        m = _re.search(pattern, raw_text)
        if m:
            return m.group(1)
    # not a known explorer link — assume it's already a raw hash, just take the first whitespace-separated token
    return raw_text.split()[0] if raw_text else raw_text
