import tkinter as tk
import requests
import threading
import time
import json
from collections import defaultdict
from datetime import datetime, timezone
import os
import hashlib
from typing import Any, Dict, List

# === Constants ===
API_URL = "http://localhost:11990/Player"
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
        threading.Thread(target=self.poll_api_loop, daemon=True).start()

        # Schedule periodic UI refresh
        self.schedule_ui_refresh()

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

        self.reset_button = tk.Button(self.root, text="Manual Reset", command=self.manual_reset)
        self.reset_button.pack(pady=(0, 10))

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
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    # === Logging ===
    def log_filepath(self) -> str:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return os.path.join(LOG_DIR, f"runs_{today_str}.json")

    def load_log(self):
        path = self.log_filepath()
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
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
            except Exception as e:
                print(f"Failed to load log file: {e}")
                self._loaded_from_log = False
        else:
            self._loaded_from_log = False

    def save_log(self):
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
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

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
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        path = os.path.join(LOG_DIR, f"error_{datetime.now().strftime('%Y-%m-%d')}.txt")
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception as e:
            print("Failed to write error log:", e)

    # === UI Refresh ===
    def refresh_ui(self):
        now = datetime.now(timezone.utc)
        elapsed = now - self.start_time

        self.label_player_name.config(text=self.player_name)
        self.label_server_time.config(text=f"Server Time (GMT): {now:%Y-%m-%d %H:%M:%S}")
        self.label_elapsed_time.config(text=f"App Running: {str(elapsed).split('.')[0]}")

        self.text_output.configure(state="normal")
        self.text_output.delete("1.0", tk.END)

        total_gold = self.gold_coins_total
        sections = [
            ("Total Runs", f"{self.counter:,}"),
            ("Total Gold Coins", f"{total_gold:,}"),
            ("Total Estimated Gold", f"{self.total_estimated_gold:,.0f}"),
            ("Total ENJ Value", f"{self.total_enj_value:,.2f}"),
        ]

        adventures_data = sorted(self.adventure_counts.items(), key=lambda x: -x[1])
        experiences_data = [("Character XP", self.total_character_xp)] + [
            (skill, self.skill_xp_totals[skill])
            for skill in SKILLS if self.skill_xp_totals.get(skill, 0) > 0
        ]

        blockchain_data = sorted(
            ((name, amount) for name, amount in self.blockchain_totals.items() if name != "Gold Coins"),
            key=lambda x: x[0].lower()
        )

        non_blockchain_data = sorted(
            ((name, amount) for name, amount in self.non_blockchain_totals.items()
             if name in self.non_blockchain_items),
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

        insert_bold("\nTracked Non-Blockchain Items (UI only):")
        if non_blockchain_data:
            for name, amount in non_blockchain_data:
                self.text_output.insert(tk.END, f"{name} x{amount:,}\n")
        else:
            self.text_output.insert(tk.END, "(none)\n")

        self.text_output.configure(state="disabled")

    def schedule_ui_refresh(self):
        self.refresh_ui()
        self.root.after(1000, self.schedule_ui_refresh)

    # === API Polling ===
    def poll_api_loop(self):
        while True:
            try:
                response = requests.get(API_URL, timeout=REQUEST_TIMEOUT)
                if response.status_code != 200:
                    raise requests.RequestException(f"Status {response.status_code}")
                data = response.json()
                if data.get("PlayerName"):
                    self.player_name = data["PlayerName"]

                adventure = data.get("LastAdventure", {})
                sig = self.adventure_signature(adventure)
                today = datetime.now(timezone.utc).date()

                if today != self.current_log_date:
                    self.reset_daily_counters(today)

                if self.last_adventure_signature is None:
                    if not getattr(self, "_loaded_from_log", False):
                        self.process_adventure(adventure)
                    self.last_adventure_signature = sig
                elif sig != self.last_adventure_signature:
                    self.last_adventure_signature = sig
                    self.process_adventure(adventure)

                self.save_log()

            except requests.exceptions.Timeout:
                self.save_error_log("Error: Request timed out")
            except requests.exceptions.RequestException as e:
                self.save_error_log(f"HTTP Error: {e}")
            except ValueError:
                self.save_error_log("Error: Invalid JSON received")
            except Exception as e:
                self.save_error_log(f"Unexpected Error: {e}")

            time.sleep(CHECK_INTERVAL)

    # === Helpers ===
    def reset_daily_counters(self, today_date):
        self.counter = 0
        self.blockchain_totals.clear()
        self.non_blockchain_totals.clear()
        self.adventure_counts.clear()
        self.total_character_xp = 0
        self.skill_xp_totals.clear()
        self.total_enj_value = 0.0
        self.gold_coins_total = 0
        self.total_estimated_gold = 0
        #self.last_adventure_signature = None
        self.current_log_date = today_date
        self.start_time = datetime.now(timezone.utc)
    
    def manual_reset(self):
        today = datetime.now(timezone.utc).date()
        self.reset_daily_counters(today)

    def process_adventure(self, adventure: Dict[str, Any]):
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
                # UI/persistence only for configured items
                if name in self.non_blockchain_items:
                    self.non_blockchain_totals[name] += amount
                # Include in estimated gold unless excluded
                if name not in self.non_blockchain_exclude:
                    estimated_gold += amount * market_val

        self.total_estimated_gold += estimated_gold


if __name__ == "__main__":
    root = tk.Tk()
    app = RunCounterApp(root)
    root.mainloop()
