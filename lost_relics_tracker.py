import tkinter as tk
import requests
import threading
import time
import json
from collections import defaultdict
from datetime import datetime, timedelta
import os

API_URL = "http://localhost:11990/Player"
CHECK_INTERVAL = 5  # seconds
LOG_DIR = "run_logs"

class RunCounterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Lost Relics Daily Tracker")
        self.root.geometry("350x380")
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)

        self.counter = 0
        self.blockchain_totals = defaultdict(int)
        self.adventure_counts = defaultdict(int)
        self.total_character_xp = 0
        self.skill_xp_totals = defaultdict(int)
        self.last_adventure_json = None
        self.player_name = "Unknown Player"
        self.start_time = datetime.now()
        self.current_log_date = datetime.now().date()

        # Player name label
        self.label_player_name = tk.Label(root, text=self.player_name, font=("Arial", 20, "bold"))
        self.label_player_name.pack(pady=(10,0))

        # System time label
        self.label_system_time = tk.Label(root, font=("Arial", 10))
        self.label_system_time.pack()

        # Elapsed time label
        self.label_elapsed_time = tk.Label(root, font=("Arial", 10))
        self.label_elapsed_time.pack(pady=(0,10))

        # Developer label
        self.credit_label = tk.Label(root, text="Developed by Capoeira", font=("Arial", 8), fg="gray")
        self.credit_label.pack(side="bottom", pady=(0, 5))

        # Frame + Scrollbar + Text for main content
        frame = tk.Frame(root)
        frame.pack(fill="both", expand=True, padx=5, pady=5)

        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")

        self.text_output = tk.Text(
            frame, font=("Arial", 11), wrap="word",
            yscrollcommand=scrollbar.set, height=18, width=42
        )
        self.text_output.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.text_output.yview)
        self.text_output.configure(state="disabled")

        # Ensure log directory exists
        os.makedirs(LOG_DIR, exist_ok=True)

        # Load today's log if exists
        self.load_log()

        # Initialize labels immediately
        self.update_time_labels()
        self.update_text_output()

        # Start polling thread
        threading.Thread(target=self.poll_api_loop, daemon=True).start()

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
                    self.adventure_counts = defaultdict(int, data.get("adventure_counts", {}))
                    self.total_character_xp = data.get("total_character_xp", 0)
                    self.skill_xp_totals = defaultdict(int, data.get("skill_xp_totals", {}))
                    self.player_name = data.get("player_name", "Unknown Player")
                    self.current_log_date = datetime.now().date()
                    self.label_player_name.config(text=self.player_name)
                    print(f"Loaded log from {path}")
            except Exception as e:
                print(f"Failed to load log file: {e}")

    def save_log(self):
        path = self.log_filepath()
        data = {
            "runs": self.counter,
            "blockchain_totals": dict(self.blockchain_totals),
            "adventure_counts": dict(self.adventure_counts),
            "total_character_xp": self.total_character_xp,
            "skill_xp_totals": dict(self.skill_xp_totals),
            "player_name": self.player_name,
        }
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Failed to save log file: {e}")

    def update_time_labels(self):
        now = datetime.now()
        self.label_system_time.config(text=f"System Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")

        elapsed = now - self.start_time
        elapsed_str = str(elapsed).split('.')[0]  # Remove microseconds
        self.label_elapsed_time.config(text=f"App Running: {elapsed_str}")

    def update_text_output(self):
        # Build content section titles

        self.text_output.configure(state="normal")
        self.text_output.delete("1.0", tk.END)

        def insert_bold_line(text):
            self.text_output.insert(tk.END, text + "\n", "bold")

        # Total runs
        insert_bold_line(f"Total Runs: {self.counter}")

        # Adventures by run count
        insert_bold_line("\nAdventures:")
        if self.adventure_counts:
            sorted_adventures = sorted(self.adventure_counts.items(), key=lambda x: -x[1])
            for name, count in sorted_adventures:
                self.text_output.insert(tk.END, f"{name} x{count}\n")
        else:
            self.text_output.insert(tk.END, "(no adventures)\n")

        # Experience section
        insert_bold_line("\nExperience:")
        self.text_output.insert(tk.END, f"Character XP: {self.total_character_xp}\n")
        for skill in ["Fishing", "Mining", "Scavenging", "Woodcutting"]:
            xp = self.skill_xp_totals.get(skill, 0)
            if xp > 0:
                self.text_output.insert(tk.END, f"{skill}: {xp}\n")

        # Blockchain items 
        insert_bold_line("\nBlockchain Items:")
        if self.blockchain_totals:
            sorted_items = sorted(self.blockchain_totals.items(), key=lambda x: x[0].lower())
            for name, amount in sorted_items:
                self.text_output.insert(tk.END, f"{name} x{amount}\n")
        else:
            self.text_output.insert(tk.END, "(none)\n")

        self.text_output.configure(state="disabled")
        # Add tag config for bold
        self.text_output.tag_configure("bold", font=("Arial", 11, "bold"))

    def poll_api_loop(self):
        while True:
            try:
                response = requests.get(API_URL)
                if response.status_code == 200:
                    data = response.json()
                    player_name = data.get("PlayerName", "Unknown Player")
                    if player_name != self.player_name:
                        self.player_name = player_name
                        self.root.after(0, lambda: self.label_player_name.config(text=player_name))
                    adventure = data.get("LastAdventure", {})
                    current_adventure_json = json.dumps(adventure, sort_keys=True)

                    # Check if date changed (midnight reset)
                    now_date = datetime.now().date()
                    if now_date != self.current_log_date:
                        # New day - reset all counts
                        self.counter = 0
                        self.blockchain_totals.clear()
                        self.adventure_counts.clear()
                        self.total_character_xp = 0
                        self.skill_xp_totals.clear()
                        self.last_adventure_json = None
                        self.current_log_date = now_date
                        self.start_time = datetime.now()
                        print("New day detected, counters reset.")

                    if self.last_adventure_json is None:
                        self.last_adventure_json = current_adventure_json
                    elif current_adventure_json != self.last_adventure_json:
                        self.counter += 1
                        self.last_adventure_json = current_adventure_json

                        # Player name
                        new_name = data.get("PlayerName", "Unknown Player")
                        if new_name != self.player_name:
                            self.player_name = new_name
                            self.root.after(0, lambda: self.label_player_name.config(text=new_name))

                        # Adventure name count
                        adventure_name = adventure.get("AdventureName", "Unknown")
                        self.adventure_counts[adventure_name] += 1

                        # Add character XP
                        self.total_character_xp += adventure.get("ExperienceAmount", 0)

                        # Add skill XP
                        for xp_entry in adventure.get("Experience", []):
                            skill = xp_entry.get("Type")
                            amount = xp_entry.get("Amount", 0)
                            if skill in {"Fishing", "Mining", "Scavenging", "Woodcutting"}:
                                self.skill_xp_totals[skill] += amount

                        # Add blockchain items
                        items = adventure.get("Items", [])
                        for item in items:
                            if item.get("IsBlockchain", False):
                                name = item.get("Name", "Unknown")
                                amount = item.get("Amount", 1)
                                self.blockchain_totals[name] += amount

                    self.update_time_labels()
                    self.update_text_output()
                    self.save_log()

            except Exception as e:
                print("Error:", e)

            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    root = tk.Tk()
    app = RunCounterApp(root)
    root.mainloop()
