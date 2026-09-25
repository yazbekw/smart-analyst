from datetime import datetime, timezone
from app.database import get_client
from app.collector import fetch_ohlcv


def get_active_signals() -> list[dict]:
    res = (
        get_client()
        .table("active_signals")
        .select("*")
        .eq("status", "active")
        .execute()
    )
    return res.data or []


def open_signal(result: dict) -> int:
    """يفتح إشارة جديدة ويسجل حدث opened"""
    lv = result.get("levels") or {}
    direction = "LONG" if "BUY" in result["state"] else "SHORT"
    res = get_client().table("active_signals").insert({
        "symbol": result["symbol"],
        "direction": direction,
        "state": result["state"],
        "initial_score": result["score"],
        "current_score": result["score"],
        "entry_low": lv.get("entry_low"),
        "entry_high": lv.get("entry_high"),
        "stop_loss": lv.get("stop_loss"),
        "tp1": lv.get("tp1"),
        "tp2": lv.get("tp2"),
        "tp3": lv.get("tp3"),
        "rr": lv.get("rr"),
        "price_at_signal": result["price"],
        "last_reasons": result["reasons"],
        "last_warnings": result["warnings"],
    }).execute()
    sid = res.data[0]["id"]
    log_event(sid, result["symbol"], "opened", None, result["score"],
              None, result["state"], result["price"], "إشارة جديدة")
    return sid


def update_signal(sid: int, result: dict, delta: dict | None):
    """يحدّث الإشارة النشطة ويسجل التطور"""
    old = get_client().table("active_signals").select("*").eq("id", sid).single().execute().data
    old_score = old["current_score"]
    old_state = old["state"]

    get_client().table("active_signals").update({
        "state": result["state"],
        "current_score": result["score"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_reasons": result["reasons"],
        "last_warnings": result["warnings"],
    }).eq("id", sid).execute()

    # تحديد نوع الحدث
    event_type = "stable"
    if delta and delta.get("has_previous"):
        d = delta["total_delta"]
        if d >= 5: event_type = "strengthened"
        elif d <= -5: event_type = "weakened"

    log_event(sid, result["symbol"], event_type, old_score, result["score"],
              old_state, result["state"], result["price"], None)


def check_tp_sl(sid: int, signal: dict, current_price: float) -> str | None:
    """يتحقق إن كان السعر وصل TP أو SL"""
    direction = signal["direction"]

    if direction == "LONG":
        if signal.get("stop_loss") and current_price <= signal["stop_loss"]:
            return "sl_hit"
        if signal.get("tp3") and current_price >= signal["tp3"]:
            return "tp3_hit"
        if signal.get("tp2") and current_price >= signal["tp2"]:
            return "tp2_hit"
        if signal.get("tp1") and current_price >= signal["tp1"]:
            return "tp1_hit"
    else:
        if signal.get("stop_loss") and current_price >= signal["stop_loss"]:
            return "sl_hit"
        if signal.get("tp3") and current_price <= signal["tp3"]:
            return "tp3_hit"
        if signal.get("tp2") and current_price <= signal["tp2"]:
            return "tp2_hit"
        if signal.get("tp1") and current_price <= signal["tp1"]:
            return "tp1_hit"
    return None


def close_signal(sid: int, status: str, symbol: str, price: float, note: str):
    get_client().table("active_signals").update({
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", sid).execute()
    log_event(sid, symbol, status, None, None, None, None, price, note)


def invalidate_signal(sid: int, symbol: str, price: float, reason: str):
    close_signal(sid, "invalidated", symbol, price, reason)


def log_event(sid, symbol, event_type, old_score, new_score, old_state, new_state, price, note):
    get_client().table("signal_events").insert({
        "signal_id": sid,
        "symbol": symbol,
        "event_type": event_type,
        "old_score": old_score,
        "new_score": new_score,
        "old_state": old_state,
        "new_state": new_state,
        "price": price,
        "note": note,
    }).execute()
