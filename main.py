from flask import Flask, jsonify, request
from flask_cors import CORS
import os, requests
from statistics import mean
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

POLYGON_KEY = os.environ.get("POLYGON_API_KEY")

# Simple universe for movers (stocks + crypto-style tickers)
STOCK_MOVERS = ["NVDA", "TSLA", "AMD", "SMCI", "PLTR", "COIN", "MARA", "RIOT", "BITF", "BTBT"]

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
    elif tf == "5D":
        start = (today - timedelta(days=5)).strftime("%Y-%m-%d")
        data = polygon_ohlc(symbol, 5, "minute", start, end)
    else:  # 1M
        start = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        data = polygon_ohlc(symbol, 1, "day", start, end)

    candles = []
    for c in data:
        candles.append({
            "time": int(c["t"] / 1000),
            "open": c["o"],
            "high": c["h"],
            "low": c["l"],
            "close": c["c"]
        })

    return jsonify(candles)

@app.route("/analyze")
def analyze():
    symbol = request.args.get("ticker") or request.args.get("symbol")
    mode = request.args.get("mode", "day")

    if not symbol:
        return jsonify({"error": "Missing ticker"}), 400
    if not POLYGON_KEY:
        return jsonify({"error": "Polygon API key not configured"}), 500

    symbol = symbol.upper()
    today = datetime.utcnow().strftime("%Y-%m-%d")

    candles = polygon_ohlc(symbol, 1, "minute", today, today)
    last_trade = get_last_trade(symbol)

    # After-hours / closed market path
    if not candles:
        d = get_prev(symbol)
        if not d and not last_trade:
            return jsonify({"error": "Market data unavailable"}), 503

        price = last_trade or round(d["c"], 2)
        open_price = d["o"] if d else price
        change = round(((price - open_price) / open_price) * 100, 2)

        if mode == "day":
            signal = "Bullish Bias" if change > 0.5 else "Fade Risk" if change < -1 else "Chop Zone"
            entry = "Next session open or range break"
            stop = "Below session low"
            target = "High of day"
        else:
            signal = "Pullback Zone" if change < 0 else "Base Building"
            entry = "Near support"
            stop = "Below base"
            target = "Trend continuation"

        summary = (
            f"{symbol} last traded at ${price} ({change}%). "
            "Using most recent available data (after-hours supported). "
            f"Bias: {signal}. Entry: {entry}. Stop: {stop}. Target: {target}."
        )

        return jsonify({
            "ticker": symbol,
            "price": price,
            "change": change,
            "signal": signal,
            "entry": entry,
            "stop": stop,
            "target": target,
            "summary": summary
        })

    # Intraday path
    closes = [c["c"] for c in candles]
    highs = [c["h"] for c in candles]
    lows = [c["l"] for c in candles]

    price = round(closes[-1], 2)
    open_price = candles[0]["o"]
    change = round(((price - open_price) / open_price) * 100, 2)

    ema9 = mean(closes[-9:])
    ema21 = mean(closes[-21:]) if len(closes) >= 21 else mean(closes)
    ema50 = mean(closes[-50:]) if len(closes) >= 50 else mean(closes)

    if mode == "day":
        if price > ema9 > ema21:
            signal = "Bullish Momentum"
            entry = f"Pullback near EMA9 ({round(ema9,2)})"
            stop = f"Below EMA21 ({round(ema21,2)})"
            target = f"High of day near {round(max(highs),2)}"
        elif price < ema9:
            signal = "Weak / Fade"
            entry = f"Rejection near EMA9 ({round(ema9,2)})"
            stop = f"Above EMA21 ({round(ema21,2)})"
            target = f"Lows near {round(min(lows),2)}"
        else:
            signal = "Chop"
            entry = "Wait for range break"
            stop = "Tight"
            target = "Scalp only"
    else:
        if price > ema21 > ema50:
            signal = "Uptrend Pullback"
            entry = f"Near EMA21 ({round(ema21,2)})"
            stop = f"Below EMA50 ({round(ema50,2)})"
            target = "Prior swing high"
        elif price < ema50:
            signal = "Downtrend / Avoid"
            entry = "Wait for base"
            stop = "N/A"
            target = "N/A"
        else:
            signal = "Base Forming"
            entry = "Break above range"
            stop = "Below base"
            target = "Trend continuation"

    summary = (
        f"{symbol} is trading at ${price} ({change}%). "
        f"Bias: {signal}. Entry: {entry}. Stop: {stop}. Target: {target}."
    )

    return jsonify({
        "ticker": symbol,
        "price": price,
        "change": change,
        "signal": signal,
        "entry": entry,
        "stop": stop,
        "target": target,
        "summary": summary
    })

@app.route("/movers")
def movers():
    results = []
    for t in STOCK_MOVERS:
        d = get_prev(t)
        if d:
            price = round(d["c"], 2)
            change = round(((d["c"] - d["o"]) / d["o"]) * 100, 2)
            results.append({"ticker": t, "price": price, "change": change})

    results = sorted(results, key=lambda x: abs(x["change"]), reverse=True)
    return jsonify(results[:8])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)