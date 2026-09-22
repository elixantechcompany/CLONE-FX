# Multi-Account Trading Platform - Deployment Checklist

Complete checklist for deploying the trading platform on FREE TIERS only.

## ✅ Phase 1: Foundation (COMPLETED)

### Database Setup
- [x] Supabase database schema with RLS enabled
- [x] 5-account hard limit constraint
- [x] Trading accounts table with encrypted passwords
- [x] Trading signals table with expiration
- [x] Emergency commands table
- [x] Automated cleanup functions

### Python Engine Core
- [x] MT5 trend analyzer (50 EMA on H4/H1)
- [x] Signal generation with 5-minute freshness
- [x] Multi-account execution engine
- [x] Funded account protection (3.5% daily loss)
- [x] Dynamic lot sizing based on equity
- [x] Emergency position closure

### PWA Foundation
- [x] Next.js 14 mobile-first structure
- [x] High-contrast dark mode interface
- [x] PWA manifest and service worker
- [x] TypeScript configuration
- [x] Tailwind CSS styling
- [x] Supabase client integration

## 🚀 Phase 2: Deployment Steps

### Step 1: Supabase Setup
1. Create free Supabase project at https://supabase.com
2. Run `supabase/schema.sql` in SQL Editor
3. Get project URL and keys from Project Settings → API
4. Configure Row Level Security (already in schema)

### Step 2: Vercel Deployment (PWA)
1. Push code to GitHub repository
2. Import project in Vercel
3. Set root directory to `pwa-frontend`
4. Add environment variables:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
5. Deploy and test PWA installation

### Step 3: AWS Instance Setup
1. Launch t2.micro Windows instance (Free Tier)
2. Connect via RDP
3. Install Python 3.11
4. Install MetaTrader 5
5. Upload project files to instance

### Step 4: Python Engine Configuration
1. Run `aws-deployment/setup_aws_instance.py`
2. Configure `.env` file with Supabase credentials
3. Run `aws-deployment/mt5_memory_optimization.bat`
4. Manually configure MT5 settings
5. Add trading accounts via PWA

### Step 5: Testing & Validation
1. Test MT5 connections
2. Verify signal generation
3. Test multi-account execution
4. Validate emergency kill switch
5. Monitor memory usage

## 🔧 Configuration Files

### Environment Variables (PWA)
```env
NEXT_PUBLIC_SUPABASE_URL=your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

### Environment Variables (Python)
```env
SUPABASE_URL=your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
MT5_SYMBOL=XAUUSD
DAILY_LOSS_LIMIT_PCT=3.5
RISK_PER_TRADE_PCT=1.0
SIGNAL_LIFETIME_MINUTES=5
SIGNAL_GENERATION_INTERVAL_SECONDS=60
```

## 📱 PWA Features Verification

### Dashboard
- [ ] Account cards display correctly
- [ ] Balance and equity updates
- [ ] Connection status indicators
- [ ] Daily P&L tracking
- [ ] Emergency kill button functional

### Account Management
- [ ] Add account form works
- [ ] 5-account limit enforced
- [ ] Account deletion works
- [ ] Active/inactive toggle works
- [ ] Form validation working

### Signals Page
- [ ] Signals display with freshness
- [ ] Copy buttons work correctly
- [ ] Expired signals fade out
- [ ] Signal parameters accurate
- [ ] Trend alignment shown

## 🤖 Python Engine Verification

### Trend Analysis
- [ ] 50 EMA calculation correct on H4
- [ ] 50 EMA calculation correct on H1
- [ ] BUY/SELL conditions enforced
- [ ] ATR-based stop losses working
- [ ] Minimum 1:2 risk-reward enforced

### Multi-Account Execution
- [ ] Concurrent execution across accounts
- [ ] Dynamic lot sizing accurate
- [ ] Account isolation maintained
- [ ] Connection error handling
- [ ] Trade execution confirmation

### Risk Management
- [ ] 3.5% daily loss limit enforced
- [ ] Emergency closure triggers correctly
- [ ] Equity monitoring active
- [ ] Position limits respected
- [ ] Risk percentage calculations correct

## 🔒 Security Verification

### Database Security
- [ ] RLS policies active
- [ ] User data isolation working
- [ ] Password encryption functional
- [ ] Account limit enforced at DB level
- [ ] API authentication working

### Application Security
- [ ] Supabase auth integration
- [ ] Environment variables secured
- [ ] No hardcoded credentials
- [ ] HTTPS enforced on Vercel
- [ ] Input validation on all forms

## 📊 Performance Monitoring

### AWS Instance
- [ ] Memory usage < 900MB
- [ ] CPU usage reasonable
- [ ] No memory leaks detected
- [ ] MT5 optimization effective
- [ ] Python engine stable

### PWA Performance
- [ ] Load time < 3 seconds
- [ ] PWA installs correctly
- [ ] Offline functionality working
- [ ] Mobile responsive design
- [ ] Signal refresh rate appropriate

## 🚨 Emergency Procedures

### Emergency Kill Switch
- [ ] PWA button triggers immediate closure
- [ ] Python engine respects emergency command
- [ ] All accounts close positions
- [ ] System enters safe mode
- [ ] Recovery procedure documented

### System Recovery
- [ ] Backup configuration files
- [ ] Document recovery steps
- [ ] Test restore procedure
- [ ] AWS instance backup created
- [ ] Rollback plan available

## 📈 Success Criteria

### Functional Requirements
- [ ] System runs 24/7 without intervention
- [ ] Signals generate based on 50 EMA strategy
- [ ] Multi-account execution works concurrently
- [ ] Funded account protection active
- [ ] Mobile PWA fully functional

### Technical Requirements
- [ ] All components on FREE TIERS
- [ ] Memory usage within AWS limits
- [ ] Response times acceptable
- [ ] Error handling comprehensive
- [ ] Logging and monitoring active

### Business Requirements
- [ ] 5-account limit strictly enforced
- [ ] Risk management rules followed
- [ ] Emergency procedures functional
- [ ] User data properly secured
- [ ] System maintainable and documented

## 🎯 Next Steps

1. **Deploy PWA to Vercel** (30 minutes)
2. **Set up AWS instance** (1 hour)
3. **Configure MT5 terminals** (30 minutes)
4. **Test signal generation** (30 minutes)
5. **Validate multi-account execution** (1 hour)
6. **Test emergency procedures** (30 minutes)
7. **Monitor for 24 hours** (1 day)
8. **Go live with real accounts** (after testing)

## 📞 Support Resources

- **Documentation**: `README.md`
- **Deployment Guide**: `aws-deployment/deployment_guide.md`
- **Database Schema**: `supabase/schema.sql`
- **API Documentation**: `pwa-frontend/app/api/`
- **Python Modules**: `python-engine/`

---

**⚠️ FINAL REMINDER**: This system involves real financial trading. Complete thorough testing with demo accounts before deploying with real money. Start with small position sizes and monitor closely.