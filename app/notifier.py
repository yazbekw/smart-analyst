import asyncio
import httpx
from datetime import datetime, timezone

from app.config import (
    NTFY_TOPIC, NTFY_SERVER, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    TRADE_NOTIFY_BOT_TOKEN, TRADE_NOTIFY_CHAT_ID,
    TRADE_MARGIN_USDT, TRADE_LEVERAGE,
    TAKE_PROFIT_USDT, STOP_LOSS_USDT,
)
from app.reporter import build_full_report


async def notify_ntfy(title, message, priority="default", tags=None):
    if not NTFY_TOPIC:
        return

    safe_title = title.encode("ascii", "ignore").decode("ascii") or "Smart Analyst"
    safe_tags = []
    if tags:
        for t in tags:
            safe_tags.append(t.encode("ascii", "ignore").decode("ascii") or "info")

    headers = {"Title": safe_title, "Priority": priority}
    if safe_tags:
        headers["Tags"] = ",".join(safe_tags)

    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    content=message.encode("utf-8"),
                    headers=headers,
                )
                if response.status_code < 400:
                    print(f"[ntfy] ✅ أُرسل (محاولة {attempt + 1})")
                    return
                else:
                    print(f"[ntfy] ⚠️ HTTP {response.status_code}")
        except Exception as e:
            print(f"[ntfy] ❌ محاولة {attempt + 1}: {type(e).__name__}: {e}")
            if attempt < 2:
                await asyncio.sleep(3)

    print(f"[ntfy] ❌ فشلت جميع المحاولات")


async def notify_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    chunks = [message[i:i+3800] for i in range(0, len(message), 3800)]
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for chunk in chunks:
                await client.post(url, json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                })
    except Exception as e:
        print(f"[telegram] {e}")


async def notify_trade_event(event_type: str, trade: dict):
    """
    إشعار فتح/إغلاق صفقة عبر بوت منفصل.
    event_type: "opened" أو "closed"
    """
    if not TRADE_NOTIFY_BOT_TOKEN or not TRADE_NOTIFY_CHAT_ID:
        return

    symbol = trade.get("symbol", "?")
    direction = trade.get("direction", "?")
    entry = trade.get("entry_price", 0)
    size = trade.get("size", 0)

    if event_type == "opened":
        emoji = "🟢" if direction == "LONG" else "🔴"
        notional = float(entry) * float(size)
        lines = [
            f"{emoji} <b>صفقة جديدة فُتحت</b>",
            "━━━━━━━━━━━━━━━━━━━",
            f"📌 {symbol} — <b>{direction}</b>",
            f"💰 الدخول: <code>{entry}</code>",
            f"📊 الحجم: <code>{float(size):.8f}</code>",
            f"💵 Margin: ${TRADE_MARGIN_USDT}",
            f"⚙️ Leverage: {TRADE_LEVERAGE}x",
            f"💼 Notional: ${notional:.2f}",
            "",
            f"🎯 TP: +${TAKE_PROFIT_USDT}",
            f"🛑 SL: -${STOP_LOSS_USDT}",
            "",
            f"📊 Score: {trade.get('signal_score', '?')}",
            f"🕐 {datetime.now(timezone.utc).strftime('%H:%M')} UTC",
        ]
    else:
        status = trade.get("hit", "closed")
        pnl = trade.get("pnl", 0)
        emoji = "🎯" if pnl > 0 else "🛑"
        lines = [
            f"{emoji} <b>صفقة أُغلقت — {status}</b>",
            "━━━━━━━━━━━━━━━━━━━",
            f"📌 {symbol} — {direction}",
            f"💰 الدخول: <code>{entry}</code>",
            f"💵 الخروج: <code>{trade.get('exit_price', 0)}</code>",
            f"📊 PnL: <b>{'+' if pnl > 0 else ''}${pnl:.2f}</b>",
            "",
            f"🕐 {datetime.now(timezone.utc).strftime('%H:%M')} UTC",
        ]

    text = "\n".join(lines)
    url = f"https://api.telegram.org/bot{TRADE_NOTIFY_BOT_TOKEN}/sendMessage"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(url, json={
                "chat_id": TRADE_NOTIFY_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })
    except Exception as e:
        print(f"[notify_trade] {e}")


def _plain(text):
    for t in ["<b>", "</b>", "<code>", "</code>", "<i>", "</i>"]:
        text = text.replace(t, "")
    return text


async def notify_full_analysis(result: dict, delta: dict | None = None,
                                priority: str = "default"):
    title = f"{result['state']} — {result['symbol']}"
    text = build_full_report(result, delta=delta)

    tags = []
    if "BUY" in result["state"]:
        tags = ["chart_with_upwards_trend"]
    elif "SELL" in result["state"]:
        tags = ["chart_with_downwards_trend"]

    await asyncio.gather(
        notify_ntfy(title, _plain(text), priority=priority, tags=tags),
        notify_telegram(text),
        return_exceptions=True,
    )


async def notify_signal(result, priority="default"):
    await notify_full_analysis(result, delta=None, priority=priority)


async def notify_delta(symbol, result, delta):
    if not delta.get("has_previous"):
        return
    await notify_full_analysis(result, delta=delta, priority="default")


async def notify_anomaly(symbol, anomaly, price):
    title = f"{symbol} - {anomaly['type']}"
    text = (
        f"⚡ <b>حدث مفاجئ — {symbol}</b>\n\n"
        f"{anomaly['message']}\n\n"
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
        "",
        f"الرمز: {symbol}",
        f"السعر الحالي: <code>{result['price']}</code>",
        f"الحالة: {result['state']} ({result['score']})",
    ]
    if event == "sl_hit":
        lines += ["", "🛑 يُنصح بمراجعة الصفقة والخروج."]
    if event in ("tp1_hit", "tp2_hit", "tp3_hit"):
        lines += ["", "✅ يمكن تحريك الوقف إلى نقطة التعادل."]

    text = "\n".join(lines)
    priority = "urgent" if event in ("sl_hit", "invalidated") else "high"
    await asyncio.gather(
        notify_ntfy(title, _plain(text), priority=priority, tags=["bell"]),
        notify_telegram(text),
        return_exceptions=True,
    )