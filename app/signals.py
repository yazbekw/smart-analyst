import pandas as pd
import pandas_ta as ta


# ============ Trend ============
def sig_price_above_ema200(df):
    ema200 = ta.ema(df["close"], length=200)
    if ema200 is None or ema200.isna().all():
        return 0, None
    if df["close"].iloc[-1] > ema200.iloc[-1]:
        return 3, "السعر فوق EMA200"
    return -3, "السعر تحت EMA200"


def sig_ema50_above_ema200(df):
    ema50 = ta.ema(df["close"], length=50)
    ema200 = ta.ema(df["close"], length=200)
    if ema50 is None or ema200 is None or ema200.isna().all():
        return 0, None
    if ema50.iloc[-1] > ema200.iloc[-1]:
        return 2, "EMA50 فوق EMA200"
    return -2, "EMA50 تحت EMA200"


def sig_ema50_slope_up(df):
    ema50 = ta.ema(df["close"], length=50)
    if ema50 is None or len(ema50.dropna()) < 5:
        return 0, None
    slope = ema50.iloc[-1] - ema50.iloc[-5]
    if slope > 0:
        return 2, "ميل EMA50 صاعد"
    return -2, "ميل EMA50 هابط"


def sig_price_above_ema20(df):
    ema20 = ta.ema(df["close"], length=20)
    if ema20 is None or ema20.isna().all():
        return 0, None
    if df["close"].iloc[-1] > ema20.iloc[-1]:
        return 1, "السعر فوق EMA20"
    return -1, "السعر تحت EMA20"


def sig_adx_strength(df):
    adx = ta.adx(df["high"], df["low"], df["close"], length=14)
    if adx is None or adx.empty:
        return 0, None
    val = adx["ADX_14"].iloc[-1]
    if pd.isna(val):
        return 0, None
    if val > 25:
        return 2, f"ADX قوي ({val:.1f})"
    if val < 15:
        return -1, f"ADX ضعيف ({val:.1f})"
    return 0, None


# ============ Momentum ============
def sig_macd_cross(df):
    macd = ta.macd(df["close"])
    if macd is None or macd.empty:
        return 0, None
    dif = macd["MACD_12_26_9"].iloc[-1]
    dea = macd["MACDs_12_26_9"].iloc[-1]
    if pd.isna(dif) or pd.isna(dea):
        return 0, None
    if dif > dea:
        return 3, "تقاطع MACD إيجابي"
    return -3, "تقاطع MACD سلبي"


def sig_rsi_zone(df):
    rsi = ta.rsi(df["close"], length=14)
    if rsi is None or rsi.isna().all():
        return 0, None
    v = rsi.iloc[-1]
    if pd.isna(v):
        return 0, None
    if 50 <= v <= 70:
        return 2, f"RSI في منطقة صاعدة ({v:.1f})"
    if v > 70:
        return -2, f"RSI تشبع شرائي ({v:.1f})"
    if v < 30:
        return 1, f"RSI تشبع بيعي ({v:.1f})"
    return 0, None


def sig_roc_positive(df):
    roc = ta.roc(df["close"], length=10)
    if roc is None or roc.isna().all():
        return 0, None
    v = roc.iloc[-1]
    if pd.isna(v):
        return 0, None
    if v > 0:
        return 1, f"ROC موجب ({v:.2f})"
    return -1, f"ROC سالب ({v:.2f})"


# ============ Volume ============
def sig_volume_ratio(df, ratio_threshold=1.5):
    avg_vol = df["volume"].rolling(20).mean().iloc[-1]
    cur_vol = df["volume"].iloc[-1]
    if pd.isna(avg_vol) or avg_vol == 0:
        return 0, None
    ratio = cur_vol / avg_vol
    if ratio >= ratio_threshold:
        return 3, f"حجم التداول {ratio:.1f}× المتوسط"
    if ratio < 0.7:
        return -1, "حجم أقل من المتوسط"
    return 0, None


def sig_volume_price_agreement(df):
    """هل السعر يتحرك مع الحجم؟"""
    last3 = df.tail(3)
    if len(last3) < 3:
        return 0, None
    price_up = last3["close"].iloc[-1] > last3["close"].iloc[0]
    vol_up = last3["volume"].iloc[-1] > last3["volume"].iloc[0]
    if price_up and vol_up:
        return 2, "السعر يرتفع مع حجم متزايد"
    if price_up and not vol_up:
        return -1, "السعر يرتفع بحجم ضعيف"
    if not price_up and vol_up:
        return -2, "السعر يهبط بحجم مرتفع"
    return 0, None


