# AWS Deployment Guide for Multi-Account Trading Platform

Complete guide for deploying the trading platform on AWS t2.micro Windows Free Tier.

## Prerequisites

- AWS Free Tier account
- Basic knowledge of Windows Server administration
- MetaTrader 5 installation files
- Supabase project already set up

## Step 1: Launch AWS t2.micro Windows Instance

1. **Log in to AWS Console** and navigate to EC2
2. **Launch Instance**:
   - Select "Windows Server 2022 Base"
   - Instance type: `t2.micro` (Free Tier eligible)
   - Configure security group to allow RDP (Port 3389)
3. **Create Key Pair** for secure access
4. **Launch Instance** and wait for it to be running

## Step 2: Connect to Windows Instance

1. **Get Password**:
   - Select instance → Actions → Connect → RDP client
   - Decrypt password using your key pair
2. **Connect via RDP** using the provided password
3. **Initial Windows Setup**:
   - Set region and keyboard
   - Create administrator password
   - Enable Windows updates (but configure to notify only)

## Step 3: Install Required Software

### Python Installation
```powershell
# Download Python 3.11
# Visit https://www.python.org/downloads/windows/
# Download Windows installer (64-bit)
# Run installer with "Add Python to PATH" checked
```

### MetaTrader 5 Installation
```powershell
# Download MT5 from your broker (Exness, etc.)
# Run installer with default settings
# Install to: C:\Program Files\MetaTrader 5\
```

### Git Installation (Optional but recommended)
```powershell
# Download Git for Windows
# https://git-scm.com/download/win
# Install with default settings
```

## Step 4: Deploy Trading Platform

### Option A: Clone Repository (if using Git)
```powershell
# Open PowerShell or Command Prompt
cd C:\
git clone <your-repository-url> multi_account_trader
cd multi_account_trader
```

### Option B: Manual Upload
1. **Compress project files** on local machine
2. **Upload to AWS** via RDP clipboard or drag-and-drop
3. **Extract** to `C:\multi_account_trader`

## Step 5: Run Setup Script

```powershell
cd C:\multi_account_trader\aws-deployment
python setup_aws_instance.py
```

The setup script will:
- ✅ Check system requirements
- ✅ Install Python dependencies
- ✅ Create MT5 optimization script
- ✅ Configure environment variables
- ✅ Create service and startup scripts
- ✅ Setup monitoring

## Step 6: Configure Environment Variables

1. **Edit `.env` file**:
```powershell
cd C:\multi_account_trader\python-engine
notepad .env.template
```

2. **Add your credentials**:
```env
SUPABASE_URL=your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
MT5_SYMBOL=XAUUSD
DAILY_LOSS_LIMIT_PCT=3.5
RISK_PER_TRADE_PCT=1.0
```

3. **Save as `.env`** (without .template extension)

## Step 7: Optimize MT5 for Low Memory

1. **Run MT5 optimization script**:
```powershell
cd C:\multi_account_trader\aws-deployment
mt5_memory_optimization.bat
```

2. **Manual MT5 Configuration**:
   - Open MT5 using the new desktop shortcut
   - Go to `Tools → Options → Charts`
   - Set "Max bars in charts" to `5000`
   - Set "Max bars in history" to `5000`
   - Go to `Tools → Options → News` and disable
   - Go to `Tools → Options → Mail` and disable
   - Go to `Tools → Options → Calendar` and disable
   - Enable "Allow algo trading" in Experts tab

## Step 8: Configure MT5 Trading Accounts

1. **Login to MT5** with your trading accounts
2. **Enable Algo Trading**:
   - Tools → Options → Experts → "Allow algorithmic trading"
3. **Test Connection**:
   - Open each account
   - Verify connection status
   - Check account balance and equity

## Step 9: Add Accounts to Supabase

1. **Access your PWA** (deployed on Vercel)
2. **Navigate to Accounts page**
3. **Add each MT5 account**:
   - Account number
   - Broker name
   - MT5 server
   - Password (will be encrypted)
   - Risk percentage

## Step 10: Test Trading Engine

1. **Run manual test**:
```powershell
cd C:\multi_account_trader\python-engine
python main.py
```

2. **Monitor logs**:
```powershell
# Check logs in real-time
Get-Content logs\trading_engine.log -Wait -Tail 20
```

3. **Verify functionality**:
   - Signal generation working
   - Account connections established
   - Risk management active
   - Emergency commands functional

## Step 11: Set Up Auto-Startup

### Option A: Windows Startup Folder
```powershell
# Copy startup script to Windows startup folder
copy C:\multi_account_trader\aws-deployment\startup.bat "C:\Users\Administrator\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\"
```

