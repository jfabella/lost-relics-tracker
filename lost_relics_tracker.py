import tkinter as tk
import requests
import threading
import time
import json
import os
import hashlib
import re
import signal
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("LR_API_URL", "http://localhost:11990/Player")
CHECK_INTERVAL = 5
REQUEST_TIMEOUT = 10
LOG_DIR = "run_logs"
CONFIG_FILE = "non_blockchain_config.json"
EXCLUDE_FILE = "non_blockchain_exclude.json"
DEFAULT_TRACKED_NON_BLOCKCHAIN_ITEMS = ["Deepsea Coffer", "Golden Grind Chest", "Frostfall Shard"]
DEFAULT_EXCLUDED_NON_BLOCKCHAIN_ITEMS = ["Deepsea Coffer"]
SKILLS = {"Fishing", "Mining", "Scavenging", "Woodcutting"}


class APIClient:
    def __init__(self, api_url: str, timeout: int = 10):
        self.api_url = api_url
        self.timeout = timeout
        self.session = requests.Session()

    def fetch_player_data(self) -> dict:
        r = self.session.get(self.api_url, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass


class DataManager:
    def __init__(self, log_dir: str, config_file: str, exclude_file: str):
        self.log_dir = log_dir
        os.makedirs(log_dir, mode=0o755, exist_ok=True)
        self.lock = threading.RLock()
        self.reset_daily_counters_locked(datetime.now(timezone.utc).date())
        self.player_name = "Unknown Player"
        self.last_adventure_signature = None
        self._loaded_from_log = False
        self.non_blockchain_items = self.load_config(config_file, DEFAULT_TRACKED_NON_BLOCKCHAIN_ITEMS)
        self.non_blockchain_exclude = self.load_config(exclude_file, DEFAULT_EXCLUDED_NON_BLOCKCHAIN_ITEMS)
        self.load_log()

    def reset_daily_counters_locked(self, today_date):
        self.counter = 0
        self.blockchain_totals = defaultdict(int)
        self.non_blockchain_totals = defaultdict(int)
        self.adventure_counts = defaultdict(int)
        self.total_character_xp = 0
        self.skill_xp_totals = defaultdict(int)
        self.total_enj_value = 0.0
        self.gold_coins_total = 0
        self.total_estimated_gold = 0
        self.market_values = {}
        self.current_log_date = today_date
        self.start_time = datetime.now(timezone.utc)

    def load_config(self, filepath: str, defaults: List[str]) -> List[str]:
        if os.path.isfile(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(defaults, f, indent=2)
        except Exception:
            pass
        return defaults

    def log_filepath(self) -> str:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return os.path.join(self.log_dir, f"runs_{today_str}.json")

    def load_log(self):
        path = self.log_filepath()
        tmp_path = path + ".tmp"
        data = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.save_error_log(f"Corrupted or missing log file {path}: {e}")
            try:
                with open(tmp_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                os.replace(tmp_path, path)
            except Exception:
                data = {}
        if data:
            with self.lock:
                self.counter = data.get("runs", 0)
                self.blockchain_totals.update(data.get("blockchain_totals", {}))
                self.non_blockchain_totals.update(data.get("non_blockchain_totals", {}))
                self.adventure_counts.update(data.get("adventure_counts", {}))
                self.total_character_xp = data.get("total_character_xp", 0)
                self.skill_xp_totals.update(data.get("skill_xp_totals", {}))
                self.player_name = data.get("player_name", "Unknown Player")
                self.total_enj_value = data.get("total_enj_value", 0.0)
                self.gold_coins_total = data.get("gold_coins_total", 0)
                self.total_estimated_gold = data.get("total_estimated_gold", 0)
                self.last_adventure_signature = data.get("last_adventure_signature")
                self._loaded_from_log = True

    def save_log(self):
        with self.lock:
            data = {
                "runs": self.counter,
                "blockchain_totals": dict(self.blockchain_totals),
                "non_blockchain_totals": dict(self.non_blockchain_totals),
                "adventure_counts": dict(self.adventure_counts),
                "total_character_xp": self.total_character_xp,
                "skill_xp_totals": dict(self.skill_xp_totals),
                "player_name": self.player_name,
                "total_enj_value": self.total_enj_value,
                "gold_coins_total": self.gold_coins_total,
                "total_estimated_gold": self.total_estimated_gold,
                "last_adventure_signature": self.last_adventure_signature,
            }
        tmp_path = self.log_filepath() + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.log_filepath())
        except Exception:
            pass

    def process_adventure_locked(self, adventure: Dict[str, Any]):
        self.counter += 1
        self.adventure_counts[adventure.get("AdventureName", "Unknown")] += 1
        self.total_character_xp += adventure.get("ExperienceAmount", 0)
        for xp in adventure.get("Experience", []):
            if xp.get("Type") in SKILLS:
                self.skill_xp_totals[xp["Type"]] += xp.get("Amount", 0)
        estimated_gold = 0
        for item in adventure.get("Items", []):
            name, amount, mv = item.get("Name", "Unknown"), item.get("Amount", 1), item.get("MarketValue", 0)
            if name == "Gold Coins":
                self.gold_coins_total += amount
                estimated_gold += amount
            if item.get("IsBlockchain", False):
                self.blockchain_totals[name] += amount
                if mv:
                    self.market_values[name] = mv
                    self.total_enj_value += (mv / 100.0) * amount
            else:
                if name in self.non_blockchain_items:
                    self.non_blockchain_totals[name] += amount
                if name not in self.non_blockchain_exclude:
                    estimated_gold += amount * mv
        self.total_estimated_gold += estimated_gold

    @staticmethod
    def adventure_signature(adventure: Dict[str, Any]) -> str:
        items = sorted([(i.get("Name"), i.get("Amount", 1), i.get("IsBlockchain", False))
                        for i in adventure.get("Items", [])])
        sig_data = {"name": adventure.get("AdventureName", "Unknown"), "items": items}
        return hashlib.sha256(json.dumps(sig_data, sort_keys=True).encode()).hexdigest()

    def save_error_log(self, message: str):
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        path = os.path.join(self.log_dir, f"error_{now.strftime('%Y-%m-%d')}.txt")
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {message}\n")
        except Exception:
            pass


class TrackerUI:
    def __init__(self, root: tk.Tk, dm: DataManager):
        self.root, self.dm, self.dark_mode = root, dm, True
        self.build_ui()
        self.apply_theme()

    def build_ui(self):
        self.root.title("Lost Relics Daily Tracker")
        self.root.geometry("350x600")
        self.root.resizable(True, True)
        self.root.attributes('-topmost', True)
        self.label_player_name = tk.Label(self.root, text=self.dm.player_name, font=("Arial", 20, "bold"))
        self.label_player_name.pack(pady=(10, 0))
        self.label_server_time = tk.Label(self.root, font=("Arial", 10)); self.label_server_time.pack()
        self.label_elapsed_time = tk.Label(self.root, font=("Arial", 10)); self.label_elapsed_time.pack(pady=(0, 5))
        self.toggle_button = tk.Button(self.root, text="Toggle Theme", command=self.toggle_theme)
        self.toggle_button.pack(pady=(0, 10))
        self.credit_label = tk.Label(self.root, text="Developed by Capoeira", font=("Arial", 8))
        self.credit_label.pack(side="bottom", pady=(0, 5))
        frame = tk.Frame(self.root); frame.pack(fill="both", expand=True, padx=5, pady=5)
        scrollbar = tk.Scrollbar(frame); scrollbar.pack(side="right", fill="y")
        self.text_output = tk.Text(frame, font=("Arial", 11), wrap="word",
                                   yscrollcommand=scrollbar.set, height=28, width=42, borderwidth=0)
        self.text_output.pack(side="left", fill="both", expand=True); scrollbar.config(command=self.text_output.yview)
        self.text_output.configure(state="disabled"); self.text_output.tag_configure("bold", font=("Arial", 11, "bold"))

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    def apply_theme(self):
        if self.dark_mode:
            bg, fg, select_bg, credit_color = "#1e1e1e", "#d4d4d4", "#444444", "#888888"
        else:
            bg, fg, select_bg, credit_color = "#ffffff", "#000000", "#cce6ff", "gray"
        widgets = [self.root, self.label_player_name, self.label_server_time,
                   self.label_elapsed_time, self.toggle_button, self.credit_label, self.text_output]
        for w in widgets: w.configure(bg=bg)
        self.label_player_name.configure(fg=fg)
        self.label_server_time.configure(fg=fg)
        self.label_elapsed_time.configure(fg=fg)
        self.toggle_button.configure(fg=fg, activebackground=select_bg)
        self.credit_label.configure(fg=credit_color)
        self.text_output.configure(fg=fg, insertbackground=fg, selectbackground=select_bg)

    def refresh_ui(self):
        with self.dm.lock:
            snap = dict(
                player_name=self.dm.player_name, counter=self.dm.counter,
                total_enj_value=self.dm.total_enj_value, gold_coins_total=self.dm.gold_coins_total,
                total_estimated_gold=self.dm.total_estimated_gold, adventure_counts=dict(self.dm.adventure_counts),
                total_character_xp=self.dm.total_character_xp, skill_xp_totals=dict(self.dm.skill_xp_totals),
                blockchain_totals=dict(self.dm.blockchain_totals), non_blockchain_totals=dict(self.dm.non_blockchain_totals),
                non_blockchain_items=set(self.dm.non_blockchain_items), start_time=self.dm.start_time
            )
        now = datetime.now(timezone.utc); elapsed = now - snap["start_time"]
        self.label_player_name.config(text=snap["player_name"])
        self.label_server_time.config(text=f"Server Time (GMT): {now:%Y-%m-%d %H:%M:%S}")
        self.label_elapsed_time.config(text=f"App Running: {str(elapsed).split('.')[0]}")
        yview = self.text_output.yview()
        self.text_output.configure(state="normal"); self.text_output.delete("1.0", tk.END)

        def bold(t): self.text_output.insert(tk.END, t + "\n", "bold")
        bold(f"Total Runs: {snap['counter']:,}")
        bold(f"Total Gold Coins: {snap['gold_coins_total']:,}")
        bold(f"Total Estimated Gold: {snap['total_estimated_gold']:,.0f}")
        bold(f"Total ENJ Value: {snap['total_enj_value']:,.2f}\n")

        bold("Adventures:")
        if snap["adventure_counts"]:
            for n, c in sorted(snap["adventure_counts"].items(), key=lambda x: -x[1]):
                self.text_output.insert(tk.END, f"{n} x{c:,}\n")
        else:
            self.text_output.insert(tk.END, "(no adventures)\n")

        bold("\nExperience:")
        self.text_output.insert(tk.END, f"Character XP: {snap['total_character_xp']:,}\n")
        for s, xp in snap["skill_xp_totals"].items():
            self.text_output.insert(tk.END, f"{s}: {xp:,}\n")

        bold("\nBlockchain Items:")
        if snap["blockchain_totals"]:
            for n, a in sorted(snap["blockchain_totals"].items()):
                self.text_output.insert(tk.END, f"{n} x{a:,}\n")
        else:
            self.text_output.insert(tk.END, "(none)\n")

        bold("\nTracked Non-Blockchain Items:")
        filtered = [(n, a) for n, a in snap["non_blockchain_totals"].items() if n in snap["non_blockchain_items"]]
        if filtered:
            for n, a in sorted(filtered):
                self.text_output.insert(tk.END, f"{n} x{a:,}\n")
        else:
            self.text_output.insert(tk.END, "(none)\n")

        self.text_output.configure(state="disabled"); self.text_output.yview_moveto(yview[0])


class RunCounterApp:
    def __init__(self, root: tk.Tk):
        self.dm = DataManager(LOG_DIR, CONFIG_FILE, EXCLUDE_FILE)
        self.ui = TrackerUI(root, self.dm)
        self.api = APIClient(API_URL, REQUEST_TIMEOUT)

        self.stop_event = threading.Event()
        self.worker_thread = threading.Thread(target=self.poll_api_loop, daemon=True)
        self.worker_thread.start()

        self.schedule_ui_refresh()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.install_signal_handlers()
        self.install_excepthook()

    def poll_api_loop(self):
        try:
            while not self.stop_event.is_set():
                try:
                    data = self.api.fetch_player_data()
                    if data.get("PlayerName"):
                        with self.dm.lock:
                            self.dm.player_name = data["PlayerName"]

                    adv = data.get("LastAdventure", {})
                    if adv.get("AdventureName"):
                        sig = self.dm.adventure_signature(adv)
                        with self.dm.lock:
                            if sig != self.dm.last_adventure_signature:
                                self.dm.last_adventure_signature = sig
                                self.dm.process_adventure_locked(adv)
                        self.dm.save_log()
                except Exception as e:
                    self.dm.save_error_log(f"Polling error: {e}")

                if self.stop_event.wait(CHECK_INTERVAL):
                    break
        finally:
            self.api.close()

    def schedule_ui_refresh(self):
        if not self.stop_event.is_set():
            self.ui.refresh_ui()
            self.ui.root.after(1000, self.schedule_ui_refresh)

    def on_close(self):
        self.stop_event.set()
        try:
            self.dm.save_log()
        except Exception:
            pass

        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.5)

        self.ui.root.destroy()

    def install_signal_handlers(self):
        def handler(signum, frame):
            self.dm.save_error_log(f"Received signal {signum}, shutting down.")
            self.on_close()

        for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
            if sig is not None:
                try:
                    signal.signal(sig, handler)
                except Exception:
                    pass

    def install_excepthook(self):
        def _hook(exc_type, exc, tb):
            try:
                self.dm.save_error_log(f"Uncaught exception: {exc_type.__name__}: {exc}")
                self.dm.save_log()
            finally:
                self.stop_event.set()
                if self.worker_thread.is_alive():
                    try:
                        self.worker_thread.join(timeout=2.5)
                    except Exception:
                        pass
                sys.__excepthook__(exc_type, exc, tb)
                try:
                    self.ui.root.quit()
                except Exception:
                    pass
        sys.excepthook = _hook


if __name__ == "__main__":
    root = tk.Tk()
    app = RunCounterApp(root)
    try:
        root.mainloop()
    finally:
        app.stop_event.set()
        try: app.dm.save_log()
        except Exception: pass
        if app.worker_thread.is_alive():
            try: app.worker_thread.join(timeout=2.5)
            except Exception: pass
