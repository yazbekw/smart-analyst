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
from app.paper import open_paper_trade, check_paper_trades
from app.correlation import build_correlation_context
from app.experiments import get_active_variants, passes_variant

scheduler = AsyncIOScheduler()
_last_states: dict[str, tuple] = {}


async def scan_all():
    print("🔄 بدء دورة التحليل...")

    # ============================================================
    # 1. جلب Variants النشطة
    # ============================================================
    variants = get_active_variants()
    print(f"📊 Variants نشطة: {len(variants)}")
    for v in variants:
        print(f"     • {v.get('name')} — {v.get('description', '')}")

    # ============================================================
    # 2. جلب بيانات BTC كمرجع
    # ============================================================
    try:
        df_btc = fetch_ohlcv(BTC_REFERENCE, "15m", limit=100)
    except Exception as e:
        print(f"⚠️ تعذر جلب BTC: {e}")
        df_btc = None

    # ============================================================
    # 3. جلب الإشارات النشطة
    # ============================================================
    try:
        active = {s["symbol"]: s for s in get_active_signals()}
    except Exception as e:
        print(f"⚠️ تعذر جلب active signals: {e}")
        active = {}

    # ============================================================
    # 4. فحص الصفقات الورقية (Paper Trading)
    # ============================================================
    current_prices = {}
    try:
        for sym in SYMBOLS:
            try:
                df_tmp = fetch_ohlcv(sym, "15m", limit=2)
                if df_tmp is not None and len(df_tmp) > 0:
                    current_prices[sym] = float(df_tmp["close"].iloc[-1])
            except Exception:
                pass

        closed_paper = check_paper_trades(current_prices)
        for ct in closed_paper:
            pnl = ct.get("pnl", 0) or 0
            variant_tag = ct.get("variant", "?")
            print(f"    💰 [{variant_tag}] paper closed: {ct['symbol']} {ct['hit']} PnL={pnl:.2f}")
    except Exception as e:
        print(f"⚠️ paper check: {e}")

    # ============================================================
    # 5. بناء سياق الترابط
    # ============================================================
    symbols_data = {}
    try:
        for sym in SYMBOLS:
            try:
                symbols_data[sym] = fetch_ohlcv(sym, "15m", limit=50)
            except Exception:
                symbols_data[sym] = None

        correlation_context = build_correlation_context(symbols_data, df_btc)
    except Exception as e:
        print(f"⚠️ correlation: {e}")
        correlation_context = {}

    # ============================================================
    # 6. حلقة التحليل الرئيسية
    # ============================================================
    for symbol in SYMBOLS:
        try:
            # ---------- التحليل الأساسي ----------
            result = analyze_symbol(symbol, df_btc=df_btc)

            # إضافة سياق الترابط
            result["correlation"] = correlation_context

            regime_name = (result.get("regime") or {}).get("regime", "?")
            print(f"  {symbol}: {result['state']} ({result['score']}) [{regime_name}]")

            # ---------- حساب Delta ----------
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

            # ---------- كشف الشواذ ----------
            try:
                ob = fetch_orderbook(symbol)
                trades = fetch_trades(symbol, limit=200)
                df_15m_anom = fetch_ohlcv(symbol, "15m", limit=100)

                for a in detect_anomalies(symbol, df_15m_anom, ob, trades, df_btc):
                    if recently_alerted(symbol, a["type"], minutes=30):
                        continue

                    save_anomaly(symbol, a)
                    await notify_anomaly(symbol, a, result["price"])
                    print(f"    ⚡ anomaly: {symbol} {a['type']} ({a['severity']})")
            except Exception as e:
                print(f"  anomaly {symbol}: {e}")

            # ============================================================
            # 7. نظام التجارب (A/B Testing) — يشمل WAIT FOR CONFIRMATION
            # ============================================================
            if result["state"] not in ("NO TRADE", "WATCH"):
                try:
                    df_15m_filter = fetch_ohlcv(symbol, "15m", limit=100)
                except Exception:
                    df_15m_filter = None

                variants_opened = 0
                variants_skipped = 0

                for variant in variants:
                    variant_name = variant.get("name", "baseline")
                    # config قد يكون dict أو JSON من DB
                    config = variant.get("config") or variant

                    try:
                        allowed, reason = passes_variant(result, config, df_15m_filter)
                    except Exception as e:
                        print(f"    ❌ [{variant_name}] passes_variant error: {e}")
                        continue

                    if allowed:
                        try:
                            paper = open_paper_trade(result, variant=variant_name)
                            if paper:
                                entry = paper.get("entry_price", 0)
                                print(f"    💰 [{variant_name}] paper opened @ {entry:.4f}")
                                variants_opened += 1
                            else:
                                print(f"    ⚠️ [{variant_name}] open_paper_trade عاد None")
                        except Exception as e:
                            print(f"    ❌ [{variant_name}] paper error: {e}")
                    else:
                        print(f"    ⏭️ [{variant_name}] تجاهل: {reason}")
                        variants_skipped += 1

                if variants_opened > 0:
                    print(f"    📊 فُتحت {variants_opened} صفقة (تجاهل {variants_skipped})")

            # ============================================================
            # 8. إدارة دورة حياة الإشارة (baseline فقط)
            # ============================================================
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
