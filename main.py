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

# 🔵 INSERTED: Strategy profiles to make each mode truly distinct
STRATEGY_PROFILES = {
    "scalp": {
        "banner": "SCALP — High-speed micro moves. Tight stops. Rapid exits.",
        "style": "scalp",
        "risk": [
            "Slippage risk is elevated",
            "Execution speed matters",
            "Do not hold through pullbacks"
        ],
        "summary_suffix": " This is a precision execution environment."
    },
    "day": {
        "banner": "DAY — Intraday structure. Trend + momentum balance.",
        "style": "day",
        "risk": [
            "Midday chop can invalidate setups",
            "Avoid overtrading",
            "Respect VWAP reactions"
        ],
        "summary_suffix": " Designed for session-based positioning."
    },
    "swing": {
        "banner": "SWING — Multi-day positioning. Wider stops. Larger targets.",
        "style": "swing",
        "risk": [
            "Overnight gap risk",
            "Macro news sensitivity",
            "Requires patience"
        ],
        "summary_suffix": " This thesis spans multiple sessions."
    },
    "momentum": {
        "banner": "MOMENTUM — Breakouts and continuation. Ride strength.",
        "style": "momentum",
        "risk": [
            "Failed breakouts reverse fast",
            "Late entries get trapped",
            "Volume confirmation is mandatory"
        ],
        "summary_suffix": " Designed for acceleration phases."
    },
    "mean": {
        "banner": "MEAN — Fade extremes. Reversion to equilibrium.",
        "style": "mean",
        "risk": [
            "Trends can overpower mean reversion",
            "Early entries compound loss",
            "Scale in only at extremes"
        ],
        "summary_suffix": " This is a counter-trend framework."
    }
}

@app.route("/")
def home():
    return "AI Market Backend is running!"

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "ai-market-backend"})

def market_now():
    return datetime.now(ZoneInfo("America/New_York"))

# 🔵 INSERTED: Hardened Polygon previous-close fetch
def get_prev(symbol):
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev?apiKey={POLYGON_KEY}"
    r = requests.get(url, timeout=10)
    try:
        d = r.json()
    except Exception as e:
        print("PREV JSON ERROR:", e, r.text)
        return None

    if "results" not in d or not d["results"]:
        print("PREV EMPTY:", d)
        return None

    return d["results"][0]

    except Exception as e:
        print("get_prev error:", e)
        return None

def get_last_trade(symbol):
    try:
        url = f"https://api.polygon.io/v2/last/trade/{symbol}?apiKey={POLYGON_KEY}"
        r = requests.get(url, timeout=5)

        if r.status_code != 200:
            print("LAST HTTP ERROR:", symbol, r.status_code, r.text)
            return None

        try:
            d = r.json()
        except Exception as e:
            print("LAST JSON ERROR:", symbol, e, r.text)
            return None

        if "results" not in d or not d["results"]:
            print("LAST EMPTY:", symbol, d)
            return None

        if "p" not in d["results"]:
            print("LAST MISSING PRICE:", symbol, d["results"])
            return None

        return round(d["results"]["p"], 2)

    except Exception as e:
        print("get_last_trade error:", symbol, e)
        return None

