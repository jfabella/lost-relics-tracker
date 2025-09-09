import tkinter as tk
from tkinter import simpledialog, messagebox
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
from openpyxl import Workbook
from tkinter import filedialog, messagebox

def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS  
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:11990/Player")
APP_VERSION = "0.1.0"
CHECK_INTERVAL = 5
REQUEST_TIMEOUT = 10
LOG_DIR = "run_logs"
SETTINGS_FILE = "settings.conf"
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
        self.settings = self.load_settings()
        self.load_log()
    
    def load_settings(self) -> dict:
        default_settings = {
            "window_width": 350,
            "window_height": 600,
            "dark_mode": True,
            "show_totals": {
                "runs": True,
                "gold": True,
                "estimated_gold": True,
                "enj": True,
            },
            "show_sections": {
                "adventures": True,
                "experience": True,
                "blockchain": True,
                "non_blockchain": True,
            },
        }
        if os.path.isfile(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return {**default_settings, **json.load(f)}
            except Exception:
                pass
        return default_settings

    def save_settings(self, settings: dict):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2)
        except Exception:
            pass    

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

    def summarize_logs(self, start_date: str, end_date: str) -> str:
        #"""Summarize logs from start_date to end_date (format: YYYY-MM-DD)."""
        summary = {
            "Total Runs": 0,
            "Total Gold Coins": 0,
            "Total Estimated Gold": 0,
            "Total ENJ Value": 0.0,
            "Total Character XP": 0,
            "Skill XP Totals": defaultdict(int),
            "Adventure Counts": defaultdict(int),
            "Blockchain Totals": defaultdict(int),
            "Non-Blockchain Totals": defaultdict(int),
        }

        try:
            for fname in os.listdir(self.log_dir):
                if fname.startswith("runs_") and fname.endswith(".json"):
                    date_part = fname[5:-5]
                    if start_date <= date_part <= end_date:
                        with open(os.path.join(self.log_dir, fname), "r", encoding="utf-8") as f:
                            data = json.load(f)

                        summary["Total Runs"] += data.get("runs", 0)
                        summary["Total Gold Coins"] += data.get("gold_coins_total", 0)
                        summary["Total Estimated Gold"] += data.get("total_estimated_gold", 0)
                        summary["Total ENJ Value"] += data.get("total_enj_value", 0.0)
                        summary["Total Character XP"] += data.get("total_character_xp", 0)

                        for k, v in data.get("skill_xp_totals", {}).items():
                            summary["Skill XP Totals"][k] += v
                        for k, v in data.get("adventure_counts", {}).items():
                            summary["Adventure Counts"][k] += v
                        for k, v in data.get("blockchain_totals", {}).items():
                            summary["Blockchain Totals"][k] += v
                        for k, v in data.get("non_blockchain_totals", {}).items():
                            summary["Non-Blockchain Totals"][k] += v
        except Exception as e:
            return f"Error summarizing logs: {e}"

        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            elapsed_days = max((end_dt - start_dt).days + 1, 1)
        except Exception:
            elapsed_days = 1
 
        lines = [
            f"Total Runs: {summary['Total Runs']:,}",
            f"Total Gold Coins: {summary['Total Gold Coins']:,}",
            f"Total Estimated Gold: {summary['Total Estimated Gold']:,}",
            f"Total ENJ Value: {summary['Total ENJ Value']:.2f}",
            f"Total Character XP: {summary['Total Character XP']:,}\n",
            f"Daily Averages:",
            f"  Avg Runs per Day: {summary['Total Runs'] / elapsed_days:.2f}",
            f"  Avg Estimated Gold per Day: {summary['Total Estimated Gold'] / elapsed_days:.2f}",
            f"  Avg ENJ Value per Day: {summary['Total ENJ Value'] / elapsed_days:.4f}",
            f"  Avg Character XP per Day: {summary['Total Character XP'] / elapsed_days:.0f}",
        ]
        for skill, xp in summary["Skill XP Totals"].items():
            lines.append(f"  Avg {skill} XP per Day: {xp / elapsed_days:.0f}")

        lines.append("\nSkill XP Totals:")
        for k, v in summary["Skill XP Totals"].items():
            lines.append(f"  {k}: {v:,}")
        lines.append("\nAdventures:")
        for k, v in summary["Adventure Counts"].items():
            lines.append(f"  {k}: {v:,}")
        lines.append("\nBlockchain Items:")
        for k, v in summary["Blockchain Totals"].items():
            lines.append(f"  {k}: {v:,}")
        lines.append("\nNon-Blockchain Items:")
        for k, v in summary["Non-Blockchain Totals"].items():
            lines.append(f"  {k}: {v:,}")

        return "\n".join(lines)


    def export_summary_to_excel(self, summary: dict, start_date: str, end_date: str):
        wb = Workbook()
        ws = wb.active
        ws.title = "Summary Report"

        ws.append(["Lost Relics Adventure Report"])
        ws.append([f"From {start_date} to {end_date}"])
        ws.append([])

        ws.append(["Totals"])
        ws.append(["Total Runs", summary["Total Runs"]])
        ws.append(["Total Gold Coins", summary["Total Gold Coins"]])
        ws.append(["Total Estimated Gold", summary["Total Estimated Gold"]])
        ws.append(["Total ENJ Value", summary["Total ENJ Value"]])
        ws.append(["Total Character XP", summary["Total Character XP"]])
        ws.append([])

        ws.append(["Skill XP Totals"])
        for k, v in summary["Skill XP Totals"].items():
            ws.append([k, v])
        ws.append([])

        ws.append(["Adventures"])
        for k, v in summary["Adventure Counts"].items():
            ws.append([k, v])
        ws.append([])

        ws.append(["Blockchain Items"])
        for k, v in summary["Blockchain Totals"].items():
            ws.append([k, v])
        ws.append([])

        ws.append(["Non-Blockchain Items"])
        for k, v in summary["Non-Blockchain Totals"].items():
            ws.append([k, v])

        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx")],
            title="Save Report As"
        )
        if file_path:
            wb.save(file_path)
            messagebox.showinfo("Export Successful", f"Report saved to {file_path}")

