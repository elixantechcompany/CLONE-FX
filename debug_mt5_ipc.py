import MetaTrader5 as mt5
from dotenv import load_dotenv
import os

load_dotenv("config/.env")

login = int(os.getenv("ACCOUNT_1_LOGIN", "313812184"))
password = os.getenv("ACCOUNT_1_PASSWORD", "WZ4nsEO#W*D*")
server = os.getenv("ACCOUNT_1_SERVER", "BrightFunded-Server")
path = r"C:\Program Files\MetaTrader 5\terminal64.exe"

print(f"Testing mt5.initialize(path='{path}', login={login}, server='{server}')...")
res = mt5.initialize(path=path, login=login, password=password, server=server, timeout=10000)
print(f"Result: {res}")
if not res:
    print(f"Last error: {mt5.last_error()}")
else:
    acc = mt5.account_info()
    term = mt5.terminal_info()
    print(f"SUCCESS: Account {acc.login if acc else 'None'} ({acc.server if acc else 'None'})")
    print(f"Terminal build: {term.build if term else 'None'}, Algo trading allowed: {term.trade_allowed if term else 'None'}")
    mt5.shutdown()
