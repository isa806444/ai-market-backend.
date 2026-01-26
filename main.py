from flask import Flask, jsonify
from flask_cors import CORS
import yfinance as yf
import os

app = Flask(__name__)
CORS(app)  # <-- This is the key line

WATCHLIST = ["BITF", "BTBT", "SGMT", "BNGO", "AMRX", "KSCP"]

def classify_signal(change_pct):
    if change_pct >= 6:
        return "Breakout"
    elif change_pct >= 3:
        return "Momentum"
    elif change_pct > 0:
        return "Bullish"
    else:
        return "Weak"

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

@app.route("/scan")
def scan():
    results = []

    for ticker in WATCHLIST:
        try:
            stock = yf.Ticker(ticker)
            data = stock.history(period="2d")

            if len(data) < 2:
                continue

            prev_close = float(data["Close"].iloc[-2])
            current = float(data["Close"].iloc[-1])

            change_pct = ((current - prev_close) / prev_close) * 100
            signal = classify_signal(change_pct)

            results.append({
                "ticker": ticker,
                "price": round(current, 2),
                "change": round(change_pct, 2),
                "signal": signal
            })

        except Exception:
            continue

    return jsonify({"results": results})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)