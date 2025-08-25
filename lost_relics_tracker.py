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


# == Load Environment Variables ===
load_dotenv()

# === Constants ===
API_URL = os.environ["API_URL"]
CHECK_INTERVAL = 5  # seconds
REQUEST_TIMEOUT = 10  # seconds
LOG_DIR = "run_logs"
CONFIG_FILE = "non_blockchain_config.json"
EXCLUDE_FILE = "non_blockchain_exclude.json"
DEFAULT_TRACKED_NON_BLOCKCHAIN_ITEMS = ["Deepsea Coffer", "Golden Grind Chest", "Frostfall Shard"]
DEFAULT_EXCLUDED_NON_BLOCKCHAIN_ITEMS = ["Deepsea Coffer"]
SKILLS = {"Fishing", "Mining", "Scavenging", "Woodcutting"}


class RunCounterApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.setup_window()

        # === Memory Safety ===
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self._loaded_from_log = False

        # === State ===
        self.dark_mode = True
        self.counter = 0
        self.blockchain_totals: defaultdict[str, int] = defaultdict(int)
        self.non_blockchain_totals: defaultdict[str, int] = defaultdict(int)
        self.adventure_counts: defaultdict[str, int] = defaultdict(int)
        self.total_character_xp = 0
        self.skill_xp_totals: defaultdict[str, int] = defaultdict(int)
        self.total_enj_value = 0.0
        self.gold_coins_total = 0
        self.total_estimated_gold = 0
        self.last_adventure_signature: str | None = None
        self.player_name = "Unknown Player"
        self.start_time = datetime.now(timezone.utc)
        self.current_log_date = datetime.now(timezone.utc).date()
        self.market_values: Dict[str, float] = {}

        # Load configurations
        self.non_blockchain_items = self.load_config(CONFIG_FILE, DEFAULT_TRACKED_NON_BLOCKCHAIN_ITEMS)
        self.non_blockchain_exclude = self.load_config(EXCLUDE_FILE, DEFAULT_EXCLUDED_NON_BLOCKCHAIN_ITEMS)

        # Build UI
        self.build_ui()

        # Ensure log directory exists
        os.makedirs(LOG_DIR, exist_ok=True)
        self.load_log()

        # Start API polling thread 
        self.worker_thread = threading.Thread(target=self.poll_api_loop, name="poll_api_loop", daemon=True)
        self.worker_thread.start()

        # Schedule periodic UI refresh
        self.schedule_ui_refresh()

        # Graceful shutdown handlers
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.install_signal_handlers()
        self.install_global_excepthook()

    # === Window Setup ===
    def setup_window(self):
        self.root.title("Lost Relics Daily Tracker")
        self.root.geometry("350x600")
        self.root.resizable(True, True)
        self.root.attributes('-topmost', True)

    # === Config Handling ===
    def load_config(self, filepath: str, defaults: List[str]) -> List[str]:
        if os.path.isfile(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        # fallback to defaults
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(defaults, f, indent=2)
        except Exception as e:
            print(f"Failed to save config {filepath}: {e}")
        return defaults

    # === UI Construction ===
    def build_ui(self):
        self.label_player_name = tk.Label(self.root, text=self.player_name, font=("Arial", 20, "bold"))
        self.label_player_name.pack(pady=(10, 0))

        self.label_server_time = tk.Label(self.root, font=("Arial", 10))
        self.label_server_time.pack()
        self.label_elapsed_time = tk.Label(self.root, font=("Arial", 10))
        self.label_elapsed_time.pack(pady=(0, 5))

        self.toggle_button = tk.Button(self.root, text="Toggle Theme", command=self.toggle_theme)
        self.toggle_button.pack(pady=(0, 10))

        #self.reset_button = tk.Button(self.root, text="Manual Reset", command=self.manual_reset)
        #self.reset_button.pack(pady=(0, 10))

        self.credit_label = tk.Label(self.root, text="Developed by Capoeira", font=("Arial", 8))
        self.credit_label.pack(side="bottom", pady=(0, 5))

        frame = tk.Frame(self.root)
        frame.pack(fill="both", expand=True, padx=5, pady=5)
        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")
        self.text_output = tk.Text(
            frame, font=("Arial", 11), wrap="word",
            yscrollcommand=scrollbar.set, height=28, width=42, borderwidth=0
        )
        self.text_output.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.text_output.yview)
        self.text_output.configure(state="disabled")
        self.text_output.tag_configure("bold", font=("Arial", 11, "bold"))

        self.apply_theme()

    # === Theme Handling ===
    def apply_theme(self):
        if self.dark_mode:
            bg, fg, select_bg, credit_color = "#1e1e1e", "#d4d4d4", "#444444", "#888888"
        else:
            bg, fg, select_bg, credit_color = "#ffffff", "#000000", "#cce6ff", "gray"

        widgets = [
            self.root, self.label_player_name, self.label_server_time, self.label_elapsed_time,
            self.toggle_button, self.credit_label, self.text_output
        ]
        for w in widgets:
            w.configure(bg=bg)
        self.label_player_name.configure(fg=fg)
        self.label_server_time.configure(fg=fg)
        self.label_elapsed_time.configure(fg=fg)
        self.toggle_button.configure(fg=fg, activebackground=select_bg, relief="raised")
        self.credit_label.configure(fg=credit_color)
        self.text_output.configure(fg=fg, insertbackground=fg, selectbackground=select_bg)

    def toggle_theme(self):
        with self.lock:
            self.dark_mode = not self.dark_mode
        self.apply_theme()

    # === Logging ===
    def log_filepath(self) -> str:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return os.path.join(LOG_DIR, f"runs_{today_str}.json")

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
                self.save_error_log(f"Recovered log from backup: {tmp_path}")
                os.replace(tmp_path, path)
            except Exception as e2:
                self.save_error_log(f"Failed to recover from backup {tmp_path}: {e2}")
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
        else:
            with self.lock:
                self._loaded_from_log = False

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
        except Exception as e:
            print(f"Failed to save log file: {e}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    # === Adventure Signature ===
    @staticmethod
    def adventure_signature(adventure: Dict[str, Any]) -> str:
        name = adventure.get("AdventureName", "Unknown")
        items = sorted([
            (i.get("Name"), i.get("Amount", 1), i.get("IsBlockchain", False))
            for i in adventure.get("Items", [])
        ])
        signature_data = {"name": name, "items": items}
        return hashlib.sha256(json.dumps(signature_data, sort_keys=True).encode()).hexdigest()

    # === Error Logging ===
    def save_error_log(self, message: str):
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        path = os.path.join(LOG_DIR, f"error_{now.strftime('%Y-%m-%d')}.txt")

        # First-time setup of tracking attributes
        if not hasattr(self, "_last_error"):
            self._last_error = None
            self._last_error_time = datetime.min

        normalized = re.sub(r"0x[0-9A-Fa-f]+", "0xXXXXXXXX", message)

        # Suppress duplicates within 5 minutes (300s)
        if self._last_error == normalized and (now - self._last_error_time).total_seconds() < 300:
            return

        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception as e:
            print("Failed to write error log:", e)

        self._last_error = normalized
        self._last_error_time = now

    # === UI Refresh ===
    def refresh_ui(self):
        # Snapshot state under lock to avoid torn reads
        with self.lock:
            now = datetime.now(timezone.utc)
            elapsed = now - self.start_time
            player_name = self.player_name
            counter = self.counter
            total_enj_value = self.total_enj_value
            gold_coins_total = self.gold_coins_total
            total_estimated_gold = self.total_estimated_gold
            adventure_counts = dict(self.adventure_counts)
            total_character_xp = self.total_character_xp
            skill_xp_totals = dict(self.skill_xp_totals)
            blockchain_totals = {k: v for k, v in self.blockchain_totals.items() if k != "Gold Coins"}
            non_blockchain_totals = dict(self.non_blockchain_totals)
            non_blockchain_items = set(self.non_blockchain_items)

        self.label_player_name.config(text=player_name)
        self.label_server_time.config(text=f"Server Time (GMT): {now:%Y-%m-%d %H:%M:%S}")
        self.label_elapsed_time.config(text=f"App Running: {str(elapsed).split('.')[0]}")

        yview = self.text_output.yview()
        self.text_output.configure(state="normal")
        self.text_output.delete("1.0", tk.END)

        sections = [
            ("Total Runs", f"{counter:,}"),
            ("Total Gold Coins", f"{gold_coins_total:,}"),
            ("Total Estimated Gold", f"{total_estimated_gold:,.0f}"),
            ("Total ENJ Value", f"{total_enj_value:,.2f}"),
        ]

        adventures_data = sorted(adventure_counts.items(), key=lambda x: -x[1])
        experiences_data = [("Character XP", total_character_xp)] + [
            (skill, skill_xp_totals.get(skill, 0))
            for skill in SKILLS if skill_xp_totals.get(skill, 0) > 0
        ]

        blockchain_data = sorted(blockchain_totals.items(), key=lambda x: x[0].lower())
        non_blockchain_data = sorted(
            ((name, amount) for name, amount in non_blockchain_totals.items() if name in non_blockchain_items),
            key=lambda x: x[0].lower()
        )

        def insert_bold(text: str):
            self.text_output.insert(tk.END, text + "\n", "bold")

        for title, value in sections:
            insert_bold(f"{title}: {value}")

        insert_bold("\nAdventures:")
        if adventures_data:
            for name, count in adventures_data:
                self.text_output.insert(tk.END, f"{name} x{count:,}\n")
        else:
            self.text_output.insert(tk.END, "(no adventures)\n")

        insert_bold("\nExperience:")
        for name, xp in experiences_data:
            self.text_output.insert(tk.END, f"{name}: {xp:,}\n")

        insert_bold("\nBlockchain Items:")
        if blockchain_data:
            for name, amount in blockchain_data:
                self.text_output.insert(tk.END, f"{name} x{amount:,}\n")
        else:
            self.text_output.insert(tk.END, "(none)\n")

        insert_bold("\nTracked Non-Blockchain Items:")
        if non_blockchain_data:
            for name, amount in non_blockchain_data:
                self.text_output.insert(tk.END, f"{name} x{amount:,}\n")
        else:
            self.text_output.insert(tk.END, "(none)\n")

        self.text_output.configure(state="disabled")
        self.text_output.yview_moveto(yview[0])

    def schedule_ui_refresh(self):
        if self.stop_event.is_set():
            return
        self.refresh_ui()
        self.root.after(1000, self.schedule_ui_refresh)

    # === API Polling ===
    def poll_api_loop(self):
        session = requests.Session()
        try:
            while not self.stop_event.is_set():
                try:
                    response = session.get(API_URL, timeout=REQUEST_TIMEOUT)
                    if response.status_code != 200:
                        raise requests.RequestException(f"Status {response.status_code}")
                    data = response.json()
                    if data.get("PlayerName"):
                        with self.lock:
                            self.player_name = data["PlayerName"]

                    adventure = data.get("LastAdventure", {})
                    adventure_name = adventure.get("AdventureName", "").strip()

                    if not adventure_name:
                        # No adventure to process; wait for next poll or shutdown
                        if self.stop_event.wait(CHECK_INTERVAL):
                            break
                        continue

                    sig = self.adventure_signature(adventure)
                    today = datetime.now(timezone.utc).date()

                    with self.lock:
                        if today != self.current_log_date:
                            # Reset daily counters at UTC midnight
                            self.reset_daily_counters_locked(today)

                        if self.last_adventure_signature is None:
                            if not self._loaded_from_log or not self.last_adventure_signature:
                                # process first seen adventure for this session
                                self.process_adventure_locked(adventure)
                            self.last_adventure_signature = sig
                        elif sig != self.last_adventure_signature:
                            self.last_adventure_signature = sig
                            self.process_adventure_locked(adventure)

                    # Save log outside of the inner lock region
                    self.save_log()

                except requests.exceptions.Timeout:
                    self.save_error_log("Error: Request timed out")
                except requests.exceptions.RequestException as e:
                    self.save_error_log(f"HTTP Error: {e}")
                except ValueError:
                    self.save_error_log("Error: Invalid JSON received")
                except Exception as e:
                    self.save_error_log(f"Unexpected Error: {e}")

                if self.stop_event.wait(CHECK_INTERVAL):
                    break
        finally:
            try:
                session.close()
            except Exception:
                pass

    # === Helpers ===
    def reset_daily_counters_locked(self, today_date):
        # assumes caller holds self.lock
        self.counter = 0
        self.blockchain_totals.clear()
        self.non_blockchain_totals.clear()
        self.adventure_counts.clear()
        self.total_character_xp = 0
        self.skill_xp_totals.clear()
        self.total_enj_value = 0.0
        self.gold_coins_total = 0
        self.total_estimated_gold = 0
        # self.last_adventure_signature = None 
        self.current_log_date = today_date
        self.start_time = datetime.now(timezone.utc)

    def reset_daily_counters(self, today_date):
        with self.lock:
            self.reset_daily_counters_locked(today_date)

    def manual_reset(self):
        today = datetime.now(timezone.utc).date()
        self.reset_daily_counters(today)
        self.save_log()

    def process_adventure_locked(self, adventure: Dict[str, Any]):
        # assumes caller holds self.lock
        self.counter += 1
        self.adventure_counts[adventure.get("AdventureName", "Unknown")] += 1
        self.total_character_xp += adventure.get("ExperienceAmount", 0)
        for xp in adventure.get("Experience", []):
            skill = xp.get("Type")
            if skill in SKILLS:
                self.skill_xp_totals[skill] += xp.get("Amount", 0)

        estimated_gold = 0
        for item in adventure.get("Items", []):
            name = item.get("Name", "Unknown")
            amount = item.get("Amount", 1)
            market_val = item.get("MarketValue", 0)

            # Gold Coins handled separately
            if name == "Gold Coins":
                self.gold_coins_total += amount
                estimated_gold += amount

            # Blockchain
            if item.get("IsBlockchain", False):
                self.blockchain_totals[name] += amount
                if market_val:
                    self.market_values[name] = market_val
                    self.total_enj_value += (market_val / 100.0) * amount

            # Non-blockchain
            if not item.get("IsBlockchain", False):
                if name in self.non_blockchain_items:
                    self.non_blockchain_totals[name] += amount
                if name not in self.non_blockchain_exclude:
                    estimated_gold += amount * market_val

        self.total_estimated_gold += estimated_gold

    def process_adventure(self, adventure: Dict[str, Any]):
        with self.lock:
            self.process_adventure_locked(adventure)

    # === Graceful Exit ===
    def on_close(self):
        self.stop_event.set()
        try:
            self.save_log()
        except Exception:
            pass
        if getattr(self, "worker_thread", None) and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.5)
        self.root.destroy()

    def install_signal_handlers(self):
        def handler(signum, frame):
            self.save_error_log(f"Received signal {signum}, shutting down gracefully.")
            self.on_close()
        for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
            if sig is not None:
                try:
                    signal.signal(sig, handler)
                except Exception:
                    pass

    def install_global_excepthook(self):
        # Log uncaught exceptions and attempt a graceful shutdown
        def _hook(exc_type, exc, tb):
            try:
                self.save_error_log(f"Uncaught exception: {exc_type.__name__}: {exc}")
                self.save_log()
            finally:
                self.stop_event.set()
                if getattr(self, "worker_thread", None) and self.worker_thread.is_alive():
                    try:
                        self.worker_thread.join(timeout=2.5)
                    except Exception:
                        pass
                # Let default excepthook print the traceback
                sys.__excepthook__(exc_type, exc, tb)
                # Ensure Tk exits
                try:
                    self.root.quit()
                except Exception:
                    pass
        sys.excepthook = _hook


if __name__ == "__main__":
    root = tk.Tk()
    app = RunCounterApp(root)
    try:
        root.mainloop()
    finally:
        # Fallback ensure save on unexpected mainloop exit
        app.stop_event.set()
        try:
            app.save_log()
        except Exception:
            pass
        if getattr(app, "worker_thread", None) and app.worker_thread.is_alive():
            try:
                app.worker_thread.join(timeout=2.5)
            except Exception:
                pass
