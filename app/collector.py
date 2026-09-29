"""
Collector متعدد المصادر:
- يحاول عدة مصادر (CoinEx → Binance → OKX → Bybit)
- يكشف البيانات القديمة (Stale)
- يقارن الأسعار بين المصادر
- يعيد أفضل مصدر
"""
import ccxt
import pandas as pd
import time
from datetime import datetime, timezone

from app.config import EXCHANGE_ID, OHLCV_LIMIT


# ============================================================
# إعدادات
# ============================================================
# ترتيب المصادر (الأول يُجرَّب أولاً)
EXCHANGE_PRIORITY = ["coinex", "binance", "okx", "bybit"]

# إذا كان السعر مختلفاً بأكثر من هذه النسبة → رفض
MAX_PRICE_DIFF_PCT = 1.0

# إذا كانت آخر شمعة أقدم من هذه الثواني → رفض
MAX_STALE_SECONDS = 900  # 15 دقيقة


# ============================================================
# Cache للمصادر
# ============================================================
_exchanges = {}


def _get_exchange(exchange_id: str):
    """إرجاع مصدر CCXT (مع cache)"""
    if exchange_id not in _exchanges:
        try:
            ex = getattr(ccxt, exchange_id)({
                "enableRateLimit": True,
                "timeout": 30000,
                "options": {"defaultType": "spot"},
            })
            _exchanges[exchange_id] = ex
            print(f"🔗 تم تحميل: {exchange_id}")
        except Exception as e:
            print(f"❌ فشل تحميل {exchange_id}: {e}")
            return None
    return _exchanges.get(exchange_id)


# ============================================================
# الفحص والصحة
# ============================================================
def _is_fresh(df: pd.DataFrame, timeframe: str) -> tuple:
    """
    يفحص إن كانت الشمعة الأخيرة حديثة.
    يعيد: (fresh?، سبب)
    """
    if df is None or len(df) == 0:
        return False, "بيانات فارغة"

    # آخر شمعة
    last_ts = df["timestamp"].iloc[-1]
    if pd.isna(last_ts):
        return False, "timestamp فارغ"

    # حساب الفرق بالثواني
    last_dt = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    age = (now - last_dt).total_seconds()

    # الوقت المتوقع للإطار
    tf_seconds = {
        "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "4h": 14400, "1d": 86400,
    }.get(timeframe, 900)

    # مسموح: شمعة أخيرة + هامش
    max_age = tf_seconds + 300  # +5 دقائق هامش

    if age > max_age:
        return False, f"قديمة ({age/60:.1f} دقيقة > {max_age/60:.1f})"

    return True, None


def _is_valid_prices(df: pd.DataFrame) -> tuple:
    """يتأكد أن الأسعار منطقية"""
    if df is None or len(df) == 0:
        return False, "فارغ"

    # فحص NULL
    if df[["open", "high", "low", "close"]].isna().any().any():
        return False, "قيم NULL"

    # فحص صفر
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        return False, "قيم ≤ 0"

    # فحص OHLC متسق
    invalid = (
        (df["high"] < df["low"]) |
        (df["high"] < df["open"]) |
        (df["high"] < df["close"]) |
        (df["low"] > df["open"]) |
        (df["low"] > df["close"])
    )
    if invalid.any():
        return False, "OHLC غير متسق"

    # فحص "ثابت" (كل الشموع بنفس السعر → مشبوه)
    if len(df) >= 5:
        last5 = df.tail(5)
        if (last5["close"] == last5["close"].iloc[0]).all():
            return False, "أسعار ثابتة (5 شموع متطابقة)"

    return True, None


# ============================================================
# جلب من مصدر واحد
# ============================================================
def _fetch_from(exchange_id: str, symbol: str, timeframe: str, limit: int):
    """يجرب الجلب من مصدر واحد"""
    ex = _get_exchange(exchange_id)
    if not ex:
        return None, "المصدر غير متاح"

    try:
        # ⚠️ cache معطّل
        if hasattr(ex, "options"):
            ex.options["fetchOHLCVWarning"] = False

        raw = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

        if not raw or len(raw) < 10:
            return None, f"بيانات قليلة ({len(raw) if raw else 0} شمعة)"

        df = pd.DataFrame(
            raw,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = df["timestamp"].astype("int64")

        # فحص
        valid, reason = _is_valid_prices(df)
        if not valid:
            return None, reason

        fresh, reason = _is_fresh(df, timeframe)
        if not fresh:
            return None, reason

        return df, None

    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:80]}"


