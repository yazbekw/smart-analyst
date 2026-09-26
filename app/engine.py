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
    """يحسب ATR بأمان"""
    try:
        if df is None or len(df) < length + 2:
            return None
        atr = ta.atr(df["high"], df["low"], df["close"], length=length)
        if atr is None or atr.isna().all():
            return None
        return float(atr.iloc[-1])
    except Exception:
        return None


def _atr_safe(df_1h, df_15m):
    """
    يحسب ATR ذكياً:
    - يستخدم 1H أولاً (أوسع، أقل ضجيجاً)
    - إذا لم يتوفر، يستخدم 15M مع معامل تعويضي
    """
    atr_1h = _atr(df_1h, length=14)
    if atr_1h and atr_1h > 0:
        return atr_1h, "1H"

    atr_15m = _atr(df_15m, length=14)
    if atr_15m and atr_15m > 0:
        # 15M ATR × 2 ≈ 1H ATR تقريباً
        return atr_15m * 2.0, "15M×2"

    return None, "none"


def calculate_levels(df_1h, df_15m, state):
    """
    حساب المستويات مع SL أوسع بكثير:
    
    - ATR من 1H (أوسع، أقل ضجيجاً)
    - SL = 3.5 ATR (كان 1.5)
    - TP1 = 5.0 ATR (R:R = 1.43)
    - TP2 = 8.0 ATR
    - TP3 = 12.0 ATR
    """
    try:
        price = float(df_15m["close"].iloc[-1])
        atr, atr_source = _atr_safe(df_1h, df_15m)

        if atr is None or atr == 0:
            atr = price * 0.01  # 1% احتياطي

        # حد أدنى: SL لا يقل عن 0.8% من السعر
        min_sl_distance = price * 0.008
        sl_distance = max(atr * 3.5, min_sl_distance)

        if "BUY" in state:
            entry_low = price - atr * 0.3
            entry_high = price + atr * 0.2
            sl = price - sl_distance
            tp1 = price + sl_distance * 1.43
            tp2 = price + sl_distance * 2.29
            tp3 = price + sl_distance * 3.43
        elif "SELL" in state:
            entry_low = price - atr * 0.2
            entry_high = price + atr * 0.3
            sl = price + sl_distance
            tp1 = price - sl_distance * 1.43
            tp2 = price - sl_distance * 2.29
            tp3 = price - sl_distance * 3.43
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
            "atr": round(atr, 6),
            "atr_source": atr_source,
            "sl_pct": round(sl_distance / price * 100, 3),
        }
    except Exception as e:
        print(f"[calculate_levels] {e}")
        return None


def _safe_call(fn, *args, **kwargs):
    """استدعاء آمن لدوال الإشارات"""
    try:
        r = fn(*args, **kwargs)
        if r is None or len(r) != 2:
            return 0, None
        return r
    except Exception as e:
        print(f"[signal {fn.__name__}] {e}")
        return 0, None


