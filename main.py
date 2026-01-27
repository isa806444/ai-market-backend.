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

    # 🔴 NEW: lightweight live tick endpoint
@app.route("/last-trade")
def last_trade_route():
    sym = request.args.get("ticker", "").upper()
    if not sym:
        return jsonify({"error": "Missing ticker"}), 400

    p = get_last_trade(sym)
    return jsonify({
        "ticker": sym,
        "price": p
    })

@app.route("/chart")
def chart():
    symbol = request.args.get("ticker")
    tf = request.args.get("tf", "1D")

    if not symbol:
        return jsonify([])

    symbol = symbol.upper()
    now = market_now()
    end = now.strftime("%Y-%m-%d")

    if tf == "1D":
        start = end
        data = polygon_ohlc(symbol, 1, "minute", start, end)
        if not data:
            y = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            data = polygon_ohlc(symbol, 1, "minute", y, y)
    elif tf == "5D":
        start = (now - timedelta(days=5)).strftime("%Y-%m-%d")
        data = polygon_ohlc(symbol, 5, "minute", start, end)
    else:
        start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        data = polygon_ohlc(symbol, 1, "day", start, end)

    candles = [{
        "time": int(c["t"] / 1000),
        "open": c["o"],
        "high": c["h"],
        "low": c["l"],
        "close": c["c"]
    } for c in data]

    return jsonify(candles)

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
    now = market_now()
    today = now.strftime("%Y-%m-%d")

    candles = polygon_ohlc(symbol, 1, "minute", today, today)
    last_trade = get_last_trade(symbol)

    # No intraday + no last trade → try previous session
    if not candles and not last_trade:
        d = get_prev(symbol)

        if d:
            price = round(d["c"], 2)
            open_price = d["o"]
            change = round(((price - open_price) / open_price) * 100, 2)

            bias = "Bullish" if change > 0 else "Bearish" if change < 0 else "Neutral"
            trend = "Sideways (after-hours)"

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
                    "entry": f"{round(price * 1.003, 2)} – break above range",
                    "stop": f"{support} – below support",
                    "targets": [
                        f"{resistance} (near resistance)",
                        f"{round(resistance * 1.02, 2)} (extension)"
                    ]
                },
                "risk_notes": [
                    "After-hours liquidity is thin",
                    "Expect wider spreads at open",
                    "Wait for volume confirmation"
                ],
                "summary": (
                    f"{symbol} last closed at ${price} ({change}%). "
                    "Live data is offline; structure is based on the most recent confirmed session."
                ),
                "reasoning": trader_reasoning(bias, support, resistance)
            }

            LAST_SNAPSHOT[symbol] = payload
            return jsonify(payload)

        if symbol in LAST_SNAPSHOT:
            cached = LAST_SNAPSHOT[symbol].copy()
            cached["summary"] += (
                " Live market data is temporarily unavailable. "
                "This analysis is based on the most recent confirmed market structure "
                f"for {symbol} and remains valid for strategic planning. "
                "Await fresh volume before acting."
            )
            return jsonify(cached)

        return jsonify({
            "ticker": symbol,
            "price": "—",
            "bias": "Unavailable",
            "trend": "No live feed",
            "levels": {"support": "—", "resistance": "—"},
            "plan": {"entry": "Wait for data", "stop": "N/A", "targets": []},
            "risk_notes": [
                "No market data returned from provider.",
                "This can occur after-hours or during API outages.",
                "Try again shortly."
            ],
            "summary": (
                "Live market data is temporarily unavailable. "
                f"{symbol} has no confirmed session data yet."
            ),
            "reasoning": "Market structure cannot be evaluated without confirmed price flow."
        })

    # AFTER-HOURS WITH LAST TRADE
    if not candles:
        d = get_prev(symbol)
        price = last_trade or round(d["c"], 2)
        open_price = d["o"] if d else price
        change = round(((price - open_price) / open_price) * 100, 2)

        bias = "Bullish" if change > 0 else "Bearish" if change < 0 else "Neutral"
        trend = "Sideways (after-hours)"

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
                "entry": f"{round(price * 1.003, 2)} – break above current range",
                "stop": f"{support} – below session support",
                "targets": [
                    f"{resistance} (near resistance)",
                    f"{round(resistance * 1.02, 2)} (extension)"
                ]
            },
            "risk_notes": [
                "After-hours liquidity is thin",
                "Expect wider spreads at open",
                "Wait for volume confirmation"
            ],
            "summary": (
                f"{symbol} last traded at ${price} ({change}%). "
                "Market is currently closed; using most recent confirmed data."
            ),
            "reasoning": trader_reasoning(bias, support, resistance)
        }

        LAST_SNAPSHOT[symbol] = payload
        return jsonify(payload)

    # INTRADAY PATH
    closes = [c["c"] for c in candles]
    highs = [c["h"] for c in candles]

    price = round(closes[-1], 2)
    open_price = candles[0]["o"]
    change = round(((price - open_price) / open_price) * 100, 2)

    ema9 = mean(closes[-9:])
    ema21 = mean(closes[-21:]) if len(closes) >= 21 else mean(closes)

    bias = "Bullish" if price > ema21 else "Bearish" if price < ema21 else "Neutral"
    trend = "Upward (short-term)" if ema9 > ema21 else "Downward (short-term)"

    support = round(ema21, 2)
    resistance = round(max(highs), 2)

    payload = {
        "ticker": symbol,
        "price": price,
        "change": change,
        "bias": bias,
        "trend": trend,
        "levels": {"support": str(support), "resistance": str(resistance)},
        "plan": {
            "entry": f"{round(price * 1.003, 2)} – break above current range",
            "stop": f"{round(ema21 * 0.995, 2)} – below trend support",
            "targets": [
                f"{resistance} (range high)",
                f"{round(resistance * 1.02, 2)} (extension)"
            ]
        },
        "risk_notes": [
            "Watch volume for confirmation",
            "Be cautious near resistance",
            "Move stop to breakeven on strength"
        ],
        "summary": (
            f"{symbol} is trading at ${price} ({change}%). "
            f"Structure remains {bias.lower()} with {trend.lower()} momentum."
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