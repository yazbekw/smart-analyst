import pandas as pd
import pandas_ta_classic as ta
from app.collector import fetch_ohlcv, fetch_orderbook, fetch_trades
from app.signals import *
from app.patterns import scan_patterns
from app.regime import detect_regime, regime_multipliers
from app.database import save_snapshot
from app.config import BTC_REFERENCE


# ============================================================
# Helpers
# ============================================================
def _atr(df, length=14):
    try:
        if df is None or len(df) < length + 2:
            return None
        atr = ta.atr(df["high"], df["low"], df["close"], length=length)
        if atr is None or atr.isna().all():
            return None
        return float(atr.iloc[-1])
    except Exception:
        return None


def calculate_levels(df_15m, state, symbol="BTC/USDT"):
    """
    SL = 2% | TP1 = 1% | TP2 = 2% | TP3 = 3%
    R-Multiple: SL=-1R, TP1=+0.5R, TP2=+1R, TP3=+1.5R
    """
    try:
        price = float(df_15m["close"].iloc[-1])

        SL_PCT = 2.0
        TP1_PCT = 1.0
        TP2_PCT = 2.0
        TP3_PCT = 3.0

        if "BUY" in state or state == "EARLY OPPORTUNITY":
            entry_low = price * 0.999
            entry_high = price * 1.001
            sl = price * (1 - SL_PCT / 100)
            tp1 = price * (1 + TP1_PCT / 100)
            tp2 = price * (1 + TP2_PCT / 100)
            tp3 = price * (1 + TP3_PCT / 100)
        elif "SELL" in state:
            entry_low = price * 0.999
            entry_high = price * 1.001
            sl = price * (1 + SL_PCT / 100)
            tp1 = price * (1 - TP1_PCT / 100)
            tp2 = price * (1 - TP2_PCT / 100)
            tp3 = price * (1 - TP3_PCT / 100)
        else:
            return None

        risk = abs(price - sl)
        reward = abs(tp1 - price)
        rr = reward / risk if risk > 0 else 0

        return {
            "entry_low": round(entry_low, 6),
            "entry_high": round(entry_high, 6),
            "stop_loss": round(sl, 6),
            "tp1": round(tp1, 6),
            "tp2": round(tp2, 6),
            "tp3": round(tp3, 6),
            "rr": round(rr, 2),
            "sl_pct": SL_PCT,
            "tp1_pct": TP1_PCT,
            "tp2_pct": TP2_PCT,
            "tp3_pct": TP3_PCT,
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


def _context_quality(regime, adx_val, breakdown):
    """
    حساب جودة السياق (Context Quality).
    النطاق: -8 إلى +8
    """
    cq = 0

    # Regime
    if regime == "trending": cq += 3
    elif regime == "neutral": cq += 1
    elif regime == "ranging": cq -= 1
    elif regime == "low_vol": cq -= 2
    elif regime == "high_vol": cq -= 2

    # ADX
    if adx_val >= 30: cq += 3
    elif adx_val >= 25: cq += 2
    elif adx_val >= 20: cq += 1
    elif adx_val >= 15: cq += 0
    else: cq -= 1

    # Order Flow
    of = breakdown.get("orderflow", 0)
    if of > 0: cq += 1
    elif of < -3: cq -= 1

    # Volume
    vol = breakdown.get("volume", 0)
    if vol > 0: cq += 1
    elif vol < -2: cq -= 1

    return cq


def _build_result(symbol, price, score, state, breakdown, reasons, warnings, levels, regime_info):
    result = {
        "symbol": symbol,
        "price": round(price, 6),
        "score": int(score),
        "state": state,
        "breakdown": breakdown,
        "reasons": reasons,
        "warnings": warnings,
        "levels": levels,
        "regime": regime_info,
    }
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
                "regime": regime_info,
            },
        })
    except Exception as e:
        print(f"[save_snapshot {symbol}] {e}")
    return result


