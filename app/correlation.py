SECTORS = {
    "L1":       ["BTC/USDT", "ETH/USDT", "SOL/USDT", "ADA/USDT", "AVAX/USDT", "BNB/USDT"],
    "DeFi":     ["UNI/USDT", "AAVE/USDT", "LINK/USDT", "MATIC/USDT"],
    "Meme":     ["DOGE/USDT", "SHIB/USDT", "PEPE/USDT"],
    "Payments": ["XRP/USDT", "XLM/USDT", "LTC/USDT"],
    "AI":       ["FET/USDT", "RNDR/USDT", "AGIX/USDT"],
    "Gaming":   ["SAND/USDT", "MANA/USDT", "AXS/USDT"],
}


def get_sector(symbol: str) -> str:
    """يعيد القطاع الذي تنتمي إليه العملة"""
    for sector, coins in SECTORS.items():
        if symbol in coins:
            return sector
    return "Other"


def build_correlation_context(symbols_data: dict, btc_df, lookback=15) -> dict:
    """يبني سياق الترابط + تحليل القطاعات"""
    result = {
        "btc_change": 0, "coins": {}, "leaders": [], "laggards": [],
        "sectors": {},
    }
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
            sector = get_sector(sym)

            result["coins"][sym] = {
                "change": round(coin_change, 2),
                "vs_btc": round(vs_btc, 2),
                "sector": sector,
            }

            if vs_btc > 1.5:
                result["leaders"].append(sym)
            elif vs_btc < -1.5:
                result["laggards"].append(sym)

        # ===== تحليل القطاعات (جديد) =====
        for sym, data in result["coins"].items():
            sector = data["sector"]
            if sector not in result["sectors"]:
                result["sectors"][sector] = {
                    "coins": [],
                    "avg_change": 0,
                    "avg_vs_btc": 0,
                }
            result["sectors"][sector]["coins"].append(sym)

        for sector, data in result["sectors"].items():
            coins = data["coins"]
            if coins:
                changes = [result["coins"][c]["change"] for c in coins]
                vs_btcs = [result["coins"][c]["vs_btc"] for c in coins]
                data["avg_change"] = round(sum(changes) / len(changes), 2)
                data["avg_vs_btc"] = round(sum(vs_btcs) / len(vs_btcs), 2)

    except Exception as e:
        print(f"[correlation] {e}")
    return result


def get_sector_strength(correlation_context: dict, symbol: str) -> tuple:
    """
    يعيد قوة قطاع العملة المحددة.
    Returns: (sector, avg_vs_btc, momentum_label)
    """
    try:
        sector = get_sector(symbol)
        sectors = correlation_context.get("sectors", {})
        if sector not in sectors:
            return sector, 0, "unknown"
        data = sectors[sector]
        vs_btc = data.get("avg_vs_btc", 0)
        if vs_btc > 1.0:
            label = "قوي"
        elif vs_btc < -1.0:
            label = "ضعيف"
        else:
            label = "متوسط"
        return sector, vs_btc, label
    except Exception:
        return "Other", 0, "unknown"
