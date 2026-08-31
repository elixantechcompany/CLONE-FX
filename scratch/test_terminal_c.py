import MetaTrader5 as mt5

path_c = r"c:\Users\PwezaCore\Desktop\MT5_Account_C\terminal64.exe"
print(f"Connecting to Terminal C at {path_c}...")

if not mt5.initialize(path=path_c, login=49837916, password="POIUasdf888!", server="HFMarketsGlobal-Demo"):
    print(f"Failed to initialize Terminal C: {mt5.last_error()}")
else:
    acc = mt5.account_info()
    term = mt5.terminal_info()
    print(f"TERMINAL C CONNECTED!")
    print(f"Login: {acc.login}, Server: {acc.server}, Balance: ${acc.balance:.2f}")
    print(f"Trade Allowed: {acc.trade_allowed}, Trade Expert: {acc.trade_expert}, Terminal Allowed: {term.trade_allowed}")

mt5.shutdown()
