import tkinter as tk
import requests
import threading
import time
import json
from collections import defaultdict
from datetime import datetime
import os

API_URL = "http://localhost:11990/Player"
CHECK_INTERVAL = 5  # seconds
LOG_DIR = "run_logs"
CONFIG_FILE = "non_blockchain_config.json"

class RunCounterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Lost Relics Daily Tracker")
        self.root.geometry("350x600")
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)

        # Default to dark mode
        self.dark_mode = True  

        self.counter = 0
        self.blockchain_totals = defaultdict(int)   
        self.market_values = defaultdict(float)     
        self.adventure_counts = defaultdict(int)
        self.total_character_xp = 0
        self.skill_xp_totals = defaultdict(int)
        self.non_blockchain_totals = defaultdict(int)  
        self.total_enj_value = 0.0
        self.last_adventure_json = None
        self.player_name = "Unknown Player"
        self.start_time = datetime.now()
        self.current_log_date = datetime.now().date()

        # Load non-blockchain config (create if not exists)
        self.non_blockchain_items = self.load_config()

        # === UI Labels ===
        self.label_player_name = tk.Label(root, text=self.player_name, font=("Arial", 20, "bold"))
        self.label_player_name.pack(pady=(10, 0))

        self.label_system_time = tk.Label(root, font=("Arial", 10))
        self.label_system_time.pack()

        self.label_elapsed_time = tk.Label(root, font=("Arial", 10))
        self.label_elapsed_time.pack(pady=(0, 5))

        # Toggle Theme Button
        self.toggle_button = tk.Button(root, text="Toggle Theme", command=self.toggle_theme)
        self.toggle_button.pack(pady=(0, 10))

        self.credit_label = tk.Label(root, text="Developed by Capoeira", font=("Arial", 8))
        self.credit_label.pack(side="bottom", pady=(0, 5))

        # === Text Output + Scrollbar ===
        frame = tk.Frame(root)
        frame.pack(fill="both", expand=True, padx=5, pady=5)

        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")

        self.text_output = tk.Text(
            frame, font=("Arial", 11), wrap="word",
            yscrollcommand=scrollbar.set, height=28, width=42,
            borderwidth=0
        )
        self.text_output.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.text_output.yview)
        self.text_output.configure(state="disabled")
        self.text_output.tag_configure("bold", font=("Arial", 11, "bold"))

        # Apply initial theme
        self.apply_theme()

        # Ensure log directory exists
        os.makedirs(LOG_DIR, exist_ok=True)

        # Load today's log if exists
        self.load_log()

        # Initial updates
        self.update_time_labels()
        self.update_text_output()

        # Start polling thread
        threading.Thread(target=self.poll_api_loop, daemon=True).start()

    # === Config Handling ===
    def load_config(self):
        if os.path.isfile(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    return json.load(f)
            except:
                return ["Deepsea Coffer", "Golden Grind Chest", "Frostfall Shard"]
        else:
            # Create file with default items
            default_items = ["Deepsea Coffer", "Golden Grind Chest", "Frostfall Shard"]
            try:
                with open(CONFIG_FILE, "w") as f:
                    json.dump(default_items, f, indent=2)
            except Exception as e:
                print("Failed to create default config:", e)
            return default_items

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.non_blockchain_items, f, indent=2)
        except Exception as e:
            print("Failed to save config:", e)

    # === Theme Handling ===
    def apply_theme(self):
        if self.dark_mode:
            bg_color = "#1e1e1e"
            fg_color = "#d4d4d4"
            select_bg = "#444444"
            credit_color = "#888888"
        else:
            bg_color = "#ffffff"
            fg_color = "#000000"
            select_bg = "#cce6ff"
            credit_color = "gray"

        self.root.configure(bg=bg_color)
        self.label_player_name.configure(bg=bg_color, fg=fg_color)
        self.label_system_time.configure(bg=bg_color, fg=fg_color)
        self.label_elapsed_time.configure(bg=bg_color, fg=fg_color)
        self.toggle_button.configure(bg=bg_color, fg=fg_color, activebackground=select_bg, relief="raised")
        self.credit_label.configure(bg=bg_color, fg=credit_color)
        self.text_output.configure(bg=bg_color, fg=fg_color, insertbackground=fg_color, selectbackground=select_bg)

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    # === Logging ===
    def log_filepath(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(LOG_DIR, f"runs_{today_str}.json")

    def load_log(self):
        path = self.log_filepath()
        if os.path.isfile(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                    self.counter = data.get("runs", 0)
                    self.blockchain_totals = defaultdict(int, data.get("blockchain_totals", {}))
                    self.non_blockchain_totals = defaultdict(int, data.get("non_blockchain_totals", {}))
                    self.adventure_counts = defaultdict(int, data.get("adventure_counts", {}))
                    self.total_character_xp = data.get("total_character_xp", 0)
                    self.skill_xp_totals = defaultdict(int, data.get("skill_xp_totals", {}))
                    self.player_name = data.get("player_name", "Unknown Player")
                    self.total_enj_value = data.get("total_enj_value", 0.0)
                    self.current_log_date = datetime.now().date()
                    self.label_player_name.config(text=self.player_name)
            except Exception as e:
                print(f"Failed to load log file: {e}")

    def save_log(self):
        path = self.log_filepath()
        data = {
            "runs": self.counter,
            "blockchain_totals": dict(self.blockchain_totals),
            "non_blockchain_totals": dict(self.non_blockchain_totals),
            "adventure_counts": dict(self.adventure_counts),
            "total_character_xp": self.total_character_xp,
            "skill_xp_totals": dict(self.skill_xp_totals),
            "player_name": self.player_name,
            "total_enj_value": self.total_enj_value,
        }
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Failed to save log file: {e}")

    # === UI Updates ===
    def update_time_labels(self):
        now = datetime.now()
        self.label_system_time.config(text=f"System Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        elapsed = now - self.start_time
        self.label_elapsed_time.config(text=f"App Running: {str(elapsed).split('.')[0]}")

    def update_text_output(self):
        self.text_output.configure(state="normal")
        self.text_output.delete("1.0", tk.END)

        def insert_bold(text): 
            self.text_output.insert(tk.END, text + "\n", "bold")

        insert_bold(f"Total Runs: {self.counter:,}")

        total_gold = self.blockchain_totals.get("Gold Coins", 0)
        self.text_output.insert(tk.END, f"Total Gold Coins: {total_gold:,}\n")
        self.text_output.insert(tk.END, f"Total ENJ Value: {self.total_enj_value:,.2f}\n")

        insert_bold("\nAdventures:")
        if self.adventure_counts:
            for name, count in sorted(self.adventure_counts.items(), key=lambda x: -x[1]):
                self.text_output.insert(tk.END, f"{name} x{count:,}\n")
        else:
            self.text_output.insert(tk.END, "(no adventures)\n")

        insert_bold("\nExperience:")
        self.text_output.insert(tk.END, f"Character XP: {self.total_character_xp:,}\n")
        for skill in ["Fishing", "Mining", "Scavenging", "Woodcutting"]:
            xp = self.skill_xp_totals.get(skill, 0)
            if xp > 0:
                self.text_output.insert(tk.END, f"{skill}: {xp:,}\n")

        insert_bold("\nBlockchain Items:")
        blockchain_items = {k: v for k, v in self.blockchain_totals.items() if k != "Gold Coins"}
        if blockchain_items:
            for name, amount in sorted(blockchain_items.items(), key=lambda x: x[0].lower()):
                self.text_output.insert(tk.END, f"{name} x{amount:,}\n")
        else:
            self.text_output.insert(tk.END, "(none)\n")

        insert_bold("\nTracked Non-Blockchain Items:")
        if self.non_blockchain_totals:
            for name, amount in sorted(self.non_blockchain_totals.items(), key=lambda x: x[0].lower()):
                self.text_output.insert(tk.END, f"{name} x{amount:,}\n")
        else:
            self.text_output.insert(tk.END, "(none)\n")

        self.text_output.configure(state="disabled")

    # === API Polling ===
    def poll_api_loop(self):
        while True:
            try:
                response = requests.get(API_URL)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("PlayerName") and data["PlayerName"] != self.player_name:
                        self.player_name = data["PlayerName"]
                        self.root.after(0, lambda: self.label_player_name.config(text=self.player_name))

                    adventure = data.get("LastAdventure", {})
                    current_adventure_json = json.dumps(adventure, sort_keys=True)

                    now_date = datetime.now().date()
                    if now_date != self.current_log_date:
                        self.counter = 0
                        self.blockchain_totals.clear()
                        self.non_blockchain_totals.clear()
                        self.adventure_counts.clear()
                        self.total_character_xp = 0
                        self.skill_xp_totals.clear()
                        self.total_enj_value = 0.0
                        self.last_adventure_json = None
                        self.current_log_date = now_date
                        self.start_time = datetime.now()
                        print("New day detected, counters reset.")

                    if self.last_adventure_json is None:
                        self.last_adventure_json = current_adventure_json
                    elif current_adventure_json != self.last_adventure_json:
                        self.counter += 1
                        self.last_adventure_json = current_adventure_json

                        self.adventure_counts[adventure.get("AdventureName", "Unknown")] += 1
                        self.total_character_xp += adventure.get("ExperienceAmount", 0)
                        for xp in adventure.get("Experience", []):
                            skill = xp.get("Type")
                            amount = xp.get("Amount", 0)
                            if skill in {"Fishing", "Mining", "Scavenging", "Woodcutting"}:
                                self.skill_xp_totals[skill] += amount

                        for item in adventure.get("Items", []):
                            name = item.get("Name", "Unknown")
                            amount = item.get("Amount", 1)
                            market_val = item.get("MarketValue", 0)

                            # Always track Gold Coins
                            if name == "Gold Coins":
                                self.blockchain_totals[name] += amount

                            # Only track blockchain items for ENJ
                            if item.get("IsBlockchain", False):
                                self.blockchain_totals[name] += amount
                                if market_val:
                                    self.market_values[name] = market_val
                                    self.total_enj_value += (market_val / 100.0) * amount

                            # Track chosen non-blockchain items
                            if not item.get("IsBlockchain", False) and name in self.non_blockchain_items:
                                self.non_blockchain_totals[name] += amount

                    self.update_time_labels()
                    self.update_text_output()
                    self.save_log()

            except Exception as e:
                print("API Error:", e)

            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    root = tk.Tk()
    app = RunCounterApp(root)
    root.mainloop()
