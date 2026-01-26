from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import requests
from statistics import mean
from datetime import datetime

app = Flask(__name__)
CORS(app)

POLYGON_KEY = os.environ.get("POLYGON_API_KEY")

@app.route("/")
def home():
    return "AI Market Backend is running!"

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "ai-market-backend"
    })

@app.route("/analyze")
def analyze():
    symbol = request.args.get("ticker") or request.args.get("symbol")

    if not symbol:
        return jsonify({"error": "Missing ticker"}), 400

    if not POLYGON_KEY:
        return jsonify({"error": "Polygon API key not configured"}), 500

    symbol = symbol.upper()
    today = datetime.utcnow().strftime("%Y-%m-%d")

    # Try intraday first (market hours)
    intraday_url = (
        f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/"
        f"{today}/{today}?adjusted=true&sort=asc&limit=5000&apiKey={POLYGON_KEY}"
    )

    r = requests.get(intraday_url, timeout=10)
    data = r.json()

    candles = data.get("results")

    # Fallback to previous daily candle if intraday is empty
    if not candles:
        daily_url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev?apiKey={POLYGON_KEY}"
        r = requests.get(daily_url, timeout=10)
        data = r.json()

        if "results" not in data or not data["results"]:
            return jsonify({"error": "No market data found for ticker"}), 404

        d = data["results"][0]
        price = round(d["c"], 2)
        open_price = d["o"]
        change = round(((price - open_price) / open_price) * 100, 2)

        signal = "Bullish" if change > 1 else "Weak" if change < -1 else "Neutral"

        summary = (
            f"{symbol} is trading at ${price}. It moved {change}% today. "
            f"Short-term momentum is {signal.lower()}."
        )

        return jsonify({
            "ticker": symbol,
            "price": price,
            "change": change,
            "signal": signal,
            "summary": summary
        })

    # Intraday path (market open)
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

    if price > short_ma > long_ma and change > 0.5:
        signal = "Bullish"
        confidence = "High"
    elif price < short_ma < long_ma and change < -0.5:
        signal = "Bearish"
        confidence = "High"
    elif today_range > avg_range * 1.5:
        signal = "Breakout"
        confidence = "Medium"
    else:
        signal = "Neutral"
        confidence = "Low"

    summary = (
        f"{symbol} is trading at ${price}. It moved {change}% today. "
        f"Short-term trend is "
        f"{'up' if short_ma > long_ma else 'down' if short_ma < long_ma else 'flat'}. "
        f"Bias: {signal} ({confidence} confidence)."
    )

    return jsonify({
        "ticker": symbol,
        "price": price,
        "change": change,
        "signal": signal,
        "summary": summary
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)