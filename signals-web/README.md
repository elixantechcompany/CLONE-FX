# XAUUSD / BTCUSD Multi-Timeframe Signal Interface

A 3-timeframe (**30M / 1H / 4H**) confluence scanning system for **XAUUSD (Gold)** and **BTCUSD (Bitcoin)**. Deployed to **Vercel** with a **Supabase** backend, a **5-minute GitHub Actions clock**, and instant **Telegram alerts**.

Strictly **manual execution**: designed to protect prop firm challenges and funded accounts by filtering for **fewer, higher-conviction setups** instead of noisy overtrading.

---

## 🏗️ System Architecture

```
GitHub Actions (every 5 min cron)
      │
      ▼
POST /api/scan (Vercel Next.js Function)
      │
      ├─ Fetch 4H, 1H, 30M candles (XAUUSD & BTCUSD)
      ├─ Run 3-Timeframe Confluence Engine:
      │    • 4H Macro Bias: 20/50 EMA slope + Swing structure (HH/HL vs LH/LL)
      │    • 1H Setup: Pullback to prior structure level, liquidity sweep, or S/D zone
      │    • 30M Trigger: Rejection pin-bar (wick >= 25%) or momentum breakout
      │
      ▼
If 3/3 or 2/3 Confirmed -> Write to Supabase `signals` table
      │
      ├─ Telegram Bot sends instant Markdown alert
      │
      ▼
You review alert -> Execute manually on Exness / MT5
      │
      ▼
Next.js Dashboard shows Live Setups + History Log (Mark Hit-TP / Hit-SL)
```

---

## 🚀 Quick Setup Guide

### 1. Database Setup (Supabase)
1. Go to [Supabase](https://supabase.com) and create a free project.
2. In your Supabase dashboard, click **SQL Editor** on the left menu.
3. Open [`signals-web/supabase/schema.sql`](./supabase/schema.sql), copy its contents, paste into the SQL editor, and click **Run**.
4. In **Project Settings** &rarr; **API**, copy:
   - Project URL (`NEXT_PUBLIC_SUPABASE_URL`)
   - `anon` public key (`NEXT_PUBLIC_SUPABASE_ANON_KEY`)
   - `service_role` secret key (`SUPABASE_SERVICE_ROLE_KEY`)

### 2. Telegram Bot Setup (Free)
1. Message `@BotFather` on Telegram and send `/newbot` to create a bot. Copy the API Token (`TELEGRAM_BOT_TOKEN`).
2. Start a chat with your new bot or add it to a private channel.
3. Get your Chat ID by messaging `@userinfobot` or checking `https://api.telegram.org/bot<TOKEN>/getUpdates`. Copy the Chat ID (`TELEGRAM_CHAT_ID`).

### 3. Deploy to Vercel
1. Push your repository to GitHub.
2. Go to [Vercel](https://vercel.com) and click **Add New** &rarr; **Project**.
3. Import your repository.
4. Set **Root Directory** to `signals-web`.
5. Under **Environment Variables**, add:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `CRON_SECRET` = (create any random string, e.g. `prop-gold-secret-9942`)
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `TWELVE_DATA_API_KEY` (optional)
6. Click **Deploy**. Your app will be live at `https://your-project.vercel.app`.

### 4. Configure GitHub Actions (5-Minute Clock)
1. In your GitHub repository, go to **Settings** &rarr; **Secrets and variables** &rarr; **Actions**.
2. Add two repository secrets:
   - `VERCEL_APP_URL` = `your-project.vercel.app` (without `https://`)
   - `CRON_SECRET` = (the same secret string you set in Vercel)
3. The workflow in [`.github/workflows/scanner.yml`](../.github/workflows/scanner.yml) will now automatically trigger your scanner every 5 minutes!

---

## 🎯 Confluence Engine Specifications

| Timeframe | Purpose | Conditions Enforced |
| :--- | :--- | :--- |
| **4H** | **Bias Only** | Price relative to 20 & 50 EMA + Higher Highs/Lows vs Lower Highs/Lows. If ranging, **hard gate active** (no trades). |
| **1H** | **Setup Detection** | Evaluated only if 4H has bias. Identifies retest of prior structure, liquidity sweep, or key supply/demand zone. |
| **30M** | **Entry Trigger** | Evaluated only if 1H setup formed. Rejection pin-bar (wick >= 25%) or momentum closed breakout. |

### Risk & Reward Rules:
- **Stop Loss**: 1.5× ATR on the 30M entry candle (minimum 2.50 pts on Gold, 150 pts on BTC).
- **Take Profit**: Minimum **1:2.0** Risk-to-Reward ratio calculated off the stop distance.
- **Confluence Scoring**:
  - `3/3`: All 3 timeframes aligned (**Approved for Prop Firm Funded Accounts**).
  - `2/3`: Lower confidence (**Reserve for Demo / Backtest validation**).

---

## 🛡️ Prop Firm Risk Guardrails
1. **Never trade 2/3 signals on a funded account** — stick strictly to 3/3 setups.
2. **Cap daily trades at 2–3 maximum** even if the scanner identifies more. Overtrading is the #1 reason prop accounts fail.
3. **Audit your history log**: After every trade, click **Hit TP**, **Hit SL**, or **Not Taken** on your dashboard to evaluate edge over 4–6 weeks.
