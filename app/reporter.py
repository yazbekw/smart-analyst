from datetime import datetime
from app.collector import fetch_ohlcv
from app.config import BTC_REFERENCE


def _trend_emoji(state: str) -> str:
    if "STRONG BUY" in state: return "🟢🔥"
    if "BUY" in state: return "🟢"
    if "WATCH" in state: return "🟡"
    if "STRONG SELL" in state: return "🔴🔥"
    if "SELL" in state: return "🔴"
    return "⚪"


def _trend_label(df, lookback=10) -> str:
    """يحدد اتجاه إطار زمني معين"""
    try:
        if df is None or len(df) < lookback:
            return "⚪ غير محدد"
        first = df["close"].iloc[-lookback]
        last = df["close"].iloc[-1]
        change = (last / first - 1) * 100
        if change > 0.5: return "🟢 صاعد"
        if change < -0.5: return "🔴 هابط"
        return "🟡 جانبي"
    except Exception:
        return "⚪ غير محدد"


def _fmt_num(n):
    """تنسيق الأرقام"""
    try:
        n = float(n)
        if n >= 1000:
            return f"{n:,.2f}"
        if n >= 1:
            return f"{n:.4f}"
        return f"{n:.6f}"
    except Exception:
        return str(n)


def build_full_report(result: dict, delta: dict | None = None) -> str:
    """
    يبني تقريراً كاملاً بالعربية من نتيجة التحليل.
    """
    symbol = result["symbol"]
    state = result["state"]
    score = result["score"]
    price = result["price"]
    bd = result.get("breakdown", {})
    reasons = result.get("reasons", [])
    warnings = result.get("warnings", [])
    levels = result.get("levels") or {}

    # جلب الأطر الزمنية
    try:
        df_1d = fetch_ohlcv(symbol, "1d", limit=20)
        df_4h = fetch_ohlcv(symbol, "4h", limit=20)
        df_1h = fetch_ohlcv(symbol, "1h", limit=20)
        df_15m = fetch_ohlcv(symbol, "15m", limit=20)
    except Exception:
        df_1d = df_4h = df_1h = df_15m = None

    # التغير على 24 ساعة
    try:
        change_24h = (df_1h["close"].iloc[-1] / df_1h["close"].iloc[-24] - 1) * 100 if df_1h is not None else 0
    except Exception:
        change_24h = 0

    now = datetime.now().strftime("%Y-%m-%d — %H:%M")

    lines = []
    lines.append("🧠 <b>SMART MARKET ANALYST</b>")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊 تقرير السوق — {now}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    # العنوان الرئيسي
    emoji = _trend_emoji(state)
    lines.append(f"{emoji} <b>{symbol}</b> — {state}")
    lines.append("")
    lines.append(f"السعر: <b>{_fmt_num(price)}</b>")
    lines.append(f"التغير 24س: <b>{change_24h:+.2f}%</b>")
    lines.append("")

    # الاتجاهات
    lines.append("📈 <b>الاتجاه (متعدد الأطر):</b>")
    lines.append(f"  1D  {_trend_label(df_1d)}")
    lines.append(f"  4H  {_trend_label(df_4h)}")
    lines.append(f"  1H  {_trend_label(df_1h)}")
    lines.append(f"  15M {_trend_label(df_15m)}")
    lines.append("")

    # مكونات النقاط
    lines.append("⚡ <b>تفصيل النقاط:</b>")
    lines.append(f"  Trend:      {bd.get('trend', 0):+d}")
    lines.append(f"  Momentum:   {bd.get('momentum', 0):+d}")
    lines.append(f"  Volume:     {bd.get('volume', 0):+d}")
    lines.append(f"  Order Flow: {bd.get('orderflow', 0):+d}")
    lines.append(f"  Structure:  {bd.get('structure', 0):+d}")
    lines.append(f"  Context:    {bd.get('context', 0):+d}")
    lines.append(f"  Risk:       {bd.get('risk', 0):+d}")
    lines.append(f"  ───────────────")
    lines.append(f"  <b>المجموع: {score}/100</b>")
    lines.append("")

    # الأسباب
    if reasons:
        lines.append("📋 <b>الأسباب:</b>")
        for r in reasons[:10]:
            lines.append(f"  • {r}")
        lines.append("")

    # خطة التداول
    if levels:
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🎯 <b>خطة التداول:</b>")
        lines.append("")
        lines.append(f"  📍 الدخول:  {_fmt_num(levels.get('entry_low'))} – {_fmt_num(levels.get('entry_high'))}")
        lines.append(f"  🛑 الوقف:   {_fmt_num(levels.get('stop_loss'))}")
        lines.append(f"  🎯 TP1:     {_fmt_num(levels.get('tp1'))}")
        lines.append(f"  🎯 TP2:     {_fmt_num(levels.get('tp2'))}")
        lines.append(f"  🎯 TP3:     {_fmt_num(levels.get('tp3'))}")
        lines.append(f"  ⚖️ R:R:     1 : {levels.get('rr', '—')}")
        lines.append("")

    # التطور (إن وجد)
    if delta and delta.get("has_previous"):
        d = delta["total_delta"]
        arrow = "📈" if d > 0 else "📉" if d < 0 else "➖"
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"{arrow} <b>التطور منذ آخر تقرير:</b>")
        lines.append(f"  النقاط: {delta['prev_score']} → {score} ({d:+d})")
        if delta.get("notable_changes"):
            for c in delta["notable_changes"]:
                lines.append(f"  • {c}")
        if delta.get("flips"):
            lines.append(f"  ⚡ انقلاب: {', '.join(delta['flips'])}")
        lines.append("")

    # التحذيرات
    if warnings:
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("⚠️ <b>مخاطر:</b>")
        for w in warnings[:5]:
            lines.append(f"  • {w}")
        lines.append("")

    # الإجراء
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    if "BUY" in state:
        lines.append("📌 <b>الإجراء:</b> انتظر تأكيد الإغلاق فوق منطقة الدخول قبل التنفيذ")
    elif "SELL" in state:
        lines.append("📌 <b>الإجراء:</b> انتظر تأكيد الإغلاق تحت منطقة الدخول")
    elif state == "WATCH":
        lines.append("📌 <b>الإجراء:</b> مراقبة — لا تدخل حتى تتضح الإشارة")
    else:
        lines.append("📌 <b>الإجراء:</b> لا تداول — انتظر إشارة أوضح")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)
