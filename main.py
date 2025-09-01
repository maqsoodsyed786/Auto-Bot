import os, requests, time, hashlib, hmac, json

API_KEY = "OgYia0BEgBrhkuboyEo6aW2TjxAmdY"   # store in env in production
API_SECRET = "hVg8Yy2RCKkCaA1d7UstrJ8QCnMxKl3Q0OOkHup1breugVV1pRelebuHVlI9"
BASE_URL = "https://cdn-ind.testnet.deltaex.org"  # Sandbox endpoint

def get_public_ip():
    ip = requests.get("https://api.ipify.org").text
    return ip

print("Your current public IP is:", get_public_ip())

# delta_scalper_ema.py
# Works on Delta Exchange (India) TESTNET by default
# Strategy: 1m EMA(9/21) crossover, market entries, tight TP/SL, simple risk controls

import os, time, hmac, hashlib, json, requests
from collections import deque

# ==========================
# CONFIG
# ==========================

USE_TESTNET   = True
BASE_URL      = "https://cdn-ind.testnet.deltaex.org" if USE_TESTNET else "https://api.india.delta.exchange"

SYMBOL        = "BTCUSD"   # Ticker symbol
PRODUCT_ID    = 81         # BTCUSD perpetual on Delta India (confirm via /v2/products)

RESOLUTION    = "1m"       # candle resolution
FAST_EMA      = 9
SLOW_EMA      = 21
LOOKBACK      = 120        # candles to pull (>= SLOW_EMA*4)

SIZE          = 1          # contract size per trade (adjust to your account)
TAKE_PROFIT_P = 0.15/100   # +0.15%
STOP_LOSS_P   = 0.10/100   # -0.10%

COOLDOWN_SEC  = 60         # min gap between new entries
MAX_TRADES_HR = 12         # safety limit
POLL_SEC      = 15         # main loop delay

USER_AGENT    = "delta-ema-scalper/1.0"

# ==========================
# AUTH / SIGNING
# ==========================
def sign_request(path, method="GET", query="", body=""):
    ts = str(int(time.time()))
    message = method + ts + path + (query or "") + (body or "")
    sig = hmac.new(API_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "api-key": API_KEY,
        "timestamp": ts,
        "signature": sig,
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json"
    }
    return headers

# ==========================
# HTTP HELPERS
# ==========================
def http_get(path, params=None, auth=False):
    query = ""
    url = BASE_URL + path
    if params:
        # Build stable query string in key order
        items = sorted(params.items())
        query = "?" + "&".join(f"{k}={v}" for k, v in items)
        url += query
    headers = sign_request(path, "GET", query if query else "", "") if auth else {"User-Agent": USER_AGENT}
    r = requests.get(url, headers=headers, timeout=30)
    return r.json()

def http_post(path, payload, auth=True):
    body = json.dumps(payload) if payload else ""
    headers = sign_request(path, "POST", "", body) if auth else {"User-Agent": USER_AGENT, "Content-Type":"application/json"}
    url = BASE_URL + path
    r = requests.post(url, headers=headers, data=body, timeout=30)
    return r.json()

def http_delete(path, auth=True):
    headers = sign_request(path, "DELETE", "", "") if auth else {"User-Agent": USER_AGENT}
    url = BASE_URL + path
    r = requests.delete(url, headers=headers, timeout=30)
    return r.json()

# ==========================
# MARKET DATA
# ==========================
def get_candles(symbol, resolution, start=None, end=None, limit=LOOKBACK):
    # /v2/history/candles?symbol=BTCUSD&resolution=1m&limit=120
    params = {"symbol": symbol, "resolution": resolution, "limit": limit}
    print(params)
    end = int(time.time())               # current timestamp
    start = end - (60 * 60)         # 60 minutes ago
    if start: params["start"] = start
    if end:   params["end"]   = end
    data = http_get("/v2/history/candles", params=params, auth=False)
    # Expected: {"success":true, "result":[{"time":..., "open":..., "high":..., "low":..., "close":..., "volume":...}, ...]}
    if not data.get("success"):
        print("Candle fetch error:", data)
        return []
    return data.get("result", [])

def get_ticker(symbol=SYMBOL):
    data = http_get(f"/v2/tickers/{symbol}", auth=False)
    # Expected includes last traded / mark etc.
    if not data.get("success"):
        print("Ticker error:", data)
        return {}
    return data.get("result", {})

# ==========================
# TRADING: ORDERS & POSITION MGMT
# ==========================
def place_market(side, size, product_id=PRODUCT_ID):
    payload = {
        "product_id": product_id,
        "size": size,
        "side": side,  # "buy" or "sell"
        "order_type": "market_order"
    }
    resp = http_post("/v2/orders", payload, auth=True)
    return resp

def reduce_market_close(side_opened, size, product_id=PRODUCT_ID):
    # close with opposite side and reduce_only
    close_side = "sell" if side_opened == "buy" else "buy"
    payload = {
        "product_id": product_id,
        "size": size,
        "side": close_side,
        "order_type": "market_order",
        "reduce_only": True
    }
    resp = http_post("/v2/orders", payload, auth=True)
    return resp

