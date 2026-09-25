from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import SYMBOLS, SCAN_INTERVAL_MINUTES, NOTIFY_ONLY_ON_CHANGE, MIN_NOTIFY_SCORE, BTC_REFERENCE
from app.collector import fetch_ohlcv
from app.engine import analyze_symbol
from app.notifier import notify_signal
from app.database import get_last_signal_for, save_signal

scheduler = AsyncIOScheduler()
_last_states: dict[str, tuple] = {}


async def scan_all():
    print("🔄 بدء دورة التحليل...")

    # BTC كمرجع
    try:
        df_btc = fetch_ohlcv(BTC_REFERENCE, "15m", limit=100)
    except Exception as e:
        print(f"⚠️ تعذر جلب BTC: {e}")
        df_btc = None

    for symbol in SYMBOLS:
        try:
            result = analyze_symbol(symbol, df_btc=df_btc)
            print(f"  {symbol}: {result['state']} ({result['score']})")

            # شرط الإشعار
            should_notify = False
            if abs(result["score"]) >= MIN_NOTIFY_SCORE and result["state"] != "NO TRADE":
                last = _last_states.get(symbol)
                current_key = (result["state"], result["score"])

                if not NOTIFY_ONLY_ON_CHANGE:
                    should_notify = True
                else:
                    if last != current_key:
                        should_notify = True
                _last_states[symbol] = current_key

            if should_notify:
                priority = "high" if "STRONG" in result["state"] else "default"
                await notify_signal(result, priority=priority)

                # حفظ في جدول signals
                save_signal({
                    "symbol": symbol,
                    "state": result["state"],
                    "score": result["score"],
                    "price": result["price"],
                    "entry_low": result["levels"]["entry_low"] if result.get("levels") else None,
                    "entry_high": result["levels"]["entry_high"] if result.get("levels") else None,
                    "stop_loss": result["levels"]["stop_loss"] if result.get("levels") else None,
                    "tp1": result["levels"]["tp1"] if result.get("levels") else None,
                    "tp2": result["levels"]["tp2"] if result.get("levels") else None,
                    "tp3": result["levels"]["tp3"] if result.get("levels") else None,
                    "rr": result["levels"]["rr"] if result.get("levels") else None,
                    "reasons": result["reasons"],
                    "warnings": result["warnings"],
                })
        except Exception as e:
            print(f"❌ خطأ في {symbol}: {e}")

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
