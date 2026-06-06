#!/usr/bin/env python3
"""
Scraper Control Panel Pro — redesigned UI.
"""

import subprocess
import sys
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import shlex
import json
from pathlib import Path
from datetime import datetime

# ========== CONFIGURATION ==========
PYTHON_EXE  = r"C:\Users\abdo\AppData\Local\Programs\Python\Python312\python.exe"
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
# ===================================

SCRIPT_GROUPS = {
    "FaselHD": {
        "Series (all)":     [PYTHON_EXE, "-u", "FaselSeriesScraper.py"],
        "Series (asian)":   [PYTHON_EXE, "-u", "FaselSeriesScraper.py", "asian-series"],
        "Series (tvshows)": [PYTHON_EXE, "-u", "FaselSeriesScraper.py", "tvshows"],
        "Movies (all)":     [PYTHON_EXE, "-u", "FaselMoviesScraper.py"],
        "Movies (dubbed)":  [PYTHON_EXE, "-u", "FaselMoviesScraper.py", "--category", "dubbed-movies"],
        "Movies (hindi)":   [PYTHON_EXE, "-u", "FaselMoviesScraper.py", "--category", "hindi"],
        "Movies (asian)":   [PYTHON_EXE, "-u", "FaselMoviesScraper.py", "--category", "asian-movies"],
        "Movies (anime)":   [PYTHON_EXE, "-u", "FaselMoviesScraper.py", "--category", "anime-movies"],
        "Anime":            [PYTHON_EXE, "-u", "FaselAnimeScraper.py"],
    },
    "Akwam": {
        "Arabic Series":    [PYTHON_EXE, "-u", "AkwamArabicSeries.py"],
    },
    "Episodes": {
        "Update All":       [PYTHON_EXE, "-u", "update_episodes.py"],
        "Update Specific":  [PYTHON_EXE, "-u", "update_specific_episodes.py"],
        "Check New":        [PYTHON_EXE, "-u", "check_new_episodes.py"],
    },
    "Ratings": {
        "IMDbAPI → TMDb → OMDb": [PYTHON_EXE, "-u", "update_ratings.py", "--sources", "imdbapi,tmdb,omdb"],
        "TMDb → OMDb":           [PYTHON_EXE, "-u", "update_ratings.py", "--sources", "tmdb,omdb"],
        "IMDbAPI → TMDb":        [PYTHON_EXE, "-u", "update_ratings.py", "--sources", "imdbapi,tmdb"],
        "TMDb only":             [PYTHON_EXE, "-u", "update_ratings.py", "--sources", "tmdb"],
        "IMDbAPI only":          [PYTHON_EXE, "-u", "update_ratings.py", "--sources", "imdbapi"],
        "TMDb‑first":            [PYTHON_EXE, "-u", "update_ratings.py", "--tmdb-first"],
        "Custom order":          [PYTHON_EXE, "-u", "update_ratings.py"],
        "Specific category":     [PYTHON_EXE, "-u", "update_ratings.py"],
    },
    "Series IMDb Match": {
        "All series":        [PYTHON_EXE, "-u", "match_series_imdb.py"],
        "Series only":       [PYTHON_EXE, "-u", "match_series_imdb.py", "--category", "series"],
        "TV Shows only":     [PYTHON_EXE, "-u", "match_series_imdb.py", "--category", "tvshows"],
        "Asian Series only": [PYTHON_EXE, "-u", "match_series_imdb.py", "--category", "asian-series"],
        "Anime only":        [PYTHON_EXE, "-u", "match_series_imdb.py", "--category", "anime"],
    },
    "MAL": {
        "Anime (all)":        [PYTHON_EXE, "-u", "update_mal.py"],
        "Anime only":         [PYTHON_EXE, "-u", "update_mal.py", "--category", "anime.json"],
        "Anime Movies only":  [PYTHON_EXE, "-u", "update_mal.py", "--category", "anime-movies.json"],
        "Force re-process":   [PYTHON_EXE, "-u", "update_mal.py", "--force"],
        "Specific IDs":       [PYTHON_EXE, "-u", "update_mal.py"],
    },
    "Clean & Fix": {
        "Clean all":                  [PYTHON_EXE, "-u", "clean_metadata.py"],
        "Clean + backfill year":      [PYTHON_EXE, "-u", "clean_metadata.py", "--backfill-year"],
        "Clean + translate genres":   [PYTHON_EXE, "-u", "clean_metadata.py", "--translate-genres"],
        "Backfill year from title":   [PYTHON_EXE, "-u", "clean_metadata.py", "--backfill-year"],
        "Backfill year from ratings": [PYTHON_EXE, "-u", "clean_metadata.py", "--backfill-from-ratings"],
        "Backfill airing season":     [PYTHON_EXE, "-u", "clean_metadata.py", "--backfill-airing-season"],
        "Full clean (all steps)":     [PYTHON_EXE, "-u", "clean_metadata.py", "--backfill-year", "--backfill-from-ratings", "--backfill-airing-season", "--translate-genres"],
    },
    "Metadata": {
        "Runtime: all sources":       [PYTHON_EXE, "-u", "update_runtime.py", "--sources", "imdbapi,tmdb,omdb"],
        "Runtime: IMDbAPI → TMDb":    [PYTHON_EXE, "-u", "update_runtime.py", "--sources", "imdbapi,tmdb"],
        "Runtime: IMDbAPI only":      [PYTHON_EXE, "-u", "update_runtime.py", "--sources", "imdbapi"],
        "Runtime: Custom order":      [PYTHON_EXE, "-u", "update_runtime.py"],
        "Runtime: Specific category": [PYTHON_EXE, "-u", "update_runtime.py"],
    },
}

SORT_CATEGORIES = [
    "All Categories",
    "movies",
    "dubbed-movies",
    "hindi",
    "asian-movies",
    "anime-movies",
    "anime",
    "series",
    "tvshows",
    "asian-series",
    "arabic-series",
]

