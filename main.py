from flask import Flask, jsonify, request
from flask_cors import CORS
import os, requests
from statistics import mean
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

app = Flask(__name__)
CORS(app)

POLYGON_KEY = os.environ.get("POLYGON_API_KEY")

# Cache last successful analysis per ticker
LAST_SNAPSHOT = {}

@app.route("/")
def home():
    return "AI Market Backend is running!"

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "ai-market-backend"})

def market_now():
    return datetime.now(ZoneInfo("America/New_York"))

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

def trader_reasoning(bias, support, resistance):
    if bias == "Bullish":
        return (
            f"Price is holding above key demand near {support}, keeping buyers in control. "
            f"Momentum favors continuation toward {resistance}, but strength must be confirmed by volume. "
            "A failure to hold trend support invalidates the setup."
        )
    if bias == "Bearish":
        return (
            f"Price remains capped beneath resistance near {resistance}, signaling overhead supply. "
            f"Rallies without volume are likely to fade back toward {support}. "
            "Only a clean reclaim of resistance shifts control."
        )
    return (
        "Price is compressing inside a tight range, reflecting balance between buyers and sellers. "
        "Without volume expansion, directional attempts are prone to failure. "
        "Wait for a decisive break before committing risk."
    )

@app.route("/analyze")
def analyze():
    symbol = request.args.get("ticker") or request.args.get("symbol")
    if not symbol:
        return jsonify({"error": "Missing ticker"}), 400
    if not POLYGON_KEY:
        return jsonify({"error": "Polygon API key not configured"}), 500

    symbol = symbol.upper()

    last_trade = get_last_trade(symbol)
    d = get_prev(symbol)

    if not last_trade and not d:
        if symbol in LAST_SNAPSHOT:
            cached = LAST_SNAPSHOT[symbol].copy()
            cached["summary"] += (
                " Live market data is temporarily unavailable. "
                "This analysis is based on the most recent confirmed structure "
                f"for {symbol}. Await fresh price flow."
            )
            return jsonify(cached)

        payload = {
            "ticker": symbol,
            "price": "—",
            "change": 0,
            "bias": "Neutral",
            "trend": "Unknown",
            "levels": {"support": "N/A", "resistance": "N/A"},
            "plan": {
                "entry": "Wait for confirmation",
                "stop": "Define after data",
                "targets": []
            },
            "risk_notes": [
                "Live feed unavailable",
                "Structure is synthetic",
                "Do not trade without price confirmation"
            ],
            "summary": (
                f"{symbol} data is currently unavailable. "
                "This is a structural placeholder only."
            ),
            "reasoning": (
                "Without confirmed price flow, the market is treated as neutral. "
                "Professional traders remain flat in these conditions."
            )
        }

        LAST_SNAPSHOT[symbol] = payload
        return jsonify(payload)

    if last_trade and d:
        price = last_trade
        open_price = d["o"]
    elif d:
        price = round(d["c"], 2)
        open_price = d["o"]
    else:
        price = last_trade
        open_price = price

    change = round(((price - open_price) / open_price) * 100, 2) if open_price else 0

    bias = "Bullish" if change > 0 else "Bearish" if change < 0 else "Neutral"
    trend = "Active Market" if last_trade else "After-hours"

    support = round(price * 0.99, 2)
    resistance = round(price * 1.01, 2)

    payload = {
        "ticker": symbol,
        "price": price,
        "change": change,
        "bias": bias,
        "trend": trend,
        "levels": {"support": str(support), "resistance": str(resistance)},
        "plan": {
            "entry": f"{round(price * 1.003, 2)} – reclaim momentum",
            "stop": f"{support} – below structure",
            "targets": [
                f"{resistance} (first objective)",
                f"{round(resistance * 1.02, 2)} (extension)"
            ]
        },
        "risk_notes": [
            "Confirm with volume",
            "Avoid chasing extensions",
            "Reduce size in chop"
        ],
        "summary": (
            f"{symbol} is trading at ${price} ({change}%). "
            f"Market bias is {bias.lower()}."
        ),
        "reasoning": trader_reasoning(bias, support, resistance)
    }

    LAST_SNAPSHOT[symbol] = payload
    return jsonify(payload)

@app.route("/movers")
def movers():
    if not POLYGON_KEY:
        return jsonify([])

    try:
        check_day = market_now()

        for _ in range(7):
            if check_day.weekday() >= 5:
                check_day -= timedelta(days=1)
                continue

            day = check_day.strftime("%Y-%m-%d")
            url = (
                f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{day}"
                f"?adjusted=true&apiKey={POLYGON_KEY}"
            )
            r = requests.get(url, timeout=15)
            data = r.json().get("results", [])

            if data:
                movers = []
                for d in data:
                    o = d.get("o", 0)
                    c = d.get("c", 0)
                    if o and c:
                        change = round(((c - o) / o) * 100, 2)
                        movers.append({
                            "ticker": d["T"],
                            "price": round(c, 2),
                            "change": change
                        })

                movers = sorted(movers, key=lambda x: abs(x["change"]), reverse=True)
                return jsonify(movers[:5])

            check_day -= timedelta(days=1)

        return jsonify([])

    except Exception as e:
        print("Movers error:", e)
        return jsonify([])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)