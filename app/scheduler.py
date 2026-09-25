from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import (
    SYMBOLS, SCAN_INTERVAL_MINUTES, NOTIFY_ONLY_ON_CHANGE,
    MIN_NOTIFY_SCORE, BTC_REFERENCE,
)
from app.collector import fetch_ohlcv, fetch_orderbook, fetch_trades
from app.engine import analyze_symbol
from app.notifier import (
    notify_full_analysis,
    notify_anomaly,
    notify_lifecycle,
    notify_signal,
    notify_delta,
)
from app.database import save_signal
from app.delta import get_previous_snapshot, compute_delta
from app.anomaly import detect_anomalies, save_anomaly
from app.lifecycle import (
    get_active_signals, open_signal, update_signal,
    check_tp_sl, close_signal, invalidate_signal,
)

scheduler = AsyncIOScheduler()
_last_states: dict[str, tuple] = {}


async def scan_all():
    print("🔄 بدء دورة التحليل...")

    try:
        df_btc = fetch_ohlcv(BTC_REFERENCE, "15m", limit=100)
    except Exception as e:
        print(f"⚠️ تعذر جلب BTC: {e}")
        df_btc = None

    active = {s["symbol"]: s for s in get_active_signals()}

    for symbol in SYMBOLS:
        try:
            result = analyze_symbol(symbol, df_btc=df_btc)
            print(f"  {symbol}: {result['state']} ({result['score']})")

            # 1) Delta
            prev = get_last_snapshot(symbol)
            curr_snap = {
                "trend_score": result["breakdown"]["trend"],
                "momentum_score": result["breakdown"]["momentum"],
                "volume_score": result["breakdown"]["volume"],
                "orderflow_score": result["breakdown"]["orderflow"],
                "structure_score": result["breakdown"]["structure"],
                "context_score": result["breakdown"]["context"],
                "risk_score": result["breakdown"]["risk"],
                "total_score": result["score"],
                "state": result["state"],
            }
            delta = compute_delta(prev, curr_snap)

            # 2) Anomalies
            ob = None
            trades = None
            try:
                from app.collector import fetch_orderbook, fetch_trades
                ob = fetch_orderbook(symbol)
                trades = fetch_trades(symbol, limit=200)
                df_15m = fetch_ohlcv(symbol, "15m", limit=100)
                anomalies = detect_anomalies(symbol, df_15m, ob, trades, df_btc)
                for a in anomalies:
                    save_anomaly(symbol, a)
                    await notify_anomaly(symbol, a, result["price"])
            except Exception as e:
                print(f"  anomaly error {symbol}: {e}")

            # 3) Signal Lifecycle
            active_sig = active.get(symbol)
            if active_sig:
                # فحص TP/SL
                hit = check_tp_sl(active_sig["id"], active_sig, result["price"])
                if hit:
                    await notify_lifecycle(symbol, hit, result, active_sig)
                    close_signal(active_sig["id"], hit, symbol, result["price"], hit)
                    del active[symbol]
                else:
                    # فحص الانقلاب (هل انقلبت الإشارة؟)
                    new_dir = "LONG" if "BUY" in result["state"] else "SHORT"
                    if new_dir != active_sig["direction"] and abs(result["score"]) >= 8:
                        invalidate_signal(
                            active_sig["id"], symbol, result["price"],
                            f"انقلاب الاتجاه من {active_sig['direction']} إلى {new_dir}"
                        )
                        await notify_lifecycle(symbol, "invalidated", result, active_sig)
                        del active[symbol]
                    else:
                        # تحديث الإشارة
                        update_signal(active_sig["id"], result, delta)
                        if delta["has_previous"] and abs(delta["total_delta"]) >= 3:
                            await notify_delta(symbol, result, delta)
                        active_sig["current_score"] = result["score"]
            else:
                # لا توجد إشارة نشطة — هل نفتح واحدة؟
                if abs(result["score"]) >= MIN_NOTIFY_SCORE and result["state"] != "NO TRADE":
                    should_open = True
                    if NOTIFY_ONLY_ON_CHANGE:
                        last = _last_states.get(symbol)
                        if last == (result["state"], result["score"]):
                            should_open = False
                    if should_open:
                        sid = open_signal(result)
                        await notify_signal(result, priority="high" if "STRONG" in result["state"] else "default")
                        save_signal({
                            "symbol": symbol,
                            "state": result["state"],
                            "score": result["score"],
                            "price": result["price"],
                            "entry_low": (result.get("levels") or {}).get("entry_low"),
                            "entry_high": (result.get("levels") or {}).get("entry_high"),
                            "stop_loss": (result.get("levels") or {}).get("stop_loss"),
                            "tp1": (result.get("levels") or {}).get("tp1"),
                            "tp2": (result.get("levels") or {}).get("tp2"),
                            "tp3": (result.get("levels") or {}).get("tp3"),
                            "rr": (result.get("levels") or {}).get("rr"),
                            "reasons": result["reasons"],
                            "warnings": result["warnings"],
                        })

            _last_states[symbol] = (result["state"], result["score"])

        except Exception as e:
            print(f"❌ خطأ في {symbol}: {e}")
            import traceback
            traceback.print_exc()

    print("✅ انتهت الدورة")


def start_scheduler():
    scheduler.add_job(
        scan_all, "interval",
        minutes=SCAN_INTERVAL_MINUTES,
        id="scan_all", replace_existing=True,
    )
    scheduler.start()
    print(f"⏱️ Scheduler يعمل كل {SCAN_INTERVAL_MINUTES} دقيقة")
