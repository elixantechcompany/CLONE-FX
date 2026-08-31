import MetaTrader5 as mt5
import time

print("--- TESTING TERMINAL A (BrightFunded) ---")
mt5.shutdown()
res_a = mt5.initialize(login=312128694, password="!i9uTy1ojF2@", server="BrightFunded-Server")
print(f"Terminal A init: {res_a}")
acc_a = mt5.account_info()
if acc_a:
    print(f"Account A Login: {acc_a.login}, Server: {acc_a.server}, Equity: ${acc_a.equity:.2f}")
else:
    print(f"Account A failed: {mt5.last_error()}")

print("\n--- TESTING TERMINAL C (HFMarkets) ---")
path_c = r"c:\Users\PwezaCore\Desktop\MT5_Account_C\terminal64.exe"
mt5.shutdown()
res_c = mt5.initialize(path=path_c, login=49837916, password="POIUasdf888!", server="HFMarketsGlobal-Demo")
print(f"Terminal C init: {res_c}")
acc_c = mt5.account_info()
if acc_c:
    print(f"Account C Login: {acc_c.login}, Server: {acc_c.server}, Equity: ${acc_c.equity:.2f}")
else:
    print(f"Account C failed: {mt5.last_error()}")

mt5.shutdown()
