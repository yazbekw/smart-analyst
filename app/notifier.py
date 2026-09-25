import asyncio
import httpx
from app.config import (
    NTFY_TOPIC, NTFY_SERVER, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
)


async def notify_ntfy(title, message, priority="default", tags=None):
    """إرسال إشعار عبر ntfy مع دعم UTF-8 كامل"""
    if not NTFY_TOPIC:
        return

    # ترميز الـ Title والـ Tags بأمان (إزالة الإيموجي غير المدعوم)
    safe_title = title.encode("ascii", "ignore").decode("ascii") or "Smart Analyst"
    safe_tags = []
    if tags:
        for t in tags:
            safe_tags.append(t.encode("ascii", "ignore").decode("ascii") or "info")

    headers = {
        "Title": safe_title,
        "Priority": priority,
    }
    if safe_tags:
        headers["Tags"] = ",".join(safe_tags)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{NTFY_SERVER}/{NTFY_TOPIC}",
                content=message.encode("utf-8"),  # ← UTF-8 صريح
                headers=headers,
            )
    except Exception as e:
        print(f"[ntfy] {e}")


async def notify_telegram(message):
    """إرسال إشعار عبر Telegram (يدعم UTF-8 كاملاً)"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })
    except Exception as e:
        print(f"[telegram] {e}")


def _plain(text):
    """إزالة وسوم HTML البسيطة"""
    for t in ["<b>", "</b>", "<code>", "</code>", "<i>", "</i>"]:
        text = text.replace(t, "")
    return text


def format_signal_message(result: dict) -> str:
    emoji = {
        "STRONG BUY SETUP": "🟢🔥",
        "BUY SETUP": "🟢",
        "WATCH": "🟡",
        "NO TRADE": "⚪",
        "SELL SETUP": "🔴",
        "STRONG SELL SETUP": "🔴🔥",
    }.get(result["state"], "❓")

    lines = [
        f"{emoji} <b>{result['symbol']}</b>",
        f"الحالة: <b>{result['state']}</b>",
        f"النقاط: <b>{result['score']}/100</b>",
        f"السعر: <code>{result['price']}</code>",
        "",
    ]
    if result.get("levels"):
        lv = result["levels"]
        lines += [
            f"📍 <b>الدخول:</b> {lv['entry_low']} – {lv['entry_high']}",
            f"🛑 <b>الوقف:</b> {lv['stop_loss']}",
            f"🎯 <b>TP1:</b> {lv['tp1']}",
            f"🎯 <b>TP2:</b> {lv['tp2']}",
            f"🎯 <b>TP3:</b> {lv['tp3']}",
            f"⚖️ <b>R:R</b> = {lv['rr']}",
            "",
        ]
    if result.get("reasons"):
        lines.append("📋 <b>الأسباب:</b>")
        for r in result["reasons"][:8]:
            lines.append(f"• {r}")
        lines.append("")
    if result.get("warnings"):
        lines.append("⚠️ <b>تحذيرات:</b>")
        for w in result["warnings"][:5]:
            lines.append(f"• {w}")
    return "\n".join(lines)


async def notify_signal(result, priority="default"):
    title = f"{result['state']} — {result['symbol']}"
    text = format_signal_message(result)
    tags = (
        ["chart_with_upwards_trend"] if "BUY" in result["state"]
        else ["chart_with_downwards_trend"] if "SELL" in result["state"]
        else []
    )
    await asyncio.gather(
        notify_ntfy(title, _plain(text), priority=priority, tags=tags),
        notify_telegram(text),
        return_exceptions=True,
    )


async def notify_delta(symbol, result, delta):
    if not delta.get("has_previous"):
        return
    d = delta["total_delta"]
    title = f"{delta['emoji']} تطور {symbol} ({d:+d})"
    lines = [
        f"{delta['emoji']} <b>{symbol}</b> — تطور الإشارة",
        f"النقاط: <b>{delta['prev_score']} → {result['score']}</b> ({d:+d})",
        f"السعر: <code>{result['price']}</code>",
        "",
        f"📝 {delta['message']}",
    ]
    if delta.get("notable_changes"):
        lines += ["", "🔍 <b>تغيرات ملحوظة:</b>"]
        for c in delta["notable_changes"]:
            lines.append(f"• {c}")
    if delta.get("flips"):
        lines += ["", f"⚡ <b>انقلاب:</b> {', '.join(delta['flips'])}"]
    text = "\n".join(lines)
    await asyncio.gather(
        notify_ntfy(title, _plain(text), priority="default"),
        notify_telegram(text),
        return_exceptions=True,
    )


async def notify_anomaly(symbol, anomaly, price):
    title = f"{symbol} - {anomaly['type']}"
    text = (
        f"⚡ <b>حدث مفاجئ — {symbol}</b>\n"
        f"{anomaly['message']}\n"
        f"السعر: <code>{price}</code>\n"
        f"الخطورة: {anomaly['severity']}"
    )
    priority = "urgent" if anomaly["severity"] == "high" else "high"
    await asyncio.gather(
        notify_ntfy(title, _plain(text), priority=priority, tags=["warning"]),
        notify_telegram(text),
        return_exceptions=True,
    )


async def notify_lifecycle(symbol, event, result, signal):
    labels = {
        "tp1_hit": "🎯 TP1 تحقق",
        "tp2_hit": "🎯🎯 TP2 تحقق",
        "tp3_hit": "🏆 TP3 تحقق",
        "sl_hit": "🛑 وقف الخسارة ضُرب",
        "invalidated": "❌ الإشارة أُلغيت",
    }
    title = f"{labels.get(event, event)} — {symbol}"
    lines = [
        f"<b>{labels.get(event, event)}</b>",
        f"الرمز: {symbol}",
        f"السعر الحالي: <code>{result['price']}</code>",
        f"الحالة: {result['state']} ({result['score']})",
    ]
    if event == "sl_hit":
        lines += ["", "🛑 يُنصح بمراجعة الصفقة والخروج."]
    text = "\n".join(lines)
    priority = "urgent" if event in ("sl_hit", "invalidated") else "high"
    await asyncio.gather(
        notify_ntfy(title, _plain(text), priority=priority, tags=["bell"]),
        notify_telegram(text),
        return_exceptions=True,
    )