# ============================================================
# الواجهة الرئيسية: fetch_ohlcv
# ============================================================
def fetch_ohlcv(symbol: str, timeframe: str = "15m", limit: int = OHLCV_LIMIT) -> pd.DataFrame | None:
    """
    يجرب عدة مصادر بالترتيب.
    - إذا نجح مصدر → يُرجع بياناته
    - إذا فشل الأول → يجرب التالي
    - إذا فشل الكل → None
    """
    primary = EXCHANGE_ID.lower()
    order = [primary] + [x for x in EXCHANGE_PRIORITY if x != primary]

    results = []

    for ex_id in order:
        df, err = _fetch_from(ex_id, symbol, timeframe, limit)

        if df is not None:
            last_close = float(df["close"].iloc[-1])
            last_ts = datetime.fromtimestamp(
                df["timestamp"].iloc[-1] / 1000, tz=timezone.utc
            )
            age_min = (datetime.now(timezone.utc) - last_ts).total_seconds() / 60

            results.append({
                "source": ex_id,
                "df": df,
                "price": last_close,
                "age_min": age_min,
                "error": None,
            })
            print(f"✅ [{symbol}] {timeframe} ← {ex_id}: {last_close} "
                  f"(عمر: {age_min:.1f}د)")
            # ⚠️ لا نُكمل — نأخذ أول مصدر ناجح
            return df
        else:
            results.append({
                "source": ex_id,
                "df": None,
                "price": None,
                "error": err,
            })
            print(f"❌ [{symbol}] {timeframe} ← {ex_id}: {err}")

    # ============================================================
    # كل المصادر فشلت
    # ============================================================
    print(f"🚨 [{symbol}] {timeframe}: كل المصادر فشلت!")
    for r in results:
        print(f"   - {r['source']}: {r['error']}")
    return None


# ============================================================
# مقارنة الأسعار (للتشخيص)
# ============================================================
def compare_prices(symbol: str) -> dict:
    """
    يجلب السعر من كل المصادر ويقارن.
    يُستخدم للتشخيص.
    """
    results = {}
    prices = []

    for ex_id in EXCHANGE_PRIORITY:
        ex = _get_exchange(ex_id)
        if not ex:
            results[ex_id] = {"error": "غير متاح"}
            continue

        try:
            ticker = ex.fetch_ticker(symbol)
            price = float(ticker["last"])
            results[ex_id] = {
                "price": price,
                "timestamp": ticker.get("timestamp"),
            }
            prices.append((ex_id, price))
        except Exception as e:
            results[ex_id] = {"error": str(e)[:80]}

    # حساب الفرق
    if len(prices) >= 2:
        min_price = min(p for _, p in prices)
        max_price = max(p for _, p in prices)
        diff_pct = (max_price - min_price) / min_price * 100

        results["_summary"] = {
            "min": min_price,
            "max": max_price,
            "diff_pct": round(diff_pct, 3),
            "warning": diff_pct > MAX_PRICE_DIFF_PCT,
        }

    return results


# ============================================================
# Order Book & Trades (مع multi-source)
# ============================================================
def fetch_orderbook(symbol: str, depth: int = 50) -> dict:
    """يجلب دفتر الأوامر من أول مصدر ناجح"""
    primary = EXCHANGE_ID.lower()
    order = [primary] + [x for x in EXCHANGE_PRIORITY if x != primary]

    for ex_id in order:
        ex = _get_exchange(ex_id)
        if not ex:
            continue
        try:
            ob = ex.fetch_order_book(symbol, limit=depth)
            if ob and ob.get("bids") and ob.get("asks"):
                return {
                    "bids": ob["bids"],
                    "asks": ob["asks"],
                    "timestamp": ob["timestamp"],
                    "source": ex_id,
                }
        except Exception as e:
            print(f"⚠️ [{symbol}] orderbook {ex_id}: {str(e)[:60]}")
            continue

    # fallback: dict فارغ
    return {"bids": [], "asks": [], "timestamp": None, "source": None}


def fetch_trades(symbol: str, limit: int = 200) -> list:
    """يجلب الصفقات من أول مصدر ناجح"""
    primary = EXCHANGE_ID.lower()
    order = [primary] + [x for x in EXCHANGE_PRIORITY if x != primary]

    for ex_id in order:
        ex = _get_exchange(ex_id)
        if not ex:
            continue
        try:
            trades = ex.fetch_trades(symbol, limit=limit)
            if trades:
                result = []
                for t in trades:
                    side = t.get("side")
                    if not side and "info" in t:
                        raw = str(t["info"]).lower()
                        side = "buy" if "buy" in raw else "sell"
                    result.append({
                        "price": float(t["price"]),
                        "amount": float(t["amount"]),
                        "side": side or "buy",
                        "timestamp": t.get("timestamp"),
                    })
                return result
        except Exception as e:
            print(f"⚠️ [{symbol}] trades {ex_id}: {str(e)[:60]}")
            continue

    return []


# ============================================================
# Self-Test (للتشغيل اليدوي)
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("🔍 فحص المصادر")
    print("=" * 60)

    # 1. قارن الأسعار
    print("\n📊 مقارنة الأسعار BTC/USDT:")
    prices = compare_prices("BTC/USDT")
    for k, v in prices.items():
        print(f"   {k}: {v}")

    # 2. جرّب fetch_ohlcv
    print("\n📈 اختبار fetch_ohlcv:")
    df = fetch_ohlcv("BTC/USDT", "15m", limit=5)
    if df is not None:
        print(df.tail())
    else:
        print("❌ فشل")
