from flask import Flask, jsonify, request
from flask_cors import CORS
import os, requests
from statistics import mean
from datetime import datetime, timedelta

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
    return jsonify({"status": "ok", "service": "ai-market-backend"})

def polygon_ohlc(symbol, multiplier, timespan, start, end):
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/"
        f"{multiplier}/{timespan}/{start}/{end}"
        f"?adjusted=true&sort=asc&limit=5000&apiKey={POLYGON_KEY}"
    )
    r = requests.get(url, timeout=10)
    return r.json().get("results", [])

def get_prev(symbol):
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev?apiKey={POLYGON_KEY}"
    r = requests.get(url, timeout=10)
    d = r.json()
    if "results" not in d or not d["results"]:
        return None
    return d["results"][0]

def get_last_trade(symbol):
    try:
        r = requests.get(
            f"https://api.polygon.io/v2/last/trade/{symbol}?apiKey={POLYGON_KEY}",
            timeout=5
        )
        d = r.json()
        if "results" in d and "p" in d["results"]:
            return round(d["results"]["p"], 2)
    except:
        pass
    return None

@app.route("/chart")
def chart():
    symbol = request.args.get("ticker")
    tf = request.args.get("tf", "1D")

    if not symbol:
        return jsonify([])

    symbol = symbol.upper()
    today = datetime.utcnow()
    end = today.strftime("%Y-%m-%d")

    data = []

    if tf == "1D":
        start = end
        data = polygon_ohlc(symbol, 1, "minute", start, end)
        if not data:
            y = (today - timedelta(days=1)).strftime("%Y-%m-%d")
            data = polygon_ohlc(symbol, 1, "minute", y, y)

    elif tf == "5D":
        start = (today - timedelta(days=5)).strftime("%Y-%m-%d")
        data = polygon_ohlc(symbol, 5, "minute", start, end)

    else:  # 1M
        start = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        data = polygon_ohlc(symbol, 1, "day", start, end)

    candles = []
    for c in data:
        candles.append({
            "time": int(c["t"] / 1000),
            "open": c["o"],
            "high": c["h"],
            "low": c["l"],
            "close": c["c"]
        })

    return jsonify(candles)

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

    candles = polygon_ohlc(symbol, 1, "minute", today, today)
    last_trade = get_last_trade(symbol)

    # AFTER-HOURS / CLOSED MARKET
    if not candles:
        d = get_prev(symbol)

        # OPTION B: Graceful fallback – never 503
        if not d and not last_trade:
            return jsonify({
                "ticker": symbol,
                "price": "—",
                "bias": "Unavailable",
                "trend": "No live feed",
                "levels": {
                    "support": "—",
                    "resistance": "—"
                },
                "plan": {
                    "entry": "Wait for data",
                    "stop": "N/A",
                    "targets": []
                },
                "risk_notes": [
                    "No market data returned from provider.",
                    "This can occur after-hours or during API outages.",
                    "Try again in a moment."
                ],
                "summary": f"{symbol} data is temporarily unavailable. This is usually caused by after-hours gaps or API limits."
            })

        price = last_trade or round(d["c"], 2)
        open_price = d["o"] if d else price
        change = round(((price - open_price) / open_price) * 100, 2)

        bias = "Bullish" if change > 0 else "Bearish" if change < 0 else "Neutral"
        trend = "Sideways (after-hours)"

        support = round(price * 0.99, 2)
        resistance = round(price * 1.01, 2)

        plan_entry = f"{round(price * 1.003, 2)} – break above current range"
        plan_stop = f"{support} – below session support"
        targets = [
            f"{round(resistance, 2)} (near resistance)",
            f"{round(resistance * 1.02, 2)} (extension)"
        ]

        risk_notes = [
            "After-hours liquidity is thin",
            "Expect wider spreads at open",
            "Wait for volume confirmation"
        ]

        summary = (
            f"{symbol} last traded at ${price} ({change}%). "
            "Market is currently closed; using most recent data. "
            f"Bias is {bias} with a {trend.lower()} structure."
        )

        return jsonify({
            "ticker": symbol,
            "price": price,
            "change": change,
            "bias": bias,
            "trend": trend,
            "levels": {
                "support": str(support),
                "resistance": str(resistance)
            },
            "plan": {
                "entry": plan_entry,
                "stop": plan_stop,
                "targets": targets
            },
            "risk_notes": risk_notes,
            "summary": summary
        })

    # INTRADAY PATH
    closes = [c["c"] for c in candles]
    highs = [c["h"] for c in candles]
    lows = [c["l"] for c in candles]

    price = round(closes[-1], 2)
    open_price = candles[0]["o"]
    change = round(((price - open_price) / open_price) * 100, 2)

    ema9 = mean(closes[-9:])
    ema21 = mean(closes[-21:]) if len(closes) >= 21 else mean(closes)

    bias = "Bullish" if price > ema21 else "Bearish" if price < ema21 else "Neutral"
    trend = "Upward (short-term)" if ema9 > ema21 else "Downward (short-term)"

    support = round(ema21, 2)
    resistance = round(max(highs), 2)

    plan_entry = f"{round(price * 1.003, 2)} – break above current range"
    plan_stop = f"{round(ema21 * 0.995, 2)} – below trend support"
    targets = [
        f"{round(resistance, 2)} (range high)",
        f"{round(resistance * 1.02, 2)} (extension)"
    ]

    risk_notes = [
        "Watch volume for confirmation",
        "Be cautious near resistance",
        "Move stop to breakeven on strength"
    ]

    summary = (
        f"{symbol} is trading at ${price} ({change}%). "
        f"Structure remains {bias.lower()} with {trend.lower()} momentum. "
        f"Holding above {support} favors continuation."
    )

    return jsonify({
        "ticker": symbol,
        "price": price,
        "change": change,
        "bias": bias,
        "trend": trend,
        "levels": {
            "support": str(support),
            "resistance": str(resistance)
        },
        "plan": {
            "entry": plan_entry,
            "stop": plan_stop,
            "targets": targets
        },
        "risk_notes": risk_notes,
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
            results.append({"ticker": t, "price": price, "change": change})

    results = sorted(results, key=lambda x: abs(x["change"]), reverse=True)
    return jsonify(results[:8])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)