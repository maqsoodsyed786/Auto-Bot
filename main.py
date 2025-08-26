import os, requests, time, hashlib, hmac, json

API_KEY = "OgYia0BEgBrhkuboyEo6aW2TjxAmdY"   # store in env in production
API_SECRET = "hVg8Yy2RCKkCaA1d7UstrJ8QCnMxKl3Q0OOkHup1breugVV1pRelebuHVlI9"
BASE_URL = "https://cdn-ind.testnet.deltaex.org"  # Sandbox endpoint

def get_public_ip():
    ip = requests.get("https://api.ipify.org").text
    return ip

print("Your current public IP is:", get_public_ip())

def sign_request(path, method="GET", query="", body=""):
    timestamp = str(int(time.time()))
    message = method + timestamp + path + query + body   # correct order
    signature = hmac.new(
        API_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return {
        "api-key": API_KEY,
        "timestamp": timestamp,
        "signature": signature,
        "User-Agent": "my-api-client",
        "Content-Type": "application/json"
    }

def get_balance():
    path = "/v2/wallet/balances"
    url = BASE_URL + path
    headers = sign_request(path, "GET")
    r = requests.get(url, headers=headers)
    return r.json()

print("Balances:", get_balance())
