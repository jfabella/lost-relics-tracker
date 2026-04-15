import tkinter as tk
import customtkinter as ctk
from tkinter import simpledialog, messagebox, filedialog
import threading
import json
import os
import signal
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

import requests
import websocket
from openpyxl import Workbook


def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# ---------------------------------------------------------------------------
# Load .env if present
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
WS_URL          = os.getenv("WS_URL", "ws://localhost:11991/")
COINGECKO_URL   = "https://api.coingecko.com/api/v3/simple/price"
APP_VERSION     = "0.2.2"
RECONNECT_DELAY = 5
LOG_DIR         = "run_logs"
SETTINGS_FILE   = "settings.conf"
CONFIG_FILE     = "non_blockchain_config.json"
EXCLUDE_FILE    = "non_blockchain_exclude.json"

DEFAULT_TRACKED_NON_BLOCKCHAIN_ITEMS  = ["Deepsea Coffer", "Golden Grind Chest", "Frostfall Shard", "Axiom Sigil"]
DEFAULT_EXCLUDED_NON_BLOCKCHAIN_ITEMS = ["Deepsea Coffer"]
SKILLS           = {"Fishing", "Scavenging", "Titanfall", "Breach"}
TRANSPARENT_KEY  = "#010203"
H_WINDOW_WIDTH   = 1400
H_WINDOW_HEIGHT  = 300

# ---------------------------------------------------------------------------
# Fonts 
# ---------------------------------------------------------------------------
FONT_PLAYER_NAME  = ("Roboto", 26, "bold")
FONT_SECTION      = ("Roboto", 10, "bold")   # section headers in the data panel
FONT_BODY         = ("Roboto", 14)           # main data rows
FONT_ENJIN        = ("Roboto", 14, "bold")   # enjin price label
FONT_TIME         = ("Roboto", 13)           # local time / app running
FONT_RESET        = ("Roboto", 12)           # reset countdown
FONT_WS           = ("Roboto", 11, "italic") # WS status
FONT_FOOTER       = ("Roboto", 9)            # version / credit
FONT_POPUP_TITLE  = ("Roboto", 16, "bold")   # popup window titles
FONT_POPUP_BODY   = ("Roboto", 13)           # popup body text