### Option B: Windows Service (More robust)
```powershell
# Install as Windows service using NSSM (Non-Sucking Service Manager)
# Download: https://nssm.cc/download
nssm install TradingEngine C:\multi_account_trader\aws-deployment\run_trading_service.bat
nssm start TradingEngine
```

## Step 12: Configure Monitoring

### Health Check Script
```powershell
# Run periodic health checks
cd C:\multi_account_trader\aws-deployment
health_check.bat
```

### Log Monitoring
```powershell
# Monitor trading engine logs
Get-Content C:\multi_account_trader\python-engine\logs\trading_engine.log -Wait -Tail 50
```

### AWS CloudWatch (Optional)
- Install CloudWatch agent
- Configure memory and CPU monitoring
- Set up alarms for high memory usage

## Step 13: Security Hardening

### Windows Firewall
```powershell
# Allow only necessary ports
New-NetFirewallRule -DisplayName "Allow RDP" -Direction Inbound -Protocol TCP -LocalPort 3389 -Action Allow
```

### Windows Updates
- Configure to check for updates but notify before install
- Schedule updates during low-activity periods

### User Management
- Create separate user for trading operations
- Use strong passwords
- Enable Windows Defender

## Step 14: Performance Optimization

### Memory Management
```powershell
# Set PowerShell to use minimal memory
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
[System.GC]::Collect()
```

### MT5 Optimization
- Close unnecessary charts
- Use minimal indicators
- Disable Expert Advisors that aren't needed
- Reduce history data

### Python Optimization
- Use the provided optimized Python script
- Monitor memory usage in Task Manager
- Restart service if memory exceeds 800MB

## Step 15: Backup and Recovery

### Configuration Backup
```powershell
# Backup important configuration files
Copy-Item C:\multi_account_trader\python-engine\.env C:\backup\.env
Copy-Item C:\multi_account_trader\config\ C:\backup\config\ -Recurse
```

### AWS Instance Backup
- Create AMI (Amazon Machine Image) of configured instance
- Schedule regular snapshots
- Document recovery procedure

## Troubleshooting

### MT5 Connection Issues
- Verify MT5 is running and logged in
- Check "Allow algo trading" is enabled
- Ensure account credentials are correct
- Test MT5 terminal connection manually

### Python Dependencies
```powershell
# Reinstall dependencies if needed
cd C:\multi_account_trader\python-engine
pip install -r requirements.txt --force-reinstall
```

### Memory Issues
- Monitor Task Manager for memory usage
- Reduce MT5 chart history further if needed
- Restart trading service periodically
- Consider upgrading to t3.micro if consistently hitting limits

### Signal Generation Issues
- Check MT5 market data connection
- Verify symbol is correct (XAUUSD)
- Check trading hours (market open)
- Review logs for specific error messages

## Maintenance Schedule

### Daily
- Check trading engine logs
- Verify account connections
- Monitor memory usage
- Review daily P&L

### Weekly
- Review signal performance
- Check emergency command logs
- Verify backup integrity
- Review AWS costs

### Monthly
- Apply Windows updates
- Review and optimize settings
- Update trading platform if needed
- Security audit

## Cost Monitoring

### AWS Free Tier Limits
- t2.micro: 750 hours/month
- Data transfer: 100 GB/month
- Ensure you stay within free tier limits

### Cost Optimization Tips
- Stop instance when not in use
- Use CloudWatch free tier monitoring
- Monitor data transfer costs
- Set up billing alerts

## Emergency Procedures

### Trading Engine Crash
1. Check logs for error messages
2. Restart service: `nssm restart TradingEngine`
3. If persistent, restart AWS instance
4. Restore from backup if needed

### Account Breach
1. Immediate: Use emergency kill switch in PWA
2. Change MT5 account passwords
3. Review recent trading activity
4. Report to broker if suspicious activity

### AWS Instance Issues
1. Check AWS Console for instance status
2. Review system logs via AWS Console
3. Reboot instance if needed
4. Launch new instance if unrecoverable

## Success Criteria

✅ Trading engine runs 24/7 without manual intervention
✅ Memory usage stays below 900MB consistently
✅ Signals generate and execute correctly
✅ Emergency commands function properly
✅ Daily P&L tracking accurate
✅ Account connections stable
✅ Logs capture all important events
✅ Monitoring and alerts working

## Support and Documentation

- Main README: `../README.md`
- Database Schema: `../supabase/schema.sql`
- API Documentation: `../pwa-frontend/app/api/`
- Python Modules: `../python-engine/`

---

**⚠️ IMPORTANT**: This system involves real financial trading. Test thoroughly with demo accounts before using real money. Monitor closely during initial deployment.