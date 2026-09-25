# Smart Market Analyst

محلل سوق آلي يجمع الأدلة من عدة مؤشرات ويعطي قراراً مشروحاً مع درجة ثقة.

## 🚀 النشر على Render

### 1. إعداد Supabase
نفذ SQL التالي في SQL Editor:

```sql
CREATE TABLE ohlcv (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp BIGINT NOT NULL,
    open NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC, volume NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, timeframe, timestamp)
);
CREATE INDEX idx_ohlcv_symbol_tf ON ohlcv(symbol, timeframe, timestamp DESC);

CREATE TABLE snapshots (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    price NUMERIC,
    trend_score INT, momentum_score INT, volume_score INT,
    orderflow_score INT, structure_score INT, context_score INT, risk_score INT,
    total_score INT,
    state TEXT,
    details JSONB
);
CREATE INDEX idx_snapshots_ts ON snapshots(timestamp DESC);

CREATE TABLE signals (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    state TEXT,
    score INT,
    price NUMERIC,
    entry_low NUMERIC, entry_high NUMERIC,
    stop_loss NUMERIC,
    tp1 NUMERIC, tp2 NUMERIC, tp3 NUMERIC,
    rr NUMERIC,
    reasons JSONB, warnings JSONB,
    outcome TEXT DEFAULT 'pending'
);
```

### 2. إعداد ntfy
- حمّل تطبيق **ntfy** على هاتفك
- اختر topic فريد، مثال: `smart-analyst-ahmad-2024`
- ضعه في `NTFY_TOPIC`

### 3. إعداد Telegram (اختياري)
- أنشئ bot عبر `@BotFather` → احصل على token
- أرسل رسالة للـ bot ثم افتح:
  `https://api.telegram.org/bot<TOKEN>/getUpdates`
- استخرج `chat.id`

### 4. النشر
- ارفع المشروع إلى GitHub
- Render → New → Web Service
- اختر `render.yaml` أو أدخل الإعدادات يدوياً
- أضف المتغيرات السرية

## 📡 واجهات API
- `GET /` — لوحة المراقبة
- `GET /api/snapshots` — آخر تحليل لكل عملة
- `GET /api/signals` — الإشارات الأخيرة
- `POST /api/scan` — تشغيل دورة فحص يدوياً
- `POST /api/analyze/{symbol}` — تحليل رمز محدد

## ⚠️ ملاحظة Render Free
النسخة المجانية تنام بعد 15 دقيقة من عدم الاستخدام. للاستمرارية 24/7:
- استخدم **UptimeRobot** لضرب `/api/status` كل 5 دقائق، أو
- ارتقِ إلى خطة مدفوعة ($7/شهر)