class TrackerUI:
    def __init__(self, root: tk.Tk, dm: DataManager):
        self.root, self.dm = root, dm
        settings = dm.settings  
        self.currency_var = tk.StringVar(value=self.dm.settings.get("currency", "usd"))
        self.dark_mode = settings.get("dark_mode", True)

        self.show_totals = {
            "runs": tk.BooleanVar(value=settings["show_totals"].get("runs", True)),
            "gold": tk.BooleanVar(value=settings["show_totals"].get("gold", True)),
            "estimated_gold": tk.BooleanVar(value=settings["show_totals"].get("estimated_gold", True)),
            "enj": tk.BooleanVar(value=settings["show_totals"].get("enj", True)),
            "enjin_price": tk.BooleanVar(value=True),
        }
        self.show_sections = {
            "adventures": tk.BooleanVar(value=settings["show_sections"].get("adventures", True)),
            "experience": tk.BooleanVar(value=settings["show_sections"].get("experience", True)),
            "blockchain": tk.BooleanVar(value=settings["show_sections"].get("blockchain", True)),
            "non_blockchain": tk.BooleanVar(value=settings["show_sections"].get("non_blockchain", True)),
        }

        self.enjin_price_text = "Enjin Price: Loading..."
        self.build_ui(settings)
        self.build_menu()
        self.apply_theme()
        self.update_enjin_price()

    def build_ui(self, settings: dict):
        self.root.title("Lost Relics Daily Tracker")
        w = settings.get("window_width", 350)
        h = settings.get("window_height", 600)
        self.root.geometry(f"{w}x{h}")
        self.root.resizable(True, True)
        self.root.attributes('-topmost', True)
        self.label_player_name = tk.Label(self.root, text=self.dm.player_name, font=("Calibri", 20, "bold"))
        self.label_player_name.pack(pady=(10, 0))
        self.label_server_time = tk.Label(self.root, font=("Calibri", 10)); self.label_server_time.pack()
        self.label_elapsed_time = tk.Label(self.root, font=("Calibri", 10)); self.label_elapsed_time.pack(pady=(0, 5))
        #self.toggle_button = tk.Button(self.root, text="Toggle Theme", command=self.toggle_theme)
        #self.toggle_button.pack(pady=(0, 10))
        self.enjin_label = tk.Label(self.root, text="Enjin Price: Loading...", font=("Calibri", 11, "bold"))
        self.enjin_label.pack(pady=(0, 5))
        self.credit_label = tk.Label(self.root, text="Developed by Capoeira", font=("Calibri", 8))
        self.credit_label.pack(side="bottom", pady=(0, 5))
        self.version_label = tk.Label(self.root, text=f"Version {APP_VERSION}", font=("Calibri", 8))
        self.version_label.pack(side="bottom", pady=(0, 5))
        frame = tk.Frame(self.root); frame.pack(fill="both", expand=True, padx=5, pady=5)
        scrollbar = tk.Scrollbar(frame); scrollbar.pack(side="right", fill="y")
        self.text_output = tk.Text(frame, font=("Calibri", 11), wrap="word", yscrollcommand=scrollbar.set, height=28, width=42, borderwidth=0)
        self.text_output.pack(side="left", fill="both", expand=True); scrollbar.config(command=self.text_output.yview)
        self.text_output.configure(state="disabled"); self.text_output.tag_configure("bold", font=("Calibri", 11, "bold"))

    def build_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Summarize Runs", command=self.summarize_runs_popup)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=0)

        totals_menu = tk.Menu(view_menu, tearoff=0)
        totals_menu.add_checkbutton(label="Enjin Price", variable=self.show_totals["enjin_price"], command=self.refresh_ui)
        totals_menu.add_checkbutton(label="Total Runs", variable=self.show_totals["runs"], command=self.refresh_ui)
        totals_menu.add_checkbutton(label="Total Gold Coins", variable=self.show_totals["gold"], command=self.refresh_ui)
        totals_menu.add_checkbutton(label="Total Estimated Gold", variable=self.show_totals["estimated_gold"], command=self.refresh_ui)
        totals_menu.add_checkbutton(label="Total ENJ Value", variable=self.show_totals["enj"], command=self.refresh_ui)
        view_menu.add_cascade(label="Totals", menu=totals_menu)

        sections_menu = tk.Menu(view_menu, tearoff=0)
        sections_menu.add_checkbutton(label="Adventures", variable=self.show_sections["adventures"], command=self.refresh_ui)
        sections_menu.add_checkbutton(label="Experience", variable=self.show_sections["experience"], command=self.refresh_ui)
        sections_menu.add_checkbutton(label="Blockchain Items", variable=self.show_sections["blockchain"], command=self.refresh_ui)
        sections_menu.add_checkbutton(label="Non-Blockchain Items", variable=self.show_sections["non_blockchain"], command=self.refresh_ui)
        view_menu.add_cascade(label="Sections", menu=sections_menu)

        currency_menu = tk.Menu(view_menu, tearoff=0)
        for cur in ["usd", "php", "eur", "gbp"]:
            currency_menu.add_radiobutton(
                label=cur.upper(),
                variable=self.currency_var,
                value=cur,
                command=lambda c=cur: self.update_currency(c)
            )
        view_menu.add_cascade(label="Currency", menu=currency_menu)

        menubar.add_cascade(label="View", menu=view_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Toggle Theme", command=self.toggle_theme)
        menubar.add_cascade(label="Settings", menu=settings_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Donate / Support", command=self.show_donate)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

    def show_about(self):
        messagebox.showinfo("About", "Lost Relics Daily Tracker\nDeveloped by Capoeira")

    def show_donate(self):
        donate_window = tk.Toplevel(self.root)
        donate_window.title("Donate / Support")
        donate_window.resizable(True, True)  

        width, height = 400, 400 
        screen_w = donate_window.winfo_screenwidth()
        screen_h = donate_window.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        donate_window.geometry(f"{width}x{height}+{x}+{y}")

        bg = "#ffffff" if not self.dark_mode else "#1e1e1e"
        fg = "#000000" if not self.dark_mode else "#d4d4d4"
        donate_window.configure(bg=bg)

        tk.Label(donate_window, text="Support / Donations", font=("Calibri", 14, "bold"), bg=bg, fg=fg).pack(pady=(10, 5))

        tk.Label(
            donate_window,
            text="If you enjoy this tool and want to support its development, you can donate:\n\nEnjin Matrixchain:",
            font=("Calibri", 11),
            bg=bg,
            fg=fg,
            justify="left",
            wraplength=380
        ).pack(pady=(0, 5))

        address = "efQUbKs6THBXz5iqgbq6xueTicyF35TepybZY36RFQwZ5gRm6"
        address_entry = tk.Entry(donate_window, font=("Calibri", 11), bg="#f0f0f0", fg="#000000")
        address_entry.pack(pady=(0, 5), fill="x", padx=10)
        address_entry.insert(0, address)
        address_entry.config(state="readonly")

        def copy_address():
            donate_window.clipboard_clear()
            donate_window.clipboard_append(address)
            messagebox.showinfo("Copied", "Address copied to clipboard!")

        tk.Button(donate_window, text="Copy Address", command=copy_address).pack(pady=(0, 10))

        try:
            from PIL import Image, ImageTk

            qr_img_path = resource_path("images/qr_matrixchain.png")
            if os.path.isfile(qr_img_path):
                qr_img = Image.open(qr_img_path)
                qr_photo = ImageTk.PhotoImage(qr_img)
                tk.Label(donate_window, image=qr_photo, bg=bg).pack()
                donate_window.qr_photo = qr_photo
            else:
                tk.Label(donate_window, text="QR Image not found", font=("Calibri", 10), bg=bg, fg="red").pack()
        except Exception as e:
            tk.Label(donate_window, text=f"QR Image error: {e}", font=("Calibri", 10), bg=bg, fg="red").pack()

    def summarize_runs_popup(self):
        start_date = simpledialog.askstring("Summarize Runs", "Start Date (YYYY-MM-DD):")
        if not start_date:
            return
        end_date = simpledialog.askstring("Summarize Runs", "End Date (YYYY-MM-DD):")
        if not end_date:
            return

        summary = self.dm.summarize_logs(start_date, end_date)

        summary_window = tk.Toplevel(self.root)
        summary_window.title("Summary of Runs")
        screen_w = summary_window.winfo_screenwidth()
        screen_h = summary_window.winfo_screenheight()
        width = 500
        height = screen_h
        x = (screen_w - width) // 2  
        y = 0  
        summary_window.geometry(f"{width}x{height}+{x}+{y}")
        summary_window.resizable(True, True)

        if self.dark_mode:
            bg, fg, select_bg, credit_color = "#080808", "#d4d4d4", "#99D1AE", "#888888"
        else:
            bg, fg, select_bg, credit_color = "#ffffff", "#000000", "#cce6ff", "gray"

        summary_window.configure(bg=bg)

        title_label = tk.Label(
            summary_window,
            text="Lost Relics Adventure Report",
            font=("Calibri", 16, "bold"),
            bg=bg,
            fg=fg
        )
        title_label.pack(pady=(10, 0))

        date_label = tk.Label(
            summary_window,
            text=f"From {start_date} to {end_date}",
            font=("Calibri", 11),
            bg=bg,
            fg=fg
        )
        date_label.pack(pady=(0, 10))

        btn_frame = tk.Frame(summary_window, bg=bg)
        btn_frame.pack(pady=8)

        export_btn = tk.Button(
            summary_window,
            text="Download as Excel",
            #command=lambda: self.dm.export_summary_to_excel(summary, start_date, end_date),
            bg=bg, fg=fg,
            activebackground=select_bg,
            relief="groove"
        )
        export_btn.pack(pady=(0, 10))

        frame = tk.Frame(summary_window, bg=bg)
        frame.pack(fill="both", expand=True, padx=10, pady=5)

        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")

        text_area = tk.Text(
            frame,
            wrap="word",
            yscrollcommand=scrollbar.set,
            font=("Calibri", 11),
            bg=bg,
            fg=fg,
            insertbackground=fg,
            selectbackground=select_bg,
            relief="flat",
            borderwidth=0
        )
        text_area.insert("1.0", summary)
        text_area.configure(state="disabled")
        text_area.pack(side="left", fill="both", expand=True)

        scrollbar.config(command=text_area.yview)

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.dm.settings["dark_mode"] = self.dark_mode
        self.dm.save_settings(self.dm.settings)
        self.apply_theme()

    def apply_theme(self):
        if self.dark_mode:
            bg, fg, select_bg, credit_color = "#1e1e1e", "#d4d4d4", "#444444", "#888888"
        else:
            bg, fg, select_bg, credit_color = "#ffffff", "#000000", "#cce6ff", "gray"

        widgets = [
            self.root,
            self.label_player_name,
            self.label_server_time,
            self.label_elapsed_time,
            self.credit_label,
            self.version_label,
            self.enjin_label,
            self.text_output
        ]

        for w in widgets:
            w.configure(bg=bg)

        #self.enjin_label.config(bg=self.root["bg"])
        self.label_player_name.configure(fg=fg)
        self.label_server_time.configure(fg=fg)
        self.label_elapsed_time.configure(fg=fg)
        self.version_label.configure(fg=credit_color)
        self.credit_label.configure(fg=credit_color)
        self.text_output.configure(fg=fg, insertbackground=fg, selectbackground=select_bg)

    def update_enjin_price(self):
        try:
            vs_currency = self.currency_var.get()

            response = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": "enjincoin",
                    "vs_currencies": vs_currency,
                    "include_24hr_change": "true"
                },
                timeout=5
            )
            data = response.json().get("enjincoin", {})

            price = data.get(vs_currency)
            change = data.get(f"{vs_currency}_24h_change", 0.0)
            cur = vs_currency.upper()

            if price is None:
                self.enjin_label.config(text=f"Enjin Price: N/A ({cur})", fg="black")
            else:
                price_str = f"{price:,.3f}"
                arrow = "▲" if change >= 0 else "▼"
                color = "limegreen" if change >= 0 else "red"

                self.enjin_label.config(
                    text=f"Enjin Price: {price_str} {cur} {arrow} {abs(change):.1f}% (24h)",
                    fg=color
                )

        except requests.exceptions.HTTPError as e:
            if hasattr(e, "response") and e.response is not None and e.response.status_code == 429:
                self.enjin_label.config(text="Enjin Price: Rate limit exceeded", fg="black")
            else:
                self.enjin_label.config(text="Enjin Price: Error", fg="black")
        except Exception:
            self.enjin_label.config(text="Enjin Price: Error", fg="black")
        finally:
            self.root.after(600000, self.update_enjin_price)  # refresh every 10 min

    def update_currency(self, new_currency: str):
        self.currency_var.set(new_currency)
        self.dm.settings["currency"] = new_currency
        self.dm.save_settings(self.dm.settings)  
        self.update_enjin_price()
        self.dm.settings["currency"] = new_currency
        self.dm.save_settings(self.dm.settings)

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

        now = datetime.now(timezone.utc)
        elapsed = now - snap["start_time"]
        self.label_player_name.config(text=snap["player_name"])
        self.label_server_time.config(text=f"Server Time (GMT): {now:%Y-%m-%d %H:%M:%S}")
        self.label_elapsed_time.config(text=f"App Running: {str(elapsed).split('.')[0]}")
        yview = self.text_output.yview()
        self.text_output.configure(state="normal")
        self.text_output.delete("1.0", tk.END)

        def bold(t): self.text_output.insert(tk.END, t + "\n", "bold")

        #if self.show_totals["enjin_price"].get():
        #    bold(self.enjin_price_text)
        #    self.text_output.insert(tk.END, "\n")
        if self.show_totals["runs"].get():
            bold(f"Total Runs: {snap['counter']:,}")
        if self.show_totals["gold"].get():
            bold(f"Total Gold Coins: {snap['gold_coins_total']:,}")
        if self.show_totals["estimated_gold"].get():
            bold(f"Total Estimated Gold: {snap['total_estimated_gold']:,.0f}")
        if self.show_totals["enj"].get():
            bold(f"Total ENJ Value: {snap['total_enj_value']:,.2f}")
        self.text_output.insert(tk.END, "\n")

        if self.show_sections["adventures"].get():
            bold("Adventures:")
            if snap["adventure_counts"]:
                for n, c in sorted(snap["adventure_counts"].items(), key=lambda x: -x[1]):
                    self.text_output.insert(tk.END, f"{n} x{c:,}\n")
            else:
                self.text_output.insert(tk.END, "(no adventures)\n")

        if self.show_sections["experience"].get():
            bold("\nExperience:")
            self.text_output.insert(tk.END, f"Character XP: {snap['total_character_xp']:,}\n")
            for s, xp in snap["skill_xp_totals"].items():
                self.text_output.insert(tk.END, f"{s}: {xp:,}\n")

        if self.show_sections["blockchain"].get():
            bold("\nBlockchain Items:")
            if snap["blockchain_totals"]:
                for n, a in sorted(snap["blockchain_totals"].items()):
                    self.text_output.insert(tk.END, f"{n} x{a:,}\n")
            else:
                self.text_output.insert(tk.END, "(none)\n")

        if self.show_sections["non_blockchain"].get():
            bold("\nTracked Non-Blockchain Items:")
            filtered = [(n, a) for n, a in snap["non_blockchain_totals"].items() if n in snap["non_blockchain_items"]]
            if filtered:
                for n, a in sorted(filtered):
                    self.text_output.insert(tk.END, f"{n} x{a:,}\n")
            else:
                self.text_output.insert(tk.END, "(none)\n")

        self.text_output.configure(state="disabled")
        self.text_output.yview_moveto(yview[0])


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
                    today = datetime.now(timezone.utc).date()
                    with self.dm.lock:
                        if today != self.dm.current_log_date:
                            self.dm.reset_daily_counters_locked(today)

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
        try:
            w, h = self.ui.root.winfo_width(), self.ui.root.winfo_height()
            settings = {
                "window_width": w,
                "window_height": h,
                "dark_mode": self.ui.dark_mode,
                "show_totals": {k: v.get() for k, v in self.ui.show_totals.items()},
                "show_sections": {k: v.get() for k, v in self.ui.show_sections.items()},
                "currency": self.ui.currency_var.get(),
            }
            self.dm.save_settings(settings)
        except Exception:
            pass

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
