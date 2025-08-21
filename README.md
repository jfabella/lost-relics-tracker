# Lost Relics Daily Tracker

Keep track of your daily Lost Relics adventure runs, items, and XP in one simple desktop app. Built with Python and Tkinter.

---

## Support / Donations
If you enjoy this tool and want to support its development, you can donate:

- **Enjin Matrixchain**: `<your_enjin_wallet_address_here>`  
- **Enjin Relaychain**: `<your_enjin_wallet_address_here>`

Every bit helps keep the app running and improving — thank you! 

---

## Features

### 1. Player Info
- See your player name, level, and XP.
- Tracks total character XP and selected skills: Fishing, Mining, Scavenging, Woodcutting.
- XP from each adventure is added automatically.

### 2. Adventure Logging
- The app checks the game for your latest adventure automatically.
- Adventures are tracked so duplicates are avoided.
- Counts how many times you've completed each adventure.

### 3. Gold & Items
- **Gold Coins** are tracked separately and saved.
- **Non-blockchain items**:
  - Only the items listed in `non_blockchain_config.json` show in the app and are saved.
  - You can choose items that **don’t count** toward total estimated gold using `non_blockchain_exclude.json`.
- **ALL Blockchain items** are automatically tracked, with their ENJ value calculated at the time of the adventure.

### 4. Total Estimated Gold
- Shows Gold Coins plus the value of non-excluded non-blockchain items.
- Items in `non_blockchain_exclude.json` are ignored.
- Total estimated gold is saved even if you restart the app.

### 5. User Interface
- Shows:
  - Player name and server time
  - How long the app has been running
  - Total runs, gold coins, estimated gold, ENJ value
  - Adventure counts
  - Character and skill XP
  - Blockchain items
  - Tracked non-blockchain items
- **Toggle Theme** button: switch between light and dark mode.
- **Manual Reset** button: reset daily counters without duplicating adventures.

### 6. Daily Reset
- Counters reset automatically at midnight.
- Prevents counting the same adventure twice.
- Keeps track of the last adventure so the first new adventure is counted correctly.

### 7. Logging
- Saves daily JSON files in `run_logs/` with:
  - Runs, gold coins, total estimated gold
  - Blockchain and tracked non-blockchain items
  - Adventure counts and XP
  - Last adventure signature
- Errors and API issues are saved in `run_logs/error_YYYY-MM-DD.txt`.

---

## How to Use

2. **Set Up Tracked Items**
   - Open `non_blockchain_config.json` to add or remove non-blockchain items to track in the UI.
   - Open `non_blockchain_exclude.json` to list items that **should not count** toward estimated gold.

3. **Run the App**
```bash
python lost_relics_tracker.py
 ```

2. **Configure Tracked Items**
   - Edit `non_blockchain_config.json` to add or remove non-blockchain items that should appear in the UI and be persisted.
   - Edit `non_blockchain_exclude.json` to add items that should **not contribute** to total estimated gold.

3. **UI Interaction**
   - **Toggle Theme**: Switch between light and dark modes.
   - **Manual Reset**: Clears counters for the current day but preserves the last adventure signature.

4. **Data Persistence**
- All your adventure data is automatically saved in daily JSON files inside `run_logs/`.
- This includes:
  - Total runs
  - Gold Coins collected
  - Total estimated gold
  - Blockchain and tracked non-blockchain items
  - Character XP and skill XP totals
- When you restart the app, all these numbers are preserved so you can continue where you left off.

5. **Viewing Logs**
- Any errors with the API, timeouts, or invalid data are logged in `run_logs/error_YYYY-MM-DD.txt`.
- Daily adventure data is stored in `run_logs/runs_YYYY-MM-DD.json` for review or backup.

6. **Daily Reset**
- Counters automatically reset at midnight to start a fresh day.
- The app remembers the last adventure signature to **avoid counting the same adventure twice** after a reset.

7. **Manual Reset**
- You can reset counters manually at any time using the **Manual Reset** button in the UI.
- This clears all counters for the current day **without duplicating the last adventure**, letting you start fresh whenever needed.


## Configuration Files

- **`non_blockchain_config.json`**
  - These are items whose count you want to monitor during your adventures.
  - Example:
    ```json
    [
      "Deepsea Coffer",
      "Golden Grind Chest",
      "Frostfall Shard",
      "Coin Pouch",
      "Coal"
    ]
    ```

- **`non_blockchain_exclude.json`**
  - Items to exclude from total estimated gold (you don’t plan to sell).
  - Example:
    ```json
    [
      "Deepsea Coffer",
      "Zukaron",
      "Large Bones",
      "Giant Bone",
      "
    ]
    ```

## Requirements

- Python 3.10+
- Modules:
  - `tkinter`
  - `requests`


## 🙋‍♂️ Developer

Made with ❤️ by **Capoeira**

Feel free to share, modify, or contribute!

```

---

