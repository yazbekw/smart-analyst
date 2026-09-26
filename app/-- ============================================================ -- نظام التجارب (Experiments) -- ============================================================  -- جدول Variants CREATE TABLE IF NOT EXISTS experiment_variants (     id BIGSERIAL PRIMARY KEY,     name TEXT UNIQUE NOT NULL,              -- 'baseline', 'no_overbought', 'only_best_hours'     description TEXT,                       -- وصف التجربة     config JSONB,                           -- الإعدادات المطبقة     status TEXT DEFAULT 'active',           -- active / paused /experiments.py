"""
نظام التجارب — يدير variants مختلفة من الاستراتيجية.
كل variant له إعدادات مختلفة تُخزَّن في DB.
"""
from datetime import datetime, timezone
from app.database import get_client


# ============================================================
# Variants (يمكن تعديلها من DB أو هنا)
# ============================================================
VARIANTS = {
    "baseline": {
        "description": "الإعدادات الحالية",
        "min_score": 18,
        "sl_atr": 3.5,
        "rsi_filter": False,
        "hour_filter": False,
        "no_short": False,
        "symbols": "all",
    },
    "no_overbought": {
        "description": "بدون دخول عند RSI تشبع شرائي",
        "min_score": 18,
        "sl_atr": 3.5,
        "rsi_filter": True,
        "hour_filter": False,
        "no_short": False,
        "symbols": "all",
    },
    "best_hours": {
        "description": "فقط الساعات المربحة",
        "min_score": 18,
        "sl_atr": 3.5,
        "rsi_filter": False,
        "hour_filter": True,
        "no_short": False,
        "symbols": "all",
    },
    "no_short": {
        "description": "بدون SHORT + RSI filter",
        "min_score": 18,
        "sl_atr": 3.5,
        "rsi_filter": True,
        "hour_filter": False,
        "no_short": True,
        "symbols": "all",
    },
    "strict": {
        "description": "كل الفلاتر + عتبات عالية",
        "min_score": 20,
        "sl_atr": 4.0,
        "rsi_filter": True,
        "hour_filter": True,
        "no_short": True,
        "symbols": ["SOL/USDT", "AVAX/USDT", "BNB/USDT"],
    },
}


GOOD_HOURS = {6, 8, 9, 10, 16, 23}
BAD_HOURS = {1, 3, 4, 5, 7, 11, 12, 13, 14, 18, 22}


def get_active_variants() -> list:
    """يعيد قائمة الـ variants النشطة"""
    try:
        res = (
            get_client().table("experiment_variants")
            .select("*").eq("status", "active").execute()
        )
        return res.data or []
    except Exception:
        # fallback: من VARIANTS الافتراضية
        return [{"name": k, **v} for k, v in VARIANTS.items()]


def passes_variant(result: dict, variant_config: dict, df_15m=None) -> tuple:
    """
    يفحص إن كانت الإشارة تنطبق على variant معين.
    يعيد: (ينطبق؟, السبب)
    """
    state = result.get("state", "NO TRADE")
    score = result.get("score", 0)
    symbol = result.get("symbol", "")

    # 1. النقاط الدنيا
    min_score = variant_config.get("min_score", 18)
    if abs(score) < min_score:
        return False, f"score < {min_score}"

    # 2. فلتر العملات
    symbols_filter = variant_config.get("symbols", "all")
    if symbols_filter != "all" and symbol not in symbols_filter:
        return False, f"{symbol} غير مسموح"

    # 3. منع SHORT
    if variant_config.get("no_short") and "SELL" in state:
        return False, "SHORT مُعطّل"

    # 4. فلتر الساعات
    if variant_config.get("hour_filter"):
        hour_utc = datetime.now(timezone.utc).hour
        if hour_utc in BAD_HOURS:
            return False, f"ساعة {hour_utc} UTC محظورة"
        if hour_utc not in GOOD_HOURS:
            # ساعات محايدة → نسمح لكن بحذر
            pass

    # 5. فلتر RSI (التشبع الشرائي)
    if variant_config.get("rsi_filter") and df_15m is not None:
        try:
            import pandas_ta_classic as ta
            import pandas as pd
            rsi = ta.rsi(df_15m["close"], length=14)
            if rsi is not None and not rsi.isna().all():
                rsi_val = rsi.iloc[-1]
                if not pd.isna(rsi_val) and "BUY" in state and rsi_val > 72:
                    return False, f"RSI مشبع شرائياً ({rsi_val:.1f})"
        except Exception:
            pass

    return True, None


def record_trade_variant(trade_id: int, variant: str, config: dict):
    """يسجّل variant على صفقة"""
    try:
        get_client().table("paper_trades").update({
            "variant": variant,
            "config_snapshot": config,
        }).eq("id", trade_id).execute()
    except Exception as e:
        print(f"[record_variant] {e}")


def log_experiment(variant: str, note: str, metrics: dict = None):
    """يسجّل حدث في يوميات التجارب"""
    try:
        get_client().table("experiment_log").insert({
            "variant": variant,
            "note": note,
            "metrics": metrics or {},
        }).execute()
    except Exception as e:
        print(f"[log_experiment] {e}")
