from flask import Flask, jsonify, request
import os
import requests

app = Flask(__name__)

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
    # Accept either ?ticker= or ?symbol=
    symbol = request.args.get("ticker") or request.args.get("symbol")

    if not symbol:
        return jsonify({"error": "Missing ticker"}), 400

    if not POLYGON_KEY:
        return jsonify({"error": "Polygon API key not configured"}), 500

    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol.upper()}/prev?apiKey={POLYGON_KEY}"
    r = requests.get(url)
    data = r.json()

    if "results" not in data or not data["results"]:
        return jsonify({"error": "No data found for ticker"}), 404

    result = data["results"][0]

    price = round(result["c"], 2)
    open_price = result["o"]

    change = round(((price - open_price) / open_price) * 100, 2)

    if change > 1:
        signal = "Bullish"
    elif change < -1:
        signal = "Weak"
    else:
        signal = "Neutral"

    return jsonify({
        "ticker": symbol.upper(),
        "price": price,
        "change": change,
        "signal": signal,
        "summary": f"{symbol.upper()} is trading at ${price}. It moved {change}% today. Short-term momentum is {signal.lower()}."
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)