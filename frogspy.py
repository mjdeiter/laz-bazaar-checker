"""
frogspy.py — FrogSpy v1.5.0
Bazaar price checker for Project Lazarus EverQuest EMU
Originally created by Alektra <Lederhosen>

Includes the FrogTracker API data layer (formerly frogspy_scraper.py).
Entry points:
  - CLI:  python frogspy.py --inventory <file> [options]
  - GUI:  python frogspy.py --gui   (or launched via frogspy.bat)
"""

from __future__ import annotations

import argparse
import datetime
import dataclasses
import os
import random
import sys
import threading
import time
import urllib3
import requests
from typing import Optional

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCRIPT_VERSION   = "1.5.0"
FROGTRACKER_BASE = "https://frogtracker.biz/Home"

_DEFAULT_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# ── Status constants ────────────────────────────────────────────────────────────

STATUS_UNDERCUT  = "undercut"
STATUS_NONE      = "none"
STATUS_CHEAPEST  = "cheapest"

# ── Scrapers / data layer ───────────────────────────────────────────────────────

@dataclasses.dataclass
class PriceWindows:
    seven_day_low:      Optional[int]
    seven_day_median:   Optional[int]
    thirty_day_low:     Optional[int]
    thirty_day_median:  Optional[int]
    ninety_day_low:     Optional[int]
    ninety_day_median:  Optional[int]
    one_year_low:       Optional[int]
    one_year_median:    Optional[int]
    lifetime_low:       Optional[int]
    lifetime_median:    Optional[int]


@dataclasses.dataclass
class HistoryEntry:
    auction_date:   str
    price:          int
    seller_name:    str
    is_for_sale_now: bool


@dataclasses.dataclass
class ItemHistoryResult:
    item_name:        str
    last_scrape_time: Optional[int]
    history:          list
    windows:          PriceWindows

    def active_listings(self):
        return [e for e in self.history if e.is_for_sale_now]

    def active_listings_excluding(self, trader_name: str):
        lower = trader_name.lower()
        return [e for e in self.active_listings() if e.seller_name.lower() != lower]

    def competitor_prices(self, trader_name: str):
        return sorted(e.price for e in self.active_listings_excluding(trader_name))


@dataclasses.dataclass
class HotDeal:
    item_name:    str
    price:        int
    seller_name:  str
    lowest_price: Optional[int]


class _TTLCache:
    def __init__(self, ttl_seconds: int = 300):
        self._ttl   = ttl_seconds
        self._store = {}

    def get(self, key: str):
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > self._ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value) -> None:
        self._store[key] = (time.time(), value)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()


