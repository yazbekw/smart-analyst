from datetime import datetime, timezone
from app.database import get_client


def open_paper_trade(signal_result, capital=10000, risk_pct=1.0, variant="baseline"):
    """يفتح صفقة ورقية مع R-Multiple"""
    lv = signal_result.get("levels") or {}
    if not lv or not lv.get("entry_low"):
        return None

    direction = "LONG" if "BUY" in signal_result["state"] else "SHORT"
    entry = (lv["entry_low"] + lv["entry_high"]) / 2.0

    risk_per_unit = abs(entry - lv["stop_loss"])
    if risk_per_unit == 0:
        return None

    risk_amount = capital * (risk_pct / 100.0)
    size = risk_amount / risk_per_unit

    try:
        res = get_client().table("paper_trades").insert({
            "symbol": signal_result["symbol"],
            "direction": direction,
            "entry_price": entry,
            "stop_loss": lv["stop_loss"],
            "tp1": lv["tp1"],
            "tp2": lv["tp2"],
            "tp3": lv["tp3"],
            "size": round(size, 8),
            "risk_amount": round(risk_amount, 2),
            "status": "open",
            "signal_score": signal_result["score"],
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "variant": variant,  # ← جديد
            "config_snapshot": {
                "min_score": signal_result.get("score"),
                "regime": (signal_result.get("regime") or {}).get("regime"),
            },
        }).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        print(f"[paper.open] {e}")
        return None


def check_paper_trades(current_prices: dict):
    """
    فحص الصفقات مع R-Multiple صحيح:
    - TP1 = +2.0R
    - TP2 = +3.5R
    - TP3 = +5.5R
    - SL  = -1.0R
    """
    try:
        res = get_client().table("paper_trades").select("*").eq("status", "open").execute()
        trades = res.data or []
    except Exception as e:
        print(f"[paper.check] {e}")
        return []

    closed = []
    for t in trades:
        price = current_prices.get(t["symbol"])
        if not price:
            continue

        hit = None
        exit_price = None
        r_multiple = 0

        if t["direction"] == "LONG":
            if price <= t["stop_loss"]:
                hit, exit_price, r_multiple = "sl_hit", t["stop_loss"], -1.0
            elif price >= t["tp3"]:
                hit, exit_price, r_multiple = "tp3_hit", t["tp3"], 5.5
            elif price >= t["tp2"]:
                hit, exit_price, r_multiple = "tp2_hit", t["tp2"], 3.5
            elif price >= t["tp1"]:
                hit, exit_price, r_multiple = "tp1_hit", t["tp1"], 2.0
        else:
            if price >= t["stop_loss"]:
                hit, exit_price, r_multiple = "sl_hit", t["stop_loss"], -1.0
            elif price <= t["tp3"]:
                hit, exit_price, r_multiple = "tp3_hit", t["tp3"], 5.5
            elif price <= t["tp2"]:
                hit, exit_price, r_multiple = "tp2_hit", t["tp2"], 3.5
            elif price <= t["tp1"]:
                hit, exit_price, r_multiple = "tp1_hit", t["tp1"], 2.0

        if hit:
            risk_amount = t.get("risk_amount") or 100
            pnl = risk_amount * r_multiple

            try:
                get_client().table("paper_trades").update({
                    "status": hit,
                    "exit_price": exit_price,
                    "pnl": round(pnl, 2),
                    "r_multiple": r_multiple,
                    "closed_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", t["id"]).execute()
                closed.append({**t, "hit": hit, "pnl": pnl, "r_multiple": r_multiple})
            except Exception as e:
                print(f"[paper.update] {e}")

    return closed


def get_paper_stats(initial_capital=10000):
    """إحصائيات Paper Trading"""
    try:
        closed = get_client().table("paper_trades").select("*").neq("status", "open").execute().data or []
        open_t = get_client().table("paper_trades").select("*").eq("status", "open").execute().data or []
    except Exception as e:
        print(f"[paper.stats] {e}")
        closed, open_t = [], []

    if not closed:
        return {
            "initial_capital": initial_capital,
            "equity": initial_capital,
            "total_pnl": 0,
            "total_pnl_pct": 0,
            "win_rate": 0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "open_trades": len(open_t),
            "avg_win": 0,
            "avg_loss": 0,
            "profit_factor": 0,
        }

    wins = [t for t in closed if (t.get("pnl") or 0) > 0]
    losses = [t for t in closed if (t.get("pnl") or 0) <= 0]
    total_pnl = sum(t.get("pnl") or 0 for t in closed)
    gross_win = sum(t.get("pnl") or 0 for t in wins)
    gross_loss = abs(sum(t.get("pnl") or 0 for t in losses))

    return {
        "initial_capital": initial_capital,
        "equity": round(initial_capital + total_pnl, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl / initial_capital * 100, 2),
        "win_rate": round(len(wins) / len(closed) * 100, 1),
        "total_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "open_trades": len(open_t),
        "avg_win": round(gross_win / len(wins), 2) if wins else 0,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else 0,
    }
