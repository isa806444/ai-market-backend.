from flask import Flask, jsonify
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)  # Allow your mobile app to call this API

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
    return jsonify({
        "message": "pong"
    })

@app.route("/scan")
def scan():
    return jsonify({
        "results": [
            {"ticker": "BITF", "price": 2.31, "signal": "Bullish"},
            {"ticker": "BTBT", "price": 3.04, "signal": "Momentum"},
            {"ticker": "SGMT", "price": 1.12, "signal": "Breakout"}
        ]
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)