import pandas_ta as ta


def detect_regime(df_1h: "pd.DataFrame") -> dict:
    """يكتشف حالة السوق: trending / ranging / high_vol / low_vol"""
    try:
        adx = ta.adx(df_1h["high"], df_1h["low"], df_1h["close"], length=14)
        atr = ta.atr(df_1h["high"], df_1h["low"], df_1h["close"], length=14)

        adx_val = 0.0
        if adx is not None and not adx.empty and "ADX_14" in adx.columns:
            v = adx["ADX_14"].iloc[-1]
            if v == v:  # not NaN
                adx_val = float(v)

        atr_pct = 0.0
        if atr is not None and not atr.isna().all():
            price = float(df_1h["close"].iloc[-1])
            if price > 0:
                atr_pct = float(atr.iloc[-1]) / price * 100

        if atr_pct > 3.0:
            regime = "high_vol"
        elif atr_pct < 0.5:
            regime = "low_vol"
        elif adx_val > 25:
            regime = "trending"
        elif adx_val < 20:
            regime = "ranging"
        else:
            regime = "neutral"

        return {
            "regime": regime,
            "adx": round(adx_val, 1),
            "atr_pct": round(atr_pct, 2),
        }
    except Exception as e:
        print(f"[regime] {e}")
        return {"regime": "unknown", "adx": 0, "atr_pct": 0}


def regime_multipliers(regime: str) -> dict:
    """مضاعفات الأوزان حسب حالة السوق"""
    return {
        "trending":  {"trend": 1.3, "momentum": 1.3, "volume": 1.1,
                      "orderflow": 1.0, "structure": 1.0, "context": 1.0},
        "ranging":   {"trend": 0.6, "momentum": 0.6, "volume": 1.0,
                      "orderflow": 1.1, "structure": 1.3, "context": 1.0},
        "high_vol":  {"trend": 0.8, "momentum": 0.9, "volume": 1.0,
                      "orderflow": 0.9, "structure": 1.0, "context": 0.9},
        "low_vol":   {"trend": 0.9, "momentum": 0.8, "volume": 1.1,
                      "orderflow": 1.0, "structure": 1.2, "context": 1.0},
    }.get(regime, {"trend": 1, "momentum": 1, "volume": 1,
                   "orderflow": 1, "structure": 1, "context": 1})


REGIME_LABELS = {
    "trending":  ("📈", "TRENDING", "السوق في اتجاه واضح — نعزز الزخم"),
    "ranging":   ("↔️", "RANGING", "السوق جانبي — نعزز الدعم/المقاومة"),
    "high_vol":  ("🔥", "HIGH VOLATILITY", "تقلب عالٍ — نخفف الثقة"),
    "low_vol":   ("😴", "LOW VOLATILITY", "تقلب منخفض — نبحث عن اختراق"),
    "neutral":   ("⚖️", "NEUTRAL", "حالة محايدة"),
    "unknown":   ("❓", "UNKNOWN", "لا يمكن تحديد الحالة"),
}
