from datetime import datetime, timezone
from app.database import get_client
from app.config import (
    TRADE_MARGIN_USDT, TRADE_LEVERAGE, TRADE_NOTIONAL_USDT,
    ENABLE_TAKE_PROFIT, TAKE_PROFIT_USDT,
    ENABLE_STOP_LOSS, STOP_LOSS_USDT,
)


def open_paper_trade(signal_result, capital=10000, risk_pct=1.0):
    """
    ⚠️ نظام جديد:
    - Margin = $3
    - Leverage = 30x
    - Notional = $90
    - TP = +$0.50
    - SL = -$2.00
    """
    lv = signal_result.get("levels") or {}
    if not lv or not lv.get("entry_low"):
        return None

    direction = "LONG" if "BUY" in signal_result["state"] else "SHORT"
    entry = (lv["entry_low"] + lv["entry_high"]) / 2.0

    if entry <= 0:
        return None

    # حجم الصفقة من Notional
    size = TRADE_NOTIONAL_USDT / entry

    # TP/SL بالدولار
    if direction == "LONG":
        tp_price = entry + (TAKE_PROFIT_USDT / size)
        sl_price = entry - (STOP_LOSS_USDT / size)
    else:
        tp_price = entry - (TAKE_PROFIT_USDT / size)
        sl_price = entry + (STOP_LOSS_USDT / size)

    try:
        res = get_client().table("paper_trades").insert({
            "symbol": signal_result["symbol"],
            "direction": direction,
            "entry_price": entry,
            "stop_loss": sl_price,
            "tp1": tp_price,
            "tp2": tp_price * (1.02 if direction == "LONG" else 0.98),
            "tp3": tp_price * (1.03 if direction == "LONG" else 0.97),
            "size": round(size, 10),
            "risk_amount": STOP_LOSS_USDT,
            "status": "open",
            "signal_score": signal_result["score"],
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "variant": "v2",
        }).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        print(f"[paper.open] {e}")
        return None


def check_paper_trades(current_prices: dict):
    """
    فحص الصفقات بناءً على PnL بالدولار:
    - TP: عند +$0.50
    - SL: عند -$2.00
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

        entry = float(t["entry_price"])
        size = float(t["size"])
        direction = t["direction"]

        if direction == "LONG":
            unrealized_pnl = (price - entry) * size
        else:
            unrealized_pnl = (entry - price) * size

        hit = None
        exit_price = None
        r_multiple = 0

        # فحص TP
        if ENABLE_TAKE_PROFIT and unrealized_pnl >= TAKE_PROFIT_USDT:
            hit = "tp1_hit"
            exit_price = price
            r_multiple = round(unrealized_pnl / STOP_LOSS_USDT, 2)

        # فحص SL
        elif ENABLE_STOP_LOSS and unrealized_pnl <= -STOP_LOSS_USDT:
            hit = "sl_hit"
            exit_price = price
            r_multiple = round(unrealized_pnl / STOP_LOSS_USDT, 2)

        if hit:
            pnl = round(unrealized_pnl, 2)
            try:
                get_client().table("paper_trades").update({
                    "status": hit,
                    "exit_price": exit_price,
                    "pnl": pnl,
                    "r_multiple": r_multiple,
                    "closed_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", t["id"]).execute()
                closed.append({**t, "hit": hit, "pnl": pnl, "r_multiple": r_multiple})
            except Exception as e:
                print(f"[paper.update] {e}")

    return closed


def get_paper_stats(initial_capital=10000):
    try:
        closed = get_client().table("paper_trades").select("*").neq("status", "open").execute().data or []
        open_t = get_client().table("paper_trades").select("*").eq("status", "open").execute().data or []
    except Exception as e:
        print(f"[paper.stats] {e}")
        closed, open_t = [], []

    if not closed:
        return {
            "initial_capital": initial_capital, "equity": initial_capital,
            "total_pnl": 0, "total_pnl_pct": 0, "win_rate": 0,
            "total_trades": 0, "wins": 0, "losses": 0,
            "open_trades": len(open_t), "avg_win": 0, "avg_loss": 0,
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