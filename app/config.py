import os
from dotenv import load_dotenv

load_dotenv()

# CoinEx
EXCHANGE_ID = os.getenv("EXCHANGE_ID", "coinex")
SYMBOLS = [s.strip() for s in os.getenv(
    "SYMBOLS", "BTC/USDT,ETH/USDT,BNB/USDT,SOL/USDT"
).split(",") if s.strip()]

TIMEFRAMES = ["1d", "4h", "1h", "15m", "5m"]
OHLCV_LIMIT = 200

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Notifications
NTFY_TOPIC = os.getenv("NTFY_TOPIC")
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Scheduler
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))
NOTIFY_ONLY_ON_CHANGE = os.getenv("NOTIFY_ONLY_ON_CHANGE", "true").lower() == "true"
MIN_NOTIFY_SCORE = int(os.getenv("MIN_NOTIFY_SCORE", "8"))

# App
PORT = int(os.getenv("PORT", "8000"))
