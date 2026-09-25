import pandas_ta as ta
from app.collector import fetch_ohlcv, fetch_orderbook, fetch_trades
from app.signals import *
from app.database import save_snapshot
from app.config import BTC_REFERENCE


def _atr(df, length=14):
    try:
        atr = ta.atr(df["high"], df["low"], df["close"], length=length)
        if atr is None or atr.isna().all():
            return None
        return float(atr.iloc[-1])
    except Exception:
        return None


def calculate_levels(df_15m, state):
    """حساب مستويات الدخول/الوقف/الأهداف بناءً على ATR"""
    try:
        price = float(df_15m["close"].iloc[-1])
        atr = _atr(df_15m)
        if atr is None or atr == 0:
            atr = price * 0.005

        if "BUY" in state:
            entry_low = price - atr * 0.3
            entry_high = price + atr * 0.2
            sl = price - atr * 1.5
            tp1 = price + atr * 1.5
            tp2 = price + atr * 3.0
            tp3 = price + atr * 5.0
        elif "SELL" in state:
            entry_low = price - atr * 0.2
            entry_high = price + atr * 0.3
            sl = price + atr * 1.5
            tp1 = price - atr * 1.5
            tp2 = price - atr * 3.0
            tp3 = price - atr * 5.0
        else:
            return None

        risk = abs(price - sl)
        rr = abs(tp1 - price) / risk if risk > 0 else 0

        return {
            "entry_low": round(entry_low, 6),
            "entry_high": round(entry_high, 6),
            "stop_loss": round(sl, 6),
            "tp1": round(tp1, 6),
            "tp2": round(tp2, 6),
            "tp3": round(tp3, 6),
            "rr": round(rr, 2),
        }
    except Exception as e:
        print(f"[calculate_levels] {e}")
        return None


def _safe_call(fn, *args, **kwargs):
    """استدعاء آمن لدوال الإشارات — يعيد (0, None) عند الخطأ"""
    try:
        result = fn(*args, **kwargs)
        if result is None or len(result) != 2:
            return 0, None
        return result
    except Exception as e:
        print(f"[signal error: {fn.__name__}] {e}")
        return 0, None


def analyze_symbol(symbol: str, df_btc=None) -> dict:
    """التحليل الكامل لرمز واحد"""

    # ===== سحب البيانات =====
    df_4h = fetch_ohlcv(symbol, "4h", limit=300)
    df_1h = fetch_ohlcv(symbol, "1h", limit=300)
    df_15m = fetch_ohlcv(symbol, "15m", limit=300)
    ob = fetch_orderbook(symbol)
    trades = fetch_trades(symbol, limit=200)

    score = 0
    reasons = []
    warnings = []
    breakdown = {
        "trend": 0, "momentum": 0, "volume": 0,
        "orderflow": 0, "structure": 0, "context": 0, "risk": 0,
    }

    # ===== Trend =====
    for df, tf in [(df_4h, "4H"), (df_1h, "1H")]:
        s, r = _safe_call(sig_price_above_ema200, df)
        score += s; breakdown["trend"] += s
        if r: reasons.append(f"[{tf}] {r}")

        s, r = _safe_call(sig_ema50_above_ema200, df)
        score += s; breakdown["trend"] += s
        if r and tf == "1H": reasons.append(f"[{tf}] {r}")

        s, r = _safe_call(sig_ema50_slope_up, df)
        score += s; breakdown["trend"] += s
        if r and tf == "1H": reasons.append(f"[{tf}] {r}")

    s, r = _safe_call(sig_price_above_ema20, df_15m)
    score += s; breakdown["trend"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_adx_strength, df_1h)
    score += s; breakdown["trend"] += s
    if r: reasons.append(f"[1H] {r}")

    # ===== Momentum =====
    s, r = _safe_call(sig_macd_cross, df_15m)
    score += s; breakdown["momentum"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_rsi_zone, df_15m)
    score += s; breakdown["momentum"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_roc_positive, df_15m)
    score += s; breakdown["momentum"] += s
    if r: reasons.append(f"[15M] {r}")

    # ===== Volume =====
    s, r = _safe_call(sig_volume_ratio, df_15m)
    score += s; breakdown["volume"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_volume_price_agreement, df_15m)
    score += s; breakdown["volume"] += s
    if r: reasons.append(f"[15M] {r}")

    # ===== Order Flow =====
    s, r = _safe_call(sig_orderbook_imbalance, ob)
    score += s; breakdown["orderflow"] += s
    if r: reasons.append(r)

    s, r = _safe_call(sig_taker_buy_pressure, trades)
    score += s; breakdown["orderflow"] += s
    if r: reasons.append(r)

    # ===== Structure =====
    s, r = _safe_call(sig_broke_resistance, df_15m)
    score += s; breakdown["structure"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_near_support, df_15m)
    score += s; breakdown["structure"] += s
    if r: reasons.append(f"[15M] {r}")

    # ===== Context =====
    if df_btc is not None and symbol != BTC_REFERENCE:
        s, r = _safe_call(sig_btc_trend, df_btc)
        score += s; breakdown["context"] += s
        if r: reasons.append(r)

        s, r = _safe_call(sig_relative_strength, df_15m, df_btc)
        score += s; breakdown["context"] += s
        if r: reasons.append(r)

    # ===== تحديد الحالة الأولية =====
    def _state(s):
        if s >= 15: return "STRONG BUY SETUP"
        if s >= 8: return "BUY SETUP"
        if s >= 3: return "WATCH"
        if s <= -15: return "STRONG SELL SETUP"
        if s <= -8: return "SELL SETUP"
        return "NO TRADE"

    state = _state(score)

    # ===== حساب المستويات =====
    levels = calculate_levels(df_15m, state) if state != "NO TRADE" else None

    if levels:
        s, r = _safe_call(
            sig_rr_ratio,
            df_15m["close"].iloc[-1],
            levels["stop_loss"],
            levels["tp1"],
        )
        score += s; breakdown["risk"] += s
        if r:
            if s < 0:
                warnings.append(r)
            else:
                reasons.append(r)

    s, r = _safe_call(sig_resistance_close, df_15m)
    score += s; breakdown["risk"] += s
    if r: warnings.append(r)

    # ===== إعادة التقييم بعد Risk =====
    state = _state(score)
    price = float(df_15m["close"].iloc[-1])

    result = {
        "symbol": symbol,
        "price": round(price, 6),
        "score": int(score),
        "state": state,
        "breakdown": breakdown,
        "reasons": reasons,
        "warnings": warnings,
        "levels": levels,
    }

    # ===== الحفظ في Supabase =====
    try:
        save_snapshot({
            "symbol": symbol,
            "price": price,
            "trend_score": breakdown["trend"],
            "momentum_score": breakdown["momentum"],
            "volume_score": breakdown["volume"],
            "orderflow_score": breakdown["orderflow"],
            "structure_score": breakdown["structure"],
            "context_score": breakdown["context"],
            "risk_score": breakdown["risk"],
            "total_score": int(score),
            "state": state,
            "details": {
                "reasons": reasons,
                "warnings": warnings,
                "levels": levels,
            },
        })
    except Exception as e:
        print(f"[save_snapshot {symbol}] {e}")

    return result
