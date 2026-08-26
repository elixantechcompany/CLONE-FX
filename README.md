# Musumali Automated Gold (XAUUSD) Trading Bot (Exness + MT5)

An institutional-grade automated trading system for **Gold (XAUUSD / XAUUSDm)** running locally on Windows 11 with **Exness** and **MetaTrader 5 (MT5)**, powered by **The Musumali Strategy** (Price Action + Liquidity Sweeps + HTF Bias).

---

## 🎯 The Musumali Strategy Architecture

The bot enforces the exact 4-step sequence from the strategy transcript:

```
                  ┌──────────────────────────────────────────────┐
                  │ 1. Market Nature / Trend Bias (Daily HTF)    │
                  │    • Uptrend: Higher-Highs & Higher-Lows     │
                  │    • Downtrend: Lower-Highs & Lower-Lows     │
                  │    • Ranging/Choppy: SKIP TRADING            │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │ 2. Area of Benefit (H1 Timeframe)            │
                  │    • Zone marked by candle BODIES at prior   │
                  │      reaction cluster (Support / Demand)     │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │ 3. Liquidity Sweep                           │
                  │    • Price wicks below cluster lows (wicks)  │
                  │    • Hard filter: No sweep = No trade        │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │ 4. Musumali Candle (Signal / Rejection)      │
                  │    • Closes back INSIDE or ABOVE the zone    │
                  │    • Bullish or lower-wick rejection profile │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │ 5. Entry Trigger & Fixed Risk Execution      │
                  │    • Entry: Subsequent candle breaks high/low│
                  │    • Stop-Loss: Below Musumali candle wick   │
                  │    • Take-Profit: Fixed R:R target (e.g. 1.5)│
                  │    • Daily Discipline: Max 2 trades/day cap  │
                  └──────────────────────────────────────────────┘
```

---

## 📂 Project Structure

```
GOLD CLONE/
├── config/
│   ├── config.yaml          # All Musumali strategy parameters, risk %, timeframes
│   ├── .env.example         # Exness MT5 account credentials template
│   └── .env                 # Your private credentials (created from .env.example)
├── src/
│   ├── connection.py        # MT5 terminal connection & symbol auto-detection
│   ├── risk_manager.py      # % Equity lot sizing, spread guard, daily trade cap (2/day)
│   ├── strategy.py          # 4-step Musumali strategy & signal engine
│   ├── execution.py         # Order placement, static SL/TP, break-even updates
│   └── bot.py                # Main orchestrator loop
├── logs/                    # Rotating daily audit logs
├── backtest.py              # Historical backtester & strategy validator
├── requirements.txt         # Dependencies
├── run.py                   # Main bot launcher
└── README.md
```

---

## 🚀 Quick Setup on Windows 11

### 1. Requirements
- Python 3.10, 3.11, or 3.12 (64-bit).
- MetaTrader 5 Terminal installed from Exness.

### 2. Enable Algo Trading in MT5
In your MT5 terminal:
1. Go to **Tools** &rarr; **Options** &rarr; **Expert Advisors**.
2. Check **"Allow Algo Trading"**.

### 3. Install Dependencies
Open PowerShell or Command Prompt in this folder:
```powershell
pip install -r requirements.txt
```

### 4. Configure Your Exness Credentials
1. Copy `config/.env.example` to `config/.env`:
```powershell
copy config\.env.example config\.env
```
2. Open `config/.env` in Notepad or your editor:
```ini
MT5_ACCOUNT_NUMBER=12345678
MT5_PASSWORD=YourPasswordHere
MT5_SERVER=Exness-MT5Trial    # or Exness-MT5Real
MT5_PATH=""                   # Optional: Path to terminal64.exe if non-standard
```

### 5. Validate with Historical Backtest (Optional)
Run the backtest script to simulate the Musumali strategy against past Gold data:
```powershell
python backtest.py
```

### 6. Launch Live Trading Bot
```powershell
python run.py
```
