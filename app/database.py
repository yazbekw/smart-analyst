from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_KEY

_client: Client = None

def get_client() -> Client:
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("Supabase credentials missing")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def save_ohlcv(symbol: str, timeframe: str, rows: list[dict]):
    if not rows:
        return
    client = get_client()
    for r in rows:
        r["symbol"] = symbol
        r["timeframe"] = timeframe
    client.table("ohlcv").upsert(
        rows, on_conflict="symbol,timeframe,timestamp"
    ).execute()


def save_snapshot(data: dict):
    get_client().table("snapshots").insert(data).execute()


def save_signal(data: dict):
    get_client().table("signals").insert(data).execute()


def get_recent_signals(limit: int = 50) -> list:
    res = (
        get_client()
        .table("signals")
        .select("*")
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def get_latest_snapshots() -> list:
    """أحدث snapshot لكل رمز"""
    res = (
        get_client()
        .table("snapshots")
        .select("*")
        .order("timestamp", desc=True)
        .limit(200)
        .execute()
    )
    rows = res.data or []
    latest = {}
    for r in rows:
        if r["symbol"] not in latest:
            latest[r["symbol"]] = r
    return list(latest.values())


def get_last_signal_for(symbol: str) -> dict | None:
    res = (
        get_client()
        .table("signals")
        .select("*")
        .eq("symbol", symbol)
        .order("timestamp", desc=True)
        .limit(1)
        .execute()
    )
    return (res.data or [None])[0]