# ── Tooltips ──────────────────────────────────────────────────────────────────
TOOLTIPS = {
    # FaselHD scrapers
    "FaselHD:Series (all)":     "Scrapes all FaselHD series categories in one run: series, tvshows, asian-series, and anime.",
    "FaselHD:Series (asian)":   "Scrapes only the Asian series category from FaselHD (asian-series.json).",
    "FaselHD:Series (tvshows)": "Scrapes only the TV Shows category from FaselHD (tvshows.json).",
    "FaselHD:Movies (all)":     "Scrapes all FaselHD movie categories: movies, dubbed-movies, hindi, asian-movies, and anime-movies.",
    "FaselHD:Movies (dubbed)":  "Scrapes only Arabic-dubbed foreign movies from FaselHD (dubbed-movies.json).",
    "FaselHD:Movies (hindi)":   "Scrapes only Hindi/Bollywood movies from FaselHD (hindi.json).",
    "FaselHD:Movies (asian)":   "Scrapes only Asian movies from FaselHD (asian-movies.json).",
    "FaselHD:Movies (anime)":   "Scrapes only anime movies from FaselHD (anime-movies.json).",
    "FaselHD:Anime":            "Scrapes the FaselHD anime series category (anime.json).",
    # Akwam
    "Akwam:Arabic Series":      "Scrapes Arabic series from Akwam (arabic-series.json).",
    # Episodes
    "Episodes:Update All":      "Checks all series/anime across every category (50/day limit). Compares stored episode count vs live site count. If counts match it only syncs the main JSON and skips. If different, it deep-fetches and appends the new episodes.",
    "Episodes:Update Specific": "Prompts for one or more series IDs and fetches their episodes directly. Use when you know exactly which series need updating.",
    "Episodes:Check New":       "Scans live episode feeds on FaselHD and Akwam /recent (7 pages each). Detects series that have new episodes not yet stored locally. If any are found, automatically launches Update Specific for those IDs.",
    # Ratings
    "Ratings:IMDbAPI → TMDb → OMDb": "Fetches ratings using all three sources in order: IMDbAPI first, TMDb second, OMDb as last resort.",
    "Ratings:TMDb → OMDb":           "Fetches ratings from TMDb first, falls back to OMDb if not found.",
    "Ratings:IMDbAPI → TMDb":        "Fetches ratings from IMDbAPI first, falls back to TMDb if not found.",
    "Ratings:TMDb only":             "Fetches ratings from TMDb only with no fallback.",
    "Ratings:IMDbAPI only":          "Fetches ratings from IMDbAPI only with no fallback.",
    "Ratings:TMDb‑first":            "Forces TMDb as the primary source regardless of what data already exists.",
    "Ratings:Custom order":          "Prompts for a custom source order (e.g. imdbapi,omdb) then runs ratings update.",
    "Ratings:Specific category":     "Prompts for a category file and source order, then updates ratings for that category only.",
    # Series IMDb Match
    "Series IMDb Match:All series":        "For series without an IMDb ID: searches IMDbAPI by title, then compares your stored season/episode structure against IMDb's to confirm the match (80% similarity threshold). On success, writes the IMDb ID and fetched rating into the rating file.",
    "Series IMDb Match:Series only":       "Same as 'All series' but limited to series.json only.",
    "Series IMDb Match:TV Shows only":     "Same as 'All series' but limited to tvshows.json only.",
    "Series IMDb Match:Asian Series only": "Same as 'All series' but limited to asian-series.json only.",
    "Series IMDb Match:Anime only":        "Same as 'All series' but limited to anime.json only.",
    # MAL
    "MAL:Anime (all)":        "Enriches both anime.json and anime-movies.json with MyAnimeList data: episode count, runtime, release date, genres (EN + AR), airing status, and MAL rating/rank/popularity. Skips items that already have a mal_id.",
    "MAL:Anime only":         "Same as 'Anime (all)' but processes anime.json only.",
    "MAL:Anime Movies only":  "Same as 'Anime (all)' but processes anime-movies.json only.",
    "MAL:Force re-process":   "Re-runs MAL matching for items that already have a mal_id, overwriting all existing MAL fields.",
    "MAL:Specific IDs":       "Prompts for one or more content IDs then runs MAL matching only for those specific items.",
    # Clean & Fix
    "Clean & Fix:Clean all":                  "Cleans all category JSONs: normalizes genres (hyphen→space), standardizes country names, converts runtime to int, and fixes malformed release dates. Backs up originals to ./baks/ first.",
    "Clean & Fix:Clean + backfill year":      "Runs full clean, then scans each title for an embedded year (e.g. 'Movie Name 2024') and fills it into ReleaseDate if the field is empty.",
    "Clean & Fix:Clean + translate genres":   "Runs full clean, then fills missing Arabic genre translations into the GenresAr field.",
    "Clean & Fix:Backfill year from title":   "Only extracts the release year from title text for entries missing ReleaseDate. Skips all other cleaning steps.",
    "Clean & Fix:Backfill year from ratings": "For series/anime with an empty ReleaseDate, copies the year from their corresponding rating file. Only affects series categories.",
    "Clean & Fix:Backfill airing season":     "Copies mal_season from each anime/anime-movies rating file into AiringSeason in the main JSON (e.g. 'spring 2019' → 'Spring 2019'). Only fills entries that are missing AiringSeason. Run after MAL update.",
    "Clean & Fix:Full clean (all steps)":     "Runs every step: genre/country/runtime/date cleaning + year from title + year from ratings + airing season from MAL + Arabic genre translations.",
    # Metadata / Runtime
    "Metadata:Runtime: all sources":       "Fetches runtime for all content using IMDbAPI, TMDb, and OMDb as cascading fallbacks.",
    "Metadata:Runtime: IMDbAPI → TMDb":    "Fetches runtime from IMDbAPI first, falls back to TMDb if missing.",
    "Metadata:Runtime: IMDbAPI only":      "Fetches runtime from IMDbAPI only with no fallback.",
    "Metadata:Runtime: Custom order":      "Prompts for a custom source order (e.g. tmdb,omdb) then fetches runtime.",
    "Metadata:Runtime: Specific category": "Prompts for a category and source order, then fetches runtime for that category only.",
}

MANUAL_TOOLTIPS = {
    "✏  Set IMDb ID":       "Opens a dialog to manually assign an IMDb ID (tt...) to a specific item in any category. Useful for fixing wrong or missing IMDb matches.",
    "🎌  Set MAL ID":       "Opens a dialog to manually assign a MyAnimeList ID to a specific anime item. Useful when auto-matching fails.",
    "⭐  Get Rating by ID": "Prompts for a category and one or more content IDs, then fetches and updates their rating immediately.",
    "🎌  Get MAL by ID":    "Prompts for one or more anime content IDs and a category file, then fetches and updates their MAL data immediately.",
    "⏱  Get Runtime by ID":"Prompts for a category and one or more content IDs, then fetches and updates their runtime immediately.",
    "📋  Select Series":    "Open a popup to browse all episodic series, search, and select multiple IDs to update episodes.",
}

SORT_TOOLTIP = "Sorts the selected category's JSON dict into a pre-sorted array (newest first by ReleaseDate, then last_scraped as tiebreaker). Output goes to output/sorted/{category}.json."


