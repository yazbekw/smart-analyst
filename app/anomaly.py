from datetime import datetime, timedelta, timezone
from app.database import get_client


def detect_anomalies(symbol, df_15m, ob, trades, df_btc=None):
    """
    كاشف الأحداث الشاذة — النسخة المحسّنة النهائية.
    
    التحسينات:
    - taker: نافذة أطول (100 صفقة) + عتبات أعلى (85%/15%) + تأكيد سعري + تأكيد حجم
    - orderflow: |imb| >= 0.7 + حجم كافٍ
    - volume_spike: 4x/6x
    - sharp_move: 1.5%/2.5%
    - btc_shock: 1.5%/2.0%
    """
    anomalies = []

    # ============================================================
    # 1. قفزة في الحجم
    # ============================================================
    try:
        avg_vol = df_15m["volume"].rolling(20).mean().iloc[-1]
        cur_vol = df_15m["volume"].iloc[-1]
        if avg_vol and avg_vol > 0 and cur_vol == cur_vol:
            ratio = cur_vol / avg_vol
            if ratio >= 6.0:
                anomalies.append({
                    "type": "volume_spike",
                    "severity": "high",
                    "details": {"ratio": round(ratio, 2)},
                    "message": f"⚡ قفزة حادة في الحجم {ratio:.1f}× المتوسط",
                })
            elif ratio >= 4.0:
                anomalies.append({
                    "type": "volume_spike",
                    "severity": "medium",
                    "details": {"ratio": round(ratio, 2)},
                    "message": f"📊 ارتفاع ملحوظ في الحجم {ratio:.1f}× المتوسط",
                })
    except Exception as e:
        print(f"[anomaly.volume] {e}")

    # ============================================================
    # 2. انقلاب حاد في Order Flow (دفتر الأوامر)
    # ============================================================
    try:
        bids_vol = sum(p * a for p, a in ob["bids"][:20])
        asks_vol = sum(p * a for p, a in ob["asks"][:20])
        total = bids_vol + asks_vol
        if total > 0:
            imb = (bids_vol - asks_vol) / total
            if abs(imb) >= 0.70:
                anomalies.append({
                    "type": "orderflow_extreme",
                    "severity": "high",
                    "details": {"imbalance": round(imb, 3), "total_vol": round(total, 2)},
                    "message": f"🔥 ضغط {'شراء' if imb > 0 else 'بيع'} حاد في الدفتر ({imb:+.2f})",
                })
    except Exception as e:
        print(f"[anomaly.orderflow] {e}")

    # ============================================================
    # 3. ضغط Taker عنيف (محسّن — مع تأكيد سعري وحجم)
    # ============================================================
    try:
        if trades and len(trades) >= 100:
            buy_vol = sum(t["amount"] for t in trades if t["side"] == "buy")
            sell_vol = sum(t["amount"] for t in trades if t["side"] == "sell")
            tot = buy_vol + sell_vol

            if tot > 0:
                ratio = buy_vol / tot

                # تأكيد سعري
                price_change = 0
                if len(df_15m) >= 2:
                    prev_c = df_15m["close"].iloc[-2]
                    last_c = df_15m["close"].iloc[-1]
                    if prev_c > 0:
                        price_change = (last_c / prev_c - 1) * 100

                # تأكيد حجم
                avg_vol = df_15m["volume"].rolling(20).mean().iloc[-1]
                cur_vol = df_15m["volume"].iloc[-1]
                vol_ratio = (cur_vol / avg_vol) if (avg_vol and avg_vol > 0) else 0

                # شراء عنيف: 85%+ شراء + السعر يرتفع + حجم مرتفع
                if ratio >= 0.85 and price_change > 0.2 and vol_ratio > 1.5:
                    anomalies.append({
                        "type": "taker_aggressive_buy",
                        "severity": "high",
                        "details": {
                            "buy_ratio": round(ratio, 3),
                            "price_change": round(price_change, 2),
                            "vol_ratio": round(vol_ratio, 2),
                            "trades_count": len(trades),
                        },
                        "message": f"🟢 شراء تنفيذي عنيف {ratio*100:.0f}% (السعر +{price_change:.2f}%)",
                    })

                # بيع عنيف: 15%- شراء + السعر يهبط + حجم مرتفع
                elif ratio <= 0.15 and price_change < -0.2 and vol_ratio > 1.5:
                    anomalies.append({
                        "type": "taker_aggressive_sell",
                        "severity": "high",
                        "details": {
                            "buy_ratio": round(ratio, 3),
                            "price_change": round(price_change, 2),
                            "vol_ratio": round(vol_ratio, 2),
                            "trades_count": len(trades),
                        },
                        "message": f"🔴 بيع تنفيذي عنيف {(1-ratio)*100:.0f}% (السعر {price_change:.2f}%)",
                    })
    except Exception as e:
        print(f"[anomaly.taker] {e}")

    # ============================================================
    # 4. تحرك حاد
    # ============================================================
    try:
        if len(df_15m) >= 2:
            last_c = df_15m["close"].iloc[-1]
            prev_c = df_15m["close"].iloc[-2]
            if prev_c > 0:
                change = (last_c / prev_c - 1) * 100
                if abs(change) >= 2.5:
                    anomalies.append({
                        "type": "sharp_move",
                        "severity": "high",
                        "details": {"change_pct": round(change, 2)},
                        "message": f"{'🚀' if change > 0 else '💥'} تحرك حاد {change:+.2f}%",
                    })
                elif abs(change) >= 1.5:
                    anomalies.append({
                        "type": "sharp_move",
                        "severity": "medium",
                        "details": {"change_pct": round(change, 2)},
                        "message": f"{'📈' if change > 0 else '📉'} تحرك ملحوظ {change:+.2f}%",
                    })
    except Exception as e:
        print(f"[anomaly.sharp] {e}")

    # ============================================================
    # 5. صدمة BTC
    # ============================================================
    try:
        if df_btc is not None and len(df_btc) >= 2:
            last_c = df_btc["close"].iloc[-1]
            prev_c = df_btc["close"].iloc[-2]
            if prev_c > 0:
                change = (last_c / prev_c - 1) * 100
                if abs(change) >= 2.0:
                    anomalies.append({
                        "type": "btc_shock",
                        "severity": "high",
                        "details": {"change_pct": round(change, 2)},
                        "message": f"⚡ BTC تحرك {change:+.2f}% — تأثير على السوق",
                    })
                elif abs(change) >= 1.5:
                    anomalies.append({
                        "type": "btc_shock",
                        "severity": "medium",
                        "details": {"change_pct": round(change, 2)},
                        "message": f"📊 BTC تحرك {change:+.2f}%",
                    })
    except Exception as e:
        print(f"[anomaly.btc] {e}")

    return anomalies


def save_anomaly(symbol, anomaly):
    """يحفظ anomaly في قاعدة البيانات"""
    try:
        get_client().table("anomalies").insert({
            "symbol": symbol,
            "type": anomaly["type"],
            "severity": anomaly["severity"],
            "details": anomaly["details"],
        }).execute()
    except Exception as e:
        print(f"[save_anomaly] {e}")


def recently_alerted(symbol: str, anomaly_type: str, minutes: int = 30) -> bool:
    """يتحقق إن كان نفس النوع أُرسل خلال آخر X دقيقة"""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    try:
        res = (
            get_client().table("anomalies")
            .select("id")
            .eq("symbol", symbol)
            .eq("type", anomaly_type)
            .gte("created_at", cutoff)
            .limit(1)
            .execute()
        )
        return len(res.data or []) > 0
    except Exception as e:
        print(f"[recently_alerted] {e}")
        return False
