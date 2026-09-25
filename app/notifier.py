import asyncio
import httpx
from app.config import (
    NTFY_TOPIC, NTFY_SERVER,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
)


async def notify_ntfy(title: str, message: str, priority: str = "default", tags: list | None = None):
    if not NTFY_TOPIC:
        return
    headers = {"Title": title, "Priority": priority}
    if tags:
        headers["Tags"] = ",".join(tags)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{NTFY_SERVER}/{NTFY_TOPIC}",
                content=message.encode("utf-8"),
                headers=headers,
            )
    except Exception as e:
        print(f"[ntfy] error: {e}")


async def notify_telegram(message: str):
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
        print(f"[telegram] error: {e}")


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


async def notify_signal(result: dict, priority: str = "default"):
    title = f"{result['state']} — {result['symbol']}"
    text = format_signal_message(result)

    # ntfy (يستخدم نص عادي، نزيل HTML)
    plain = text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "")

    tags = []
    if "BUY" in result["state"]: tags = ["chart_with_upwards_trend"]
    elif "SELL" in result["state"]: tags = ["chart_with_downwards_trend"]

    await asyncio.gather(
        notify_ntfy(title, plain, priority=priority, tags=tags),
        notify_telegram(text),
        return_exceptions=True,
    )
