import ccxt
import pandas as pd
from app.config import EXCHANGE_ID, OHLCV_LIMIT
from app.database import save_ohlcv

exchange = getattr(ccxt, EXCHANGE_ID)({
    "enableRateLimit": True,
    "options": {"defaultType": "spot"},
})


def fetch_ohlcv(symbol: str, timeframe: str, limit: int = OHLCV_LIMIT) -> pd.DataFrame:
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = df["timestamp"].astype("int64")
    return df


def fetch_orderbook(symbol: str, depth: int = 50) -> dict:
    ob = exchange.fetch_order_book(symbol, limit=depth)
    return {
        "bids": ob["bids"],
        "asks": ob["asks"],
        "timestamp": ob["timestamp"],
    }


def fetch_trades(symbol: str, limit: int = 200) -> list:
    trades = exchange.fetch_trades(symbol, limit=limit)
    return [
        {
            "price": t["price"],
            "amount": t["amount"],
            "side": t["side"],
            "timestamp": t["timestamp"],
        }
        for t in trades
    ]


def store_ohlcv(symbol: str, timeframe: str):
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