# ============================================================
# Main Analysis
# ============================================================
def analyze_symbol(symbol: str, df_btc=None) -> dict:
    # ===== جلب البيانات =====
    df_4h = fetch_ohlcv(symbol, "4h", limit=300)
    df_1h = fetch_ohlcv(symbol, "1h", limit=300)
    df_15m = fetch_ohlcv(symbol, "15m", limit=300)
    df_5m = fetch_ohlcv(symbol, "5m", limit=100)
    ob = fetch_orderbook(symbol)
    trades = fetch_trades(symbol, limit=200)

    price = float(df_15m["close"].iloc[-1])

    # ===== Regime Detection =====
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
    # Trend
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

    # ============================================================
    # Momentum
    # ============================================================
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

    # ============================================================
    # Volume
    # ============================================================
    s, r = _safe_call(sig_volume_ratio, df_15m)
    raw["volume"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_volume_price_agreement, df_15m)
    raw["volume"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_volume_cluster, df_15m)
    raw["volume"] += s
    if r: reasons.append(f"[15M] {r}")

    # ============================================================
    # Order Flow
    # ============================================================
    s, r = _safe_call(sig_orderbook_imbalance, ob)
    raw["orderflow"] += s
    if r: reasons.append(r)

    s, r = _safe_call(sig_taker_buy_pressure, trades)
    raw["orderflow"] += s
    if r: reasons.append(r)

    # ============================================================
    # Structure
    # ============================================================
    s, r = _safe_call(sig_broke_resistance, df_15m)
    raw["structure"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_broke_support, df_15m)
    raw["structure"] += s
    if r: reasons.append(f"[15M] {r}")

    s, r = _safe_call(sig_near_support, df_15m)
    raw["structure"] += s
    if r: reasons.append(f"[15M] {r}")

    # ============================================================
    # Patterns
    # ============================================================
    p_score, p_reasons, p_warnings = scan_patterns(df_15m)
    raw["structure"] += p_score
    reasons.extend(p_reasons)
    warnings.extend(p_warnings)

    # ============================================================
    # Candlestick Patterns
    # ============================================================
    for fn in (sig_hammer, sig_shooting_star, sig_bullish_engulfing,
               sig_bearish_engulfing, sig_pin_bar):
        s, r = _safe_call(fn, df_15m)
        raw["structure"] += s
        if r:
            if s > 0: reasons.append(r)
            else: warnings.append(r)

    # ============================================================
    # Context
    # ============================================================
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
    # States
    # ============================================================
    def _state(s):
        if s >= 25: return "STRONG BUY SETUP"
        if s >= 18: return "BUY SETUP"
        if s >= 10: return "WAIT FOR CONFIRMATION"
        if s >= 3: return "WATCH"
        if s <= -25: return "STRONG SELL SETUP"
        if s <= -18: return "SELL SETUP"
        return "NO TRADE"

    state = _state(score)

    # ============================================================
    # فلترة الـ Regime (جديد)
    # ============================================================
    block_reason = None

    if regime == "low_vol":
        block_reason = "السوق منخفض التقلب — صفقات ضعيفة"

    if adx_val > 0 and adx_val < 20:
        block_reason = f"ADX ضعيف ({adx_val}) — سوق جانبي"

    if regime == "high_vol":
        block_reason = "تقلب عالٍ — مخاطرة مرتفعة"

    # ============================================================
    # Warnings تلقائية
    # ============================================================
    if breakdown.get("orderflow", 0) <= -3:
        warnings.append(f"Order Flow سلبي ({breakdown['orderflow']})")
    if breakdown.get("volume", 0) <= -1:
        warnings.append("الحجم أقل من المتوسط — إشارة ضعيفة")
    if regime == "ranging":
        warnings.append("السوق جانبي — احذر الاختراقات الكاذبة")

    # ============================================================
    # حساب المستويات
    # ============================================================
    levels = None
    if state in ("STRONG BUY SETUP", "BUY SETUP", "STRONG SELL SETUP", "SELL SETUP"):
        if not block_reason:
            levels = calculate_levels(df_1h, df_15m, state)

            if levels:
                s, r = _safe_call(sig_rr_ratio, price,
                                  levels["stop_loss"], levels["tp1"])
                breakdown["risk"] += s
                if r:
                    if s < 0: warnings.append(r)
                    else: reasons.append(r)

                s, r = _safe_call(sig_resistance_close, df_15m)
                breakdown["risk"] += s
                if r: warnings.append(r)
        else:
            warnings.append(f"🚫 {block_reason}")
            state = "NO TRADE"

    # ============================================================
    # 5M — تحسين الدخول
    # ============================================================
    if df_5m is not None and len(df_5m) >= 5:
        try:
            macd_5m = ta.macd(df_5m["close"])
            if macd_5m is not None and not macd_5m.empty:
                dif_5m = macd_5m["MACD_12_26_9"].iloc[-1]
                dea_5m = macd_5m["MACDs_12_26_9"].iloc[-1]
                if not pd.isna(dif_5m) and not pd.isna(dea_5m):
                    if dif_5m > dea_5m and "BUY" in state:
                        reasons.append("[5M] تأكيد MACD صاعد")
                        breakdown["momentum"] += 1
                    elif dif_5m < dea_5m and "SELL" in state:
                        reasons.append("[5M] تأكيد MACD هابط")
                        breakdown["momentum"] -= 1
        except Exception:
            pass

    # ============================================================
    # إعادة حساب score
    # ============================================================
    score = sum(breakdown.values())
    state = _state(score)

    # إعادة فلترة بعد Risk
    if state in ("STRONG BUY SETUP", "BUY SETUP") and block_reason:
        state = "NO TRADE"
        levels = None
        if f"🚫 {block_reason}" not in warnings:
            warnings.append(f"🚫 {block_reason}")

    # ============================================================
    # النتيجة
    # ============================================================
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

    # ============================================================
    # حفظ Snapshot
    # ============================================================
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
                "block_reason": block_reason,
            },
        })
    except Exception as e:
        print(f"[save_snapshot {symbol}] {e}")

    return result
