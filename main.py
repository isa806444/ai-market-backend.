from flask import Flask, jsonify

app = Flask(__name__)

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
    return {
        "results": [
            {"ticker": "BITF", "price": 2.31, "signal": "Bullish"},
            {"ticker": "BTBT", "price": 3.04, "signal": "Momentum"},
            {"ticker": "SGMT", "price": 1.12, "signal": "Breakout"}
        ]
    }

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)