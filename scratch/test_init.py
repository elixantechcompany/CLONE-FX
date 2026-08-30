import sys
import os
sys.path.insert(0, os.path.abspath("."))

import yaml
from dotenv import load_dotenv
import MetaTrader5 as mt5

load_dotenv("config/.env")
load_dotenv()

print("Step 1: Calling mt5.initialize()...", flush=True)
ok = mt5.initialize()
print(f"Step 2: mt5.initialize result: {ok}", flush=True)
acc = mt5.account_info()
print(f"Step 3: account_info: {acc.login if acc else None} on {acc.server if acc else None}", flush=True)
mt5.shutdown()
print("Step 4: Done!", flush=True)