# ===========================================================================
# DataManager
# ===========================================================================
class DataManager:
    def __init__(self, log_dir: str, config_file: str, exclude_file: str):
        self.log_dir = log_dir
        os.makedirs(log_dir, mode=0o755, exist_ok=True)
        self.lock = threading.RLock()
        self.player_name = "Unknown Player"
        self.seen_adventure_instances: set = set()
        self.seen_container_instances: set = set()
        self._loaded_from_log = False
        self.non_blockchain_items   = self.load_config(config_file,  DEFAULT_TRACKED_NON_BLOCKCHAIN_ITEMS)
        self.non_blockchain_exclude = self.load_config(exclude_file, DEFAULT_EXCLUDED_NON_BLOCKCHAIN_ITEMS)
        self.settings = self.load_settings()
        self.reset_daily_counters_locked(self.now_local().date())
        self.load_log()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def load_settings(self) -> dict:
        default_settings = {
            "window_width":  246,
            "window_height": 600,
            "dark_mode":     True,
            "currency":      "usd",
            "gmt_offset":    0,
            "overlay_mode":  False,
            "layout_mode":   "vertical",
            "show_totals": {
                "runs":           True,
                "gold":           True,
                "estimated_gold": True,
                "enj":            True,
            },
            "show_sections": {
                "adventures":   True,
                "experience":   True,
                "blockchain":   True,
                "non_blockchain": True,
                "containers":             True,
                "container_blockchain":   True,
                "container_non_blockchain": False,
            },
        }
        if os.path.isfile(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                for k, v in loaded.items():
                    if isinstance(v, dict) and isinstance(default_settings.get(k), dict):
                        default_settings[k].update(v)
                    else:
                        default_settings[k] = v
                return default_settings
            except Exception:
                pass
        return default_settings

    def save_settings(self, settings: dict):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2)
        except Exception:
            pass

    def now_local(self) -> datetime:
        tz = timezone(timedelta(hours=self.settings.get("gmt_offset", 0)))
        return datetime.now(tz)

    # ------------------------------------------------------------------
    # Daily counters
    # ------------------------------------------------------------------
    def reset_daily_counters_locked(self, today_date):
        self.counter              = 0
        self.blockchain_totals    = defaultdict(int)
        self.non_blockchain_totals= defaultdict(int)
        self.adventure_counts     = defaultdict(int)
        self.adventure_time_totals  = defaultdict(int)
        self.container_counts               = defaultdict(int)
        self.container_blockchain_totals    = defaultdict(int)
        self.container_non_blockchain_totals= defaultdict(int)
        self.total_character_xp   = 0
        self.skill_xp_totals      = defaultdict(int)
        self.total_enj_value      = 0.0
        self.gold_coins_total     = 0
        self.total_estimated_gold = 0
        self.market_values        = {}
        self.current_log_date     = today_date
        self.start_time           = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Config files
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Log persistence
    # ------------------------------------------------------------------
    def log_filepath(self) -> str:
        today_str = self.now_local().strftime("%Y-%m-%d")
        return os.path.join(self.log_dir, f"runs_{today_str}.json")

    def load_log(self):
        path     = self.log_filepath()
        tmp_path = path + ".tmp"
        data: dict = {}
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
                self.counter               = data.get("runs", 0)
                self.blockchain_totals.update(data.get("blockchain_totals", {}))
                self.non_blockchain_totals.update(data.get("non_blockchain_totals", {}))
                self.adventure_counts.update(data.get("adventure_counts", {}))
                self.adventure_time_totals.update(data.get("adventure_time_totals", {}))
                self.container_counts.update(data.get("container_counts", {}))
                self.container_blockchain_totals.update(data.get("container_blockchain_totals", {}))
                self.container_non_blockchain_totals.update(data.get("container_non_blockchain_totals", {}))
                self.seen_container_instances = set(data.get("seen_container_instances", []))
                self.total_character_xp    = data.get("total_character_xp", 0)
                self.skill_xp_totals.update(data.get("skill_xp_totals", {}))
                self.player_name           = data.get("player_name", "Unknown Player")
                self.total_enj_value       = data.get("total_enj_value", 0.0)
                self.gold_coins_total      = data.get("gold_coins_total", 0)
                self.total_estimated_gold  = data.get("total_estimated_gold", 0)
                self.seen_adventure_instances = set(data.get("seen_adventure_instances", []))
                self._loaded_from_log      = True

    def save_log(self):
        with self.lock:
            data = {
                "runs":                    self.counter,
                "blockchain_totals":       dict(self.blockchain_totals),
                "non_blockchain_totals":   dict(self.non_blockchain_totals),
                "adventure_counts":        dict(self.adventure_counts),
                "adventure_time_totals":   dict(self.adventure_time_totals),
                "container_counts":                dict(self.container_counts),
                "container_blockchain_totals":     dict(self.container_blockchain_totals),
                "container_non_blockchain_totals": dict(self.container_non_blockchain_totals),
                "seen_container_instances":        list(self.seen_container_instances),
                "total_character_xp":      self.total_character_xp,
                "skill_xp_totals":         dict(self.skill_xp_totals),
                "player_name":             self.player_name,
                "total_enj_value":         self.total_enj_value,
                "gold_coins_total":        self.gold_coins_total,
                "total_estimated_gold":    self.total_estimated_gold,
                "seen_adventure_instances": list(self.seen_adventure_instances),
            }
        path     = self.log_filepath()
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Adventure processing
    # ------------------------------------------------------------------
    def process_adventure_locked(self, adventure: Dict[str, Any]):
        self.counter += 1
        adv_name = adventure.get("AdventureName", "Unknown")
        self.adventure_counts[adv_name] += 1
        self.adventure_time_totals[adv_name] += adventure.get("TimeTaken", 0)
        self.total_character_xp += adventure.get("ExperienceAmount", 0)

        for xp in adventure.get("Experience", []):
            if xp.get("Type") in SKILLS:
                self.skill_xp_totals[xp["Type"]] += xp.get("Amount", 0)

        estimated_gold = 0
        for item in adventure.get("Items", []):
            name   = item.get("Name", "Unknown")
            amount = item.get("Amount", 1)
            mv     = item.get("MarketValue", 0)

            if name == "Gold Coins":
                self.gold_coins_total += amount
                estimated_gold        += amount

            if item.get("IsBlockchain", False):
                self.blockchain_totals[name] += amount
                if mv:
                    self.market_values[name]  = mv
                    self.total_enj_value      += (mv / 100.0) * amount
            else:
                if name in self.non_blockchain_items:
                    self.non_blockchain_totals[name] += amount
                if name not in self.non_blockchain_exclude:
                    estimated_gold += amount * mv

        self.total_estimated_gold += estimated_gold

    def process_container_locked(self, container: Dict[str, Any]):
        name  = container.get("Name", "Unknown")
        count = container.get("Count", 1)
        self.container_counts[name] += count

        for item in container.get("Items", []):
            iname  = item.get("Name", "Unknown")
            amount = item.get("Amount", 1)
            mv     = item.get("MarketValue", 0)

            if iname == "Gold Coins":
                self.gold_coins_total += amount

            if item.get("IsBlockchain", False):
                self.container_blockchain_totals[iname] += amount
                if mv:
                    self.market_values[iname] = mv
                    self.total_enj_value += (mv / 100.0) * amount
            else:
                if iname != "Gold Coins":
                    if iname in self.non_blockchain_items:
                        self.container_non_blockchain_totals[iname] += amount
                    if iname not in self.non_blockchain_exclude:
                        self.total_estimated_gold += amount * mv

    # ------------------------------------------------------------------
    # Error log
    # ------------------------------------------------------------------
    def save_error_log(self, message: str):
        now  = datetime.now()
        ts   = now.strftime("%Y-%m-%d %H:%M:%S")
        path = os.path.join(self.log_dir, f"error_{now.strftime('%Y-%m-%d')}.txt")
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {message}\n")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Summarize across date range
    # ------------------------------------------------------------------
    def summarize_logs(self, start_date: str, end_date: str) -> dict:
        summary = {
            "Total Runs":           0,
            "Total Gold Coins":     0,
            "Total Estimated Gold": 0,
            "Total ENJ Value":      0.0,
            "Total Character XP":   0,
            "Skill XP Totals":      defaultdict(int),
            "Adventure Counts":     defaultdict(int),
            "Adventure Time Totals":defaultdict(int),
            "Blockchain Totals":    defaultdict(int),
            "Non-Blockchain Totals":defaultdict(int),
            "Container Counts":                defaultdict(int),
            "Container Blockchain Totals":     defaultdict(int),
            "Container Non-Blockchain Totals": defaultdict(int),
        }
        try:
            for fname in os.listdir(self.log_dir):
                if fname.startswith("runs_") and fname.endswith(".json"):
                    date_part = fname[5:-5]
                    if start_date <= date_part <= end_date:
                        with open(os.path.join(self.log_dir, fname), "r", encoding="utf-8") as f:
                            data = json.load(f)
                        summary["Total Runs"]           += data.get("runs", 0)
                        summary["Total Gold Coins"]     += data.get("gold_coins_total", 0)
                        summary["Total Estimated Gold"] += data.get("total_estimated_gold", 0)
                        summary["Total ENJ Value"]      += data.get("total_enj_value", 0.0)
                        summary["Total Character XP"]   += data.get("total_character_xp", 0)
                        for k, v in data.get("skill_xp_totals",     {}).items(): summary["Skill XP Totals"][k]       += v
                        for k, v in data.get("adventure_counts",    {}).items(): summary["Adventure Counts"][k]      += v
                        for k, v in data.get("adventure_time_totals", {}).items(): summary["Adventure Time Totals"][k] += v
                        for k, v in data.get("blockchain_totals",   {}).items(): summary["Blockchain Totals"][k]     += v
                        for k, v in data.get("non_blockchain_totals",{}).items():summary["Non-Blockchain Totals"][k] += v
                        for k, v in data.get("container_counts",                {}).items(): summary["Container Counts"][k]                += v
                        for k, v in data.get("container_blockchain_totals",     {}).items(): summary["Container Blockchain Totals"][k]     += v
                        for k, v in data.get("container_non_blockchain_totals", {}).items(): summary["Container Non-Blockchain Totals"][k] += v
        except Exception as e:
            summary["_error"] = str(e)
        return summary

    def format_summary(self, summary: dict, start_date: str, end_date: str) -> str:
        if "_error" in summary:
            return f"Error summarizing logs: {summary['_error']}"
        try:
            elapsed_days = max(
                (datetime.strptime(end_date, "%Y-%m-%d").date()
                 - datetime.strptime(start_date, "%Y-%m-%d").date()).days + 1, 1)
        except Exception:
            elapsed_days = 1

        lines = [
            f"Total Runs: {summary['Total Runs']:,}",
            f"Total Gold Coins: {summary['Total Gold Coins']:,}",
            f"Total Estimated Gold: {summary['Total Estimated Gold']:,}",
            f"Total ENJ Value: {summary['Total ENJ Value']:.2f}",
            f"Total Character XP: {summary['Total Character XP']:,}\n",
            "Daily Averages:",
            f"  Avg Runs/Day: {summary['Total Runs'] / elapsed_days:.2f}",
            f"  Avg Estimated Gold/Day: {summary['Total Estimated Gold'] / elapsed_days:.2f}",
            f"  Avg ENJ Value/Day: {summary['Total ENJ Value'] / elapsed_days:.4f}",
            f"  Avg Character XP/Day: {summary['Total Character XP'] / elapsed_days:.0f}",
        ]
        for skill, xp in summary["Skill XP Totals"].items():
            lines.append(f"  Avg {skill} XP/Day: {xp / elapsed_days:.0f}")
        lines.append("\nSkill XP Totals:")
        for k, v in summary["Skill XP Totals"].items():   lines.append(f"  {k}: {v:,}")
        lines.append("\nAdventures:")
        for k, v in summary["Adventure Counts"].items():
            t = summary["Adventure Time Totals"].get(k, 0)
            h, rem = divmod(t, 3600); m, s = divmod(rem, 60)
            time_str = f"{h}h {m}m {s}s" if h else f"{m}m {s}s"
            lines.append(f"  {k}: {v:,}  ·  {time_str}")
        lines.append("\nBlockchain Items:")
        for k, v in summary["Blockchain Totals"].items(): lines.append(f"  {k}: {v:,}")
        lines.append("\nNon-Blockchain Items:")
        for k, v in summary["Non-Blockchain Totals"].items(): lines.append(f"  {k}: {v:,}")
        lines.append("\nOpened Containers:")
        for k, v in summary["Container Counts"].items(): lines.append(f"  {k}: {v:,}")
        lines.append("\nContainer Blockchain Items:")
        for k, v in summary["Container Blockchain Totals"].items(): lines.append(f"  {k}: {v:,}")
        lines.append("\nContainer Non-Blockchain Items:")
        for k, v in summary["Container Non-Blockchain Totals"].items(): lines.append(f"  {k}: {v:,}")
        return "\n".join(lines)

    def export_summary_to_excel(self, summary: dict, start_date: str, end_date: str):
        wb = Workbook()
        ws = wb.active
        ws.title = "Summary Report"
        ws.append(["Lost Relics Adventure Report"])
        ws.append([f"From {start_date} to {end_date}"])
        ws.append([])
        ws.append(["Totals"])
        ws.append(["Total Runs",           summary["Total Runs"]])
        ws.append(["Total Gold Coins",     summary["Total Gold Coins"]])
        ws.append(["Total Estimated Gold", summary["Total Estimated Gold"]])
        ws.append(["Total ENJ Value",      summary["Total ENJ Value"]])
        ws.append(["Total Character XP",   summary["Total Character XP"]])
        ws.append([])
        for section, label in [
            ("Skill XP Totals",       "Skill XP Totals"),
            ("Adventure Counts",      "Adventures"),
            ("Adventure Time Totals", "Adventure Time Totals"),
            ("Blockchain Totals",     "Blockchain Items"),
            ("Non-Blockchain Totals", "Non-Blockchain Items"),
            ("Container Counts",                "Opened Containers"),
            ("Container Blockchain Totals",     "Container Blockchain Items"),
            ("Container Non-Blockchain Totals", "Container Non-Blockchain Items"),
        ]:
            ws.append([label])
            for k, v in summary[section].items():
                if section == "Adventure Time Totals":
                    h, rem = divmod(v, 3600); m, s = divmod(rem, 60)
                    ws.append([k, f"{h}h {m}m {s}s" if h else f"{m}m {s}s"])
                else:
                    ws.append([k, v])
            ws.append([])

        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx")],
            title="Save Report As",
        )
        if file_path:
            wb.save(file_path)
            messagebox.showinfo("Export Successful", f"Report saved to {file_path}")


