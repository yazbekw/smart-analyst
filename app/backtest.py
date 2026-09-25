import pandas_ta_classic as ta
from app.signals import *


def _score_row(df_slice, df_btc_slice=None):
    """يشغّل المؤشرات على نافذة معينة ويعيد النقاط"""
    if len(df_slice) < 50:
        return 0
    score = 0
    checks = [
        (sig_price_above_ema200, 3), (sig_ema50_above_ema200, 2),
        (sig_ema50_slope_up, 2), (sig_price_above_ema20, 1),
        (sig_macd_cross, 3), (sig_rsi_zone, 2),
        (sig_roc_positive, 1), (sig_volume_ratio, 3),
        (sig_volume_price_agreement, 2),
    ]
    for fn, _ in checks:
        try:
            s, _r = fn(df_slice)
            score += s
        except Exception:
            pass
    return score


def backtest_symbol(symbol: str, df, lookback=200, forward=20, threshold=8):
    """
    Backtest مبسّط:
    - يشغّل المؤشرات على كل شمعة تاريخية
    - يفتح صفقة عند score >= threshold
    - يتابع forward شمعة لمعرفة TP/SL
    
    يعيد dict بإحصائيات.
    """
    trades = []
    if df is None or len(df) < lookback + forward + 20:
        return {"error": "بيانات غير كافية", "trades": [], "stats": {}}

    for i in range(lookback, len(df) - forward):
        window = df.iloc[:i]
        score = _score_row(window)
        if score < threshold:
            continue

        entry = float(df["close"].iloc[i])
        # ATR للتوقف
        atr_series = ta.atr(df["high"], df["low"], df["close"], length=14)
        if atr_series is None or atr_series.iloc[i] != atr_series.iloc[i]:
            continue
        atr = float(atr_series.iloc[i])
        sl = entry - atr * 1.5
        tp1 = entry + atr * 1.5
        tp2 = entry + atr * 3.0

        # محاكاة forward
        future = df.iloc[i + 1:i + 1 + forward]
        outcome = None
        exit_price = None
        for _, row in future.iterrows():
            if row["low"] <= sl:
                outcome, exit_price = "sl_hit", sl
                break
            if row["high"] >= tp2:
                outcome, exit_price = "tp2_hit", tp2
                break
            if row["high"] >= tp1:
                outcome, exit_price = "tp1_hit", tp1
                break
        if outcome is None:
            outcome = "expired"
            exit_price = float(future["close"].iloc[-1])

        pnl_pct = (exit_price - entry) / entry * 100
        trades.append({
            "entry": entry, "exit": exit_price,
            "outcome": outcome, "pnl_pct": round(pnl_pct, 2),
            "score": score,
        })

    if not trades:
        return {"trades": [], "stats": {"total": 0}}

    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    total_ret = sum(t["pnl_pct"] for t in trades)

    stats = {
        "total": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "avg_return": round(total_ret / len(trades), 2),
        "total_return": round(total_ret, 2),
        "avg_win": round(sum(t["pnl_pct"] for t in wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0,
        "tp1_hits": len([t for t in trades if t["outcome"] == "tp1_hit"]),
        "tp2_hits": len([t for t in trades if t["outcome"] == "tp2_hit"]),
        "sl_hits": len([t for t in trades if t["outcome"] == "sl_hit"]),
        "expired": len([t for t in trades if t["outcome"] == "expired"]),
    }
    return {"trades": trades[-50:], "stats": stats}
