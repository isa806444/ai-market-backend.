from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import os

app = Flask(__name__)
CORS(app)

def classify_signal(change_pct):
    if change_pct >= 6:
        return "Breakout"
    elif change_pct >= 3:
        return "Momentum"
    elif change_pct > 0:
        return "Bullish"
    else:
        return "Weak"

def ai_summary(ticker, price, change, signal):
    if signal == "Breakout":
        return f"{ticker} is breaking out with strong upside momentum. This usually attracts traders and volume."
    if signal == "Momentum":
        return f"{ticker} is gaining momentum. Buyers are in control and continuation is possible."
    if signal == "Bullish":
        return f"{ticker} is green and trending positively, but without explosive movement yet."
    return f"{ticker} is weak right now. Selling pressure is outweighing buying interest."

@app.route("/")
def home():
    return "AI Market Backend is running!"

@app.route("/analyze")
def analyze():
    ticker = request.args.get("ticker", "").upper().strip()

    if not ticker:
        return jsonify({"error": "Ticker required"}), 400

    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period="2d")

        if len(data) < 2:
            return jsonify({"error": "Not enough data"}), 400

        prev_close = float(data["Close"].iloc[-2])
        current = float(data["Close"].iloc[-1])
        change_pct = ((current - prev_close) / prev_close) * 100

        signal = classify_signal(change_pct)
        summary = ai_summary(ticker, current, change_pct, signal)

        return jsonify({
            "ticker": ticker,
            "price": round(current, 2),
            "change": round(change_pct, 2),
            "signal": signal,
            "summary": summary
        })

    except Exception as e:
        return jsonify({"error": "Invalid ticker"}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)