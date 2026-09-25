from app.database import get_client


def get_previous_snapshot(symbol: str) -> dict | None:
    res = (
        get_client()
        .table("snapshots")
        .select("*")
        .eq("symbol", symbol)
        .order("timestamp", desc=True)
        .limit(2)
        .execute()
    )
    rows = res.data or []
    return rows[1] if len(rows) > 1 else None


def compute_delta(prev: dict, curr: dict) -> dict:
    """يحسب الفرق بين snapshot قديم وحديث"""
    if not prev:
        return {"has_previous": False}

    fields = [
        "trend_score", "momentum_score", "volume_score",
        "orderflow_score", "structure_score", "context_score", "risk_score",
        "total_score",
    ]
    deltas = {}
    for f in fields:
        old = prev.get(f, 0) or 0
        new = curr.get(f, 0) or 0
        deltas[f] = new - old

    # تصنيف التغير
    total_delta = deltas["total_score"]

    if total_delta >= 5:
        direction = "strengthened"
        emoji = "🚀"
        msg = f"الإشارة تقوّت بشكل ملحوظ (+{total_delta})"
    elif total_delta >= 2:
        direction = "improved"
        emoji = "📈"
        msg = f"تحسن طفيف (+{total_delta})"
    elif total_delta <= -5:
        direction = "weakened_strong"
        emoji = "⚠️"
        msg = f"ضعف حاد في الإشارة ({total_delta})"
    elif total_delta <= -2:
        direction = "weakened"
        emoji = "📉"
        msg = f"ضعف طفيف ({total_delta})"
    else:
        direction = "stable"
        emoji = "➖"
        msg = "لا تغير ملحوظ"

    # كشف المكونات المتغيرة بشكل كبير
    notable_changes = []
    for k, v in deltas.items():
        if k == "total_score" or v == 0:
            continue
        if abs(v) >= 3:
            label = k.replace("_score", "")
            sign = "+" if v > 0 else ""
            notable_changes.append(f"{label}: {sign}{v}")

    # كشف انقلاب الإشارة (من موجب إلى سالب أو العكس)
    flips = []
    for k in ["trend_score", "momentum_score", "orderflow_score", "structure_score"]:
        old = prev.get(k, 0) or 0
        new = curr.get(k, 0) or 0
        if (old > 0 and new < 0) or (old < 0 and new > 0):
            flips.append(k.replace("_score", ""))

    return {
        "has_previous": True,
        "deltas": deltas,
        "total_delta": total_delta,
        "direction": direction,
        "emoji": emoji,
        "message": msg,
        "notable_changes": notable_changes,
        "flips": flips,
        "prev_state": prev.get("state"),
        "prev_score": prev.get("total_score"),
        "prev_timestamp": prev.get("timestamp"),
    }
