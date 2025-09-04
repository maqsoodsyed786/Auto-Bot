import asyncio
import time
from delta_rest_client import DeltaRestClient
from delta_rest_client import OrderType, TimeInForce
import requests

def get_public_ip():
    ip = requests.get("https://api.ipify.org").text
    return ip

print("Your current public IP is:", get_public_ip())

# === Setup ===
delta = DeltaRestClient(
    base_url='https://cdn-ind.testnet.deltaex.org',
    api_key='OgYia0BEgBrhkuboyEo6aW2TjxAmdY',
    api_secret='hVg8Yy2RCKkCaA1d7UstrJ8QCnMxKl3Q0OOkHup1breugVV1pRelebuHVlI9'
)
print(delta)

# === Bot Config ===
SYMBOL = 'BTCUSDT'
QUANTITY = 0.01
TP_PCT = 0.0005  # 0.05% profit target
SL_PCT = 0.0003  # 0.03% stop loss
WINDOW_SECONDS = 2
PRICE_WINDOW = []

# === Get product ID ===
products = delta.get_assets()  # or use v2/products via requests :contentReference[oaicite:1]{index=1}
print(products)
# You'll filter assets to locate the matching product_id for BTCUSDT

# Assume we found it:
PRODUCT_ID = 84  # replace with actual ID
print(delta.get_l2_orderbook(84),  timeout=5)

in_position = False
entry_price = 0.0

async def scalping_loop():
    global in_position, entry_price
    print("yoooooooooooooooooooo")
    while True:
        print("start")
        ob = delta.get_l2_orderbook(PRODUCT_ID)
        print(ob)
        bid = float(ob['bids'][0][0])
        ask = float(ob['asks'][0][0])
        mid_price = (bid + ask) / 2

        now = time.time()
        PRICE_WINDOW.append((now, mid_price))
        PRICE_WINDOW[:] = [(t, p) for t, p in PRICE_WINDOW if now - t <= WINDOW_SECONDS]
        print("sdbfbdjfbjdbjfbsdjfbjdsbfbdsjbfjsdbjf")

        print(f"Bid: {bid:.2f}, Ask: {ask:.2f}, Mid: {mid_price:.2f}")

        if len(PRICE_WINDOW) >= 2:
            old_price = PRICE_WINDOW[0][1]
            delta_pct = (mid_price - old_price) / old_price

            # Entry signal: rapid momentum
            if not in_position and delta_pct >= TP_PCT:
                resp = delta.place_stop_order(
                    product_id=PRODUCT_ID,
                    size=QUANTITY,
                    side='buy',
                    order_type=OrderType.MARKET
                )
                entry_price = mid_price
                in_position = True
                print(f"[BUY] Entry at {entry_price}")

            # Exit with TP/SL
            elif in_position:
                change = (mid_price - entry_price) / entry_price
                if change >= TP_PCT or change <= -SL_PCT:
                    delta.place_stop_order(
                        product_id=PRODUCT_ID,
                        size=QUANTITY,
                        side='sell',
                        order_type=OrderType.MARKET
                    )
                    print(f"[SELL] Exit at {mid_price:.2f} | {'TP' if change>=TP_PCT else 'SL'}")
                    in_position = False

        await asyncio.sleep(0.1)

if __name__ == "__main__":
    asyncio.run(scalping_loop())
