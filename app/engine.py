import pandas_ta_classic as ta
from app.collector import fetch_ohlcv, fetch_orderbook, fetch_trades
from app.signals import *
from app.patterns import scan_patterns
from app.regime import detect_regime, regime_multipliers
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
    """
    حساب المستويات مع R:R = 1:2
    SL = 1.0 ATR (مخاطرة أقل)
    TP1 = 2.0 ATR (مكافأة أكثر)
    """
    try:
        price = float(df_15m["close"].iloc[-1])
        atr = _atr(df_15m)
        if atr is None or atr == 0:
            atr = price * 0.005

        if "BUY" in state:
            entry_low = price - atr * 0.3
            entry_high = price + atr * 0.2
            sl = price - atr * 1.0
            tp1 = price + atr * 2.0
            tp2 = price + atr * 3.5
            tp3 = price + atr * 5.5
        elif "SELL" in state:
            entry_low = price - atr * 0.2
            entry_high = price + atr * 0.3
            sl = price + atr * 1.0
            tp1 = price - atr * 2.0
            tp2 = price - atr * 3.5
            tp3 = price - atr * 5.5
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
    try:
        r = fn(*args, **kwargs)
        if r is None or len(r) != 2:
            return 0, None
        return r
    except Exception as e:
        print(f"[signal {fn.__name__}] {e}")
        return 0, None


def analyze_symbol(symbol: str, df_btc=None) -> dict:
    df_4h = fetch_ohlcv(symbol, "4h", limit=300)
    df_1h = fetch_ohlcv(symbol, "1h", limit=300)
    df_15m = fetch_ohlcv(symbol, "15m", limit=300)
    ob = fetch_orderbook(symbol)
    trades = fetch_trades(symbol, limit=200)

    # ===== Regime Detection =====
    regime_info = detect_regime(df_1h)
    regime = regime_info["regime"]
    mult = regime_multipliers(regime)

    raw = {
        "trend": 0, "momentum": 0, "volume": 0,
        "orderflow": 0, "structure": 0, "context": 0, "risk": 0,
    }
    reasons = []
    warnings = []

    # ===== Trend =====
    for df, tf in [(df_4h, "4H"), (df_1h, "1H")]:
        s, r = _safe_call(sig_price_above_ema200, df)
        raw["trend"] += s
        if r: reasons.append(f"[{tf}] {r}")

        s, r = _safe_call(sig_ema50_above_ema200, df)
        raw["trend"] += s
        if r and tf == "1H": reasons.append(f"[{tf}] {r}")

        s, r = _safe_call(sig_ema50_slope_up, df)
        raw["trend"] += s
        if r and tf == "1H": reasons.append(f"[{tf}] {r}")

    s, r = _safe_call(sig_price_above_ema20, df_15m)
    raw["trend"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_adx_strength, df_1h)
    raw["trend"] += s
    if r: reasons.append(f"[1H] {r}")

    # ===== Momentum =====
    for fn in (sig_macd_cross, sig_rsi_zone, sig_roc_positive):
        s, r = _safe_call(fn, df_15m)
        raw["momentum"] += s
        if r: reasons.append(f"[15M] {r}")

    # ===== Volume =====
    s, r = _safe_call(sig_volume_ratio, df_15m)
    raw["volume"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_volume_price_agreement, df_15m)
    raw["volume"] += s
    if r: reasons.append(f"[15M] {r}")

    # ===== Order Flow =====
    s, r = _safe_call(sig_orderbook_imbalance, ob)
    raw["orderflow"] += s
    if r: reasons.append(r)

    s, r = _safe_call(sig_taker_buy_pressure, trades)
    raw["orderflow"] += s
    if r: reasons.append(r)

    # ===== Structure =====
    s, r = _safe_call(sig_broke_resistance, df_15m)
    raw["structure"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_near_support, df_15m)
    raw["structure"] += s
    if r: reasons.append(f"[15M] {r}")

    # ===== Patterns =====
    p_score, p_reasons, p_warnings = scan_patterns(df_15m)
    raw["structure"] += p_score
    reasons.extend(p_reasons)
    warnings.extend(p_warnings)

    # ===== Context =====
    if df_btc is not None and symbol != BTC_REFERENCE:
        s, r = _safe_call(sig_btc_trend, df_btc)
        raw["context"] += s
        if r: reasons.append(r)

        s, r = _safe_call(sig_relative_strength, df_15m, df_btc)
        raw["context"] += s
        if r: reasons.append(r)

    # ===== تطبيق مضاعفات Regime =====
    breakdown = {k: int(round(v * mult.get(k, 1.0))) for k, v in raw.items()}
    score = sum(breakdown.values())

    def _state(s):
        if s >= 15: return "STRONG BUY SETUP"
        if s >= 8: return "BUY SETUP"
        if s >= 3: return "WATCH"
        if s <= -15: return "STRONG SELL SETUP"
        if s <= -8: return "SELL SETUP"
        return "NO TRADE"

    state = _state(score)
    levels = calculate_levels(df_15m, state) if state != "NO TRADE" else None

    if levels:
        s, r = _safe_call(sig_rr_ratio, df_15m["close"].iloc[-1],
                          levels["stop_loss"], levels["tp1"])
        breakdown["risk"] += s
        if r:
            if s < 0: warnings.append(r)
            else: reasons.append(r)

    s, r = _safe_call(sig_resistance_close, df_15m)
    breakdown["risk"] += s
    if r: warnings.append(r)

    # ============================================================
    # Warnings تلقائية (جديد)
    # ============================================================
    if breakdown.get("orderflow", 0) <= -3:
        warnings.append(f"Order Flow سلبي ({breakdown['orderflow']}) — بائعون يسيطرون")
    if breakdown.get("volume", 0) <= -1:
        warnings.append("الحجم أقل من المتوسط — إشارة ضعيفة")
    if regime_info.get("regime") == "ranging":
        warnings.append("السوق جانبي — انتظر اختراقاً واضحاً")
    if regime_info.get("adx", 0) < 20 and regime_info.get("adx", 0) > 0:
        warnings.append(f"ADX ضعيف ({regime_info['adx']}) — لا يوجد اتجاه قوي")
    if regime_info.get("regime") == "high_vol":
        warnings.append("تقلب عالٍ — قلل حجم الصفقة")

    score = sum(breakdown.values())
    state = _state(score)
    price = float(df_15m["close"].iloc[-1])

    result = {
        "symbol": symbol, "price": round(price, 6),
        "score": int(score), "state": state,
        "breakdown": breakdown, "reasons": reasons, "warnings": warnings,
        "levels": levels, "regime": regime_info,
    }

    try:
        save_snapshot({
            "symbol": symbol, "price": price,
            "trend_score": breakdown["trend"],
            "momentum_score": breakdown["momentum"],
            "volume_score": breakdown["volume"],
            "orderflow_score": breakdown["orderflow"],
            "structure_score": breakdown["structure"],
            "context_score": breakdown["context"],
            "risk_score": breakdown["risk"],
            "total_score": int(score), "state": state,
            "details": {
                "reasons": reasons, "warnings": warnings,
                "levels": levels, "regime": regime_info,
            },
        })
    except Exception as e:
        print(f"[save_snapshot {symbol}] {e}")

    return result