# ============================================================
# Main Analysis
# ============================================================
def analyze_symbol(symbol: str, df_btc=None) -> dict:
    df_4h = fetch_ohlcv(symbol, "4h", limit=300)
    df_1h = fetch_ohlcv(symbol, "1h", limit=300)
    df_15m = fetch_ohlcv(symbol, "15m", limit=300)
    df_5m = fetch_ohlcv(symbol, "5m", limit=100)
    ob = fetch_orderbook(symbol)
    trades = fetch_trades(symbol, limit=200)

    price = float(df_15m["close"].iloc[-1])

    regime_info = detect_regime(df_1h)
    regime = regime_info["regime"]
    adx_val = regime_info.get("adx", 0)
    mult = regime_multipliers(regime)

    raw = {
        "trend": 0, "momentum": 0, "volume": 0,
        "orderflow": 0, "structure": 0, "context": 0, "risk": 0,
    }
    reasons = []
    warnings = []

    # ============================================================
    # جمع النقاط
    # ============================================================
    for df, tf in [(df_4h, "4H"), (df_1h, "1H")]:
        s, r = _safe_call(sig_price_above_ema200, df)
        raw["trend"] += s
        if r: reasons.append(f"[{tf}] {r}")

        s, r = _safe_call(sig_ema50_above_ema200, df)
        raw["trend"] += s
        if r and tf == "1H": reasons.append(f"[{tf}] {r}")

        s, r = _safe_call(sig_ema50_below_ema200, df)
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

    s, r = _safe_call(sig_distance_from_ema20, df_15m)
    raw["trend"] += s
    if r and s < 0: warnings.append(r)
    elif r: reasons.append(r)

    for fn in (sig_macd_cross, sig_rsi_zone, sig_roc_positive):
        s, r = _safe_call(fn, df_15m)
        raw["momentum"] += s
        if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_stochastic, df_15m)
    raw["momentum"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_momentum_acceleration, df_15m)
    raw["momentum"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_volume_ratio, df_15m)
    raw["volume"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_volume_price_agreement, df_15m)
    raw["volume"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_volume_cluster, df_15m)
    raw["volume"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_orderbook_imbalance, ob)
    raw["orderflow"] += s
    if r: reasons.append(r)

    s, r = _safe_call(sig_taker_buy_pressure, trades)
    raw["orderflow"] += s
    if r: reasons.append(r)

    s, r = _safe_call(sig_broke_resistance, df_15m)
    raw["structure"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_broke_support, df_15m)
    raw["structure"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_near_support, df_15m)
    raw["structure"] += s
    if r: reasons.append(f"[15M] {r}")

    p_score, p_reasons, p_warnings = scan_patterns(df_15m)
    raw["structure"] += p_score
    reasons.extend(p_reasons)
    warnings.extend(p_warnings)

    for fn in (sig_hammer, sig_shooting_star, sig_bullish_engulfing,
               sig_bearish_engulfing, sig_pin_bar):
        s, r = _safe_call(fn, df_15m)
        raw["structure"] += s
        if r:
            if s > 0: reasons.append(r)
            else: warnings.append(r)

    if df_btc is not None and symbol != BTC_REFERENCE:
        s, r = _safe_call(sig_btc_trend, df_btc)
        raw["context"] += s
        if r: reasons.append(r)

        s, r = _safe_call(sig_relative_strength, df_15m, df_btc)
        raw["context"] += s
        if r: reasons.append(r)

    # ============================================================
    # تطبيق Regime multipliers
    # ============================================================
    breakdown = {k: int(round(v * mult.get(k, 1.0))) for k, v in raw.items()}
    score = sum(breakdown.values())

    # ============================================================
    # حساب Context Quality
    # ============================================================
    cq = _context_quality(regime, adx_val, breakdown)

    # ============================================================
    # 🎯 الفلترة المتدرجة — 5 مستويات
    # ============================================================

    # المستوى 1: STRONG BUY
    if score >= 30 and cq >= 5:
        state = "STRONG BUY SETUP"
        reasons.append(f"🎯 إشارة قوية: score={score}, cq={cq}")

    # المستوى 2: BUY SETUP
    elif score >= 22 and cq >= 2:
        state = "BUY SETUP"
        reasons.append(f"✅ فرصة: score={score}, cq={cq}")

    # المستوى 3: EARLY OPPORTUNITY
    elif score >= 15 and cq >= 0:
        state = "EARLY OPPORTUNITY"
        warnings.append(f"⏳ فرصة مبكرة: score={score}, cq={cq}")
        warnings.append("انتظر تأكيد قبل الدخول")

    # المستوى 4: STRONG SELL
    elif score <= -30 and cq >= 5:
        state = "STRONG SELL SETUP"
        reasons.append(f"🔴 إشارة بيع قوية: score={score}, cq={cq}")

    # المستوى 5: SELL SETUP
    elif score <= -22 and cq >= 2:
        state = "SELL SETUP"
        reasons.append(f"🔴 فرصة بيع: score={score}, cq={cq}")

    # WATCH
    else:
        state = "WATCH"
        if -15 < score < 15:
            warnings.append(f"⏸️ سوق جانبي: score={score}")
        if cq < 0:
            warnings.append(f"⚠️ سياق ضعيف: cq={cq}")

    # ============================================================
    # حساب المستويات
    # ============================================================
    levels = None
    if state in ("STRONG BUY SETUP", "BUY SETUP", "EARLY OPPORTUNITY",
                 "STRONG SELL SETUP", "SELL SETUP"):
        levels = calculate_levels(df_15m, state, symbol=symbol)

        if levels:
            s, r = _safe_call(sig_rr_ratio, price, levels["stop_loss"], levels["tp1"])
            breakdown["risk"] += s
            if r:
                if s < 0: warnings.append(r)
                else: reasons.append(r)

    # إعادة حساب Score
    score = sum(breakdown.values())

    # إعادة تقييم الحالة بعد Risk
    if state == "STRONG BUY SETUP" and score < 30:
        state = "BUY SETUP"
    if state == "BUY SETUP" and score < 22:
        state = "EARLY OPPORTUNITY"
    if state == "EARLY OPPORTUNITY" and score < 15:
        state = "WATCH"
        levels = None

    return _build_result(symbol, price, score, state,
                        breakdown, reasons, warnings, levels, regime_info)
