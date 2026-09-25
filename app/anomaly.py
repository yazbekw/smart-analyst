from app.collector import fetch_ohlcv, fetch_orderbook, fetch_trades
from app.database import get_client


def detect_anomalies(symbol: str, df_15m, ob: dict, trades: list, df_btc=None) -> list[dict]:
    """يكشف الأحداث الشاذة التي تستدعي إشعاراً فورياً"""
    anomalies = []

    # 1. قفزة في الحجم
    avg_vol = df_15m["volume"].rolling(20).mean().iloc[-1]
    cur_vol = df_15m["volume"].iloc[-1]
    if avg_vol and avg_vol > 0:
        ratio = cur_vol / avg_vol
        if ratio >= 3:
            anomalies.append({
                "type": "volume_spike",
                "severity": "high",
                "details": {"ratio": round(ratio, 2)},
                "message": f"⚡ قفزة في الحجم {ratio:.1f}× المتوسط",
            })
        elif ratio >= 2:
            anomalies.append({
                "type": "volume_spike",
                "severity": "medium",
                "details": {"ratio": round(ratio, 2)},
                "message": f"📊 ارتفاع الحجم {ratio:.1f}× المتوسط",
            })

    # 2. انقلاب Order Flow
    bids_vol = sum(p * a for p, a in ob["bids"][:20])
    asks_vol = sum(p * a for p, a in ob["asks"][:20])
    total = bids_vol + asks_vol
    if total > 0:
        imbalance = (bids_vol - asks_vol) / total
        if abs(imbalance) >= 0.5:
            anomalies.append({
                "type": "orderflow_extreme",
                "severity": "high",
                "details": {"imbalance": round(imbalance, 3)},
                "message": f"🔥 ضغط {'شراء' if imbalance > 0 else 'بيع'} حاد في الدفتر ({imbalance:+.2f})",
            })

    # 3. انقلاب ضغط taker
    if trades:
        buy_vol = sum(t["amount"] for t in trades if t["side"] == "buy")
        sell_vol = sum(t["amount"] for t in trades if t["side"] == "sell")
        tot = buy_vol + sell_vol
        if tot > 0:
            ratio = buy_vol / tot
            if ratio >= 0.7:
                anomalies.append({
                    "type": "taker_aggressive_buy",
                    "severity": "high",
                    "details": {"buy_ratio": round(ratio, 3)},
                    "message": f"🟢 شراء تنفيذي عنيف {ratio*100:.0f}%",
                })
            elif ratio <= 0.3:
                anomalies.append({
                    "type": "taker_aggressive_sell",
                    "severity": "high",
                    "details": {"buy_ratio": round(ratio, 3)},
                    "message": f"🔴 بيع تنفيذي عنيف {(1-ratio)*100:.0f}%",
                })

    # 4. تحرك حاد خلال 5 دقائق
    if len(df_15m) >= 2:
        last_c = df_15m["close"].iloc[-1]
        prev_c = df_15m["close"].iloc[-2]
        change = (last_c / prev_c - 1) * 100
        if abs(change) >= 1.0:
            anomalies.append({
                "type": "sharp_move",
                "severity": "high" if abs(change) >= 2 else "medium",
                "details": {"change_pct": round(change, 2)},
                "message": f"{'🚀' if change > 0 else '💥'} تحرك حاد {change:+.2f}% خلال شمعة",
            })

    # 5. صدمة BTC
    if df_btc is not None and len(df_btc) >= 2:
        last_c = df_btc["close"].iloc[-1]
        prev_c = df_btc["close"].iloc[-2]
        change = (last_c / prev_c - 1) * 100
        if abs(change) >= 0.8:
            anomalies.append({
                "type": "btc_shock",
                "severity": "high" if abs(change) >= 1.5 else "medium",
                "details": {"change_pct": round(change, 2)},
                "message": f"⚡ BTC تحرك {change:+.2f}% — تأثير على السوق",
            })

    return anomalies


def save_anomaly(symbol: str, anomaly: dict):
    get_client().table("anomalies").insert({
        "symbol": symbol,
        "type": anomaly["type"],
        "severity": anomaly["severity"],
        "details": anomaly["details"],
    }).execute()
