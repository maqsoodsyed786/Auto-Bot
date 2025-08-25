import os, requests, time, hashlib, hmac, json

API_KEY = os.getenv("DELTA_API_KEY")  # stored safely in secrets
API_SECRET = os.getenv("DELTA_API_SECRET")
BASE_URL = "https://testnet-api.delta.exchange"  # Sandbox endpoint

def sign_request(path, method="GET", body=""):
    timestamp = str(int(time.time()))
    message = timestamp + method + path + body
    signature = hmac.new(
        API_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return {
        "api-key": API_KEY,
        "timestamp": timestamp,
        "signature": signature,
        "Content-Type": "application/json"
    }

def get_balance():
    path = "/v2/wallet/balances"
    url = BASE_URL + path
    r = requests.get(url, headers=sign_request(path))
    return r.json()

while True:
    print("Balances:", get_balance())
    time.sleep(60)  # runs every 1 minute