def get_positions():
    # /v2/positions (Delta supports positions endpoint)
    data = http_get("/v2/positions", auth=True)
    return data

def cancel_all_orders():
    # If you end up placing limits in future, you can clear them
    data = http_delete("/v2/orders/all", auth=True)
    return data

# ==========================
# TECHNICALS
# ==========================
def ema(series, period):
    # series: list/iterable of floats (close prices)
    if len(series) == 0:
        return []
    k = 2 / (period + 1)
    ema_vals = []
    ema_prev = series[0]
    ema_vals.append(ema_prev)
    for i in range(1, len(series)):
        ema_now = series[i] * k + ema_prev * (1 - k)
        ema_vals.append(ema_now)
        ema_prev = ema_now
    return ema_vals

def signal_from_ema(closes):
    if len(closes) < max(FAST_EMA, SLOW_EMA):
        return None
    fast = ema(closes, FAST_EMA)
    slow = ema(closes, SLOW_EMA)
    # Look at last two values for cross
    if len(fast) < 2 or len(slow) < 2:
        return None
    f_prev, f_now = fast[-2], fast[-1]
    s_prev, s_now = slow[-2], slow[-1]

    # Cross up -> BUY, Cross down -> SELL
    if f_prev <= s_prev and f_now > s_now:
        return "buy"
    if f_prev >= s_prev and f_now < s_now:
        return "sell"
    return None

# ==========================
# STATE / RISK CONTROLS
# ==========================
last_entry_ts = 0
trades_window = deque()  # track timestamps to enforce MAX_TRADES_HR

position = {
    "side": None,          # "buy" or "sell"
    "size": 0,
    "entry_price": None
}

def can_trade_now():
    global last_entry_ts, trades_window
    now = time.time()
    # cooldown
    if now - last_entry_ts < COOLDOWN_SEC:
        return False
    # trim >1h
    one_hour_ago = now - 3600
    while trades_window and trades_window[0] < one_hour_ago:
        trades_window.popleft()
    return len(trades_window) < MAX_TRADES_HR

def record_trade():
    global last_entry_ts, trades_window
    ts = time.time()
    last_entry_ts = ts
    trades_window.append(ts)

# ==========================
# MAIN LOOP
# ==========================
def main():
    global position
    print("Starting EMA scalper on", "TESTNET" if USE_TESTNET else "MAINNET", "for", SYMBOL)
    while True:
        try:
            # 1) Price data
            candles = get_candles(SYMBOL, RESOLUTION, limit=LOOKBACK)
            closes = [float(c["close"]) for c in candles] if candles else []
            ticker = get_ticker(SYMBOL)
            last_price = float(ticker.get("close", ticker.get("mark_price", 0)) or 0)

            if not closes or last_price <= 0:
                print("No market data yet. Sleeping...")
                time.sleep(POLL_SEC)
                continue

            # 2) Manage open position (TP/SL)
            if position["side"]:
                # Calculate TP/SL thresholds off entry price
                if position["entry_price"]:
                    ep = float(position["entry_price"])
                    if position["side"] == "buy":
                        tp = ep * (1 + TAKE_PROFIT_P)
                        sl = ep * (1 - STOP_LOSS_P)
                        if last_price >= tp:
                            print(f"TP hit (LONG)! last={last_price:.2f} >= {tp:.2f} — closing")
                            print(reduce_market_close("buy", position["size"]))
                            position = {"side": None, "size": 0, "entry_price": None}
                        elif last_price <= sl:
                            print(f"SL hit (LONG)! last={last_price:.2f} <= {sl:.2f} — closing")
                            print(reduce_market_close("buy", position["size"]))
                            position = {"side": None, "size": 0, "entry_price": None}
                    else:  # short
                        tp = ep * (1 - TAKE_PROFIT_P)
                        sl = ep * (1 + STOP_LOSS_P)
                        if last_price <= tp:
                            print(f"TP hit (SHORT)! last={last_price:.2f} <= {tp:.2f} — closing")
                            print(reduce_market_close("sell", position["size"]))
                            position = {"side": None, "size": 0, "entry_price": None}
                        elif last_price >= sl:
                            print(f"SL hit (SHORT)! last={last_price:.2f} >= {sl:.2f} — closing")
                            print(reduce_market_close("sell", position["size"]))
                            position = {"side": None, "size": 0, "entry_price": None}

            # 3) Entry logic (only if flat and allowed to trade)
            if position["side"] is None and can_trade_now():
                print("ppppppppp")
                sig = signal_from_ema(closes)
                print(sig,"sig")
                if sig in ("buy", "sell"):
                    print(f"Signal: {sig.upper()} — entering @ {last_price:.2f}")
                    resp = place_market(sig, SIZE, PRODUCT_ID)
                    print("Entry response:", resp)

                    # If success, set local position state
                    if resp.get("success"):
                        position["side"] = sig
                        position["size"] = SIZE
                        position["entry_price"] = last_price
                        record_trade()
                    else:
                        print("Order failed:", resp)

            time.sleep(POLL_SEC)

        except Exception as e:
            print("Loop error:", repr(e))
            time.sleep(POLL_SEC)

if __name__ == "__main__":
    main()
