from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return "AI Market Backend is running!"

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "ai-market-backend"
    })

@app.route("/ping")
def ping():
    return jsonify({"message": "pong"})

def analyze_ticker(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5d")

        if hist.empty or len(hist) < 2:
            return None

        latest = hist.iloc[-1]
        prev = hist.iloc[-2]

        price = round(float(latest["Close"]), 2)
        change = round(price - float(prev["Close"]), 2)
        pct = round((change / float(prev["Close"])) * 100, 2)

        if pct > 2:
            signal = "Bullish"
        elif pct < -2:
            signal = "Bearish"
        else:
            signal = "Weak"

        summary = (
            f"{ticker.upper()} is trading at ${price}. "
            f"It moved {pct}% today. "
            f"Short-term momentum is {signal.lower()}."
        )

        return {
            "ticker": ticker.upper(),
            "price": price,
            "change": pct,
            "signal": signal,
            "summary": summary
        }

    except Exception:
        return None

@app.route("/analyze")
def analyze():
    ticker = request.args.get("ticker", "").strip().upper()

    if not ticker:
        return jsonify({"error": "No ticker provided"}), 400

    result = analyze_ticker(ticker)

    if not result:
        return jsonify({
            "error": "Not enough data",
            "ticker": ticker
        }), 404

    return jsonify(result)

@app.route("/scan")
def scan():
    watchlist = ["BITF", "BTBT", "SGMT", "BNGO", "AMRX", "KSCP"]
    results = []

    for t in watchlist:
        r = analyze_ticker(t)
        if r:
            results.append(r)

    return jsonify({"results": results})

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)