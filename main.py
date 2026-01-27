from flask import Flask, jsonify, request
from flask_cors import CORS
import os, requests
from statistics import mean
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

POLYGON_KEY = os.environ.get("POLYGON_API_KEY")

# Cache last successful analysis per ticker
LAST_SNAPSHOT = {}

# Per-user watchlists (keyed by IP for now)
USER_WATCHLISTS = {}

@app.route("/")
def home():
    return "AI Market Backend is running!"

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "ai-market-backend"})

def polygon_ohlc(symbol, multiplier, timespan, start, end):
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/"
        f"{multiplier}/{timespan}/{start}/{end}"
        f"?adjusted=true&sort=asc&limit=5000&apiKey={POLYGON_KEY}"
    )
    r = requests.get(url, timeout=10)
    return r.json().get("results", [])

def get_prev(symbol):
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev?apiKey={POLYGON_KEY}"
    r = requests.get(url, timeout=10)
    d = r.json()
    if "results" not in d or not d["results"]:
        return None
    return d["results"][0]

def get_last_trade(symbol):
    try:
        r = requests.get(
            f"https://api.polygon.io/v2/last/trade/{symbol}?apiKey={POLYGON_KEY}",
            timeout=5
        )
        d = r.json()
        if "results" in d and "p" in d["results"]:
            return round(d["results"]["p"], 2)
    except:
        pass
    return None

def get_user_id():
    return request.headers.get("X-Forwarded-For", request.remote_addr)

@app.route("/watchlist")
def get_watchlist():
    user = get_user_id()
    tickers = USER_WATCHLISTS.get(user, [])

    results = []
    for t in tickers:
        d = get_prev(t)
        if d:
            price = round(d["c"], 2)
            change = round(((d["c"] - d["o"]) / d["o"]) * 100, 2)
        else:
            price = "—"
            change = 0

        results.append({
            "ticker": t,
            "price": price,
            "change": change
        })

    return jsonify(results)

@app.route("/watchlist/add", methods=["POST"])
def add_watchlist():
    user = get_user_id()
    ticker = request.args.get("ticker", "").upper()
    if not ticker:
        return jsonify({"error": "Missing ticker"}), 400

    USER_WATCHLISTS.setdefault(user, [])
    if ticker not in USER_WATCHLISTS[user]:
        USER_WATCHLISTS[user].append(ticker)

    return jsonify({"ok": True, "watchlist": USER_WATCHLISTS[user]})

@app.route("/watchlist/remove", methods=["POST"])
def remove_watchlist():
    user = get_user_id()
    ticker = request.args.get("ticker", "").upper()
    if not ticker:
        return jsonify({"error": "Missing ticker"}), 400

    if user in USER_WATCHLISTS and ticker in USER_WATCHLISTS[user]:
        USER_WATCHLISTS[user].remove(ticker)

    return jsonify({"ok": True, "watchlist": USER_WATCHLISTS.get(user, [])})

@app.route("/chart")
def chart():
    symbol = request.args.get("ticker")
    tf = request.args.get("tf", "1D")

    if not symbol:
        return jsonify([])

    symbol = symbol.upper()
    today = datetime.utcnow()
    end = today.strftime("%Y-%m-%d")

    if tf == "1D":
        start = end
        data = polygon_ohlc(symbol, 1, "minute", start, end)
        if not data:
            y = (today - timedelta(days=1)).strftime("%Y-%m-%d")
            data = polygon_ohlc(symbol, 1, "minute", y, y)
    elif tf == "5D":
        start = (today - timedelta(days=5)).strftime("%Y-%m-%d")
        data = polygon_ohlc(symbol, 5, "minute", start, end)
    else:
        start = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        data = polygon_ohlc(symbol, 1, "day", start, end)

    candles = [{
        "time": int(c["t"] / 1000),
        "open": c["o"],
        "high": c["h"],
        "low": c["l"],
        "close": c["c"]
    } for c in data]

    return jsonify(candles)

def trader_reasoning(bias, support, resistance):
    if bias == "Bullish":
        return (
            f"Price is holding above key demand near {support}, keeping buyers in control. "
            f"Momentum favors continuation toward {resistance}, but strength must be confirmed by volume. "
            "A failure to hold trend support invalidates the setup."
        )
    if bias == "Bearish":
        return (
            f"Price remains capped beneath resistance near {resistance}, signaling overhead supply. "
            f"Rallies without volume are likely to fade back toward {support}. "
            "Only a clean reclaim of resistance shifts control."
        )
    return (
        "Price is compressing inside a tight range, reflecting balance between buyers and sellers. "
        "Without volume expansion, directional attempts are prone to failure. "
        "Wait for a decisive break before committing risk."
    )

# --- analyze() and movers() stay exactly as in your current file ---
# (Paste the rest of your existing analyze() and movers() code below this line without changing it)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)