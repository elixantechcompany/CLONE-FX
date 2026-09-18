"""
Signals & Market Structure Dashboard Server
Continuously analyzes live market structure across symbols and timeframes,
updates dashboard/data.json in real time, and serves the UI locally at http://localhost:8080.
"""

import sys
import os
import time
import json
import threading
import webbrowser
import logging
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, List, Dict, Any
import yaml
from dotenv import load_dotenv

from src.dashboard import DashboardExporter
from src.account_manager import AccountManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [DashboardServer]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("GoldBot.DashboardServer")

PORT = 8080
DASHBOARD_DIR = Path(__file__).parent / "dashboard"

global_exporter: Optional[DashboardExporter] = None
account_manager = AccountManager()


class DashboardHTTPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def end_headers(self):
        # Prevent caching for live data.json and API responses
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/accounts":
            fleet = account_manager.get_fleet_summary()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"accounts": fleet}).encode("utf-8"))
            return
        super().do_GET()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            body = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            body = {}

        if self.path == "/api/accounts/add":
            try:
                name = body.get("name", "New Account")
                acc_type = body.get("account_type", "PERSONAL")
                balance = float(body.get("balance", 20.0))
                login = str(body.get("login", ""))
                password = str(body.get("password", ""))
                server = str(body.get("server", ""))
                path = body.get("path")
                mode = body.get("mode", "INDEPENDENT")
                exec_mode = body.get("execution_mode", "AUTOMATED_EA")

                added = account_manager.add_account(
                    name=name,
                    account_type=acc_type,
                    balance=balance,
                    login=login,
                    password=password,
                    server=server,
                    path=path,
                    mode=mode,
                    execution_mode=exec_mode,
                )

                if global_exporter:
                    global_exporter.export_data()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "account": added}).encode("utf-8"))
            except ValueError as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        elif self.path == "/api/terminals/launch":
            acc_id = body.get("account_id", "")
            success = account_manager.launch_terminal(acc_id)
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "account_id": acc_id}).encode("utf-8"))
            return

        elif self.path == "/api/terminals/launch-all":
            results = account_manager.launch_all_terminals()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "results": results}).encode("utf-8"))
            return

        elif self.path == "/api/accounts/toggle-mode":
            acc_id = body.get("account_id", "")
            mode = body.get("execution_mode", "AUTOMATED_EA")
            try:
                updated = account_manager.toggle_execution_mode(acc_id, mode)
                if global_exporter:
                    global_exporter.export_data()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "account": updated}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        # Suppress routine 200/304 log noise from 2.5s polling
        if "data.json" in args[0]:
            return
        super().log_message(format, *args)


def run_scanner_worker(exporter: DashboardExporter, stop_event: threading.Event):
    """Background thread that continuously scans market structure and refreshes data.json."""
    logger.info("Market Structure & Perfect Setups scanner thread started.")
    symbols_map = {"XAUUSD": "XAUUSDm", "BTCUSD": "BTCUSDm"}

    while not stop_event.is_set():
        try:
            exporter.export_data(
                active_symbols=symbols_map,
                active_session="Live Autonomous Scanner",
            )
        except Exception as e:
            logger.warning(f"Scanner cycle warning: {e}")

        # Sleep in small slices so shutdown is instant
        for _ in range(30):
            if stop_event.is_set():
                break
            time.sleep(0.1)


def main():
    load_dotenv("config/.env")
    load_dotenv()

    config = {}
    config_file = "config/config.yaml"
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)

    global global_exporter
    # Initialize Dashboard Exporter
    exporter = DashboardExporter(config, output_dir=str(DASHBOARD_DIR))
    global_exporter = exporter

    # Initial export so data.json exists immediately
    exporter.export_data()

    # Start background scanner
    stop_event = threading.Event()
    scanner_thread = threading.Thread(
        target=run_scanner_worker,
        args=(exporter, stop_event),
        daemon=True,
    )
    scanner_thread.start()

    # Start HTTP server
    server_address = ("", PORT)
    httpd = ThreadingHTTPServer(server_address, DashboardHTTPRequestHandler)
    url = f"http://localhost:{PORT}/index.html"

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("=" * 70)
    print("      INSTITUTIONAL MARKET STRUCTURE & SIGNALS DASHBOARD")
    print("=" * 70)
    print(f" [+] Real-time Market Structure Engine: Active")
    print(f" [+] Perfect Setups Confluence Radar:    Active")
    print(f" [+] Web Server Listening on:            http://localhost:{PORT}")
    print(f" [+] Launching browser:                  {url}")
    print("=" * 70)
    print(" Press Ctrl+C to stop the dashboard server.\n")

    # Launch browser automatically
    try:
        webbrowser.open(url)
    except Exception as e:
        logger.warning(f"Could not open browser automatically: {e}")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Dashboard server safely...")
    finally:
        stop_event.set()
        httpd.shutdown()
        httpd.server_close()
        scanner_thread.join(timeout=2.0)
        print("Dashboard server stopped.")


if __name__ == "__main__":
    main()