def trader_reasoning(bias, support, resistance, tone):
    if bias == "Bullish":
        return (
            f"{tone} Price is holding above {support}, keeping buyers in control. "
            f"Continuation favors {resistance} if volume confirms. "
            "Loss of structure invalidates the setup."
        )
    if bias == "Bearish":
        return (
            f"{tone} Price is capped beneath {resistance}, signaling supply. "
            f"Rallies without volume likely fade toward {support}. "
            "Only reclaiming resistance shifts control."
        )
    return (
        f"{tone} Price is compressing in balance. "
        "Without expansion, directional attempts fail. "
        "Wait for a decisive break."
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

        try:
            r = requests.get(url, timeout=20)
            if r.status_code != 200:
                check_day -= timedelta(days=1)
                continue

            data = r.json().get("results", [])
        except:
            check_day -= timedelta(days=1)
            continue

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

                o = prev.get("o")
                if not o:
                    continue

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
# ANALYZE WITH STRATEGIES
# =========================

@app.route("/analyze")
def analyze():
    try:
        symbol = request.args.get("ticker") or request.args.get("symbol")
        strategy = request.args.get("strategy", "day").lower()

        if not symbol:
            return jsonify({"error": "Missing ticker"}), 400
        if not POLYGON_KEY:
            return jsonify({"error": "Polygon API key not configured"}), 500

        symbol = symbol.upper()

        last_trade = get_last_trade(symbol)
        d = get_prev(symbol)
        scanner_price = get_scanner_price(symbol)

        print("LAST:", last_trade, "PREV:", d, "SCANNER:", scanner_price)

        if not last_trade and not d and scanner_price:
            last_trade = scanner_price

        if not last_trade and not d:
            if symbol in LAST_SNAPSHOT:
                cached = LAST_SNAPSHOT[symbol].copy()
                cached["summary"] += " (Live feed temporarily unavailable)"
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
                "summary": f"{symbol} data is currently unavailable.",
                "reasoning": "No confirmed price flow."
            }
            LAST_SNAPSHOT[symbol] = payload
            return jsonify(payload)

        if last_trade and d:
            price = last_trade
            open_price = d.get("o")
        elif d:
            price = round(d.get("c", 0), 2)
            open_price = d.get("o")
        else:
            price = last_trade
            open_price = price

        change = round(((price - open_price) / open_price) * 100, 2) if open_price else 0
        bias = "Bullish" if change > 0 else "Bearish" if change < 0 else "Neutral"
        trend = "Active Market" if last_trade else "After-hours"

        support = round(price * 0.99, 2)
        resistance = round(price * 1.01, 2)

        if strategy == "scalp":
            entry = f"{round(price * 1.001, 2)} – micro breakout"
            stop = f"{round(price * 0.998, 2)} – tight risk"
            targets = [f"{round(price * 1.004, 2)}", f"{round(price * 1.007, 2)}"]
            tone = "Fast execution environment."
        elif strategy == "swing":
            entry = f"{round(price * 1.01, 2)} – reclaim structure"
            stop = f"{round(price * 0.96, 2)} – below weekly support"
            targets = [f"{round(price * 1.08, 2)}", f"{round(price * 1.15, 2)}"]
            tone = "Multi-session thesis."
        elif strategy == "momentum":
            entry = f"{round(price * 1.005, 2)} – momentum continuation"
            stop = f"{round(price * 0.992, 2)} – trend failure"
            targets = [f"{round(price * 1.03, 2)}", f"{round(price * 1.06, 2)}"]
            tone = "Trend acceleration regime."
        elif strategy == "mean":
            entry = f"{round(price * 0.995, 2)} – fade extension"
            stop = f"{round(price * 1.01, 2)} – invalidation"
            targets = [f"{round(price * 0.985, 2)}", f"{round(price * 0.97, 2)}"]
            tone = "Reversion environment."
        else:
            entry = f"{round(price * 1.003, 2)} – reclaim momentum"
            stop = f"{support} – below structure"
            targets = [
                f"{resistance} (first objective)",
                f"{round(resistance * 1.02, 2)} (extension)"
            ]
            tone = "Intraday structure-focused."

        payload = {
            "ticker": symbol,
            "price": price,
            "change": change,
            "bias": bias,
            "trend": trend,
            "strategy": strategy,
            "levels": {"support": str(support), "resistance": str(resistance)},
            "plan": {
                "entry": entry,
                "stop": stop,
                "targets": targets
            },
            "risk_notes": [
                "Confirm with volume",
                "Avoid chasing",
                "Respect invalidation"
            ],
            "summary": (
                f"{symbol} is trading at ${price} ({change}%). "
                f"{strategy.title()} bias is {bias.lower()}."
            ),
            "reasoning": trader_reasoning(bias, support, resistance, tone)
        }

        profile = STRATEGY_PROFILES.get(strategy)
        if profile:
            payload["mode_banner"] = profile["banner"]
            payload["ui_style"] = profile["style"]
            payload["risk_notes"] = payload["risk_notes"] + profile["risk"]
            payload["summary"] = payload["summary"] + profile["summary_suffix"]

        LAST_SNAPSHOT[symbol] = payload
        return jsonify(payload)

    except Exception as e:
        print("ANALYZE ERROR:", e)

        symbol = request.args.get("ticker", "UNKNOWN").upper()
        fallback = LAST_SNAPSHOT.get(symbol)

        if fallback:
            cached = fallback.copy()
            cached["summary"] += " (Recovered from backend error)"
            return jsonify(cached)

        return jsonify({
            "ticker": symbol,
            "price": "—",
            "change": 0,
            "bias": "Neutral",
            "trend": "Unknown",
            "levels": {"support": "N/A", "resistance": "N/A"},
            "plan": {
                "entry": "Unavailable",
                "stop": "Unavailable",
                "targets": []
            },
            "risk_notes": ["Backend exception recovered"],
            "summary": f"{symbol} analysis failed gracefully.",
            "reasoning": "Temporary backend fault."
        })

# 🔴 Start scanner thread on boot
threading.Thread(target=scanner_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)