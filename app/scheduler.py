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
from app.anomaly import detect_anomalies, save_anomaly, recently_alerted
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

    # جلب الإشارات النشطة مرة واحدة قبل الحلقة
    try:
        active = {s["symbol"]: s for s in get_active_signals()}
    except Exception as e:
        print(f"⚠️ تعذر جلب active signals: {e}")
        active = {}

    for symbol in SYMBOLS:
        try:
            # ==================================================
            # 1. التحليل الأساسي
            # ==================================================
            result = analyze_symbol(symbol, df_btc=df_btc)
            print(f"  {symbol}: {result['state']} ({result['score']})")

            # ==================================================
            # 2. حساب Delta (مقارنة مع اللقطة السابقة)
            # ==================================================
            prev = get_previous_snapshot(symbol)
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

            # ==================================================
            # 3. كشف الشواذ (مع منع التكرار)
            # ==================================================
            try:
                ob = fetch_orderbook(symbol)
                trades = fetch_trades(symbol, limit=200)
                df_15m = fetch_ohlcv(symbol, "15m", limit=100)

                for a in detect_anomalies(symbol, df_15m, ob, trades, df_btc):
                    # تجاهل التكرار خلال آخر 30 دقيقة (نفس العملة + نفس النوع)
                    if recently_alerted(symbol, a["type"], minutes=30):
                        continue

                    save_anomaly(symbol, a)
                    await notify_anomaly(symbol, a, result["price"])
                    print(f"    ⚡ anomaly: {symbol} {a['type']} ({a['severity']})")
            except Exception as e:
                print(f"  anomaly {symbol}: {e}")

            # ==================================================
            # 4. إدارة دورة حياة الإشارة
            # ==================================================
            active_sig = active.get(symbol)

            if active_sig:
                # هل وصل TP/SL؟
                hit = check_tp_sl(active_sig["id"], active_sig, result["price"])
                if hit:
                    await notify_lifecycle(symbol, hit, result, active_sig)
                    close_signal(active_sig["id"], hit, symbol, result["price"], hit)
                    del active[symbol]
                    print(f"    🎯 signal closed: {symbol} ({hit})")
                else:
                    # هل انقلبت الإشارة؟
                    new_dir = "LONG" if "BUY" in result["state"] else "SHORT"
                    if new_dir != active_sig["direction"] and abs(result["score"]) >= 8:
                        invalidate_signal(
                            active_sig["id"],
                            symbol,
                            result["price"],
                            f"انقلاب من {active_sig['direction']} إلى {new_dir}",
                        )
                        await notify_lifecycle(symbol, "invalidated", result, active_sig)
                        del active[symbol]
                        print(f"    ❌ signal invalidated: {symbol}")
                    else:
                        # تحديث الإشارة
                        update_signal(active_sig["id"], result, delta)
                        if delta.get("has_previous") and abs(delta["total_delta"]) >= 3:
                            await notify_delta(symbol, result, delta)
                            print(f"    📊 signal updated: {symbol} (Δ{delta['total_delta']:+d})")
            else:
                # لا توجد إشارة نشطة — هل نفتح واحدة؟
                if abs(result["score"]) >= MIN_NOTIFY_SCORE and result["state"] != "NO TRADE":
                    should_open = True

                    if NOTIFY_ONLY_ON_CHANGE:
                        last = _last_states.get(symbol)
                        if last == (result["state"], result["score"]):
                            should_open = False

                    if should_open:
                        open_signal(result)
                        priority = "high" if "STRONG" in result["state"] else "default"
                        await notify_full_analysis(result, delta=delta, priority=priority)
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
                        print(f"    🆕 signal opened: {symbol} ({result['state']})")

            # تحديث الحالة الأخيرة
            _last_states[symbol] = (result["state"], result["score"])

        except Exception as e:
            print(f"❌ خطأ في {symbol}: {e}")
            import traceback
            traceback.print_exc()

    print("✅ انتهت الدورة")


def start_scheduler():
    scheduler.add_job(
        scan_all,
        "interval",
        minutes=SCAN_INTERVAL_MINUTES,
        id="scan_all",
        replace_existing=True,
    )
    scheduler.start()
    print(f"⏱️ Scheduler يعمل كل {SCAN_INTERVAL_MINUTES} دقيقة")
