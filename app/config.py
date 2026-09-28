import os
from dotenv import load_dotenv

load_dotenv()

# ===== CoinEx =====
EXCHANGE_ID = os.getenv("EXCHANGE_ID", "coinex")
SYMBOLS = [s.strip() for s in os.getenv(
    "SYMBOLS", "BTC/USDT,ETH/USDT,BNB/USDT,SOL/USDT,XRP/USDT,ADA/USDT,AVAX/USDT,DOGE/USDT"
).split(",") if s.strip()]

TIMEFRAMES = ["1d", "4h", "1h", "15m", "5m"]
OHLCV_LIMIT = 200

BTC_REFERENCE = "BTC/USDT"

# ===== Supabase =====
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ===== Notifications =====
NTFY_TOPIC = os.getenv("NTFY_TOPIC")
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ===== Scheduler =====
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))
NOTIFY_ONLY_ON_CHANGE = os.getenv("NOTIFY_ONLY_ON_CHANGE", "true").lower() == "true"
MIN_NOTIFY_SCORE = int(os.getenv("MIN_NOTIFY_SCORE", "12"))

# ===== App =====
PORT = int(os.getenv("PORT", "8000"))

# ============================================================
# 🎯 Paper Trading Parameters
# ============================================================
TRADE_MARGIN_USDT = float(os.getenv("TRADE_MARGIN_USDT", "3"))
TRADE_LEVERAGE = float(os.getenv("TRADE_LEVERAGE", "30"))
TRADE_NOTIONAL_USDT = TRADE_MARGIN_USDT * TRADE_LEVERAGE

ENABLE_TAKE_PROFIT = os.getenv("ENABLE_TAKE_PROFIT", "true").lower() == "true"
TAKE_PROFIT_USDT = float(os.getenv("TAKE_PROFIT_USDT", "0.5"))

ENABLE_STOP_LOSS = os.getenv("ENABLE_STOP_LOSS", "true").lower() == "true"
STOP_LOSS_USDT = float(os.getenv("STOP_LOSS_USDT", "2.0"))

# ===== Trade Notifications (بوت منفصل) =====
TRADE_NOTIFY_BOT_TOKEN = os.getenv("TRADE_NOTIFY_BOT_TOKEN", "")
TRADE_NOTIFY_CHAT_ID = os.getenv("TRADE_NOTIFY_CHAT_ID", "")