class ScraperClient:
    """FrogTracker API client with retry, jitter, and optional TTL cache."""

    def __init__(self, delay=0.3, retries=3, cache_ttl=300, timeout=15):
        self._delay   = delay
        self._retries = retries
        self._timeout = timeout
        self._cache   = _TTLCache(cache_ttl) if cache_ttl > 0 else None
        self._session = requests.Session()
        self._session.headers.update(_DEFAULT_HEADERS)
        self._last_req = 0.0

    def _throttle(self):
        if self._delay <= 0:
            return
        elapsed = time.time() - self._last_req
        wait = max(0.0, random.uniform(self._delay * 0.5, self._delay * 1.5) - elapsed)
        if wait:
            time.sleep(wait)
        self._last_req = time.time()

    def _get(self, endpoint: str, params: dict):
        url     = f"{FROGTRACKER_BASE}/{endpoint}"
        backoff = 1.0
        for attempt in range(1, self._retries + 1):
            try:
                self._throttle()
                resp = self._session.get(url, params=params, timeout=self._timeout, verify=False)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.HTTPError as exc:
                if exc.response is not None and exc.response.status_code < 500:
                    return None
            except requests.exceptions.RequestException:
                pass
            if attempt < self._retries:
                time.sleep(backoff + random.uniform(0, 0.5))
                backoff *= 2
        return None

    def get_item_history(self, item_name: str) -> Optional[ItemHistoryResult]:
        key = f"history:{item_name.lower()}"
        if self._cache:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
        raw = self._get("ItemHistory", {"itemName": item_name})
        if raw is None:
            return None
        result = _parse_item_history(raw)
        if result is not None and self._cache:
            self._cache.set(key, result)
        return result

    def search_items(self, query: str) -> list:
        raw = self._get("Search", {"q": query})
        return (raw or {}).get("itemNames", []) or []

    def get_hot_dealz(self) -> list:
        raw = self._get("HotDealz", {})
        deals = (raw or {}).get("dealz") or []
        results = []
        for d in deals:
            try:
                results.append(HotDeal(
                    item_name=d.get("itemName", ""),
                    price=_safe_int(d.get("price")),
                    seller_name=d.get("sellerName", ""),
                    lowest_price=d.get("lowestPrice"),
                ))
            except Exception:
                continue
        return results

    def close(self):
        self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _parse_item_history(raw: dict) -> Optional[ItemHistoryResult]:
    try:
        history = []
        for e in raw.get("history") or []:
            try:
                history.append(HistoryEntry(
                    auction_date=e.get("auctionDate", ""),
                    price=_safe_int(e.get("price")),
                    seller_name=e.get("sellerName", ""),
                    is_for_sale_now=bool(e.get("isForSaleNow", False)),
                ))
            except Exception:
                continue
        windows = PriceWindows(
            seven_day_low=raw.get("sevenDayLowestPrice"),
            seven_day_median=raw.get("sevenDayMedianPrice"),
            thirty_day_low=raw.get("thirtyDayLowestPrice"),
            thirty_day_median=raw.get("thirtyDayMedianPrice"),
            ninety_day_low=raw.get("ninetyDayLowestPrice"),
            ninety_day_median=raw.get("ninetyDayMedianPrice"),
            one_year_low=raw.get("oneYearLowestPrice"),
            one_year_median=raw.get("oneYearMedianPrice"),
            lifetime_low=raw.get("lifetimeLowestPrice"),
            lifetime_median=raw.get("lifetimeMedianPrice"),
        )
        return ItemHistoryResult(
            item_name=raw.get("itemName", ""),
            last_scrape_time=raw.get("lastScrapeTime"),
            history=history,
            windows=windows,
        )
    except Exception:
        return None


def _safe_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def make_client(delay=0.3, cache_ttl=300) -> ScraperClient:
    return ScraperClient(delay=delay, cache_ttl=cache_ttl)


# ── Shared analysis logic ───────────────────────────────────────────────────────

def load_inventory(filepath: str) -> dict:
    items = {}
    if not os.path.exists(filepath):
        return items
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) == 2:
                name = parts[0].strip()
                try:
                    items[name] = int(parts[1].strip().replace(",", ""))
                except ValueError:
                    pass
    return items


def analyze_item(item_name: str, my_price: int, history_result, trader_name: str) -> dict:
    if history_result is None:
        return {
            "name": item_name, "your_price": my_price,
            "status": STATUS_NONE, "lowest": None,
            "rivals": 0, "low7": None, "med7": None,
            "low30": None, "med30": None,
            "low90": None, "med90": None,
            "lifetime_low": None, "lifetime_med": None,
            "error": True,
        }
    prices = history_result.competitor_prices(trader_name)
    w = history_result.windows
    if not prices:
        status, lowest, rivals = STATUS_NONE, None, 0
    else:
        lowest = prices[0]
        rivals = len(prices)
        status = STATUS_CHEAPEST if my_price <= lowest else STATUS_UNDERCUT
    return {
        "name":         item_name,
        "your_price":   my_price,
        "status":       status,
        "lowest":       lowest,
        "rivals":       rivals,
        "low7":         w.seven_day_low,
        "med7":         w.seven_day_median,
        "low30":        w.thirty_day_low,
        "med30":        w.thirty_day_median,
        "low90":        w.ninety_day_low,
        "med90":        w.ninety_day_median,
        "lifetime_low": w.lifetime_low,
        "lifetime_med": w.lifetime_median,
    }


