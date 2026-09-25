def build_correlation_context(symbols_data: dict, btc_df, lookback=15) -> dict:
    """يبني سياق الترابط بين العملات"""
    result = {"btc_change": 0, "coins": {}, "leaders": [], "laggards": []}
    if btc_df is None or len(btc_df) < lookback:
        return result
    try:
        btc_change = (btc_df["close"].iloc[-1] / btc_df["close"].iloc[-lookback] - 1) * 100
        result["btc_change"] = round(btc_change, 2)

        for sym, df in symbols_data.items():
            if df is None or len(df) < lookback:
                continue
            coin_change = (df["close"].iloc[-1] / df["close"].iloc[-lookback] - 1) * 100
            vs_btc = coin_change - btc_change
            result["coins"][sym] = {
                "change": round(coin_change, 2),
                "vs_btc": round(vs_btc, 2),
            }
            if vs_btc > 1.5:
                result["leaders"].append(sym)
            elif vs_btc < -1.5:
                result["laggards"].append(sym)
    except Exception as e:
        print(f"[correlation] {e}")
    return result
