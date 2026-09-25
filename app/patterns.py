def detect_breakout_retest(df, lookback=30):
    """اختراق + إعادة اختبار ناجحة"""
    if len(df) < lookback + 5:
        return 0, None
    try:
        recent_high = df["high"].tail(lookback).iloc[:-5].max()
        current = df["close"].iloc[-1]
        if current > recent_high * 0.998:
            last5 = df.tail(5)
            touched = last5["low"].min() <= recent_high * 1.002
            bounced = df["close"].iloc[-1] > recent_high
            if touched and bounced:
                return 6, "اختراق + إعادة اختبار ناجحة"
    except Exception:
        pass
    return 0, None


def detect_fake_breakout(df, lookback=30):
    """اختراق كاذب — إشارة سلبية قوية"""
    if len(df) < lookback + 3:
        return 0, None
    try:
        recent_high = df["high"].tail(lookback).iloc[:-3].max()
        last3 = df.tail(3)
        broke = (last3["high"] > recent_high).any()
        returned = df["close"].iloc[-1] < recent_high * 0.998
        if broke and returned:
            return -5, "⚠️ اختراق كاذب — تجنب الشراء"
    except Exception:
        pass
    return 0, None


def detect_pullback(df, lookback=20):
    """تصحيح صحي داخل اتجاه صاعد"""
    if len(df) < lookback:
        return 0, None
    try:
        segment = df.tail(lookback).reset_index(drop=True)
        peak_idx = segment["high"].idxmax()
        if peak_idx >= len(segment) - 2:
            return 0, None
        peak = segment["high"].max()
        after_peak = segment.iloc[peak_idx:]
        pullback_low = after_peak["low"].min()
        current = df["close"].iloc[-1]
        if pullback_low < peak * 0.99 and current > pullback_low * 1.01 and current < peak:
            return 5, "تصحيح صحي + ارتداد — فرصة دخول"
    except Exception:
        pass
    return 0, None


def detect_higher_highs_lows(df, lookback=20):
    """قمم وقيعان صاعدة/هابطة"""
    if len(df) < lookback:
        return 0, None
    try:
        segment = df.tail(lookback)
        half = lookback // 2
        first_high = segment["high"].iloc[:half].max()
        second_high = segment["high"].iloc[half:].max()
        first_low = segment["low"].iloc[:half].min()
        second_low = segment["low"].iloc[half:].min()
        if second_high > first_high and second_low > first_low:
            return 4, "قمم وقيعان صاعدة (اتجاه مؤكد)"
        if second_high < first_high and second_low < first_low:
            return -4, "قمم وقيعان هابطة"
    except Exception:
        pass
    return 0, None


def detect_consolidation(df, lookback=20):
    """تجميع (compression) قبل اختراق"""
    if len(df) < lookback:
        return 0, None
    try:
        segment = df.tail(lookback)
        high = segment["high"].max()
        low = segment["low"].min()
        if low == 0:
            return 0, None
        range_pct = (high - low) / low * 100
        if range_pct < 2.5:
            return 3, f"تجميع ضيق ({range_pct:.1f}%) — احتمال اختراق"
    except Exception:
        pass
    return 0, None


ALL_PATTERNS = [
    detect_breakout_retest,
    detect_fake_breakout,
    detect_pullback,
    detect_higher_highs_lows,
    detect_consolidation,
]


def scan_patterns(df_15m):
    """يشغّل كل الكاشفات ويعيد مجموع النقاط + الأسباب"""
    total = 0
    reasons = []
    warnings = []
    for fn in ALL_PATTERNS:
        try:
            s, r = fn(df_15m)
            if s and r:
                total += s
                if s > 0:
                    reasons.append(f"[Pattern] {r}")
                else:
                    warnings.append(r)
        except Exception as e:
            print(f"[pattern {fn.__name__}] {e}")
    return total, reasons, warnings