def format_result_plain(result: dict) -> str:
    name      = result["name"]
    my_price  = result["your_price"]
    status    = result["status"]
    lowest    = result.get("lowest")
    rivals    = result.get("rivals", 0)
    low7      = result.get("low7")
    med7      = result.get("med7")
    pfmt      = f"{my_price:,}"

    if result.get("error"):
        return f"  {name}: Could not retrieve market data.\n"
    if status == STATUS_NONE:
        extra = f" (7d low: {low7:,} | 7d med: {med7:,})" if low7 else ""
        return f"  {name}: Your price {pfmt} -- no other sellers active.{extra}\n"
    if status == STATUS_CHEAPEST:
        stats = f" | 7d low: {low7:,} | 7d med: {med7:,}" if low7 is not None else ""
        return f"  {name}: CHEAPEST (or tied) at {pfmt} | {rivals} competitor(s){stats}\n"
    diff = my_price - lowest
    pct  = (diff / lowest) * 100
    stats = f" | 7d low: {low7:,} | 7d med: {med7:,}" if low7 is not None else ""
    return f"  {name}: UNDERCUT -- your {pfmt} vs lowest {lowest:,} (+{diff:,} / +{pct:.1f}%) | {rivals} competitor(s){stats}\n"


# ── GUI ─────────────────────────────────────────────────────────────────────────

