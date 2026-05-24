# FrogSpy

A two-part bazaar price checking tool for the [Project Lazarus](https://www.lazaruseq.com/) EverQuest emulator server, powered by [FrogTracker](https://frogtracker.biz).

## Overview

- **`frogspy.lua`** — MacroQuest Lua script that exports your trader's inventory to a flat file using MQ2Bzsrch
- **`frogspy.py`** — Python script with a full GUI and CLI; checks each item's price against live market data from [FrogTracker](https://frogtracker.biz). The FrogTracker API data layer (formerly `frogspy_scraper.py`) is included directly.
- **`frogspy_display.py`** — Optional rich terminal output module used by the CLI mode
- **`frogspy.bat`** — Double-click launcher; opens the GUI with no terminal window

## Requirements

### In-game (Lua exporter)
- MacroQuest (Rekka's E3Next build for Project Lazarus)
- MQ2Bzsrch plugin (included in the Lazarus MQ build — loaded automatically by the script)

### Python (price checker)
- Python 3.8+
- `requests` library: `pip install requests`
- `rich` library *(optional, for color CLI output)*: `pip install rich`

## Usage

### Step 1 — Export your trader inventory

1. Log into your trader character and enter trader mode (`/trader`)
2. Run the Lua script — it opens the Bazaar Search Window automatically:
   ```
   /lua run frogspy
   ```
3. This creates `kreigar_inventory.txt` on your Desktop in `ItemName|Price` format

### Step 2 — Check prices against the market

**GUI (recommended):** Double-click `frogspy.bat`, or run:
```
python frogspy.py --gui
```

The GUI lets you browse for your inventory file, set your trader name, and watch results stream in as each item is checked. Rows are color-coded: red = undercut, green = cheapest/tied, blue = solo. Click any column header to sort.

**CLI:**
```
python frogspy.py --inventory "C:\Users\YourName\Desktop\kreigar_inventory.txt"
```

If `rich` is installed you get color-coded output with a live scan feed and summary dashboard. Without it, FrogSpy falls back to plain text automatically.

#### CLI options

| Argument | Default | Description |
|---|---|---|
| `--inventory` | *(required for CLI)* | Path to inventory file |
| `--trader` | `Kreigar` | Your trader's character name |
| `--delay` | `0.3` | Seconds between API requests |
| `--output` | `frogspy_output.txt` | Output report file |
| `--no-cache` | *(flag)* | Disable the in-memory response cache |
| `--gui` | *(flag)* | Launch the graphical interface |

### Example CLI output (plain text)

```
FrogSpy v1.5.0 -- Originally created by Alektra <Lederhosen>

[1/20] Checking: Crystal Dagger (your price: 100,000)
  Crystal Dagger: UNDERCUT -- your 100,000 vs lowest 50,000 (+50,000 / +100.0%) | 1 competitor(s) | 7d low: 50,000 | 7d med: 50,000

============================================================
FrogSpy -- Kreigar -- 2026-05-24 20:58:57
============================================================
Total items checked : 20
Cheapest / tied     : 1
Being undercut      : 8
No competition      : 11
Time elapsed        : 14.4s
============================================================
```

## Using the API data layer in your own scripts

The FrogTracker client is importable directly from `frogspy.py`:

```python
from frogspy import make_client

with make_client(delay=0.3) as client:
    result = client.get_item_history("Water Flask")
    if result:
        print(result.windows.seven_day_low)          # 7-day lowest price
        print(result.windows.thirty_day_median)      # 30-day median
        print(result.competitor_prices("Kreigar"))   # sorted list of rival prices

    names = client.search_items("robe")              # item name search
    deals = client.get_hot_dealz()                   # server hot deals list
```

### Price windows available

| Field | Description |
|---|---|
| `seven_day_low` / `seven_day_median` | 7-day lowest and median |
| `thirty_day_low` / `thirty_day_median` | 30-day lowest and median |
| `ninety_day_low` / `ninety_day_median` | 90-day lowest and median |
| `one_year_low` / `one_year_median` | 1-year lowest and median |
| `lifetime_low` / `lifetime_median` | All-time lowest and median |

## Important notes

### MQ2Bzsrch on Project Lazarus
MQ2Bzsrch crashes the EQ client if it triggers a search while the Bazaar Search Window is closed. FrogSpy handles this automatically — it opens the window and waits for it to be ready before searching. No manual setup required.

MQ2Bzsrch is disabled by default in the Lazarus MQ build (`mq2bzsrch=0` in `MacroQuest.ini`). The Lua script loads it automatically at runtime — you do not need to enable it permanently.

### Price format
MQ2Bzsrch returns prices in copper (PGSC format). The script converts to platinum automatically (divided by 1000, rounded to nearest plat).

### Duplicate items
If you have multiple stacks of the same item at the same price, they appear as one entry in the inventory file. The price check still works correctly.

## File locations

| File | Location |
|---|---|
| `frogspy.lua` | `C:\Games\MacroQuest\lua\` |
| `frogspy.py` | Anywhere Python can run it |
| `frogspy_display.py` | Same directory as `frogspy.py` |
| `frogspy.bat` | Same directory as `frogspy.py` |
| Inventory file (output) | Desktop (configurable in lua script) |
| Report file (output) | Same directory as `frogspy.py` |

## License

MIT