# ===========================================================================
# WebSocketClient
# ===========================================================================
class WebSocketClient:
    """
    Maintains a persistent WebSocket connection to ws://localhost:11991/.
    On connect it sends "Adventures" and "Player" to subscribe to both event
    streams.  Incoming messages are dispatched to on_adventure / on_player
    callbacks provided by the caller.

    Auto-reconnects indefinitely with a configurable delay.
    """

    def __init__(
        self,
        url: str,
        on_adventure,   
        on_player,      
        on_container,   
        on_status,      
        stop_event: threading.Event,
        reconnect_delay: int = RECONNECT_DELAY,
    ):
        self.url             = url
        self.on_adventure    = on_adventure
        self.on_player       = on_player
        self.on_container    = on_container
        self.on_status       = on_status
        self.stop_event      = stop_event
        self.reconnect_delay = reconnect_delay
        self._ws             = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def run(self):
        """Entry-point — call from a daemon thread."""
        while not self.stop_event.is_set():
            self.on_status("Connecting…")
            try:
                self._ws = websocket.WebSocketApp(
                    self.url,
                    on_open    = self._on_open,
                    on_message = self._on_message,
                    on_error   = self._on_error,
                    on_close   = self._on_close,
                )
                self._ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                self.on_status(f"WS error: {e}")

            if self.stop_event.is_set():
                break

            self.on_status(f"Disconnected — reconnecting in {self.reconnect_delay}s…")
            self.stop_event.wait(self.reconnect_delay)

    def close(self):
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal WebSocketApp callbacks
    # ------------------------------------------------------------------
    def _on_open(self, ws):
        self.on_status("Connected")

    def _on_message(self, ws, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type", "").lower()

        if msg_type == "adventures":
            for adv in msg.get("data", []):
                self.on_adventure(adv)

        elif msg_type == "player":
            player = msg.get("data", {})
            if isinstance(player, list) and player:
                player = player[0]
            if player:
                self.on_player(player)

        elif msg_type == "containers":
            for cont in msg.get("data", []):
                self.on_container(cont)

    def _on_error(self, ws, error):
        self.on_status(f"WS error: {error}")

    def _on_close(self, ws, code, msg):
        self.on_status(f"Connection closed (code={code})")


# ===========================================================================
# TrackerUI
# ===========================================================================
class TrackerUI:
    def __init__(self, root: tk.Tk, dm: DataManager):
        self.root = root
        self.dm   = dm
        settings  = dm.settings

        self.currency_var = tk.StringVar(value=settings.get("currency", "usd"))
        self.dark_mode    = settings.get("dark_mode", True)
        ctk.set_appearance_mode("dark" if self.dark_mode else "light")

        self.show_totals = {
            "runs":           tk.BooleanVar(value=settings["show_totals"].get("runs",           True)),
            "gold":           tk.BooleanVar(value=settings["show_totals"].get("gold",           True)),
            "estimated_gold": tk.BooleanVar(value=settings["show_totals"].get("estimated_gold", True)),
            "enj":            tk.BooleanVar(value=settings["show_totals"].get("enj",            True)),
        }
        self.show_sections = {
            "adventures":    tk.BooleanVar(value=settings["show_sections"].get("adventures",    True)),
            "experience":    tk.BooleanVar(value=settings["show_sections"].get("experience",    True)),
            "blockchain":    tk.BooleanVar(value=settings["show_sections"].get("blockchain",    True)),
            "non_blockchain":tk.BooleanVar(value=settings["show_sections"].get("non_blockchain",True)),
            "containers":              tk.BooleanVar(value=settings["show_sections"].get("containers",              True)),
            "container_blockchain":    tk.BooleanVar(value=settings["show_sections"].get("container_blockchain",    True)),
            "container_non_blockchain":tk.BooleanVar(value=settings["show_sections"].get("container_non_blockchain",False)),
        }

        self._build_ui(settings)
        self._build_menu()
        self.apply_theme()
        self._update_enjin_price()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _make_textbox(self, parent) -> ctk.CTkTextbox:
        tb = ctk.CTkTextbox(parent, font=FONT_BODY, wrap="word", border_width=0)
        tb.configure(state="disabled")
        tb._textbox.tag_configure("bold", font=FONT_SECTION)
        return tb

    def _build_ui(self, settings: dict):
        self.root.title("Lost Relics Daily Tracker")
        try:
            self.root.iconbitmap("lrtracker.ico")
        except Exception:
            pass
        horizontal = settings.get("layout_mode", "vertical") == "horizontal"
        if horizontal:
            w = settings.get("window_width",  H_WINDOW_WIDTH)
            h = settings.get("window_height", H_WINDOW_HEIGHT)
        else:
            w = settings.get("window_width",  350)
            h = settings.get("window_height", 600)
        self.root.geometry(f"{w}x{h}")
        self.root.resizable(True, True)
        self.root.attributes("-topmost", True)

        if horizontal:
            self._build_ui_horizontal()
        else:
            self._build_ui_vertical()

    def _build_ui_vertical(self):
        self.label_player_name = ctk.CTkLabel(self.root, text=self.dm.player_name, font=FONT_PLAYER_NAME)
        self.label_player_name.pack(pady=(10, 0))

        self.label_server_time  = ctk.CTkLabel(self.root, text="", font=FONT_TIME)
        self.label_server_time.pack()
        self.label_elapsed_time = ctk.CTkLabel(self.root, text="", font=FONT_TIME)
        self.label_elapsed_time.pack(pady=(0, 3))
        self.label_reset_time   = ctk.CTkLabel(self.root, text="", font=FONT_RESET)
        self.label_reset_time.pack(pady=(0, 1))
        self.label_ws_status    = ctk.CTkLabel(self.root, text="WS: —", font=FONT_WS)
        self.label_ws_status.pack(pady=(0, 3))

        self.enjin_label = ctk.CTkLabel(self.root, text="Enjin Price: Loading…", font=FONT_ENJIN)
        self.enjin_label.pack(pady=(0, 5))

        self.credit_label  = ctk.CTkLabel(self.root, text="Developed by Capoeira", font=FONT_FOOTER)
        self.credit_label.pack(side="bottom", pady=(0, 5))
        self.version_label = ctk.CTkLabel(self.root, text=f"Version {APP_VERSION}", font=FONT_FOOTER)
        self.version_label.pack(side="bottom", pady=(0, 5))

        self.text_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.text_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.text_output = self._make_textbox(self.text_frame)
        self.text_output.configure(width=42, height=28)
        self.text_output.pack(fill="both", expand=True)
        self._col_textboxes   = [self.text_output]
        self._content_frames  = [self.text_frame]

    def _build_ui_horizontal(self):
        self.credit_label  = ctk.CTkLabel(self.root, text="Developed by Capoeira", font=FONT_FOOTER)
        self.credit_label.pack(side="bottom", pady=(0, 2))
        self.version_label = ctk.CTkLabel(self.root, text=f"Version {APP_VERSION}", font=FONT_FOOTER)
        self.version_label.pack(side="bottom", pady=(0, 2))


        main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)

        info_panel = ctk.CTkFrame(main_frame, fg_color="transparent")
        info_panel.pack(side="left", fill="y", padx=(0, 6))

        self.label_player_name = ctk.CTkLabel(info_panel, text=self.dm.player_name, font=FONT_PLAYER_NAME)
        self.label_player_name.pack(pady=(8, 2))

        self.label_server_time  = ctk.CTkLabel(info_panel, text="", font=FONT_TIME)
        self.label_server_time.pack()
        self.label_elapsed_time = ctk.CTkLabel(info_panel, text="", font=FONT_TIME)
        self.label_elapsed_time.pack(pady=(0, 2))
        self.label_reset_time   = ctk.CTkLabel(info_panel, text="", font=FONT_RESET)
        self.label_reset_time.pack(pady=(0, 1))
        self.label_ws_status    = ctk.CTkLabel(info_panel, text="WS: —", font=FONT_WS)
        self.label_ws_status.pack(pady=(0, 2))
        self.enjin_label = ctk.CTkLabel(info_panel, text="Enjin Price: Loading…", font=FONT_ENJIN)
        self.enjin_label.pack(pady=(4, 0))

        cols_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        cols_frame.pack(side="left", fill="both", expand=True)
        for i in range(4):
            cols_frame.columnconfigure(i, weight=1)
        cols_frame.rowconfigure(0, weight=1)

        self.col_totals = self._make_textbox(cols_frame)
        self.col_totals.grid(row=0, column=0, sticky="nsew", padx=(0, 2))
        self.col_adventures = self._make_textbox(cols_frame)
        self.col_adventures.grid(row=0, column=1, sticky="nsew", padx=2)
        self.col_loot = self._make_textbox(cols_frame)
        self.col_loot.grid(row=0, column=2, sticky="nsew", padx=2)
        self.col_containers = self._make_textbox(cols_frame)
        self.col_containers.grid(row=0, column=3, sticky="nsew", padx=(2, 0))

        self.text_output     = self.col_totals   
        self._col_textboxes  = [self.col_totals, self.col_adventures, self.col_loot, self.col_containers]
        self._content_frames = [cols_frame]

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Summarize Runs", command=self._summarize_runs_popup)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=0)

        totals_menu = tk.Menu(view_menu, tearoff=0)
        totals_menu.add_checkbutton(label="Total Runs",           variable=self.show_totals["runs"],           command=self.refresh_ui)
        totals_menu.add_checkbutton(label="Total Gold Coins",     variable=self.show_totals["gold"],           command=self.refresh_ui)
        totals_menu.add_checkbutton(label="Total Estimated Gold", variable=self.show_totals["estimated_gold"], command=self.refresh_ui)
        totals_menu.add_checkbutton(label="Total ENJ Value",      variable=self.show_totals["enj"],            command=self.refresh_ui)
        view_menu.add_cascade(label="Totals", menu=totals_menu)

        sections_menu = tk.Menu(view_menu, tearoff=0)
        sections_menu.add_checkbutton(label="Adventures",          variable=self.show_sections["adventures"],    command=self.refresh_ui)
        sections_menu.add_checkbutton(label="Experience",          variable=self.show_sections["experience"],    command=self.refresh_ui)
        sections_menu.add_checkbutton(label="Blockchain Items",    variable=self.show_sections["blockchain"],    command=self.refresh_ui)
        sections_menu.add_checkbutton(label="Non-Blockchain Items",variable=self.show_sections["non_blockchain"],command=self.refresh_ui)
        sections_menu.add_checkbutton(label="Opened Containers",             variable=self.show_sections["containers"],              command=self.refresh_ui)
        sections_menu.add_checkbutton(label="Container Blockchain Items",    variable=self.show_sections["container_blockchain"],    command=self.refresh_ui)
        sections_menu.add_checkbutton(label="Container Non-Blockchain Items",variable=self.show_sections["container_non_blockchain"],command=self.refresh_ui)
        view_menu.add_cascade(label="Sections", menu=sections_menu)

        currency_menu = tk.Menu(view_menu, tearoff=0)
        for cur in ["usd", "php", "eur", "gbp"]:
            currency_menu.add_radiobutton(
                label=cur.upper(), variable=self.currency_var, value=cur,
                command=lambda c=cur: self._update_currency(c),
            )
        view_menu.add_cascade(label="Currency", menu=currency_menu)
        menubar.add_cascade(label="View", menu=view_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Toggle Theme",      command=self.toggle_theme)
        settings_menu.add_command(label="Toggle Overlay",    command=self.toggle_overlay)
        settings_menu.add_command(label="Toggle Layout",     command=self.toggle_layout)
        settings_menu.add_command(label="Set GMT Offset",    command=self._set_gmt_popup)

        menubar.add_cascade(label="Settings", menu=settings_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Donate / Support", command=self._show_donate)
        help_menu.add_command(label="About",            command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.dm.settings["dark_mode"] = self.dark_mode
        self.dm.save_settings(self.dm.settings)
        self.apply_theme()

    def toggle_overlay(self):
        current = self.dm.settings.get("overlay_mode", False)
        self.dm.settings["overlay_mode"] = not current
        self.dm.save_settings(self.dm.settings)
        self.apply_theme()

    def toggle_layout(self):
        current  = self.dm.settings.get("layout_mode", "vertical")
        new_mode = "horizontal" if current == "vertical" else "vertical"
        self.dm.settings["layout_mode"]   = new_mode
        self.dm.settings["window_width"]  = H_WINDOW_WIDTH  if new_mode == "horizontal" else 350
        self.dm.settings["window_height"] = H_WINDOW_HEIGHT if new_mode == "horizontal" else 600
        self.dm.save_settings(self.dm.settings)
        for w in self.root.winfo_children():
            w.destroy()
        self._build_ui(self.dm.settings)
        self._build_menu()
        self.apply_theme()

    def _set_gmt_popup(self):
        current = self.dm.settings.get("gmt_offset", 0)
        raw = simpledialog.askstring(
            "Set GMT Offset",
            "Enter your GMT offset (e.g. +8, -5, 0):\n\n"
            "This controls when your daily tracker resets.\n"
            "The reset happens at midnight of the chosen timezone.",
            initialvalue=f"{current:+d}",
        )
        if raw is None:
            return
        try:
            offset = int(raw.replace("+", ""))
            if not -12 <= offset <= 14:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Offset", "Please enter a whole number between -12 and +14.")
            return
        self.dm.settings["gmt_offset"] = offset
        self.dm.save_settings(self.dm.settings)
        messagebox.showinfo("GMT Offset Updated", f"Timezone set to GMT{offset:+d}.\nTakes effect immediately.")

    def apply_theme(self):
        ctk.set_appearance_mode("dark" if self.dark_mode else "light")

        if self.dark_mode:
            fg, muted, select_bg = "#d4d4d4", "#888888", "#444444"
        else:
            fg, muted, select_bg = "#000000", "gray", "#cce6ff"

        overlay     = self.dm.settings.get("overlay_mode", False)
        win_bg      = TRANSPARENT_KEY if overlay else "transparent"
        label_fg    = "#ffffff" if overlay else fg
        label_muted = "#cccccc" if overlay else muted

        self.root.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.root.configure(fg_color=TRANSPARENT_KEY if overlay else ("gray14" if self.dark_mode else "gray95"))

        for w in [self.label_player_name, self.label_server_time,
                  self.label_elapsed_time, self.label_reset_time,
                  self.label_ws_status, self.credit_label,
                  self.version_label, self.enjin_label]:
            w.configure(fg_color=win_bg)

        self.label_player_name.configure(text_color=label_fg)
        self.label_server_time.configure(text_color=label_fg)
        self.label_elapsed_time.configure(text_color=label_fg)
        self.label_reset_time.configure(text_color=label_muted)
        self.label_ws_status.configure(text_color=label_muted)
        self.version_label.configure(text_color=label_muted)
        self.credit_label.configure(text_color=label_muted)

        for frame in self._content_frames:
            frame.configure(fg_color=TRANSPARENT_KEY if overlay else "transparent")
        for tb in self._col_textboxes:
            tb.configure(
                fg_color=TRANSPARENT_KEY if overlay else ("gray17" if self.dark_mode else "gray95"),
                text_color=fg,
            )
            tb._textbox.tag_configure("bold", font=FONT_SECTION)

    # ------------------------------------------------------------------
    # WebSocket status 
    # ------------------------------------------------------------------
    def set_ws_status(self, text: str):
        self.label_ws_status.configure(text=f"WS: {text}")

    # ------------------------------------------------------------------
    # Enjin price
    # ------------------------------------------------------------------
    def _update_enjin_price(self):
        def fetch():
            try:
                vs  = self.currency_var.get()
                r   = requests.get(
                    COINGECKO_URL,
                    params={"ids": "enjincoin", "vs_currencies": vs, "include_24hr_change": "true"},
                    timeout=5,
                )
                d      = r.json().get("enjincoin", {})
                price  = d.get(vs)
                change = d.get(f"{vs}_24h_change", 0.0)
                cur    = vs.upper()
                if price is None:
                    text, color = f"Enjin Price: N/A ({cur})", "gray"
                else:
                    arrow = "▲" if change >= 0 else "▼"
                    color = "limegreen" if change >= 0 else "tomato"
                    text  = f"Enjin Price: {price:,.3f} {cur} {arrow} {abs(change):.1f}% (24h)"
            except requests.exceptions.HTTPError as e:
                if hasattr(e, "response") and e.response and e.response.status_code == 429:
                    text, color = "Enjin Price: Rate limited", "gray"
                else:
                    text, color = "Enjin Price: Error", "gray"
            except Exception:
                text, color = "Enjin Price: Error", "gray"

            self.root.after(0, lambda t=text, c=color: self.enjin_label.configure(text=t, text_color=c))

        threading.Thread(target=fetch, daemon=True).start()
        self.root.after(600_000, self._update_enjin_price)   

    def _update_currency(self, new_currency: str):
        self.currency_var.set(new_currency)
        self.dm.settings["currency"] = new_currency
        self.dm.save_settings(self.dm.settings)
        self._update_enjin_price()

    # ------------------------------------------------------------------
    # Main display refresh
    # ------------------------------------------------------------------
    def _write_col(self, tb: ctk.CTkTextbox, lines: list):
        """Write (text, tag) pairs to a textbox, replacing all existing content."""
        tb.configure(state="normal")
        tb.delete("1.0", tk.END)
        for text, tag in lines:
            if tag:
                tb._textbox.insert(tk.END, text + "\n", tag)
            else:
                tb.insert(tk.END, text + "\n")
        tb.configure(state="disabled")

    def _refresh_horizontal(self, snap: dict):
        # Column 1 — All totals + Adventures 
        lines: list = []
        if self.show_totals["runs"].get():
            lines.append((f"Total Runs: {snap['counter']:,}", "bold"))
        if self.show_totals["gold"].get():
            lines.append((f"Total Gold Coins: {snap['gold_coins_total']:,}", "bold"))
        if self.show_totals["estimated_gold"].get():
            lines.append((f"Total Estimated Gold: {snap['total_estimated_gold']:,.0f}", "bold"))
        if self.show_totals["enj"].get():
            lines.append((f"Total ENJ Value: {snap['total_enj_value']:,.2f}", "bold"))
        if self.show_sections["adventures"].get():
            lines.append(("", ""))
            lines.append(("Adventures:", "bold"))
            if snap["adventure_counts"]:
                for n, c in sorted(snap["adventure_counts"].items(), key=lambda x: -x[1]):
                    t = snap["adventure_time_totals"].get(n, 0)
                    h, rem = divmod(t, 3600); m, s = divmod(rem, 60)
                    time_str = f"{h}h {m}m {s}s" if h else f"{m}m {s}s"
                    lines.append((f"{n} x{c:,}  ·  {time_str}", ""))
            else:
                lines.append(("(no adventures yet)", ""))
        self._write_col(self.col_totals, lines)

        # Column 2 — Experience
        lines = []
        if self.show_sections["experience"].get():
            lines.append(("Experience:", "bold"))
            lines.append((f"Character XP: {snap['total_character_xp']:,}", ""))
            for sk, xp in snap["skill_xp_totals"].items():
                lines.append((f"{sk}: {xp:,}", ""))
        self._write_col(self.col_adventures, lines)

        # Column 3 — Blockchain + Non-Blockchain
        lines = []
        if self.show_sections["blockchain"].get():
            lines.append(("Blockchain Items:", "bold"))
            if snap["blockchain_totals"]:
                for n, a in sorted(snap["blockchain_totals"].items()):
                    lines.append((f"{n} x{a:,}", ""))
            else:
                lines.append(("(none)", ""))
        if self.show_sections["non_blockchain"].get():
            lines.append(("", ""))
            lines.append(("Tracked Non-Blockchain Items:", "bold"))
            filtered = [(n, a) for n, a in snap["non_blockchain_totals"].items()
                        if n in snap["non_blockchain_items"]]
            if filtered:
                for n, a in sorted(filtered):
                    lines.append((f"{n} x{a:,}", ""))
            else:
                lines.append(("(none)", ""))
        self._write_col(self.col_loot, lines)

        # Column 4 — Containers
        lines = []
        if self.show_sections["containers"].get():
            lines.append(("Opened Containers:", "bold"))
            if snap["container_counts"]:
                for n, c in sorted(snap["container_counts"].items(), key=lambda x: -x[1]):
                    lines.append((f"{n} x{c:,}", ""))
            else:
                lines.append(("(none)", ""))
        if self.show_sections["container_blockchain"].get():
            lines.append(("", ""))
            lines.append(("Container Blockchain Items:", "bold"))
            if snap["container_blockchain_totals"]:
                for n, a in sorted(snap["container_blockchain_totals"].items()):
                    lines.append((f"{n} x{a:,}", ""))
            else:
                lines.append(("(none)", ""))
        if self.show_sections["container_non_blockchain"].get():
            lines.append(("", ""))
            lines.append(("Container Non-Blockchain Items:", "bold"))
            filtered_cont = [(n, a) for n, a in snap["container_non_blockchain_totals"].items()
                             if n in snap["non_blockchain_items"]]
            if filtered_cont:
                for n, a in sorted(filtered_cont):
                    lines.append((f"{n} x{a:,}", ""))
            else:
                lines.append(("(none)", ""))
        self._write_col(self.col_containers, lines)

    def refresh_ui(self):
        with self.dm.lock:
            snap = dict(
                player_name        = self.dm.player_name,
                counter            = self.dm.counter,
                total_enj_value    = self.dm.total_enj_value,
                gold_coins_total   = self.dm.gold_coins_total,
                total_estimated_gold=self.dm.total_estimated_gold,
                adventure_counts   = dict(self.dm.adventure_counts),
                adventure_time_totals = dict(self.dm.adventure_time_totals),
                total_character_xp = self.dm.total_character_xp,
                skill_xp_totals    = dict(self.dm.skill_xp_totals),
                blockchain_totals  = dict(self.dm.blockchain_totals),
                non_blockchain_totals=dict(self.dm.non_blockchain_totals),
                non_blockchain_items =set(self.dm.non_blockchain_items),
                container_counts               = dict(self.dm.container_counts),
                container_blockchain_totals    = dict(self.dm.container_blockchain_totals),
                container_non_blockchain_totals= dict(self.dm.container_non_blockchain_totals),
                start_time         = self.dm.start_time,
            )

        now     = self.dm.now_local()
        elapsed = now - snap["start_time"]
        offset  = self.dm.settings.get("gmt_offset", 0)
        gmt_str = f"GMT{offset:+d}" if offset != 0 else "GMT+0"
        self.label_player_name.configure(text=snap["player_name"])
        self.label_server_time.configure(text=f"Local Time ({gmt_str}): {now:%Y-%m-%d %H:%M:%S}")
        self.label_elapsed_time.configure(text=f"App Running: {str(elapsed).split('.')[0]}")

        midnight  = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        secs_left = int((midnight - now).total_seconds())
        rh, rrem  = divmod(secs_left, 3600)
        rm, rs    = divmod(rrem, 60)
        self.label_reset_time.configure(text=f"Reset in: {rh}h {rm:02d}m {rs:02d}s ({gmt_str})")

        if self.dm.settings.get("layout_mode", "vertical") == "horizontal":
            self._refresh_horizontal(snap)
            return

        yview = self.text_output._textbox.yview()
        self.text_output.configure(state="normal")
        self.text_output.delete("1.0", tk.END)

        def bold(t): self.text_output._textbox.insert(tk.END, t + "\n", "bold")

        if self.show_totals["runs"].get():           bold(f"Total Runs: {snap['counter']:,}")
        if self.show_totals["gold"].get():           bold(f"Total Gold Coins: {snap['gold_coins_total']:,}")
        if self.show_totals["estimated_gold"].get(): bold(f"Total Estimated Gold: {snap['total_estimated_gold']:,.0f}")
        if self.show_totals["enj"].get():            bold(f"Total ENJ Value: {snap['total_enj_value']:,.2f}")
        self.text_output.insert(tk.END, "\n")

        if self.show_sections["adventures"].get():
            bold("Adventures:")
            if snap["adventure_counts"]:
                for n, c in sorted(snap["adventure_counts"].items(), key=lambda x: -x[1]):
                    t = snap["adventure_time_totals"].get(n, 0)
                    h, rem = divmod(t, 3600); m, s = divmod(rem, 60)
                    time_str = f"{h}h {m}m {s}s" if h else f"{m}m {s}s"
                    self.text_output.insert(tk.END, f"{n} x{c:,}  ·  {time_str}\n")
            else:
                self.text_output.insert(tk.END, "(no adventures yet)\n")

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
            filtered = [(n, a) for n, a in snap["non_blockchain_totals"].items()
                        if n in snap["non_blockchain_items"]]
            if filtered:
                for n, a in sorted(filtered):
                    self.text_output.insert(tk.END, f"{n} x{a:,}\n")
            else:
                self.text_output.insert(tk.END, "(none)\n")

        if self.show_sections["containers"].get():
            bold("\nOpened Containers:")
            if snap["container_counts"]:
                for n, c in sorted(snap["container_counts"].items(), key=lambda x: -x[1]):
                    self.text_output.insert(tk.END, f"{n} x{c:,}\n")
            else:
                self.text_output.insert(tk.END, "(none)\n")

        if self.show_sections["container_blockchain"].get():
            bold("\nContainer Blockchain Items:")
            if snap["container_blockchain_totals"]:
                for n, a in sorted(snap["container_blockchain_totals"].items()):
                    self.text_output.insert(tk.END, f"{n} x{a:,}\n")
            else:
                self.text_output.insert(tk.END, "(none)\n")

        if self.show_sections["container_non_blockchain"].get():
            bold("\nContainer Non-Blockchain Items:")
            filtered_cont = [(n, a) for n, a in snap["container_non_blockchain_totals"].items()
                             if n in snap["non_blockchain_items"]]
            if filtered_cont:
                for n, a in sorted(filtered_cont):
                    self.text_output.insert(tk.END, f"{n} x{a:,}\n")
            else:
                self.text_output.insert(tk.END, "(none)\n")

        self.text_output.configure(state="disabled")
        self.text_output._textbox.yview_moveto(yview[0])

    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------
    def _show_about(self):
        messagebox.showinfo("About", "Lost Relics Daily Tracker\nDeveloped by Capoeira")

    def _show_donate(self):
        donate_window = ctk.CTkToplevel(self.root)
        donate_window.title("Donate / Support")
        donate_window.resizable(True, True)
        w, h = 400, 400
        sx, sy = donate_window.winfo_screenwidth(), donate_window.winfo_screenheight()
        donate_window.geometry(f"{w}x{h}+{(sx-w)//2}+{(sy-h)//2}")

        ctk.CTkLabel(donate_window, text="Support / Donations", font=FONT_POPUP_TITLE).pack(pady=(10, 5))
        ctk.CTkLabel(
            donate_window,
            text="If you enjoy this tool and want to support its development:\n\nEnjin Matrixchain:",
            font=FONT_POPUP_BODY, justify="left", wraplength=380,
        ).pack(pady=(0, 5))

        address = "efQUbKs6THBXz5iqgbq6xueTicyF35TepybZY36RFQwZ5gRm6"
        e = ctk.CTkEntry(donate_window, font=FONT_POPUP_BODY, width=380)
        e.pack(pady=(0, 5), padx=10)
        e.insert(0, address)
        e.configure(state="disabled")

        def copy():
            donate_window.clipboard_clear()
            donate_window.clipboard_append(address)
            messagebox.showinfo("Copied", "Address copied to clipboard!")

        ctk.CTkButton(donate_window, text="Copy Address", command=copy).pack(pady=(0, 10))

        try:
            from PIL import Image, ImageTk
            qr_path = resource_path("images/qr_matrixchain.png")
            if os.path.isfile(qr_path):
                img   = Image.open(qr_path)
                photo = ImageTk.PhotoImage(img)
                lbl   = ctk.CTkLabel(donate_window, image=photo, text="")
                lbl.pack()
                donate_window.qr_photo = photo
            else:
                ctk.CTkLabel(donate_window, text="QR Image not found", text_color="red").pack()
        except Exception as ex:
            ctk.CTkLabel(donate_window, text=f"QR Image error: {ex}", text_color="red").pack()

    def _summarize_runs_popup(self):
        start_date = simpledialog.askstring("Summarize Runs", "Start Date (YYYY-MM-DD):")
        if not start_date:
            return
        end_date = simpledialog.askstring("Summarize Runs", "End Date (YYYY-MM-DD):")
        if not end_date:
            return

        summary     = self.dm.summarize_logs(start_date, end_date)
        summary_txt = self.dm.format_summary(summary, start_date, end_date)

        win = ctk.CTkToplevel(self.root)
        win.title("Summary of Runs")
        sh  = win.winfo_screenheight()
        win.geometry(f"500x{sh}+{(win.winfo_screenwidth()-500)//2}+0")
        win.resizable(True, True)

        ctk.CTkLabel(win, text="Lost Relics Adventure Report", font=FONT_POPUP_TITLE).pack(pady=(10, 0))
        ctk.CTkLabel(win, text=f"From {start_date} to {end_date}", font=FONT_POPUP_BODY).pack(pady=(0, 10))

        ctk.CTkButton(
            win, text="Download as Excel",
            command=lambda: self.dm.export_summary_to_excel(summary, start_date, end_date),
        ).pack(pady=(0, 10))

        ta = ctk.CTkTextbox(win, wrap="word", font=FONT_POPUP_BODY)
        ta.pack(fill="both", expand=True, padx=10, pady=5)
        ta.insert("1.0", summary_txt)
        ta.configure(state="disabled")


# ===========================================================================
# RunCounterApp  — orchestrator
# ===========================================================================
class RunCounterApp:
    def __init__(self, root: tk.Tk):
        self.root       = root
        self.dm         = DataManager(LOG_DIR, CONFIG_FILE, EXCLUDE_FILE)
        self.ui         = TrackerUI(root, self.dm)
        self.stop_event = threading.Event()

        self.ws_client = WebSocketClient(
            url             = WS_URL,
            on_adventure    = self._handle_adventure,
            on_player       = self._handle_player,
            on_container    = self._handle_container,
            on_status       = self._handle_ws_status,
            stop_event      = self.stop_event,
            reconnect_delay = RECONNECT_DELAY,
        )

        self.ws_thread = threading.Thread(target=self.ws_client.run, daemon=True, name="ws-thread")
        self.ws_thread.start()

        self._schedule_ui_refresh()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._install_signal_handlers()
        self._install_excepthook()

    # ------------------------------------------------------------------
    # Callbacks from WebSocketClient
    # ------------------------------------------------------------------
    def _check_daily_reset(self):
        """Reset counters if the local date has rolled over. Must be called under self.dm.lock."""
        today = self.dm.now_local().date()
        if today != self.dm.current_log_date:
            self.dm.reset_daily_counters_locked(today)

    def _handle_adventure(self, adv: dict):
        """Called for each adventure object in an 'adventures' event."""
        with self.dm.lock:
            self._check_daily_reset()

            instance_id = adv.get("AdventureInstance")
            if not instance_id or not adv.get("AdventureName"):
                return
            if instance_id in self.dm.seen_adventure_instances:
                return                                 

            self.dm.seen_adventure_instances.add(instance_id)
            self.dm.process_adventure_locked(adv)

        self.dm.save_log()

    def _handle_player(self, player: dict):
        """Called when a 'player' event arrives."""
        name = player.get("PlayerName")
        if name:
            with self.dm.lock:
                self.dm.player_name = name

    def _handle_container(self, cont: dict):
        """Called for each container object in a 'containers' event."""
        with self.dm.lock:
            self._check_daily_reset()

            instance_id = cont.get("ContainerInstance")
            if not instance_id or not cont.get("Name"):
                return
            if instance_id in self.dm.seen_container_instances:
                return

            self.dm.seen_container_instances.add(instance_id)
            self.dm.process_container_locked(cont)

        self.dm.save_log()

    def _handle_ws_status(self, text: str):
        """Forward connection status to the UI label (thread-safe)."""
        self.root.after(0, self.ui.set_ws_status, text)

    # ------------------------------------------------------------------
    # UI refresh loop
    # ------------------------------------------------------------------
    def _schedule_ui_refresh(self):
        if not self.stop_event.is_set():
            self.ui.refresh_ui()
            self.root.after(1_000, self._schedule_ui_refresh)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    def _on_close(self):
        try:
            settings = {
                "window_width":  self.ui.root.winfo_width(),
                "window_height": self.ui.root.winfo_height(),
                "dark_mode":     self.ui.dark_mode,
                "currency":      self.ui.currency_var.get(),
                "gmt_offset":    self.dm.settings.get("gmt_offset", 0),
                "overlay_mode":  self.dm.settings.get("overlay_mode", False),
                "layout_mode":   self.dm.settings.get("layout_mode", "vertical"),
                "show_totals":   {k: v.get() for k, v in self.ui.show_totals.items()},
                "show_sections": {k: v.get() for k, v in self.ui.show_sections.items()},
            }
            self.dm.save_settings(settings)
        except Exception:
            pass

        self.stop_event.set()
        self.ws_client.close()

        try:
            self.dm.save_log()
        except Exception:
            pass

        if self.ws_thread.is_alive():
            self.ws_thread.join(timeout=3)

        self.root.destroy()

    def _install_signal_handlers(self):
        def handler(signum, frame):
            self.dm.save_error_log(f"Signal {signum} received, shutting down.")
            self._on_close()

        for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
            if sig:
                try:
                    signal.signal(sig, handler)
                except Exception:
                    pass

    def _install_excepthook(self):
        def _hook(exc_type, exc, tb):
            try:
                self.dm.save_error_log(f"Uncaught exception: {exc_type.__name__}: {exc}")
                self.dm.save_log()
            finally:
                self.stop_event.set()
                self.ws_client.close()
                if self.ws_thread.is_alive():
                    try: self.ws_thread.join(timeout=3)
                    except Exception: pass
                sys.__excepthook__(exc_type, exc, tb)
                try: self.root.quit()
                except Exception: pass
        sys.excepthook = _hook


# ===========================================================================
# Entry point
# ===========================================================================
if __name__ == "__main__":
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    app  = RunCounterApp(root)
    root.mainloop()