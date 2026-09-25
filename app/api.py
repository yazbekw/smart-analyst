from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.config import SYMBOLS, SCAN_INTERVAL_MINUTES, PORT
from app.scheduler import start_scheduler, scan_all
from app.engine import analyze_symbol
from app.database import get_recent_signals, get_latest_snapshots
from app.collector import fetch_ohlcv

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@app.get("/api/active-signals")
async def api_active_signals():
    from app.lifecycle import get_active_signals
    return get_active_signals()


@app.get("/api/signal-events/{signal_id}")
async def api_signal_events(signal_id: int):
    from app.database import get_client
    res = (
        get_client().table("signal_events")
        .select("*").eq("signal_id", signal_id)
        .order("created_at", desc=True).limit(100).execute()
    )
    return res.data or []


@app.get("/api/anomalies")
async def api_anomalies(limit: int = 30):
    from app.database import get_client
    res = (
        get_client().table("anomalies")
        .select("*").order("created_at", desc=True).limit(limit).execute()
    )
    return res.data or []

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    # تشغيل دورة أولى فورية
    try:
        await scan_all()
    except Exception as e:
        print(f"⚠️ first scan error: {e}")
    yield


app = FastAPI(title="Smart Market Analyst", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "symbols": SYMBOLS,
        "interval": SCAN_INTERVAL_MINUTES,
    })


@app.get("/api/status")
async def api_status():
    return {
        "status": "running",
        "symbols": SYMBOLS,
        "scan_interval_minutes": SCAN_INTERVAL_MINUTES,
    }


@app.get("/api/snapshots")
async def api_snapshots():
    return get_latest_snapshots()


@app.get("/api/signals")
async def api_signals(limit: int = 50):
    return get_recent_signals(limit)


@app.get("/api/ohlcv/{symbol:path}")
async def api_ohlcv(symbol: str, timeframe: str = "15m", limit: int = 200):
    try:
        df = fetch_ohlcv(symbol, timeframe, limit=limit)
        return df.to_dict("records")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/analyze/{symbol:path}")
async def api_analyze(symbol: str):
    try:
        df_btc = fetch_ohlcv("BTC/USDT", "15m", limit=100)
        return analyze_symbol(symbol, df_btc=df_btc)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/scan")
async def api_scan():
    await scan_all()
    return {"status": "done"}
