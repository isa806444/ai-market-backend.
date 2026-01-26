from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import requests
from statistics import mean

app = Flask(__name__)
CORS(app)  # <-- enables cross-origin requests from your static app

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

    # Pull last ~20 daily candles
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/2024-01-01/2026-12-31?limit=20&apiKey={POLYGON_KEY}"
    r = requests.get(url, timeout=10)
    data = r.json()

    if "results" not in data or not data["results"]:
        return jsonify({"error": "No data found for ticker"}), 404

    candles = data["results"]

    closes = [c["c"] for c in candles]
    opens = [c["o"] for c in candles]
    highs = [c["h"] for c in candles]
    lows = [c["l"] for c in candles]

    price = round(closes[-1], 2)
    open_price = opens[-1]
    change = round(((price - open_price) / open_price) * 100, 2)

    short_ma = mean(closes[-5:])
    long_ma = mean(closes)

    avg_range = mean([(h - l) for h, l in zip(highs, lows)])
    today_range = highs[-1] - lows[-1]

    position_in_range = (price - min(lows)) / (max(highs) - min(lows))

    # Signal logic
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

    if position_in_range > 0.8:
        range_note = "near recent highs"
    elif position_in_range < 0.2:
        range_note = "near recent lows"
    else:
        range_note = "mid-range"

    summary = (
        f"{symbol} is trading at ${price}. It moved {change}% today. "
        f"Price is {range_note}. Short-term trend is "
        f"{'up' if short_ma > long_ma else 'down' if short_ma < long_ma else 'flat'}. "
        f"Volatility is {'expanding' if today_range > avg_range else 'normal'}. "
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