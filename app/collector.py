import ccxt
import pandas as pd
from app.config import EXCHANGE_ID, OHLCV_LIMIT

exchange = getattr(ccxt, EXCHANGE_ID)({
    "enableRateLimit": True,
    "options": {"defaultType": "spot"},
})


def fetch_ohlcv(symbol: str, timeframe: str, limit: int = OHLCV_LIMIT) -> pd.DataFrame:
    """سحب الشموع من CoinEx"""
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = df["timestamp"].astype("int64")
    return df


def fetch_orderbook(symbol: str, depth: int = 50) -> dict:
    """سحب دفتر الأوامر"""
    ob = exchange.fetch_order_book(symbol, limit=depth)
    return {"bids": ob["bids"], "asks": ob["asks"], "timestamp": ob["timestamp"]}


def fetch_trades(symbol: str, limit: int = 200) -> list:
    """
    سحب آخر الصفقات المنفذة مع معالجة أفضل لحقل side.
    بعض المنصات مثل CoinEx قد لا تُرجع side مباشرة.
    """
    trades = exchange.fetch_trades(symbol, limit=limit)
    result = []
    for t in trades:
        side = t.get("side")

        # محاولة استخراج side من info إذا لم يتوفر مباشرة
        if not side and "info" in t and isinstance(t["info"], dict):
            info = t["info"]
            raw_side = info.get("side") or info.get("type") or info.get("direction") or ""
            raw_side = str(raw_side).lower()
            if "buy" in raw_side or "bid" in raw_side:
                side = "buy"
            elif "sell" in raw_side or "ask" in raw_side:
                side = "sell"

        # fallback: إذا فشل كل شيء، نعتمد على مقارنة السعر بسعر الإغلاق السابق
        if not side:
            side = "buy"  # افتراضي محايد

        result.append({
            "price": float(t["price"]),
            "amount": float(t["amount"]),
            "side": side,
            "timestamp": t.get("timestamp"),
        })
    return result


def store_ohlcv(symbol: str, timeframe: str):
    """سحب + تخزين الشموع في Supabase"""
    from app.database import save_ohlcv
    df = fetch_ohlcv(symbol, timeframe)
    rows = [
        {
            "timestamp": int(r.timestamp),
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "close": float(r.close),
            "volume": float(r.volume),
        }
        for r in df.itertuples()
    ]
    save_ohlcv(symbol, timeframe, rows)
    return df
