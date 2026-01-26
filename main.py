import os
import requests
from flask import Flask, jsonify, request
from datetime import datetime, timedelta

app = Flask(__name__)

POLYGON_KEY = os.environ.get("POLYGON_API_KEY")

def get_stock_data(ticker):
    ticker = ticker.upper()

    # Get last trade price
    price_url = f"https://api.polygon.io/v2/last/trade/{ticker}?apiKey={POLYGON_KEY}"
    price_res = requests.get(price_url, timeout=10).json()

    if "results" not in price_res:
        return None

    price = round(price_res["results"]["p"], 2)

    # Get previous close
    prev_url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={POLYGON_KEY}"
    prev_res = requests.get(prev_url, timeout=10).json()

    if "results" not in prev_res:
        return None

    prev_close = prev_res["results"][0]["c"]

    change_pct = round(((price - prev_close) / prev_close) * 100, 2)

    if change_pct >= 2:
        signal = "Bullish"
    elif change_pct <= -2:
        signal = "Bearish"
    else:
        signal = "Weak"

    analysis = (
        f"{ticker} is trading at ${price}. "
        f"It moved {change_pct}% today. "
        f"Short-term momentum is {signal.lower()}."
    )

    return {
        "ticker": ticker,
        "price": price,
        "change": change_pct,
        "signal": signal,
        "analysis": analysis
    }

@app.route("/")
def home():
    return "AI Market Backend is running!"

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "ai-market-backend"})

@app.route("/analyze")
def analyze():
    ticker = request.args.get("ticker")
    if not ticker:
        return jsonify({"error": "Missing ticker"}), 400

    data = get_stock_data(ticker)
    if not data:
        return jsonify({"error": "Ticker not found or no data"}), 404

    return jsonify(data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)