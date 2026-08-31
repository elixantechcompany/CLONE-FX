import MetaTrader5 as mt5
import time

print("Initializing MT5...")
mt5.initialize()

for i in range(2):
    print(f"\n--- Cycle {i+1} ---")
    
    # Switch to Account A
    acc = mt5.account_info()
    if not acc or acc.login != 312128694:
        print("Switching to Account A (BrightFunded)...")
        t0 = time.time()
        mt5.login(312128694, "!i9uTy1ojF2@", "BrightFunded-Server")
        print(f"Switch to A took {(time.time()-t0)*1000:.1f}ms")
    
    acc_a = mt5.account_info()
    print(f"Account A Login: {acc_a.login if acc_a else 'None'}, Balance: ${acc_a.balance if acc_a else 0:.2f}")

    # Switch to Account C
    acc = mt5.account_info()
    if not acc or acc.login != 49837916:
        print("Switching to Account C (HFMarkets)...")
        t0 = time.time()
        mt5.login(49837916, "POIUasdf888!", "HFMarketsGlobal-Demo")
        print(f"Switch to C took {(time.time()-t0)*1000:.1f}ms")
    
    acc_c = mt5.account_info()
    print(f"Account C Login: {acc_c.login if acc_c else 'None'}, Balance: ${acc_c.balance if acc_c else 0:.2f}")

mt5.shutdown()
print("\nSeamless switching test complete!")
