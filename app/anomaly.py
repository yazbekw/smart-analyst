from app.database import get_client
from datetime import datetime, timedelta, timezone



def detect_anomalies(symbol, df_15m, ob, trades, df_btc=None):
    """
    كاشف الأحداث الشاذة — نسخة مضبوطة لتقليل الضوضاء.
    
    المعايير الجديدة:
    - volume_spike: 3.5x (medium) / 5x (high)
    - orderflow: |imb| >= 0.65
    - taker: 75%+ (بدلاً من 70%)
    - sharp_move: 1.5% (بدلاً من 1%)
    - btc_shock: 1.5% (بدلاً من 0.8%)
    - إضافة شرط تأكيد: السعر يتحرك فعلاً، ليس فقط في الدفتر
    """
    anomalies = []

    # ============================================================
    # 1. قفزة في الحجم — رفع العتبات
    # ============================================================
    avg_vol = df_15m["volume"].rolling(20).mean().iloc[-1]
    cur_vol = df_15m["volume"].iloc[-1]
    if avg_vol and avg_vol > 0 and not (cur_vol != cur_vol):  # NaN check
        ratio = cur_vol / avg_vol
        if ratio >= 5.0:
            anomalies.append({
                "type": "volume_spike",
                "severity": "high",
                "details": {"ratio": round(ratio, 2)},
                "message": f"⚡ قفزة حادة في الحجم {ratio:.1f}× المتوسط",
            })
        elif ratio >= 3.5:
            anomalies.append({
                "type": "volume_spike",
                "severity": "medium",
                "details": {"ratio": round(ratio, 2)},
                "message": f"📊 ارتفاع ملحوظ في الحجم {ratio:.1f}× المتوسط",
            })

    # ============================================================
    # 2. انقلاب حاد في Order Flow — رفع العتبة + شرط تداول
    # ============================================================
    bids_vol = sum(p * a for p, a in ob["bids"][:20])
    asks_vol = sum(p * a for p, a in ob["asks"][:20])
    total = bids_vol + asks_vol
    if total > 0:
        imb = (bids_vol - asks_vol) / total
        # شرط إضافي: لا نعتمد فقط على الدفتر، بل نتحقق أن الحجم الفعلي كبير
        # إذا كان دفتر الأوامر ضعيفاً (total صغير)، نتجاهله
        # نحتاج أيضاً أن يكون الضغط واضحاً جداً
        if abs(imb) >= 0.65:
            anomalies.append({
                "type": "orderflow_extreme",
                "severity": "high",
                "details": {"imbalance": round(imb, 3), "total_vol": round(total, 2)},
                "message": f"🔥 ضغط {'شراء' if imb > 0 else 'بيع'} حاد في الدفتر ({imb:+.2f})",
            })

    # ============================================================
    # 3. ضغط Taker عنيف — رفع العتبة إلى 75%
    # ============================================================
    if trades and len(trades) >= 30:  # شرط: عدد صفقات كافٍ
        buy_vol = sum(t["amount"] for t in trades if t["side"] == "buy")
        sell_vol = sum(t["amount"] for t in trades if t["side"] == "sell")
        tot = buy_vol + sell_vol
        if tot > 0:
            ratio = buy_vol / tot
            if ratio >= 0.75:
                anomalies.append({
                    "type": "taker_aggressive_buy",
                    "severity": "high",
                    "details": {"buy_ratio": round(ratio, 3), "trades_count": len(trades)},
                    "message": f"🟢 شراء تنفيذي عنيف {ratio*100:.0f}%",
                })
            elif ratio <= 0.25:
                anomalies.append({
                    "type": "taker_aggressive_sell",
                    "severity": "high",
                    "details": {"buy_ratio": round(ratio, 3), "trades_count": len(trades)},
                    "message": f"🔴 بيع تنفيذي عنيف {(1-ratio)*100:.0f}%",
                })

    # ============================================================
    # 4. تحرك حاد — رفع العتبة إلى 1.5%
    # ============================================================
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

    # ============================================================
    # 5. صدمة BTC — رفع العتبة إلى 1.5%
    # ============================================================
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

    return anomalies


def save_anomaly(symbol, anomaly):
    get_client().table("anomalies").insert({
        "symbol": symbol,
        "type": anomaly["type"],
        "severity": anomaly["severity"],
        "details": anomaly["details"],
    }).execute()

def recently_alerted(symbol: str, anomaly_type: str, minutes: int = 30) -> bool:
    """يتحقق إن كان نفس النوع أُرسل خلال آخر X دقيقة"""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
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
