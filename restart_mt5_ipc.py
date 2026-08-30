import subprocess
import time
import MetaTrader5 as mt5

print("Restarting terminal64.exe to establish clean IPC pipe...")
# Terminate old terminal process
subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True)
time.sleep(2)

path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
print(f"Launching MT5 via Python API: {path}...")
res = mt5.initialize(path=path, timeout=30000)
print(f"mt5.initialize() returned: {res}")
if not res:
    print(f"Error: {mt5.last_error()}")
else:
    acc = mt5.account_info()
    term = mt5.terminal_info()
    print(f"SUCCESS! Logged in as: {acc.login if acc else 'None'} ({acc.server if acc else 'None'})")
    print(f"Terminal build: {term.build if term else 'None'}, Algo allowed: {term.trade_allowed if term else 'None'}")
    mt5.shutdown()