def run_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    # ── Palette ──────────────────────────────────────────────────────────────
    BG        = "#1a1a2e"
    PANEL     = "#16213e"
    ACCENT    = "#e94560"
    TEXT      = "#eaeaea"
    DIM       = "#888888"
    ROW_UNDER = "#3d1a1a"
    ROW_CHEAP = "#1a2d1a"
    ROW_SOLO  = "#1a1a2d"
    TAG_UNDER = "#ff6b6b"
    TAG_CHEAP = "#6bffb8"
    TAG_SOLO  = "#6bb5ff"
    HDR_BG    = "#0f3460"

    root = tk.Tk()
    root.title(f"FrogSpy v{SCRIPT_VERSION}")
    root.configure(bg=BG)
    root.geometry("1100x720")
    root.minsize(900, 600)

    # ── Fonts ────────────────────────────────────────────────────────────────
    try:
        import tkinter.font as tkfont
        FONT_MONO  = tkfont.Font(family="Consolas",   size=10)
        FONT_LABEL = tkfont.Font(family="Segoe UI",   size=10)
        FONT_BOLD  = tkfont.Font(family="Segoe UI",   size=10, weight="bold")
        FONT_TITLE = tkfont.Font(family="Segoe UI",   size=14, weight="bold")
    except Exception:
        FONT_MONO = FONT_LABEL = FONT_BOLD = FONT_TITLE = None

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TFrame",      background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel",      background=BG,    foreground=TEXT)
    style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
    style.configure("Dim.TLabel",  background=BG,    foreground=DIM)
    style.configure("TEntry",      fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT)
    style.configure("Accent.TButton",
                    background=ACCENT, foreground="white",
                    borderwidth=0, relief="flat", padding=(12, 6))
    style.map("Accent.TButton",
              background=[("active", "#c73652"), ("disabled", "#555555")],
              foreground=[("disabled", "#888888")])
    style.configure("TButton",
                    background=HDR_BG, foreground=TEXT,
                    borderwidth=0, relief="flat", padding=(8, 5))
    style.map("TButton", background=[("active", "#1a4a80")])

    # Treeview
    style.configure("FrogSpy.Treeview",
                    background=PANEL, foreground=TEXT,
                    fieldbackground=PANEL, rowheight=26,
                    borderwidth=0, font=FONT_MONO)
    style.configure("FrogSpy.Treeview.Heading",
                    background=HDR_BG, foreground=TEXT,
                    relief="flat", font=FONT_BOLD)
    style.map("FrogSpy.Treeview",
              background=[("selected", "#2a4a7f")],
              foreground=[("selected", "white")])

    # ── State ────────────────────────────────────────────────────────────────
    inv_path_var  = tk.StringVar()
    trader_var    = tk.StringVar(value="Kreigar")
    delay_var     = tk.StringVar(value="0.3")
    status_var    = tk.StringVar(value="Ready")
    scan_running  = threading.Event()
    results_store = []

    stat_vars = {
        "total":    tk.StringVar(value="—"),
        "undercut": tk.StringVar(value="—"),
        "cheapest": tk.StringVar(value="—"),
        "solo":     tk.StringVar(value="—"),
        "elapsed":  tk.StringVar(value="—"),
    }

    # ── Layout: top bar ──────────────────────────────────────────────────────
    top = ttk.Frame(root, style="Panel.TFrame")
    top.pack(fill="x", padx=0, pady=0)

    title_lbl = ttk.Label(top, text=f"🐸 FrogSpy  v{SCRIPT_VERSION}",
                          style="Panel.TLabel", font=FONT_TITLE)
    title_lbl.pack(side="left", padx=18, pady=12)

    sub_lbl = ttk.Label(top, text="Project Lazarus Bazaar Price Checker",
                        style="Panel.TLabel", foreground=DIM, font=FONT_LABEL)
    sub_lbl.pack(side="left", padx=0, pady=12)

    # ── Config bar ───────────────────────────────────────────────────────────
    cfg = ttk.Frame(root)
    cfg.pack(fill="x", padx=16, pady=(10, 4))

    def lbl(parent, text, **kw):
        return ttk.Label(parent, text=text, foreground=DIM, font=FONT_LABEL, **kw)

    # Inventory file row
    inv_row = ttk.Frame(cfg)
    inv_row.pack(fill="x", pady=3)
    lbl(inv_row, "Inventory file").pack(side="left", padx=(0, 8))
    inv_entry = ttk.Entry(inv_row, textvariable=inv_path_var, width=60, font=FONT_MONO)
    inv_entry.pack(side="left", padx=(0, 6))

    def browse():
        path = filedialog.askopenfilename(
            title="Select inventory file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            inv_path_var.set(path)

    ttk.Button(inv_row, text="Browse…", command=browse).pack(side="left")

    # Options row
    opt_row = ttk.Frame(cfg)
    opt_row.pack(fill="x", pady=3)
    lbl(opt_row, "Trader name").pack(side="left", padx=(0, 6))
    ttk.Entry(opt_row, textvariable=trader_var, width=16, font=FONT_MONO).pack(side="left", padx=(0, 20))
    lbl(opt_row, "Delay (s)").pack(side="left", padx=(0, 6))
    ttk.Entry(opt_row, textvariable=delay_var, width=6, font=FONT_MONO).pack(side="left")

    # ── Stat cards ───────────────────────────────────────────────────────────
    cards_frame = ttk.Frame(root)
    cards_frame.pack(fill="x", padx=16, pady=(8, 4))

    card_defs = [
        ("total",    "Items",      TEXT),
        ("undercut", "Undercut",   TAG_UNDER),
        ("cheapest", "Cheapest",   TAG_CHEAP),
        ("solo",     "Solo",       TAG_SOLO),
        ("elapsed",  "Time",       DIM),
    ]

    for key, label, color in card_defs:
        card = tk.Frame(cards_frame, bg=PANEL, padx=14, pady=8)
        card.pack(side="left", padx=(0, 8))
        tk.Label(card, textvariable=stat_vars[key], bg=PANEL,
                 fg=color, font=FONT_BOLD, width=6).pack()
        tk.Label(card, text=label, bg=PANEL, fg=DIM, font=FONT_LABEL).pack()

    # ── Treeview ─────────────────────────────────────────────────────────────
    tree_frame = ttk.Frame(root)
    tree_frame.pack(fill="both", expand=True, padx=16, pady=(4, 0))

    cols = ("status", "name", "your_price", "lowest", "gap", "rivals",
            "low7", "med7", "low30", "med30")
    col_conf = [
        ("status",     "Status",     80,  "center"),
        ("name",       "Item",       260, "w"),
        ("your_price", "Your Price", 100, "e"),
        ("lowest",     "Lowest",     100, "e"),
        ("gap",        "Gap %",      70,  "e"),
        ("rivals",     "Rivals",     60,  "center"),
        ("low7",       "7d Low",     90,  "e"),
        ("med7",       "7d Med",     90,  "e"),
        ("low30",      "30d Low",    90,  "e"),
        ("med30",      "30d Med",    90,  "e"),
    ]

    tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                        style="FrogSpy.Treeview", selectmode="browse")

    for col_id, heading, width, anchor in col_conf:
        tree.heading(col_id, text=heading,
                     command=lambda c=col_id: _sort_tree(c))
        tree.column(col_id, width=width, anchor=anchor, minwidth=40, stretch=(col_id == "name"))

    # Row tags
    tree.tag_configure("undercut", background=ROW_UNDER, foreground=TAG_UNDER)
    tree.tag_configure("cheapest", background=ROW_CHEAP, foreground=TAG_CHEAP)
    tree.tag_configure("solo",     background=ROW_SOLO,  foreground=TAG_SOLO)
    tree.tag_configure("error",    foreground=DIM)

    vsb = ttk.Scrollbar(tree_frame, orient="vertical",   command=tree.yview)
    hsb = ttk.Scrollbar(tree_frame, orient="horizontal",  command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0,  column=1, sticky="ns")
    hsb.grid(row=1,  column=0, sticky="ew")
    tree_frame.grid_rowconfigure(0, weight=1)
    tree_frame.grid_columnconfigure(0, weight=1)

    # ── Status bar ───────────────────────────────────────────────────────────
    bar = tk.Frame(root, bg=PANEL, pady=5)
    bar.pack(fill="x", side="bottom")
    tk.Label(bar, textvariable=status_var, bg=PANEL, fg=DIM,
             font=FONT_LABEL, anchor="w").pack(side="left", padx=12)

    # ── Run / Stop buttons ───────────────────────────────────────────────────
    btn_frame = ttk.Frame(root)
    btn_frame.pack(fill="x", padx=16, pady=(4, 10))

    run_btn  = ttk.Button(btn_frame, text="▶  Run Scan", style="Accent.TButton")
    stop_btn = ttk.Button(btn_frame, text="■  Stop",     state="disabled")
    run_btn.pack(side="left", padx=(0, 8))
    stop_btn.pack(side="left")

    sort_state = {"col": None, "rev": False}

    def _sort_tree(col):
        """Sort treeview by column, toggling asc/desc."""
        rev = sort_state["col"] == col and not sort_state["rev"]
        sort_state.update(col=col, rev=rev)
        items = [(tree.set(k, col), k) for k in tree.get_children("")]
        # Numeric sort for price/count columns
        num_cols = {"your_price", "lowest", "rivals", "low7", "med7", "low30", "med30"}
        def sort_key(x):
            if col in num_cols:
                try:
                    return int(x[0].replace(",", "").replace("—", "0"))
                except ValueError:
                    return 0
            return x[0].lower()
        items.sort(key=sort_key, reverse=rev)
        for idx, (_, k) in enumerate(items):
            tree.move(k, "", idx)

    def _fmt(n) -> str:
        if n is None:
            return "—"
        return f"{n:,}"

    def _clear_results():
        for item in tree.get_children():
            tree.delete(item)
        results_store.clear()
        for k in stat_vars:
            stat_vars[k].set("—")

    def _add_row(result: dict):
        status   = result["status"]
        lowest   = result.get("lowest")
        my_price = result["your_price"]

        if result.get("error"):
            tag    = "error"
            slabel = "ERROR"
            gap    = "—"
        elif status == STATUS_UNDERCUT:
            tag    = "undercut"
            slabel = "UNDERCUT"
            gap    = f"+{((my_price - lowest) / lowest * 100):.0f}%" if lowest else "—"
        elif status == STATUS_CHEAPEST:
            tag    = "cheapest"
            slabel = "CHEAPEST"
            gap    = "—"
        else:
            tag    = "solo"
            slabel = "SOLO"
            gap    = "—"

        tree.insert("", "end", tags=(tag,), values=(
            slabel,
            result["name"],
            _fmt(my_price),
            _fmt(lowest),
            gap,
            result.get("rivals") or "—",
            _fmt(result.get("low7")),
            _fmt(result.get("med7")),
            _fmt(result.get("low30")),
            _fmt(result.get("med30")),
        ))
        # Auto-scroll to latest
        children = tree.get_children()
        if children:
            tree.see(children[-1])

    def _update_stats(results: list, elapsed: float = None):
        total    = len(results)
        undercut = sum(1 for r in results if r["status"] == STATUS_UNDERCUT)
        cheapest = sum(1 for r in results if r["status"] == STATUS_CHEAPEST)
        solo     = total - undercut - cheapest
        stat_vars["total"].set(str(total))
        stat_vars["undercut"].set(str(undercut))
        stat_vars["cheapest"].set(str(cheapest))
        stat_vars["solo"].set(str(solo))
        if elapsed is not None:
            stat_vars["elapsed"].set(f"{elapsed:.1f}s")

    _stop_flag = threading.Event()

    def _do_scan():
        inv_path    = inv_path_var.get().strip()
        trader_name = trader_var.get().strip() or "Kreigar"
        try:
            delay = float(delay_var.get().strip())
        except ValueError:
            delay = 0.3

        if not inv_path:
            messagebox.showwarning("No inventory file", "Please select an inventory file first.")
            scan_running.clear()
            run_btn.config(state="normal")
            stop_btn.config(state="disabled")
            return

        items = load_inventory(inv_path)
        if not items:
            messagebox.showerror("Empty inventory",
                                 f"No items found in:\n{inv_path}\n\n"
                                 "Check that the file has lines like:\n  Crystal Dagger|100000")
            scan_running.clear()
            run_btn.config(state="normal")
            stop_btn.config(state="disabled")
            return

        root.after(0, _clear_results)
        total     = len(items)
        start     = time.time()
        completed = []

        root.after(0, lambda: status_var.set(f"Scanning {total} items…"))

        with make_client(delay=delay) as client:
            for i, (name, price) in enumerate(sorted(items.items()), 1):
                if _stop_flag.is_set():
                    break
                root.after(0, lambda n=name, idx=i:
                           status_var.set(f"[{idx}/{total}]  {n}"))
                history = client.get_item_history(name)
                result  = analyze_item(name, price, history, trader_name)
                completed.append(result)
                root.after(0, lambda r=result: _add_row(r))
                root.after(0, lambda c=list(completed): _update_stats(c))

        elapsed = time.time() - start
        root.after(0, lambda: _update_stats(completed, elapsed))
        root.after(0, lambda: status_var.set(
            f"Done — {len(completed)} item(s) scanned in {elapsed:.1f}s"
            + ("  [stopped early]" if _stop_flag.is_set() else "")
        ))
        root.after(0, lambda: run_btn.config(state="normal"))
        root.after(0, lambda: stop_btn.config(state="disabled"))
        scan_running.clear()

    def on_run():
        if scan_running.is_set():
            return
        _stop_flag.clear()
        scan_running.set()
        run_btn.config(state="disabled")
        stop_btn.config(state="normal")
        t = threading.Thread(target=_do_scan, daemon=True)
        t.start()

    def on_stop():
        _stop_flag.set()
        status_var.set("Stopping after current item…")
        stop_btn.config(state="disabled")

    run_btn.config(command=on_run)
    stop_btn.config(command=on_stop)

    # Pre-fill inventory path if there's a kreigar_inventory.txt on the Desktop
    desktop = os.path.join(os.path.expanduser("~"), "Desktop", "kreigar_inventory.txt")
    if os.path.exists(desktop):
        inv_path_var.set(desktop)

    root.mainloop()


