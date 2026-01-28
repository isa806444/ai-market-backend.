from flask import Flask, jsonify, request
from flask_cors import CORS
import os, requests, threading, time
from statistics import mean
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

app = Flask(__name__)
CORS(app)

POLYGON_KEY = os.environ.get("POLYGON_API_KEY")

LAST_SNAPSHOT = {}

# 🔴 Scanner state
SCANNER_RESULTS = []
LIQUID_UNIVERSE = []
LAST_SCAN = None

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

# =========================
# 🔴 BACKGROUND SCANNER
# =========================

def build_liquid_universe():
    global LIQUID_UNIVERSE

    now = market_now()
    check_day = now

    for _ in range(7):
        if check_day.weekday() >= 5:
            check_day -= timedelta(days=1)
            continue

        day = check_day.strftime("%Y-%m-%d")
        url = (
            f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{day}"
            f"?adjusted=true&apiKey={POLYGON_KEY}"
        )

        r = requests.get(url, timeout=20)
        data = r.json().get("results", [])

        if data:
            ranked = []
            for d in data:
                o = d.get("o", 0)
                c = d.get("c", 0)
                v = d.get("v", 0)
                if o and c and v:
                    dollar_vol = c * v
                    ranked.append((d["T"], dollar_vol))

            ranked.sort(key=lambda x: x[1], reverse=True)
            LIQUID_UNIVERSE = [t[0] for t in ranked[:500]]
            return

        check_day -= timedelta(days=1)

def scanner_loop():
    global SCANNER_RESULTS, LAST_SCAN

    while True:
        try:
            if not LIQUID_UNIVERSE:
                build_liquid_universe()

            movers = []

            for sym in LIQUID_UNIVERSE:
                last = get_last_trade(sym)
                prev = get_prev(sym)
                if not last or not prev:
                    continue

                o = prev["o"]
                change = round(((last - o) / o) * 100, 2)

                movers.append({
                    "ticker": sym,
                    "price": last,
                    "change": change
                })

            movers.sort(key=lambda x: abs(x["change"]), reverse=True)
            SCANNER_RESULTS = movers[:25]
            LAST_SCAN = market_now().isoformat()

        except Exception as e:
            print("Scanner error:", e)

        time.sleep(60)

@app.route("/scanner")
def scanner():
    return jsonify({
        "last_scan": LAST_SCAN,
        "universe_size": len(LIQUID_UNIVERSE),
        "results": SCANNER_RESULTS
    })

# =========================
# EXISTING ROUTES (UNCHANGED)
# =========================

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

# 🔴 Start scanner thread on boot
threading.Thread(target=scanner_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)