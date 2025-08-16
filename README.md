Got it! Here’s the full `README.md` content all in one code block so you can easily copy it without extra formatting or markdown interfering:

````markdown
# Lost Relics Daily Tracker

A lightweight desktop tracker for monitoring your daily Lost Relics adventure runs, blockchain items, and experience gained — built with Python and Tkinter.

---

## 🧰 Features

- 🎯 Counts daily adventure runs.
- 📊 Tracks blockchain items (names and quantities).
- ⚔️ Records experience gained:
  - Total Character XP
  - Skill XP: Fishing, Mining, Scavenging, Woodcutting
- 📅 Daily log files saved automatically.
- ⏱ Displays app uptime and system time.
- 🔁 Data resets automatically at 12:00 AM.
- 📦 Built as a standalone desktop app (no Python required after build).
- 🧑‍💻 Developed by **Capoeira**.

---

## 🖥️ Requirements (For Running from Source)

If you're running from source code (not as an executable):

- Python 3.9+
- `requests` module

Install dependencies:
```bash
pip install requests
````

---

## 🚀 How to Run

### 1. Running from Source Code (Development Mode)

**Step 1:** Clone or download the repository.

**Step 2:** Ensure you have Python 3.9 or newer installed.

Check Python version:

```bash
python --version
```

**Step 3:** Install the required Python package:

```bash
pip install requests
```

**Step 4:** Ensure the Lost Relics game is running and its local API server is active at:

```
http://localhost:11990/Player
```

**Step 5:** Run the tracker script:

```bash
python lost_relics_tracker.py
```

The tracker window will open and start displaying your daily stats.

---

### 2. Building a Standalone Executable (No Python Needed)

If you want to share the tracker with friends who do not have Python installed:

**Step 1:** Install [PyInstaller](https://pyinstaller.org/):

```bash
pip install pyinstaller
```

**Step 2:** Build the executable using PyInstaller:

```bash
pyinstaller --noconfirm --onefile --windowed lost_relics_tracker.py
```

**Step 3:** After building, find the executable in the `dist/` directory:

* On Windows: `dist\lost_relics_tracker.exe`
* On macOS/Linux: `dist/lost_relics_tracker`

**Step 4:** You can now share this executable. Your friends can run it without installing Python or any dependencies.

---

## 📂 Logs

All run data is stored in a folder called `run_logs/`, one file per day:

```
run_logs/runs_YYYY-MM-DD.json
```

This file contains your daily run counts, blockchain item totals, and XP data.

---

## 📸 UI Overview

* **Player Name** displayed at the top in large font
* **System Time** and **App Uptime**
* **Total Runs** and per-adventure run counts
* **Character XP** and **Skill XP** (Fishing, Mining, Scavenging, Woodcutting)
* **Blockchain Items** listed alphabetically with quantities

---

## ⚠️ Notes

* Make sure Lost Relics is running and the local API is available before starting the tracker.
* The app polls the API every 5 seconds.
* All data resets at midnight (system local time).
* Logs are automatically saved daily and loaded on startup.

---

## 🙋‍♂️ Developer

Made with ❤️ by **Capoeira**

Feel free to share, modify, or contribute!

```

---
