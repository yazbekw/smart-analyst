from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import SYMBOLS, SCAN_INTERVAL_MINUTES
from app.scheduler import start_scheduler, scan_all
from app.engine import analyze_symbol
from app.database import get_client, get_recent_signals, get_latest_snapshots
from app.collector import fetch_ohlcv
from app.lifecycle import get_active_signals
from app.paper import get_paper_stats
from app.regime import detect_regime

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    try:
        await scan_all()
    except Exception as e:
        print(f"⚠️ first scan error: {e}")
    yield


app = FastAPI(title="Smart Market Analyst", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ============================================================
# Pages
# ============================================================
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "symbols": SYMBOLS,
        "interval": SCAN_INTERVAL_MINUTES,
    })


# ============================================================
# Core APIs
# ============================================================
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


@app.get("/api/active-signals")
async def api_active_signals():
    return get_active_signals()


@app.get("/api/anomalies")
async def api_anomalies(limit: int = 30):
    res = (
        get_client().table("anomalies").select("*")
        .order("created_at", desc=True).limit(limit).execute()
    )
    return res.data or []


@app.get("/api/signal-events")
async def api_signal_events(limit: int = 50):
    res = (
        get_client().table("signal_events").select("*")
        .order("created_at", desc=True).limit(limit).execute()
    )
    return res.data or []


# ============================================================
# Paper Trading (NEW)
# ============================================================
@app.get("/api/paper/stats")
async def api_paper_stats():
    return get_paper_stats()


@app.get("/api/paper/trades")
async def api_paper_trades(limit: int = 50, status: str = None):
    q = (
        get_client().table("paper_trades").select("*")
        .order("opened_at", desc=True).limit(limit)
    )
    if status:
        q = q.eq("status", status)
    return q.execute().data or []


# ============================================================
# Regime (NEW)
# ============================================================
@app.get("/api/regime")
async def api_regime():
    result = {}
    for sym in SYMBOLS:
        try:
            df_1h = fetch_ohlcv(sym, "1h", limit=300)
            result[sym] = detect_regime(df_1h)
        except Exception as e:
            result[sym] = {"regime": "unknown", "error": str(e)}
    return result


# ============================================================
# Backtest (NEW)
# ============================================================
@app.post("/api/backtest/{symbol:path}")
async def api_backtest(symbol: str, timeframe: str = "1h", lookback: int = 200):
    from app.backtest import backtest_symbol
    try:
        df = fetch_ohlcv(symbol, timeframe, limit=1000)
        return backtest_symbol(symbol, df, lookback=lookback)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================
# OHLCV & Analysis
# ============================================================
@app.get("/api/ohlcv/{symbol:path}")
async def api_ohlcv(symbol: str, timeframe: str = "15m", limit: int = 100):
    try:
        return fetch_ohlcv(symbol, timeframe, limit=limit).to_dict("records")
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
