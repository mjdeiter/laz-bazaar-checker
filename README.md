# laz-bazaar-checker
<img src="https://github.com/user-attachments/assets/0bf1fa5c-a109-448b-a9ef-4b52be0d1884" width="200" alt="FrogTracker logo" />

A two-part bazaar price checking tool for the [Project Lazarus](https://www.lazaruseq.com/) EverQuest emulator server.

## Overview

- **`bazaar_checker.lua`** — MacroQuest Lua script that exports your trader's inventory to a flat file using MQ2Bzsrch
- **`bazaar_checker.py`** — Python script that reads the inventory file and checks each item's price against live market data from [FrogTracker](https://frogtracker.biz)

## Requirements

### In-game (Lua exporter)
- MacroQuest (Rekka's E3Next build for Project Lazarus)
- MQ2Bzsrch plugin (included in the Lazarus MQ build — loaded automatically by the script)

### Python (price checker)
- Python 3.8+
- `requests` library: `pip install requests`

## Usage

### Step 1 — Export your trader inventory

1. Log into your trader character and enter trader mode (`/trader`)
2. Run the Lua script — it opens the Bazaar Search Window automatically:
   ```
   /lua run bazaar_checker
   ```
3. This creates `kreigar_inventory.txt` on your Desktop in `ItemName|Price` format

### Step 2 — Check prices against the market

```
python bazaar_checker.py --inventory "C:\Users\YourName\Desktop\kreigar_inventory.txt"
```

#### Options

| Argument | Default | Description |
|---|---|---|
| `--inventory` | *(required)* | Path to inventory file |
| `--trader` | `Kreigar` | Your trader's character name |
| `--delay` | `0.3` | Seconds between API requests |
| `--output` | `bazaar_check_output.txt` | Output report file |

### Example output

```
[1/20] Checking: Crystal Dagger (your price: 100,000)
  Crystal Dagger: UNDERCUT -- your 100,000 vs lowest 50,000 (+50,000 / +100.0%) | 1 competitor(s) | 7d low: 50,000 | 7d med: 50,000

============================================================
SUMMARY for Kreigar -- 2026-05-23 13:16:59
============================================================
Total items checked : 20
Cheapest / tied     : 0
Being undercut      : 11
No competition      : 9
Time elapsed        : 15.5s
============================================================
```

## Important notes

### MQ2Bzsrch on Project Lazarus
MQ2Bzsrch crashes the EQ client if it triggers a search while the Bazaar Search Window is closed. The Lua script handles this automatically — it opens the window and waits for it to be ready before searching. No manual setup required.

MQ2Bzsrch is disabled by default in the Lazarus MQ build (`mq2bzsrch=0` in `MacroQuest.ini`). The export script loads it automatically at runtime — you do not need to enable it permanently.

### Price format
MQ2Bzsrch returns prices in copper (PGSC format). The script converts to platinum automatically (divided by 1000, rounded to nearest plat).

### Duplicate items
If you have multiple stacks of the same item at the same price, they appear as one entry in the inventory file. The price check still works correctly.

## File locations

| File | Location |
|---|---|
| `bazaar_checker.lua` | `C:\Games\MacroQuest\lua\` |
| `bazaar_checker.py` | Anywhere Python can run it |
| Inventory file (output) | Desktop (configurable in lua script) |
| Report file (output) | Same directory as `bazaar_checker.py` |

## License

MIT
