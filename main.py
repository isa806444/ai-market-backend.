from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import asyncio
import yfinance as yf
from openai import OpenAI

# Load environment variables
load_dotenv()

# OpenAI client (expects OPENAI_API_KEY in environment)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI(title="AI Market Assistant")

class AnalyzeRequest(BaseModel):
    symbol: str
    mode: str
    style: str
    preset: str | None = None

async def fetch_market_data(symbol: str):
    def _download():
        t = yf.Ticker(symbol)
        return t.history(period="1mo", interval="1d")

    try:
        hist = await asyncio.wait_for(asyncio.to_thread(_download), timeout=6)

        if hist is None or hist.empty or len(hist) < 2:
            return None

        last = hist.iloc[-1]
        prev = hist.iloc[-2]

        price = float(last["Close"])
        prev_close = float(prev["Close"])
        change_pct = ((price - prev_close) / prev_close) * 100

        high_5 = float(hist["High"].tail(5).max())
        low_5 = float(hist["Low"].tail(5).min())
        sma20 = float(hist["Close"].rolling(20).mean().iloc[-1])
        volume = int(last["Volume"])

        return {
            "price": round(price, 2),
            "prev_close": round(prev_close, 2),
            "change_pct": round(change_pct, 2),
            "high_5": round(high_5, 2),
            "low_5": round(low_5, 2),
            "sma20": round(sma20, 2),
            "volume": volume
        }

    except Exception:
        return None

def build_prompt(symbol, data, mode, style, preset):
    preset_rules = ""
    if preset == "day":
        preset_rules = "Focus on intraday momentum and tight risk."
    elif preset == "swing":
        preset_rules = "Focus on multi-day structure and trend continuation."
    elif preset == "miner":
        preset_rules = "Treat this as a crypto miner. Correlate to BTC."

    return f"""
You are a professional trading analyst.

Ticker: {symbol}

Live Market Data:
- Current Price: {data['price']}
- Previous Close: {data['prev_close']}
- Daily Change: {data['change_pct']}%
- 20-day Moving Average: {data['sma20']}
- 5-day High: {data['high_5']}
- 5-day Low: {data['low_5']}
- Volume: {data['volume']}

User Settings:
- Mode: {mode}
- Style: {style}
- Preset: {preset or "none"}

Preset Guidance:
{preset_rules}

Generate:
Bias, Trend, Support, Resistance, Entry, Stop, Targets, Risk Notes.
Use ONLY the data above.
"""

@app.get("/")
def health():
    return {"status": "ok"}

@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    symbol = req.symbol.upper().strip()

    data = await fetch_market_data(symbol)
    if not data:
        return {
            "analysis": f"⚠️ Live market data for {symbol} could not be reached right now."
        }

    prompt = build_prompt(symbol, data, req.mode, req.style, req.preset)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a disciplined market analyst."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.4
    )

    analysis = response.choices[0].message.content

    return {
        "symbol": symbol,
        "quote": data,
        "analysis": analysis
    }