class Tooltip:
    """Show a floating tooltip after a short hover delay."""
    DELAY_MS = 500
    WRAP     = 280

    def __init__(self, widget, text, theme_fn):
        self._widget   = widget
        self._text     = text
        self._theme_fn = theme_fn  # callable → returns current T dict
        self._job      = None
        self._tip      = None
        widget.bind("<Enter>",       self._schedule, add="+")
        widget.bind("<Leave>",       self._cancel,   add="+")
        widget.bind("<ButtonPress>", self._cancel,   add="+")

    def _schedule(self, _=None):
        self._cancel()
        self._job = self._widget.after(self.DELAY_MS, self._show)

    def _cancel(self, _=None):
        if self._job:
            self._widget.after_cancel(self._job)
            self._job = None
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None

    def _show(self):
        T = self._theme_fn()
        w = self._widget
        x = w.winfo_rootx() + w.winfo_width() + 8
        y = w.winfo_rooty() + (w.winfo_height() // 2) - 20

        self._tip = tk.Toplevel(w)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        self._tip.configure(bg=T["sidebar_border"])

        lbl = tk.Label(
            self._tip,
            text=self._text,
            justify=tk.LEFT,
            wraplength=self.WRAP,
            font=("Segoe UI", 10),
            bg=T["panel"],
            fg=T["fg"],
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=8,
        )
        lbl.pack(padx=1, pady=1)

# ── Colour palettes ──────────────────────────────────────────────────────────
DARK = dict(
    bg="#0f1117",
    sidebar="#161b27",
    sidebar_border="#1e2535",
    panel="#1a2030",
    fg="#c9d1e0",
    fg_muted="#5a6580",
    fg_section="#3a4d6a",
    text_bg="#0d1018",
    text_fg="#b8c4d8",
    accent="#3b82f6",
    accent_dim="#1d4ed8",
    run="#22c55e",
    run_dim="#16a34a",
    run_text="#ffffff",
    stop="#ef4444",
    stop_dim="#b91c1c",
    stop_text="#ffffff",
    stop_idle="#1e2535",
    stop_idle_fg="#3a4d6a",
    indicator_idle="#232d42",
    indicator_run="#22c55e",
    indicator_busy="#f59e0b",
    hover="#1e2a42",
    status_bg="#0d1018",
    status_fg="#5a6580",
    status_accent="#3b82f6",
)

LIGHT = dict(
    bg="#f4f6fb",
    sidebar="#eef1f8",
    sidebar_border="#dde3f0",
    panel="#ffffff",
    fg="#1e2740",
    fg_muted="#8896b5",
    fg_section="#b0bbd4",
    text_bg="#ffffff",
    text_fg="#1e2740",
    accent="#2563eb",
    accent_dim="#1d4ed8",
    run="#16a34a",
    run_dim="#15803d",
    run_text="#ffffff",
    stop="#dc2626",
    stop_dim="#b91c1c",
    stop_text="#ffffff",
    stop_idle="#e8ecf5",
    stop_idle_fg="#a0aec0",
    indicator_idle="#dde3f0",
    indicator_run="#16a34a",
    indicator_busy="#d97706",
    hover="#e4eaf8",
    status_bg="#eef1f8",
    status_fg="#8896b5",
    status_accent="#2563eb",
)


class PillButton(tk.Frame):
    def __init__(self, parent, text, command=None,
                 bg="#3b82f6", fg="#ffffff",
                 hover_bg=None, active_bg=None,
                 font=("Segoe UI", 11), padx=12, pady=4,
                 width=None, **kw):
        super().__init__(parent, bg=bg, cursor="hand2", **kw)

        self._bg     = bg
        self._fg     = fg
        self._hover  = hover_bg  or bg
        self._active = active_bg or bg
        self._cmd    = command
        self._enabled = True

        self._lbl = tk.Label(
            self, text=text, bg=bg, fg=fg,
            font=font, padx=padx, pady=pady,
            cursor="hand2",
        )
        if width:
            self._lbl.config(width=width)
        self._lbl.pack(fill=tk.BOTH, expand=True)

        for w in (self, self._lbl):
            w.bind("<Enter>",              self._on_enter)
            w.bind("<Leave>",              self._on_leave)
            w.bind("<Button-1>",           self._on_press)
            w.bind("<ButtonRelease-1>",    self._on_release)

    def _set_color(self, color):
        self.configure(bg=color)
        self._lbl.configure(bg=color)

    def _on_enter(self, _=None):
        if self._enabled:
            self._set_color(self._hover)

    def _on_leave(self, _=None):
        self._set_color(self._bg)

    def _on_press(self, _=None):
        if self._enabled:
            self._set_color(self._active)

    def _on_release(self, _=None):
        if self._enabled:
            self._set_color(self._hover)
            if self._cmd:
                self._cmd()

    def configure(self, **kw):
        if "state" in kw:
            self._enabled = kw.pop("state") != tk.DISABLED
            alpha = self._fg if self._enabled else self._active
            self._lbl.configure(fg=alpha)
        if "text" in kw:
            self._lbl.configure(text=kw.pop("text"))
        if "command" in kw:
            self._cmd = kw.pop("command")
        if "bg" in kw:
            self._bg = kw["bg"]
            self._lbl.configure(bg=kw["bg"])
        if "fg" in kw:
            self._fg = kw.pop("fg")
            if self._enabled:
                self._lbl.configure(fg=self._fg)
        if kw:
            super().configure(**kw)

    config = configure


class ScraperGUI:
    def __init__(self, root):
        self.root = root
        root.title("Scraper Control Panel")
        root.geometry("1200x740")
        root.minsize(860, 520)

        self.processes         = {}
        self.output_tabs       = {}
        self.custom_procs      = {}
        self.indicators        = {}
        self._stopped_procs    = set()
        self.sort_category_var  = tk.StringVar(value="All Categories")
        self.auto_scroll        = {}
        self.script_buttons     = {}

        self.dark_mode = True
        self.T         = DARK

        self._section_labels = []
        self._section_seps   = []

        self._build_ui()
        self._apply_theme()

    # -------------------------------------------------------------------------
    # UI CONSTRUCTION
    # -------------------------------------------------------------------------
    def _build_ui(self):
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, minsize=252, weight=0)
        self.root.columnconfigure(1, minsize=1,   weight=0)
        self.root.columnconfigure(2, weight=1)

        # Status bar
        self.status_bar = tk.Frame(self.root, height=26)
        self.status_bar.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.status_bar.grid_propagate(False)

        self._status_dot = tk.Label(self.status_bar, text="●", font=("Segoe UI", 10))
        self._status_dot.pack(side=tk.LEFT, padx=(10, 4))

        self.status_var  = tk.StringVar(value="Ready")
        self._status_lbl = tk.Label(
            self.status_bar, textvariable=self.status_var,
            anchor="w", font=("Consolas", 10),
        )
        self._status_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._clock_lbl = tk.Label(self.status_bar, font=("Consolas", 10), anchor="e")
        self._clock_lbl.pack(side=tk.RIGHT, padx=10)
        self._tick_clock()

        # Sidebar
        self.sidebar = tk.Frame(self.root, width=252)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.rowconfigure(1, weight=1)
        self.sidebar.columnconfigure(0, weight=1)

        self._title_bar = tk.Frame(self.sidebar, height=52)
        self._title_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._title_bar.grid_propagate(False)
        self._title_bar.columnconfigure(0, weight=1)

        self._title_lbl = tk.Label(
            self._title_bar, text="⬡  SCRAPER",
            font=("Segoe UI", 14, "bold"), anchor="w",
        )
        self._title_lbl.grid(row=0, column=0, sticky="w", padx=14, pady=14)

        self._theme_btn = tk.Label(
            self._title_bar, text="◐",
            font=("Segoe UI", 16), cursor="hand2",
        )
        self._theme_btn.grid(row=0, column=1, padx=12)
        self._theme_btn.bind("<Button-1>", lambda _: self.toggle_dark_mode())

        self._sidebar_canvas = tk.Canvas(
            self.sidebar, highlightthickness=0, bd=0, width=250,
        )
        sb_scroll = ttk.Scrollbar(
            self.sidebar, orient=tk.VERTICAL,
            command=self._sidebar_canvas.yview,
        )
        self.scroll_frame = tk.Frame(self._sidebar_canvas)
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self._sidebar_canvas.configure(
                scrollregion=self._sidebar_canvas.bbox("all")
            )
        )
        self._sidebar_canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self._sidebar_canvas.configure(yscrollcommand=sb_scroll.set)
        self._sidebar_canvas.grid(row=1, column=0, sticky="nsew")
        sb_scroll.grid(row=1, column=1, sticky="ns")
        self._sidebar_canvas.bind_all("<MouseWheel>", self._on_sidebar_mousewheel)

        self._sidebar_footer = tk.Frame(self.sidebar, height=52)
        self._sidebar_footer.grid(row=2, column=0, columnspan=2, sticky="ew")
        self._sidebar_footer.grid_propagate(False)
        self._sidebar_footer.columnconfigure(0, weight=1)
        self._sidebar_footer.columnconfigure(1, weight=1)

        self._custom_btn = PillButton(
            self._sidebar_footer, text="＋  Custom",
            command=self.add_custom_command,
            font=("Segoe UI", 10, "bold"),
            padx=8, pady=5,
        )
        self._custom_btn.grid(row=0, column=0, sticky="ew", padx=(10, 4), pady=10)

        self._stop_all_btn = PillButton(
            self._sidebar_footer, text="⏹  Stop All",
            command=self.stop_all_scripts,
            font=("Segoe UI", 10, "bold"),
            padx=8, pady=5,
        )
        self._stop_all_btn.grid(row=0, column=1, sticky="ew", padx=(4, 10), pady=10)

        self._divider = tk.Frame(self.root, width=1)
        self._divider.grid(row=0, column=1, sticky="nsew")

        content = tk.Frame(self.root)
        content.grid(row=0, column=2, sticky="nsew")
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(content)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 0))

        log_frame = tk.Frame(self.notebook)
        self.notebook.add(log_frame, text="  Log  ")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=("Consolas", 11),
            state=tk.DISABLED, relief=tk.FLAT, bd=0,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        for tag, col in [("ok","#22c55e"),("warn","#f59e0b"),("err","#ef4444"),("dim","#4a5568")]:
            self.log_text.tag_configure(tag, foreground=col)
        self.auto_scroll[id(self.log_text)] = tk.BooleanVar(value=True)
        self._log(f"Started — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        for group, scripts in SCRIPT_GROUPS.items():
            self._section_header(group)
            for name, cmd in scripts.items():
                self._script_row(name, cmd, group=group)

        self._section_header("Sort Output")
        self._sort_row()
        self._section_header("Manual")
        self._manual_row()

    def _tick_clock(self):
        self._clock_lbl.config(text=datetime.now().strftime("%H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    def _on_sidebar_mousewheel(self, event):
        """Scroll the sidebar canvas only when the pointer is inside the sidebar."""
        w = event.widget
        sidebar_widgets = (
            self._sidebar_canvas, self.scroll_frame, self.sidebar,
            self._title_bar, self._sidebar_footer,
        )
        while w is not None:
            if w in sidebar_widgets:
                self._sidebar_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                return
            try:
                w = w.master
            except Exception:
                return

    def _section_header(self, text):
        f = tk.Frame(self.scroll_frame)
        f.pack(fill=tk.X, pady=(10, 0))

        lbl = tk.Label(
            f, text=text.upper(),
            font=("Segoe UI", 11, "bold"), anchor="w", padx=16, pady=2,
        )
        lbl.pack(fill=tk.X)
        self._section_labels.append(lbl)

        if text:
            sep = tk.Frame(f, height=1)
            sep.pack(fill=tk.X, padx=12, pady=(1, 0))
            self._section_seps.append(sep)

    def _script_row(self, name, cmd, group=""):
        T = self.T
        outer = tk.Frame(self.scroll_frame)
        outer.pack(fill=tk.X, padx=4, pady=1)
        outer.columnconfigure(1, weight=1)

        dot = tk.Label(outer, text="●", font=("Segoe UI", 10), width=2)
        dot.grid(row=0, column=0, padx=(6, 0), pady=4)
        self.indicators[name] = dot

        lbl = tk.Label(
            outer, text=name, anchor="w",
            font=("Segoe UI", 11), padx=4, pady=5, cursor="hand2",
        )
        lbl.grid(row=0, column=1, sticky="ew")

        stop_btn = PillButton(
            outer, text="⏹  Stop",
            command=lambda n=name: self.stop_script(n),
            font=("Segoe UI", 10), padx=10, pady=4,
        )
        stop_btn.grid(row=0, column=2, padx=(2, 6), pady=3)
        stop_btn.grid_remove()

        def _start(_evt=None, n=name, c=cmd):
            self.start_script(n, c)

        def _enter(_evt=None, o=outer, l=lbl, d=dot):
            bg = self.T["hover"]
            o.configure(bg=bg)
            l.configure(bg=bg)
            d.configure(bg=bg)

        def _leave(_evt=None, o=outer, l=lbl, d=dot):
            bg = self.T["sidebar"]
            o.configure(bg=bg)
            l.configure(bg=bg)
            d.configure(bg=bg)

        for w in (outer, lbl, dot):
            w.bind("<Button-1>", _start)
            w.bind("<Enter>",    _enter)
            w.bind("<Leave>",    _leave)

        self.script_buttons[name] = (lbl, stop_btn, outer)

        tip_text = TOOLTIPS.get(f"{group}:{name}") or TOOLTIPS.get(name)
        if tip_text:
            for w in (outer, lbl, dot):
                Tooltip(w, tip_text, lambda: self.T)

    def _sort_row(self):
        row = tk.Frame(self.scroll_frame)
        row.pack(fill=tk.X, padx=4, pady=(4, 2))
        row.columnconfigure(1, weight=1)
        self._sort_row_frame = row

        dot = tk.Label(row, text="●", font=("Segoe UI", 10), width=2)
        dot.grid(row=0, column=0, padx=(6, 0))
        self.indicators["sort"] = dot

        self.sort_combo = ttk.Combobox(
            row, textvariable=self.sort_category_var,
            values=SORT_CATEGORIES,
            state="readonly", font=("Segoe UI", 10),
        )
        self.sort_combo.grid(row=0, column=1, sticky="ew", padx=(4, 2), pady=4)

        self.sort_start_btn = PillButton(
            row, text="▶",
            command=self.start_sort,
            font=("Segoe UI", 10, "bold"), padx=7, pady=2,
        )
        self.sort_start_btn.grid(row=0, column=2, padx=2)

        self.sort_stop_btn = PillButton(
            row, text="⏹  Stop",
            command=self.stop_sort,
            font=("Segoe UI", 10), padx=10, pady=4,
        )
        self.sort_stop_btn.grid(row=0, column=3, padx=(2, 6))
        self.sort_stop_btn.grid_remove()

        for w in (dot, self.sort_combo, self.sort_start_btn):
            Tooltip(w, SORT_TOOLTIP, lambda: self.T)

    def _manual_row(self):
        row = tk.Frame(self.scroll_frame)
        row.pack(fill=tk.X, padx=8, pady=(4, 16))

        # Set IMDb ID
        self._imdb_btn = PillButton(
            row, text="✏  Set IMDb ID",
            command=self.open_imdb_dialog,
            font=("Segoe UI", 11), padx=10, pady=5,
        )
        self._imdb_btn.pack(fill=tk.X, padx=4, pady=2)
        Tooltip(self._imdb_btn, MANUAL_TOOLTIPS["✏  Set IMDb ID"], lambda: self.T)

        # Set MAL ID
        self._set_mal_btn = PillButton(
            row, text="🎌  Set MAL ID",
            command=self.open_mal_setter_dialog,
            font=("Segoe UI", 11), padx=10, pady=5,
        )
        self._set_mal_btn.pack(fill=tk.X, padx=4, pady=2)
        Tooltip(self._set_mal_btn, MANUAL_TOOLTIPS["🎌  Set MAL ID"], lambda: self.T)

        # Get Rating by ID
        self._rating_by_id_btn = PillButton(
            row, text="⭐  Get Rating by ID",
            command=self.open_rating_by_id,
            font=("Segoe UI", 11), padx=10, pady=5,
        )
        self._rating_by_id_btn.pack(fill=tk.X, padx=4, pady=2)
        Tooltip(self._rating_by_id_btn, MANUAL_TOOLTIPS["⭐  Get Rating by ID"], lambda: self.T)

        # Get MAL by ID
        self._mal_by_id_btn = PillButton(
            row, text="🎌  Get MAL by ID",
            command=self.open_mal_by_id,
            font=("Segoe UI", 11), padx=10, pady=5,
        )
        self._mal_by_id_btn.pack(fill=tk.X, padx=4, pady=2)
        Tooltip(self._mal_by_id_btn, MANUAL_TOOLTIPS["🎌  Get MAL by ID"], lambda: self.T)

        # Get Runtime by ID
        self._runtime_by_id_btn = PillButton(
            row, text="⏱  Get Runtime by ID",
            command=self.open_runtime_by_id,
            font=("Segoe UI", 11), padx=10, pady=5,
        )
        self._runtime_by_id_btn.pack(fill=tk.X, padx=4, pady=2)
        Tooltip(self._runtime_by_id_btn, MANUAL_TOOLTIPS["⏱  Get Runtime by ID"], lambda: self.T)

        # NEW: Select Series popup (integrated, not external script)
        self._select_series_btn = PillButton(
            row, text="📋  Select Series",
            command=self.open_series_selector,
            font=("Segoe UI", 11), padx=10, pady=5,
        )
        self._select_series_btn.pack(fill=tk.X, padx=4, pady=2)
        Tooltip(self._select_series_btn, MANUAL_TOOLTIPS["📋  Select Series"], lambda: self.T)

    # -------------------------------------------------------------------------
    # THEME
    # -------------------------------------------------------------------------
    def _style_stop_btn(self, btn, is_running):
        T = self.T
        if is_running:
            btn._bg    = T["stop"]
            btn._hover = T["stop_dim"]
            btn._active= T["stop_dim"]
            btn._fg    = T["stop_text"]
            btn._enabled = True
            btn._lbl.configure(fg=T["stop_text"])
            btn._set_color(btn._bg)
            try:
                btn.grid()
            except Exception:
                pass
        else:
            btn._bg    = T["stop_idle"]
            btn._hover = T["stop_idle"]
            btn._active= T["stop_idle"]
            btn._fg    = T["stop_idle_fg"]
            btn._enabled = False
            btn._lbl.configure(fg=T["stop_idle_fg"])
            btn._set_color(btn._bg)
            try:
                btn.grid_remove()
            except Exception:
                pass

    def _apply_theme(self):
        T = self.T

        self.root.configure(bg=T["bg"])

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame",        background=T["bg"])
        style.configure("TNotebook",     background=T["bg"], borderwidth=0)
        style.configure("TNotebook.Tab",
                        background=T["sidebar"], foreground=T["fg_muted"],
                        padding=[14, 6], font=("Segoe UI", 11))
        style.map("TNotebook.Tab",
                  background=[("selected", T["panel"]), ("active", T["hover"])],
                  foreground=[("selected", T["fg"]),    ("active", T["fg"])])
        style.configure("TScrollbar",    background=T["sidebar"],
                        troughcolor=T["bg"], borderwidth=0, arrowsize=10)
        style.configure("TCombobox",     fieldbackground=T["sidebar"],
                        foreground=T["fg"], background=T["sidebar"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", T["sidebar"])],
                  foreground=[("readonly", T["fg"])])

        for w in (self.sidebar, self._sidebar_canvas, self.scroll_frame,
                  self._title_bar, self._sidebar_footer):
            w.configure(bg=T["sidebar"])

        self._title_lbl.configure(bg=T["sidebar"], fg=T["fg"])
        self._theme_btn.configure(bg=T["sidebar"], fg=T["fg_muted"])
        self._divider.configure(bg=T["sidebar_border"])

        for lbl in self._section_labels:
            lbl.configure(bg=T["sidebar"], fg=T["fg_section"])
            lbl.master.configure(bg=T["sidebar"])
        for sep in self._section_seps:
            sep.configure(bg=T["sidebar_border"])

        for name, (lbl, stop_btn, outer) in self.script_buttons.items():
            outer.configure(bg=T["sidebar"])
            lbl.configure(bg=T["sidebar"], fg=T["fg"])
            dot = self.indicators.get(name)
            if dot:
                dot.configure(bg=T["sidebar"])
                running = name in self.processes and self.processes[name].poll() is None
                dot.configure(fg=T["indicator_run"] if running else T["indicator_idle"])
            running = name in self.processes and self.processes[name].poll() is None
            self._style_stop_btn(stop_btn, running)

        self._sort_row_frame.configure(bg=T["sidebar"])
        sort_dot = self.indicators.get("sort")
        if sort_dot:
            sort_dot.configure(bg=T["sidebar"])
            sort_run = "sort" in self.processes and self.processes["sort"].poll() is None
            sort_dot.configure(fg=T["indicator_run"] if sort_run else T["indicator_idle"])

        sort_run = "sort" in self.processes and self.processes["sort"].poll() is None
        self.sort_start_btn._bg    = T["run"]
        self.sort_start_btn._hover = T["run_dim"]
        self.sort_start_btn._active= T["run_dim"]
        self.sort_start_btn._fg    = T["run_text"]
        self.sort_start_btn._lbl.configure(fg=T["run_text"])
        self.sort_start_btn._set_color(T["run"])
        self._style_stop_btn(self.sort_stop_btn, sort_run)

        self._custom_btn._bg    = T["accent"]
        self._custom_btn._hover = T["accent_dim"]
        self._custom_btn._active= T["accent_dim"]
        self._custom_btn._fg    = "#ffffff"
        self._custom_btn._lbl.configure(fg="#ffffff")
        self._custom_btn._set_color(T["accent"])

        self._stop_all_btn._bg    = T["stop"]
        self._stop_all_btn._hover = T["stop_dim"]
        self._stop_all_btn._active= T["stop_dim"]
        self._stop_all_btn._fg    = T["stop_text"]
        self._stop_all_btn._lbl.configure(fg=T["stop_text"])
        self._stop_all_btn._set_color(T["stop"])

        idle_bg = T["hover"]
        for btn in [self._imdb_btn, self._set_mal_btn, self._rating_by_id_btn,
                    self._mal_by_id_btn, self._runtime_by_id_btn, self._select_series_btn]:
            btn._bg    = idle_bg
            btn._hover = T["accent"]
            btn._active= T["accent_dim"]
            btn._fg    = T["fg"]
            btn._lbl.configure(fg=T["fg"])
            btn._set_color(idle_bg)
            btn.master.configure(bg=T["sidebar"])

        self.status_bar.configure(bg=T["status_bg"])
        self._status_dot.configure(bg=T["status_bg"], fg=T["status_accent"])
        self._status_lbl.configure(bg=T["status_bg"], fg=T["status_fg"])
        self._clock_lbl.configure(bg=T["status_bg"], fg=T["fg_muted"])

        self.log_text.configure(bg=T["text_bg"], fg=T["text_fg"],
                                insertbackground=T["fg"])
        for tag, col in [("ok", T["run"]), ("warn", T["indicator_busy"]),
                         ("err", T["stop"]), ("dim", T["fg_muted"])]:
            self.log_text.tag_configure(tag, foreground=col)

        for widget in self.output_tabs.values():
            try:
                widget.configure(bg=T["text_bg"], fg=T["text_fg"],
                                 insertbackground=T["fg"])
            except tk.TclError:
                pass

        for child in self.root.winfo_children():
            if isinstance(child, tk.Frame) and child not in (
                self.sidebar, self._divider, self.status_bar
            ):
                child.configure(bg=T["bg"])

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        self.T = DARK if self.dark_mode else LIGHT
        self._apply_theme()

    # -------------------------------------------------------------------------
    # SCRIPT CONTROL
    # -------------------------------------------------------------------------
    def start_script(self, name, cmd):
        if name in self.processes and self.processes[name].poll() is None:
            messagebox.showwarning("Already running", f'"{name}" is already running.')
            return
        extra = []
        if name == "Specific IDs":
            ids = simpledialog.askstring("Content IDs", "Enter IDs (space-separated):")
            if not ids:
                return
            extra = ["--ids"] + ids.split()
        elif name == "Update Specific":
            ids = simpledialog.askstring("Series IDs", "Enter IDs (space-separated):")
            if not ids:
                return
            extra = ["--ids"] + ids.split()
        elif name == "Custom order":
            sources = simpledialog.askstring(
                "Rating Sources",
                "Enter source order (comma-separated)\nOptions: imdbapi, tmdb, omdb"
            )
            if not sources:
                return
            extra = ["--sources", sources.strip()]
        elif name == "Specific category":
            sources = simpledialog.askstring(
                "Rating Sources",
                "Enter source order (comma-separated)\nOptions: imdbapi, tmdb, omdb"
            )
            if not sources:
                return
            category = simpledialog.askstring(
                "Category",
                "Enter category file name (e.g., movies.json, series.json)"
            )
            if not category:
                return
            extra = ["--sources", sources.strip(), "--category", category.strip()]
        elif name == "Runtime: Custom order":
            sources = simpledialog.askstring(
                "Runtime Sources",
                "Enter source order (comma-separated)\nOptions: imdbapi, tmdb, omdb"
            )
            if not sources:
                return
            extra = ["--sources", sources.strip()]
        elif name == "Runtime: Specific category":
            sources = simpledialog.askstring(
                "Runtime Sources",
                "Enter source order (comma-separated)\nOptions: imdbapi, tmdb, omdb"
            )
            if not sources:
                return
            category = simpledialog.askstring(
                "Category",
                "Enter category file name (e.g., movies.json, series.json)"
            )
            if not category:
                return
            extra = ["--sources", sources.strip(), "--category", category.strip()]

        proc, text_widget = self._run_subprocess(cmd + extra, name)
        if proc is None:
            return

        self.processes[name]   = proc
        self.output_tabs[name] = text_widget

        lbl, stop_btn, _ = self.script_buttons[name]
        lbl.config(fg=self.T["fg_muted"])
        self._style_stop_btn(stop_btn, True)
        self._set_indicator(name, True)
        self._set_status(f"▶  {name}")

    def stop_script(self, name):
        proc = self.processes.get(name)
        if not proc or proc.poll() is not None:
            return
        self._stopped_procs.add(proc.pid)
        self._kill_process(proc, name)
        self.processes.pop(name, None)
        self.output_tabs.pop(name, None)
        lbl, stop_btn, _ = self.script_buttons[name]
        lbl.config(fg=self.T["fg"])
        self._style_stop_btn(stop_btn, False)
        self._set_indicator(name, False)
        self._set_status(f"⏹  Stopped: {name}")

    def stop_all_scripts(self):
        names = list(self.processes.keys())
        if not names and not self.custom_procs:
            self._set_status("Nothing running")
            return
        for name in names:
            proc = self.processes.get(name)
            if proc and proc.poll() is None:
                self._stopped_procs.add(proc.pid)
                self._kill_process(proc, name)
            self.processes.pop(name, None)
            self.output_tabs.pop(name, None)
            self._set_indicator(name, False)
            if name in self.script_buttons:
                lbl, stop_btn, _ = self.script_buttons[name]
                lbl.config(fg=self.T["fg"])
                self._style_stop_btn(stop_btn, False)
        self.sort_start_btn.configure(state=tk.NORMAL)
        self._style_stop_btn(self.sort_stop_btn, False)
        for pid, (proc, text_widget, tab_frame, tab_name) in list(self.custom_procs.items()):
            if proc and proc.poll() is None:
                self._stopped_procs.add(proc.pid)
                self._kill_process(proc, tab_name)
            self.custom_procs.pop(pid, None)
            self.after(0, lambda tf=tab_frame, tn=tab_name, p=pid: self._remove_custom_tab(tf, tn, p))
        self._set_status(f"⏹  Stopped {len(names)} process(es)")

    def start_sort(self):
        if "sort" in self.processes and self.processes["sort"].poll() is None:
            messagebox.showwarning("Already running", "Sort Output is already running.")
            return
        cat = self.sort_category_var.get()
        cmd = [PYTHON_EXE, "-u", "sort_output.py"]
        if cat != "All Categories":
            cmd += ["--category", cat]
        tab_name = f"Sort: {cat}"

        proc, text_widget = self._run_subprocess(cmd, tab_name)
        if proc is None:
            return

        self.processes["sort"]   = proc
        self.output_tabs["sort"] = text_widget
        self.sort_start_btn.configure(state=tk.DISABLED)
        self._style_stop_btn(self.sort_stop_btn, True)
        self._set_indicator("sort", True)
        self._set_status(f"▶  Sort Output: {cat}")

        def _on_done():
            if proc.pid in self._stopped_procs:
                return
            self.root.after(0, lambda: self.sort_start_btn.configure(state=tk.NORMAL))
            self.root.after(0, lambda: self._style_stop_btn(self.sort_stop_btn, False))
            self.root.after(0, lambda: self._set_indicator("sort", False))
            self.processes.pop("sort", None)
            self.output_tabs.pop("sort", None)

        threading.Thread(target=lambda: (proc.wait(), _on_done()), daemon=True).start()

    def stop_sort(self):
        proc = self.processes.get("sort")
        if not proc or proc.poll() is not None:
            return
        self._stopped_procs.add(proc.pid)
        self._kill_process(proc, "sort")
        self.processes.pop("sort", None)
        self.output_tabs.pop("sort", None)
        self.sort_start_btn.configure(state=tk.NORMAL)
        self._style_stop_btn(self.sort_stop_btn, False)
        self._set_indicator("sort", False)
        self._set_status("⏹  Sort Output stopped")

    # -------------------------------------------------------------------------
    # CUSTOM COMMAND
    # -------------------------------------------------------------------------
    def add_custom_command(self):
        cmd_str = simpledialog.askstring(
            "Custom Command", "Enter command (e.g. python myscript.py --arg):"
        )
        if not cmd_str:
            return
        cmd_list = shlex.split(cmd_str)
        if cmd_list[0].lower() == "python":
            cmd_list[0] = PYTHON_EXE
        if cmd_list[0] == PYTHON_EXE and "-u" not in cmd_list:
            cmd_list.insert(1, "-u")

        tab_name  = f"Custom: {os.path.basename(cmd_list[0])}"
        tab_frame = tk.Frame(self.notebook)
        self.notebook.add(tab_frame, text=f"  {tab_name}  ")
        tab_frame.rowconfigure(0, weight=1)
        tab_frame.columnconfigure(0, weight=1)
        text_widget = self._make_output_widget(tab_frame, tab_name)

        proc, _ = self._run_subprocess(cmd_list, tab_name, text_widget)
        if proc:
            self.custom_procs[proc.pid] = (proc, text_widget, tab_frame, tab_name)
            threading.Thread(
                target=self._watch_custom, args=(proc, tab_frame, tab_name), daemon=True
            ).start()

    def _watch_custom(self, proc, tab_frame, tab_name):
        proc.wait()
        if proc.pid not in self._stopped_procs:
            for i in range(self.notebook.index("end")):
                try:
                    if self.notebook.tab(i, "text").strip() == tab_name:
                        self.notebook.tab(i, text=f"  {tab_name} (finished)  ")
                        break
                except tk.TclError:
                    pass
        else:
            self._stopped_procs.discard(proc.pid)
        self.custom_procs.pop(proc.pid, None)

    def _remove_custom_tab(self, tab_frame, tab_name, pid):
        for i in range(self.notebook.index("end")):
            try:
                if self.notebook.tab(i, "text").strip() == tab_name:
                    self.notebook.forget(i)
                    break
            except tk.TclError:
                pass
        self.custom_procs.pop(pid, None)

    # -------------------------------------------------------------------------
    # SUBPROCESS HELPERS
    # -------------------------------------------------------------------------
    def _run_subprocess(self, cmd, tab_name, text_widget=None):
        T = self.T
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        if text_widget is None:
            tab_frame = tk.Frame(self.notebook)
            self.notebook.add(tab_frame, text=f"  {tab_name}  ")
            tab_frame.rowconfigure(0, weight=1)
            tab_frame.columnconfigure(0, weight=1)
            text_widget = self._make_output_widget(tab_frame, tab_name)
            self.notebook.select(tab_frame)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                bufsize=1, creationflags=flags, env=env,
                cwd=SCRIPTS_DIR,
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not start:\n{' '.join(cmd)}\n\n{e}")
            return None, None

        t0    = time.monotonic()
        stamp = datetime.now().strftime("%H:%M:%S")
        self._append_output(text_widget,
            f"{'─'*64}\n▶  {tab_name}  [{stamp}]\n{'─'*64}\n")

        def _reader():
            for line in iter(proc.stdout.readline, ""):
                self.root.after(0, lambda l=line: self._append_output(text_widget, l))
            proc.wait()

            if proc.pid in self._stopped_procs:
                self._stopped_procs.discard(proc.pid)
                return

            elapsed = time.monotonic() - t0
            mins, secs = divmod(int(elapsed), 60)
            elapsed_str = f"{mins}m {secs}s" if mins else f"{secs}s"
            ts   = datetime.now().strftime("%H:%M:%S")
            code = proc.returncode
            self.root.after(0, lambda: self._append_output(
                text_widget,
                f"{'─'*64}\n{'✔' if code==0 else '✖'}  Finished (exit {code})  [{ts}]  ⏱ {elapsed_str}\n{'─'*64}\n"
            ))
            self.root.after(0, lambda: self._set_status(
                f"{'✔' if code==0 else '✖'}  Done: {tab_name}  (exit {code})  ⏱ {elapsed_str}"
            ))
            for sname, (slbl, stpbtn, _) in self.script_buttons.items():
                if self.processes.get(sname) is proc:
                    self.root.after(0, lambda b=slbl: b.config(fg=self.T["fg"]))
                    self.root.after(0, lambda b=stpbtn: self._style_stop_btn(b, False))
                    self.root.after(0, lambda n=sname: self._set_indicator(n, False))
                    self.processes.pop(sname, None)
                    self.output_tabs.pop(sname, None)
                    break

        threading.Thread(target=_reader, daemon=True).start()
        return proc, text_widget

    def _make_output_widget(self, parent, tab_name=None):
        T = self.T
        outer = tk.Frame(parent)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        text = scrolledtext.ScrolledText(
            outer, wrap=tk.WORD, font=("Consolas", 11),
            bg=T["text_bg"], fg=T["text_fg"],
            insertbackground=T["fg"], relief=tk.FLAT, bd=0,
        )
        text.grid(row=0, column=0, sticky="nsew")
        for tag, col in [("ok", T["run"]), ("warn", T["indicator_busy"]),
                         ("err", T["stop"]), ("dim", T["fg_muted"])]:
            text.tag_configure(tag, foreground=col)

        scroll_var = tk.BooleanVar(value=True)
        self.auto_scroll[id(text)] = scroll_var

        strip = tk.Frame(outer, height=28, bg=T["sidebar"])
        strip.grid(row=1, column=0, sticky="ew")

        def _clear(t=text):
            t.config(state=tk.NORMAL)
            t.delete("1.0", tk.END)
            t.config(state=tk.DISABLED)

        tk.Checkbutton(
            strip, text="Auto-scroll", variable=scroll_var,
            relief=tk.FLAT, bd=0, font=("Segoe UI", 10),
            bg=T["sidebar"], fg=T["fg_muted"],
            activebackground=T["sidebar"], selectcolor=T["sidebar"],
        ).pack(side=tk.RIGHT, padx=6, pady=3)

        tk.Button(
            strip, text="Clear", command=_clear,
            relief=tk.FLAT, bd=0, padx=8,
            font=("Segoe UI", 10),
            bg=T["sidebar"], fg=T["fg_muted"],
            activebackground=T["hover"],
        ).pack(side=tk.RIGHT, padx=2, pady=3)

        if tab_name:
            def _close_tab():
                for i in range(self.notebook.index("end")):
                    try:
                        if self.notebook.tab(i, "text").strip() == tab_name.strip():
                            self.notebook.forget(i)
                            break
                    except tk.TclError:
                        pass
                self.auto_scroll.pop(id(text), None)

            tk.Button(
                strip, text="✕  Close", command=_close_tab,
                relief=tk.FLAT, bd=0, padx=8,
                font=("Segoe UI", 10),
                bg=T["sidebar"], fg=T["fg_muted"],
                activebackground=T["hover"],
            ).pack(side=tk.LEFT, padx=6, pady=3)

        return text

    def _append_output(self, widget, line):
        was_disabled = str(widget.cget("state")) == "disabled"
        if was_disabled:
            widget.config(state=tk.NORMAL)

        tag = None
        low = line.lower()
        if any(x in line for x in ("✅", "🆕", "📦", "💾", "✔")):
            tag = "ok"
        elif any(x in line for x in ("⚠️", "⚠", "warning", "Warning")):
            tag = "warn"
        elif any(x in line for x in ("❌", "error", "Error", "Traceback", "Exception")):
            tag = "err"
        elif line.startswith("⏹") or "exit " in low:
            tag = "err" if ("exit 0" not in low and "exit " in low) else "dim"
        elif line.startswith("▶") or line.startswith("─"):
            tag = "dim"

        widget.insert(tk.END, line, tag) if tag else widget.insert(tk.END, line)

        if self.auto_scroll.get(id(widget), tk.BooleanVar(value=True)).get():
            widget.see(tk.END)

        if was_disabled:
            widget.config(state=tk.DISABLED)

    def _kill_process(self, proc, name=""):
        if proc is None or proc.poll() is not None:
            return
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True
                )
                if result.returncode != 0:
                    proc.terminate()
            else:
                import signal as _signal
                try:
                    os.killpg(os.getpgid(proc.pid), _signal.SIGTERM)
                except Exception:
                    proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._log(f"⚠️ {name} (PID {proc.pid}) did not exit after kill\n")
        except Exception as e:
            self._log(f"⚠️ Error stopping {name}: {e}\n")

    def _set_indicator(self, key, running):
        dot = self.indicators.get(key)
        if dot:
            dot.configure(fg=self.T["indicator_run"] if running else self.T["indicator_idle"])

    def _set_status(self, msg):
        self.status_var.set(msg)

    def _log(self, msg):
        self._append_output(self.log_text, msg)

    # -------------------------------------------------------------------------
    # MANUAL IMDb ID SETTER
    # -------------------------------------------------------------------------
    def open_imdb_dialog(self):
        categories = [
            "movies.json", "dubbed-movies.json", "hindi.json",
            "asian-movies.json", "anime-movies.json", "anime.json",
            "series.json", "tvshows.json", "asian-series.json"
        ]
        category = simpledialog.askstring(
            "Category",
            "Enter category file name:\n" + "\n".join(categories)
        )
        if not category:
            return

        content_id = simpledialog.askstring("Content ID", "Enter content ID (numeric):")
        if not content_id or not content_id.isdigit():
            messagebox.showerror("Error", "Invalid content ID. Must be numeric.")
            return

        imdb_id = simpledialog.askstring("IMDb ID", "Enter IMDb ID (e.g., tt1234567):")
        if not imdb_id or not imdb_id.startswith("tt"):
            messagebox.showerror("Error", "Invalid IMDb ID. Must start with 'tt'.")
            return

        cmd = [PYTHON_EXE, "-u", "set_imdb_id.py",
               "--category", category, "--id", content_id, "--imdb_id", imdb_id]
        proc, text_widget = self._run_subprocess(cmd, f"Set IMDb ID: {content_id}")
        if proc:
            key = f"Set IMDb ID {content_id}"
            self.processes[key]   = proc
            self.output_tabs[key] = text_widget

    # -------------------------------------------------------------------------
    # MANUAL MAL ID SETTER
    # -------------------------------------------------------------------------
    def open_mal_setter_dialog(self):
        categories = [
            "anime.json", "anime-movies.json"
        ]
        category = simpledialog.askstring(
            "Category",
            "Enter category file name:\n" + "\n".join(categories),
            initialvalue="anime.json"
        )
        if not category:
            return

        content_id = simpledialog.askstring("Content ID", "Enter content ID (numeric):")
        if not content_id or not content_id.isdigit():
            messagebox.showerror("Error", "Invalid content ID. Must be numeric.")
            return

        mal_id = simpledialog.askstring("MAL ID", "Enter MyAnimeList ID (numeric, e.g., 16498):")
        if not mal_id or not mal_id.isdigit():
            messagebox.showerror("Error", "Invalid MAL ID. Must be a positive integer.")
            return

        cmd = [PYTHON_EXE, "-u", "set_mal_id.py",
               "--category", category, "--id", content_id, "--mal_id", mal_id]
        proc, text_widget = self._run_subprocess(cmd, f"Set MAL ID: {content_id}")
        if proc:
            key = f"Set MAL ID {content_id}"
            self.processes[key]   = proc
            self.output_tabs[key] = text_widget

    # -------------------------------------------------------------------------
    # RATING / RUNTIME BY ID
    # -------------------------------------------------------------------------
    def open_rating_by_id(self):
        categories = [
            "movies.json", "dubbed-movies.json", "hindi.json",
            "asian-movies.json", "anime-movies.json", "anime.json",
            "series.json", "tvshows.json", "asian-series.json"
        ]
        category = simpledialog.askstring(
            "Category",
            "Enter category file name:\n" + "\n".join(categories)
        )
        if not category:
            return

        ids_str = simpledialog.askstring("Content IDs", "Enter one or more content IDs (space-separated):")
        if not ids_str:
            return
        ids = ids_str.split()

        cmd = [PYTHON_EXE, "-u", "update_ratings.py", "--category", category, "--ids"] + ids
        proc, text_widget = self._run_subprocess(cmd, f"Rating for IDs: {', '.join(ids)}")
        if proc:
            key = f"Rating IDs {category} {ids[0]}"
            self.processes[key] = proc
            self.output_tabs[key] = text_widget

    def open_runtime_by_id(self):
        categories = [
            "movies.json", "dubbed-movies.json", "hindi.json",
            "asian-movies.json", "anime-movies.json", "anime.json",
            "series.json", "tvshows.json", "asian-series.json"
        ]
        category = simpledialog.askstring(
            "Category",
            "Enter category file name:\n" + "\n".join(categories)
        )
        if not category:
            return

        ids_str = simpledialog.askstring("Content IDs", "Enter one or more content IDs (space-separated):")
        if not ids_str:
            return
        ids = ids_str.split()

        cmd = [PYTHON_EXE, "-u", "update_runtime.py", "--category", category, "--ids"] + ids
        proc, text_widget = self._run_subprocess(cmd, f"Runtime for IDs: {', '.join(ids)}")
        if proc:
            key = f"Runtime IDs {category} {ids[0]}"
            self.processes[key] = proc
            self.output_tabs[key] = text_widget

    def open_mal_by_id(self):
        ids_str = simpledialog.askstring("Content IDs", "Enter one or more anime IDs (space-separated):")
        if not ids_str:
            return
        ids = ids_str.split()
        category = simpledialog.askstring(
            "Category",
            "Enter category file (anime.json or anime-movies.json):",
        ) or "anime.json"
        cmd = [PYTHON_EXE, "-u", "update_mal.py", "--category", category, "--ids"] + ids
        proc, text_widget = self._run_subprocess(cmd, f"MAL for IDs: {', '.join(ids)}")
        if proc:
            key = f"MAL IDs {ids[0]}"
            self.processes[key]   = proc
            self.output_tabs[key] = text_widget

    # -------------------------------------------------------------------------
    # INTEGRATED SERIES SELECTOR POPUP
    # -------------------------------------------------------------------------
    def open_series_selector(self):
        """Create a popup to browse episodic series with queue and batch update."""
        import re  # ensure re is available

        # Load all series from episodic JSON files
        episodic_files = [
            "anime.json",
            "series.json",
            "tvshows.json",
            "asian-series.json",
            "arabic-series.json",
        ]
        series_list = []
        for filename in episodic_files:
            filepath = Path(SCRIPTS_DIR) / "output" / filename
            if not filepath.exists():
                continue
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            category = filename.replace(".json", "")
            if isinstance(data, dict):
                for cid, info in data.items():
                    title = info.get("Title", "Unknown")
                    series_list.append((str(cid), title, category))

        if not series_list:
            messagebox.showinfo("No Data", "No series found in output/")
            return

        # Remove duplicates
        seen = set()
        unique = []
        for cid, title, cat in series_list:
            if (cid, cat) not in seen:
                seen.add((cid, cat))
                unique.append((cid, title, cat))
        unique.sort(key=lambda x: (x[2], x[1].lower()))

        # Create popup
        popup = tk.Toplevel(self.root)
        popup.title("Select Series – Queue & Batch Update")
        popup.geometry("900x600")
        popup.transient(self.root)

        # Main frame with two equal columns
        main_frame = tk.Frame(popup)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        main_frame.columnconfigure(0, weight=1, uniform="col")
        main_frame.columnconfigure(1, weight=1, uniform="col")
        main_frame.rowconfigure(0, weight=1)

        # ─── LEFT PANEL ────────────────────────────────────────────────
        left_frame = tk.LabelFrame(main_frame, text="Browse Series", padx=5, pady=5)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=5)
        left_frame.rowconfigure(2, weight=1)
        left_frame.columnconfigure(0, weight=1)

        tk.Label(left_frame, text="Search (title or ID):", anchor="w").grid(row=0, column=0, sticky="ew", pady=(0,5))
        search_var = tk.StringVar()
        search_entry = tk.Entry(left_frame, textvariable=search_var)
        search_entry.grid(row=1, column=0, sticky="ew", pady=(0,5))

        # Debounced search (300ms delay)
        def debounced_filter(*args):
            if hasattr(search_entry, '_after_id') and search_entry._after_id:
                search_entry.after_cancel(search_entry._after_id)
            search_entry._after_id = search_entry.after(300, apply_filter)

        def apply_filter():
            query = search_var.get().strip().lower()
            if not query:
                filtered_items[:] = all_items
            else:
                filtered_items[:] = [item for item in all_items if query in item[1].lower() or query in item[0].lower()]
            refresh()

        search_var.trace("w", debounced_filter)

        listbox_frame = tk.Frame(left_frame)
        listbox_frame.grid(row=2, column=0, sticky="nsew")
        listbox_frame.rowconfigure(0, weight=1)
        listbox_frame.columnconfigure(0, weight=1)

        scrollbar = tk.Scrollbar(listbox_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set, selectmode=tk.EXTENDED, font=("Segoe UI",10))
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)

        all_items = unique
        filtered_items = all_items[:]

        def refresh():
            listbox.delete(0, tk.END)
            for cid, title, cat in filtered_items:
                listbox.insert(tk.END, f"[{cat}] {title} (ID: {cid})")

        def filter_list(*args):
            query = search_var.get().strip().lower()
            if not query:
                filtered_items[:] = all_items
            else:
                filtered_items[:] = [item for item in all_items if query in item[1].lower() or query in item[0].lower()]
            refresh()

        search_var.trace("w", filter_list)
        refresh()

        # ─── RIGHT PANEL ───────────────────────────────────────────────
        right_frame = tk.LabelFrame(main_frame, text="Update Queue", padx=5, pady=5)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=5)
        right_frame.rowconfigure(0, weight=1)
        right_frame.columnconfigure(0, weight=1)

        queue_listbox = tk.Listbox(right_frame, font=("Segoe UI",10), selectmode=tk.EXTENDED)
        queue_listbox.grid(row=0, column=0, sticky="nsew", pady=(0,5))

        btn_frame = tk.Frame(right_frame)
        btn_frame.grid(row=1, column=0, sticky="ew", pady=5)
        for i in range(3):
            btn_frame.columnconfigure(i, weight=1)

        def add_selected():
            for idx in listbox.curselection():
                cid, title, cat = filtered_items[idx]
                # Avoid duplicates
                if not any(f"(ID: {cid})" in queue_listbox.get(i) for i in range(queue_listbox.size())):
                    queue_listbox.insert(tk.END, f"[{cat}] {title} (ID: {cid})")
            listbox.selection_clear(0, tk.END)

        def remove_selected():
            for idx in reversed(queue_listbox.curselection()):
                queue_listbox.delete(idx)

        def clear_queue():
            queue_listbox.delete(0, tk.END)

        tk.Button(btn_frame, text="Add Selected →", command=add_selected).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        tk.Button(btn_frame, text="← Remove Selected", command=remove_selected).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        tk.Button(btn_frame, text="Clear Queue", command=clear_queue).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        # ─── UPDATE BUTTON (SAME AS YOUR WORKING VERSION) ──────────────
        def run_update():
            ids = []
            for i in range(queue_listbox.size()):
                m = re.search(r'\(ID:\s*(\d+)\)', queue_listbox.get(i))
                if m:
                    ids.append(m.group(1))
            if not ids:
                messagebox.showwarning("Empty Queue", "No series in the queue.")
                return
            popup.destroy()
            cmd = [PYTHON_EXE, "-u", "update_specific_episodes.py", "--ids"] + ids
            print(f"DEBUG: Running command: {cmd}")  # Debug line
            self._run_subprocess(cmd, f"Update episodes for {len(ids)} queued IDs")

        tk.Button(right_frame, text="▶ Update Queue", command=run_update,
                  bg="#22c55e", fg="white", font=("Segoe UI",11,"bold"), padx=10, pady=5).grid(row=2, column=0, sticky="ew", pady=5)

        # Double-click shortcuts
        listbox.bind("<Double-Button-1>", lambda e: add_selected())
        queue_listbox.bind("<Double-Button-1>", lambda e: remove_selected())

        # Cancel button
        tk.Button(popup, text="Cancel", command=popup.destroy, width=15).pack(side=tk.BOTTOM, pady=10)

        # ─── CENTER THE POPUP ──────────────────────────────────────────
        popup.update_idletasks()
        w = popup.winfo_width()
        h = popup.winfo_height()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (w // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (h // 2)
        popup.geometry(f"{w}x{h}+{x}+{y}")
        popup.grab_set()


if __name__ == "__main__":
    if not os.path.exists(PYTHON_EXE):
        import tkinter.messagebox as _mb
        _mb.showerror("Configuration Error",
                      f"Python executable not found:\n{PYTHON_EXE}\n\n"
                      "Edit PYTHON_EXE at the top of this script.")
        sys.exit(1)

    root = tk.Tk()
    app  = ScraperGUI(root)
    root.mainloop()