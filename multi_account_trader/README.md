# Multi-Account Trading Platform & Market Analyzer PWA

A comprehensive multi-account trading platform designed for FREE TIER deployment, featuring real-time signals, risk management, and mobile-first PWA interface.

## 🚀 Quick Start

### Prerequisites
- Python 3.10+ (for AWS instance)
- Node.js 20+ (for local development)
- Free Supabase account
- Free Vercel account
- AWS Free Tier (t2.micro Windows)

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd multi_account_trader
```

2. **Set up Supabase Database**
```bash
# Create a new Supabase project at https://supabase.com
# Run the schema SQL in Supabase SQL Editor
cat supabase/schema.sql
```

3. **Configure Environment Variables**
```bash
# For PWA Frontend
cd pwa-frontend
cp .env.example .env.local
# Add your Supabase credentials
```

4. **Install Dependencies**
```bash
# Frontend
cd pwa-frontend
npm install

# Python Engine
cd ../python-engine
pip install -r requirements.txt
```

## 📁 Project Structure

```
multi_account_trader/
├── supabase/
│   └── schema.sql              # Database schema with RLS
├── python-engine/
│   ├── trend_analyzer.py       # EMA trend analysis (H4/H1)
│   ├── multi_account_executor.py # Multi-account execution
│   ├── signal_generator.py     # Signal generation with freshness
│   └── requirements.txt        # Python dependencies
├── pwa-frontend/
│   ├── app/
│   │   ├── page.tsx            # Main dashboard
│   │   └── api/                # API routes
│   ├── components/             # React components
│   └── lib/                    # Utilities and types
└── README.md
```

## 🔑 Key Features

### **Trading Logic**
- **50 EMA Trend Filter**: Only trades when price aligns with 50 EMA on both H4 and H1
- **Dynamic Risk Management**: 1.5x ATR-based stop losses with minimum 1:2 risk-reward
- **Funded Account Protection**: 3.5% daily loss limit with automatic position closure
- **Multi-Account Execution**: Concurrent trading across up to 5 MT5 accounts

### **Mobile PWA**
- **High-Contrast Dark Mode**: Optimized for mobile trading
- **Real-Time Dashboard**: Live account monitoring with status indicators
- **Signal Freshness Tracking**: 5-minute signal expiration with visual fade
- **Emergency Kill Switch**: One-tap closure of all positions

### **Safety Features**
- **5-Account Hard Limit**: Database-enforced maximum per user
- **Row Level Security**: Complete data isolation per user
- **Encrypted Credentials**: Passwords encrypted at rest
- **Equity Monitoring**: 60-second equity checks with auto-closure

## 🛠️ Deployment

### **Vercel (Frontend)**
```bash
cd pwa-frontend
npm run build
vercel deploy
```

### **AWS t2.micro (Python Engine)**
```bash
# Follow AWS deployment guide
python aws-deployment/setup_aws_instance.py
```

### **Supabase (Database)**
1. Create free project at supabase.com
2. Run `supabase/schema.sql` in SQL Editor
3. Configure environment variables

## ⚙️ Configuration

### **Environment Variables (PWA)**
```env
NEXT_PUBLIC_SUPABASE_URL=your-project-url.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

### **Environment Variables (Python)**
```env
SUPABASE_URL=your-project-url.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

## 📊 Trading Strategy

### **Entry Rules**
- **BUY**: Price > 50 EMA on both H4 and H1
- **SELL**: Price < 50 EMA on both H4 and H1
- **Stop Loss**: 1.5x 14-period ATR on H1
- **Take Profit**: Minimum 1:2 risk-reward ratio

### **Risk Management**
- **Per Trade**: 1% of account equity (configurable)
- **Daily Loss**: 3.5% maximum (hard stop at 5%)
- **Position Sizing**: Dynamic based on equity and stop distance

## 🔒 Security

- **Row Level Security**: Complete user data isolation
- **Encrypted Passwords**: Using pgcrypto
- **Account Limits**: Hard 5-account limit per user
- **API Authentication**: Supabase auth integration

## 📱 PWA Features

- **Installable**: Add to home screen on mobile
- **Offline Support**: Basic functionality without internet
- **Push Notifications**: Real-time trade alerts (future)
- **Responsive Design**: Optimized for all screen sizes

## 🧪 Testing

### **Local Development**
```bash
# Frontend
cd pwa-frontend
npm run dev

# Python Engine
cd python-engine
python trend_analyzer.py
python multi_account_executor.py
```

### **Integration Testing**
```bash
# Test signal generation
python signal_generator.py

# Test multi-account execution
python multi_account_executor.py
```

## 📈 Monitoring

### **Dashboard Metrics**
- Total balance across all accounts
- Daily profit/loss tracking
- Connection status per account
- Signal freshness indicators

### **Logging**
- Python: Structured logging to console and file
- PWA: Browser console and error tracking
- Supabase: Database query logs

## 🆘 Troubleshooting

### **Common Issues**
- **MT5 Connection**: Ensure Algo Trading is enabled in MT5
- **Signal Generation**: Check market hours and symbol availability
- **PWA Installation**: Use HTTPS and valid manifest
- **AWS Memory**: Monitor RAM usage on t2.micro

### **Support**
- Check logs in `logs/` directory
- Verify Supabase connection status
- Test MT5 terminal connectivity
- Monitor AWS instance metrics

## 📄 License

Proprietary - All rights reserved

## 🤝 Contributing

This is a proprietary trading system. External contributions are not accepted.

---

**⚠️ WARNING**: This system involves real financial trading. Use at your own risk and ensure proper testing before live deployment.