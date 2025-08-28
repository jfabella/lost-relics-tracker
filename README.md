# Lost Relics Daily Tracker

Keep track of your daily Lost Relics adventure runs, items, and XP in one simple desktop app. Built with Python and Tkinter.

---
## UI Preview
<img width="346" height="667" alt="image" src="https://github.com/user-attachments/assets/4a309bda-b2ec-4f99-8e9c-99b0868eb4da" />

## Support / Donations
If you enjoy this tool and want to support its development, you can donate:

- **Enjin Matrixchain**:
- Address: efQUbKs6THBXz5iqgbq6xueTicyF35TepybZY36RFQwZ5gRm6
<img src="images/qr_matrixchain.png" alt="Enjin Matrixchain QR" width="200"/>

- **Enjin Relaychain**:
- Address: enC1SuKusQy1QhiMEC2vaavYcZxy2ovUDoZETsa9iu5zEpUTC
<img src="images/qr_relaychain.png" alt="Enjin Relaychain QR" width="200"/>

Every bit helps keep the app running and improving — thank you! 

---

## How to Use

### 1. Download and Extract
- Download the latest release from the [GitHub releases page](https://github.com/jfabella/lost-relics-tracker/tags).
- Extract the contents of the `.zip` file to a folder of your choice.
- Inside the folder, you will find the `.exe` file for the application.

### 2. Configure Tracked Items
- **Edit `non_blockchain_config.json`**:
  - Open this file in a text editor (e.g., Notepad) to add or remove non-blockchain items that you wish to track in the UI.
  - Any changes made will persist across app restarts.

- **Edit `non_blockchain_exclude.json`**:
  - This file allows you to add items that should **not contribute** to the estimated total gold.
  - Update it as needed to ensure only relevant items are tracked for gold calculation.

### 3. Run the App
- Double-click the `.exe` file to run the application.
- The app should open, and you can start interacting with the UI.

### 4. Lost Relics In-Game Settings
- Enable the Query API in your Lost Relics game by navigating to Settings → Query API.

### 5. UI Interaction
- **Toggle Theme**: Switch between light and dark modes to customize your UI experience.

### 6. Data Persistence
- All your adventure data is automatically saved in **daily JSON files** located in the `run_logs/` directory. These files include:
  - Total runs
  - Gold coins collected
  - Total estimated gold
  - Blockchain and non-blockchain tracked items
  - Character XP and skill XP totals
- On app restart, all these values are restored, allowing you to continue where you left off.

### 7. Viewing Logs
- **Error Logs**: Any errors with the API, timeouts, or invalid data are logged in:
  - `run_logs/error_YYYY-MM-DD.txt`
  
- **Daily Adventure Logs**: Adventure data for each day is stored in:
  - `run_logs/runs_YYYY-MM-DD.json`
  - These logs can be reviewed or backed up as needed.

### 8. Daily Reset
- **Automatic Reset**: Counters automatically reset at the daily server reset (midnight GMT+0).  
- **New Log File**: A fresh log file (`runs_YYYY-MM-DD.json`) is created for each new day.  
- **No Restart Needed**: The app rolls over to the new day automatically, even if it stays running.

---

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
      "Giant Bone"
    ]
    ```
## Bugs and Issues
- For any bugs or issues encountered, kindly raise it here with complete replication details:
- https://github.com/jfabella/lost-relics-tracker/issues

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