# ============ Order Flow ============
def sig_orderbook_imbalance(ob, threshold=0.2):
    bids_vol = sum(p * a for p, a in ob["bids"][:20])
    asks_vol = sum(p * a for p, a in ob["asks"][:20])
    total = bids_vol + asks_vol
    if total == 0:
        return 0, None
    imbalance = (bids_vol - asks_vol) / total
    if imbalance > threshold:
        return 2, f"ضغط شراء في دفتر الأوامر ({imbalance:+.2f})"
    if imbalance < -threshold:
        return -2, f"ضغط بيع في دفتر الأوامر ({imbalance:+.2f})"
    return 0, None


def sig_taker_buy_pressure(trades, threshold=0.55):
    if not trades:
        return 0, None
    buy_vol = sum(t["amount"] for t in trades if t["side"] == "buy")
    sell_vol = sum(t["amount"] for t in trades if t["side"] == "sell")
    total = buy_vol + sell_vol
    if total == 0:
        return 0, None
    ratio = buy_vol / total
    if ratio > threshold:
        return 2, f"ضغط شراء تنفيذي {ratio*100:.0f}%"
    if ratio < (1 - threshold):
        return -2, f"ضغط بيع تنفيذي {(1-ratio)*100:.0f}%"
    return 0, None


# ============ Structure ============
def sig_broke_resistance(df, lookback=30):
    recent_high = df["high"].tail(lookback).iloc[:-1].max()
    price = df["close"].iloc[-1]
    if pd.isna(recent_high):
        return 0, None
    if price > recent_high:
        return 4, "اختراق مقاومة حديثة"
    return 0, None


def sig_near_support(df, threshold_pct=0.01):
    recent_low = df["low"].tail(50).min()
    price = df["close"].iloc[-1]
    if pd.isna(recent_low) or price == 0:
        return 0, None
    if (price - recent_low) / price < threshold_pct:
        return 2, "السعر قريب من دعم قوي"
    return 0, None


# ============ Risk ============
def sig_rr_ratio(entry, sl, tp1):
    risk = abs(entry - sl)
    reward = abs(tp1 - entry)
    if risk == 0:
        return 0, None
    rr = reward / risk
    if rr >= 2:
        return 3, f"R:R ممتاز ({rr:.2f})"
    if rr >= 1.5:
        return 1, f"R:R مقبول ({rr:.2f})"
    return -3, f"R:R ضعيف ({rr:.2f})"


def sig_resistance_close(df, threshold_pct=0.005):
    """مقاومة قريبة جداً"""
    recent_high = df["high"].tail(30).iloc[:-1].max()
    price = df["close"].iloc[-1]
    if pd.isna(recent_high) or price == 0:
        return 0, None
    dist = (recent_high - price) / price
    if 0 < dist < threshold_pct:
        return -3, "مقاومة قريبة جداً"
    return 0, None


# ============ Context ============
def sig_btc_trend(df_btc):
    """اتجاه BTC كسياق عام"""
    ema50 = ta.ema(df_btc["close"], length=50)
    if ema50 is None or ema50.isna().all():
        return 0, None
    if df_btc["close"].iloc[-1] > ema50.iloc[-1]:
        return 3, "سياق BTC صاعد"
    return -3, "سياق BTC هابط"


def sig_relative_strength(df_coin, df_btc, lookback=15):
    """هل العملة أقوى من BTC؟"""
    if len(df_coin) < lookback or len(df_btc) < lookback:
        return 0, None
    coin_change = (df_coin["close"].iloc[-1] / df_coin["close"].iloc[-lookback] - 1) * 100
    btc_change = (df_btc["close"].iloc[-1] / df_btc["close"].iloc[-lookback] - 1) * 100
    diff = coin_change - btc_change
    if diff > 1:
        return 2, f"قوة نسبية أقوى من BTC (+{diff:.2f}%)"
    if diff < -1:
        return -2, f"قوة نسبية أضعف من BTC ({diff:.2f}%)"
    return 0, None
