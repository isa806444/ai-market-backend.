from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import requests
from statistics import mean
from datetime import datetime

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
    return jsonify({
        "status": "ok",
        "service": "ai-market-backend"
    })

def get_prev(symbol):
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev?apiKey={POLYGON_KEY}"
    r = requests.get(url, timeout=10)
    d = r.json()
    if "results" not in d or not d["results"]:
        return None
    return d["results"][0]

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

    candles = None

    # Try intraday first
    intraday_url = (
        f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/"
        f"{today}/{today}?adjusted=true&sort=asc&limit=5000&apiKey={POLYGON_KEY}"
    )

    try:
        r = requests.get(intraday_url, timeout=10)
        data = r.json()
        candles = data.get("results")
    except:
        candles = None

    # Fallback to previous daily candle (ALWAYS return real price)
    if not candles:
        d = get_prev(symbol)
        if not d:
            return jsonify({"error": "Market data unavailable"}), 503

        price = round(d["c"], 2)
        open_price = d["o"]
        change = round(((price - open_price) / open_price) * 100, 2)

        if mode == "day":
            if change > 1.5:
                signal = "Momentum Breakout"
            elif change > 0.5:
                signal = "Bullish Bias"
            elif change < -1:
                signal = "Fade Risk"
            else:
                signal = "Chop Zone"

            summary = (
                f"{symbol} last closed at ${price}. Change {change}%. "
                "Using most recent market data. "
                f"Day state: {signal}. "
                "Watch for continuation or expansion."
            )
        else:
            if change < -3:
                signal = "Oversold Reversal Watch"
            elif change < -1:
                signal = "Pullback Zone"
            elif change > 3:
                signal = "Extended – Caution"
            else:
                signal = "Base Building"

            summary = (
                f"{symbol} last closed at ${price}. Change {change}%. "
                "Using most recent market data. "
                f"Swing state: {signal}. "
                "Watch for basing and reversal."
            )

        return jsonify({
            "ticker": symbol,
            "price": price,
            "change": change,
            "signal": signal,
            "summary": summary
        })

    # Intraday path
    closes = [c["c"] for c in candles]
    opens = [c["o"] for c in candles]
    highs = [c["h"] for c in candles]
    lows = [c["l"] for c in candles]

    price = round(closes[-1], 2)
    open_price = opens[0]
    change = round(((price - open_price) / open_price) * 100, 2)

    short_ma = mean(closes[-20:]) if len(closes) >= 20 else mean(closes)
    long_ma = mean(closes)

    avg_range = mean([(h - l) for h, l in zip(highs, lows)])
    today_range = highs[-1] - lows[-1]

    if mode == "day":
        if price > short_ma and today_range > avg_range * 1.2:
            signal = "Momentum Breakout"
        elif price > short_ma:
            signal = "Bullish Bias"
        elif price < short_ma:
            signal = "Fade Risk"
        else:
            signal = "Chop Zone"

        summary = (
            f"{symbol} is trading at ${price}, change {change}%. "
            "Day mode favors speed and momentum. "
            f"State: {signal}. "
            "Watch volume and range expansion."
        )
    else:
        if change < -2:
            signal = "Oversold Reversal Watch"
        elif change < 0:
            signal = "Pullback Zone"
        elif change > 3:
            signal = "Extended – Caution"
        else:
            signal = "Base Building"

        summary = (
            f"{symbol} is trading at ${price}, change {change}%. "
            "Swing mode looks for reversals. "
            f"State: {signal}. "
            "Watch for basing and trend change."
        )

    return jsonify({
        "ticker": symbol,
        "price": price,
        "change": change,
        "signal": signal,
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
            results.append({
                "ticker": t,
                "price": price,
                "change": change
            })

    results = sorted(results, key=lambda x: abs(x["change"]), reverse=True)
    return jsonify(results[:8])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)