# ── CLI ─────────────────────────────────────────────────────────────────────────

def run_cli(args):
    try:
        from frogspy_display import (
            print_item_line, print_report,
            STATUS_UNDERCUT as _SU, STATUS_NONE as _SN, STATUS_CHEAPEST as _SC,
            console,
        )
        RICH = True
    except ImportError:
        RICH = False

    start_time = datetime.datetime.now()
    print(f"\nFrogSpy v{SCRIPT_VERSION} -- Originally created by Alektra <Lederhosen>")
    print(f"Starting at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Trader: {args.trader}")
    print(f"Inventory file: {args.inventory}\n")

    trader_items = load_inventory(args.inventory)
    if not trader_items:
        print(f"  ERROR: No items loaded from {args.inventory}")
        return

    print(f"  Loaded {len(trader_items)} item(s) from {args.inventory}")

    cache_ttl = 0 if args.no_cache else 300
    results   = []
    total     = len(trader_items)

    with make_client(delay=args.delay, cache_ttl=cache_ttl) as client:
        for i, (item_name, my_price) in enumerate(sorted(trader_items.items()), 1):
            print(f"[{i}/{total}] Checking: {item_name} (your price: {my_price:,})")
            history = client.get_item_history(item_name)
            result  = analyze_item(item_name, my_price, history, args.trader)
            results.append(result)
            if RICH:
                print_item_line(result)
            else:
                print(format_result_plain(result), end="")

    end_time = datetime.datetime.now()
    elapsed  = (end_time - start_time).total_seconds()
    undercut = sum(1 for r in results if r["status"] == STATUS_UNDERCUT)
    cheapest = sum(1 for r in results if r["status"] == STATUS_CHEAPEST)
    no_comp  = total - undercut - cheapest

    if RICH:
        print_report(results, trader=args.trader, elapsed=elapsed,
                     timestamp=end_time.strftime("%Y-%m-%d %H:%M:%S"))
    else:
        print(
            f"\n{'='*60}\n"
            f"FrogSpy -- {args.trader} -- {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'='*60}\n"
            f"Total items checked : {total}\n"
            f"Cheapest / tied     : {cheapest}\n"
            f"Being undercut      : {undercut}\n"
            f"No competition      : {no_comp}\n"
            f"Time elapsed        : {elapsed:.1f}s\n"
            f"{'='*60}\n"
        )

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(f"FrogSpy -- {args.trader} -- {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        for r in results:
            f.write(format_result_plain(r))
        f.write(
            f"\n{'='*60}\n"
            f"FrogSpy -- {args.trader} -- {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'='*60}\n"
            f"Total items checked : {total}\n"
            f"Cheapest / tied     : {cheapest}\n"
            f"Being undercut      : {undercut}\n"
            f"No competition      : {no_comp}\n"
            f"Time elapsed        : {elapsed:.1f}s\n"
            f"{'='*60}\n"
        )
    print(f"Full report saved to: {args.output}")


# ── Entry point ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=f"FrogSpy v{SCRIPT_VERSION} — Bazaar price checker for Project Lazarus"
    )
    parser.add_argument("--gui",       action="store_true",          help="Launch the graphical interface")
    parser.add_argument("--inventory",                               help="Path to inventory file (ItemName|Price per line)")
    parser.add_argument("--trader",    default="Kreigar",            help="Your trader name (default: Kreigar)")
    parser.add_argument("--delay",     type=float, default=0.3,      help="Delay between requests in seconds (default: 0.3)")
    parser.add_argument("--output",    default="frogspy_output.txt", help="Output report file")
    parser.add_argument("--no-cache",  action="store_true",          help="Disable in-memory response cache")
    args = parser.parse_args()

    if args.gui or not args.inventory:
        run_gui()
    else:
        run_cli(args)


if __name__ == "__main__":
    main()
