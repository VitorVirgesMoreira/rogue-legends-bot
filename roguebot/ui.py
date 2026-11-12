"""Tk window with Portuguese, Spanish and English controls, status and run summaries."""

import logging
from dataclasses import asdict
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from pathlib import Path
from typing import Callable

from roguebot import emulator, settings
from roguebot.activity_ui import ActivityPanel
from roguebot.diagnostics import inspect_emulator
from roguebot.device import Stopped
from roguebot.desktop_theme import ACCENT, INK, LINE, SURFACE, install_theme
from roguebot.observation import Observation
from roguebot.preview import watch as watch_preview
from roguebot.providers import PROVIDERS, find_adb
from roguebot.build import BURN, CUSTOM, PROFILES, STRATEGIES, Build
from roguebot.combat_context import Loadout
from roguebot.account_ui import AccountDialog, OBJECTIVES
from roguebot.account_scan_ui import AccountScanCoordinator
from roguebot.i18n import DEFAULT_UI_LANGUAGE, UI_LANGUAGES, tr
from roguebot.report import Report, render
from roguebot.request import BEATEN, LATEST, PENDING, STARS, FARM, ROUTINE_CHOICES, RunRequest, build_request, positive_integer
from roguebot.party_build import ROLES
from roguebot.screens import Mode
from roguebot.skills import DAMAGE_TYPES, MAGIC, PHYSICAL

log = logging.getLogger("roguebot")
APP_TITLE = "Rogue Legends Bot"
ICON = Path(__file__).parent / "assets" / "icon.png"
ICON_HEADER_SHRINK = 3  # 192 px icon -> 64 px in the header
SOURCE_OPTIONS = {LATEST: "latest", BEATEN: "beaten", PENDING: "pending", FARM: "farm", STARS: "stars"}


class App:
    def __init__(self, run: Callable[[RunRequest], Report], lang: str | None = None,
                 stop: Callable[[], None] | None = None, settings_path: Path = settings.SETTINGS_PATH):
        """run(request) does the whole job and returns a Report; it raises on failure.
        stop() asks a running job to end (it then raises from run).
        Every option is saved to settings_path (on Start, language change and close) and restored here."""
        self.run = run
        self.stop = stop
        self._stopping = False
        self._job_running = False
        self._closed = False
        self.account_reader = AccountScanCoordinator(self)
        self._run_results: queue.SimpleQueue[Report | Exception] = queue.SimpleQueue()
        self._preview_active = False
        self._preview_stop = threading.Event()
        self._preview_results = queue.Queue()
        self._observation: Observation | None = None
        self._observation_mode = "idle"
        self.settings_path = settings_path
        saved = settings.load(settings_path)
        saved_lang = saved.get("lang")
        lang = lang or (saved_lang if isinstance(saved_lang, str) and saved_lang in UI_LANGUAGES else DEFAULT_UI_LANGUAGE)
        self.lang = lang
        self._status: tuple[str, dict, str] = ("idle", {}, "black")  # i18n key, args, color
        self._texts: list[tuple[ttk.Widget, str]] = []                 # widgets to retranslate

        if sys.platform == "win32":  # own taskbar entry (and icon) instead of python.exe's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("roguebot.RogueLegendBot")
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        install_theme(self.root)
        self.root.geometry("930x684")
        self.root.minsize(790, 650)
        self.icon = tk.PhotoImage(file=ICON)
        self.root.iconphoto(True, self.icon)  # title bar and taskbar

        header = ttk.Frame(self.root, style="Header.TFrame", padding=(24, 14))
        header.pack(fill="x")
        header.columnconfigure(1, weight=1)
        self.header_icon = self.icon.subsample(ICON_HEADER_SHRINK)
        ttk.Label(header, image=self.header_icon, style="Brand.TLabel").grid(
            row=0, column=0, rowspan=2, padx=(0, 16))
        self.header_title = ttk.Label(header, text=APP_TITLE, style="Brand.TLabel")
        self.header_title.grid(row=0, column=1, sticky="w")
        self._text(ttk.Label(header, style="HeaderNote.TLabel"), "desktop_tagline").grid(
            row=1, column=1, sticky="w")
        self.changelog_toggle = ttk.Button(header, command=self._toggle_changelog)
        self.changelog_toggle.grid(row=1, column=2, sticky="e")
        top = ttk.Frame(header, style="Header.TFrame")
        top.grid(row=0, column=2, sticky="ne")
        self._text(ttk.Label(top, style="HeaderNote.TLabel"), "language").pack(side="left", padx=(0, 6))
        self.ui_lang = tk.StringVar(value=UI_LANGUAGES[lang])
        picker = ttk.Combobox(top, textvariable=self.ui_lang, values=list(UI_LANGUAGES.values()),
                              state="readonly", width=10)
        picker.pack(side="left")
        picker.bind("<<ComboboxSelected>>", lambda _: (self.set_language(
            next(k for k, v in UI_LANGUAGES.items() if v == self.ui_lang.get())), self._save_options()))

        self.workspace = ttk.Notebook(self.root)
        footer = ttk.Frame(self.root, padding=(24, 10, 24, 14))
        footer.pack(side="bottom", fill="x")
        self.workspace.pack(fill="both", expand=True, padx=24, pady=(12, 0))
        self.workspace.enable_traversal()
        self.pages = {}
        for key in ("play", "connection", "strategy", "activity"):
            page = ttk.Frame(self.workspace, padding=(4, 14, 4, 0))
            self.workspace.add(page)
            self.pages[key] = page

        connection_page = self.pages["connection"]
        self._page_intro(connection_page, "connection_title", "connection_intro")
        info = ttk.Frame(connection_page)
        info.pack(fill="x", pady=(14, 0))
        provider_row = ttk.Frame(info)
        provider_row.pack(fill="x", pady=(6, 0))
        self._text(ttk.Label(provider_row), "emulator").pack(side="left", padx=(0, 6))
        configured = saved.get("provider", "mumu")
        if configured not in PROVIDERS:
            configured = "mumu"
        self.provider = tk.StringVar(value=configured)
        self.provider_name = tk.StringVar(value=PROVIDERS[configured])
        self.provider_picker = ttk.Combobox(provider_row, textvariable=self.provider_name,
                                           values=list(PROVIDERS.values()), state="readonly", width=42)
        self.provider_picker.pack(side="left", fill="x", expand=True)
        self.provider_picker.bind("<<ComboboxSelected>>", self._change_provider)
        folder_row = ttk.Frame(info)
        self.folder_row = folder_row
        folder_row.pack(fill="x", pady=(6, 0))
        self._text(ttk.Label(folder_row), "mumu_folder").pack(side="left", padx=(0, 6))
        folder = saved.get("mumu_folder", "")
        self.mumu_folder = tk.StringVar(value=folder if emulator.tools(folder or "-") else str(emulator.find_install() or ""))
        ttk.Entry(folder_row, textvariable=self.mumu_folder, width=45).pack(side="left", fill="x", expand=True)
        self._text(ttk.Button(folder_row, command=self._browse), "browse").pack(side="left", padx=(6, 0))
        self.mumu_status = ttk.Label(info)
        self.mumu_status.pack(anchor="w")
        self.mumu_folder.trace_add("write", lambda *_: self._folder_changed())
        self._connections = saved.get("provider_connections", {})
        if not isinstance(self._connections, dict):
            self._connections = {}
        connection = self._connections.get(configured, {})
        if not isinstance(connection, dict):
            connection = {}
        self.adb_path = tk.StringVar(value=connection.get("adb_path", saved.get("adb_path", "")))
        self.device_serial = tk.StringVar(value=connection.get("device_serial", saved.get("device_serial", "")))
        manual = self._text(ttk.Checkbutton(info, command=self._show_connection_details), "connection_advanced")
        self.connection_details = tk.BooleanVar(value=False)
        manual.configure(variable=self.connection_details)
        manual.pack(anchor="w", pady=(12, 0))
        self.manual_connection = ttk.Frame(info)
        adb_row = ttk.Frame(self.manual_connection)
        adb_row.pack(fill="x", pady=(4, 0))
        self._text(ttk.Label(adb_row), "adb_path").pack(side="left", padx=(0, 6))
        self.adb_entry = ttk.Entry(adb_row, textvariable=self.adb_path, width=45)
        self.adb_entry.pack(side="left", fill="x", expand=True)
        self._text(ttk.Button(adb_row, command=self._browse_adb), "browse").pack(side="left", padx=(6, 0))
        serial_row = ttk.Frame(self.manual_connection)
        serial_row.pack(fill="x", pady=(4, 0))
        self._text(ttk.Label(serial_row), "device_serial").pack(side="left", padx=(0, 6))
        ttk.Entry(serial_row, textvariable=self.device_serial, width=24).pack(side="left")
        self.connection_actions = ttk.Frame(info)
        self.connection_actions.pack(fill="x", pady=(12, 6))
        self.check_button = self._text(ttk.Button(self.connection_actions, style="Primary.TButton",
                                                  command=self._check_connection), "check_connection")
        self.check_button.pack(side="left", padx=(0, 12))
        self._text(ttk.Label(self.connection_actions, style="Hint.TLabel"), "connection_check_help").pack(side="left")
        self.connection_status = ttk.Label(info, wraplength=680)
        self.connection_status.pack(anchor="w", pady=(4, 0))
        self.info = self._text(ttk.Label(info, wraplength=650, justify="left", style="Hint.TLabel",
                                        font=("Segoe UI", 9)), "info")
        self.info.pack(anchor="w", pady=(14, 0))
        self._connection_results = queue.Queue()
        self._connection_result = None
        self._checking_connection = False
        self.adb_path.trace_add("write", lambda *_: self._invalidate_connection())
        self.device_serial.trace_add("write", lambda *_: self._invalidate_connection())
        self._show_provider()

        play_page = self.pages["play"]
        self._page_intro(play_page, "play_title", "play_intro")
        play_content = ttk.Frame(play_page)
        play_content.pack(fill="both", expand=True, pady=(16, 0))
        play_content.columnconfigure(0, weight=1)
        frame = ttk.Frame(play_content, padding=(0, 0, 24, 0))
        frame.grid(row=0, column=0, sticky="new")
        rail = ttk.Frame(play_content, padding=13, style="Rail.TFrame")
        rail.grid(row=0, column=1, sticky="new")
        self._text(ttk.Label(rail, style="RailTitle.TLabel"), "first_run_title").pack(anchor="w")
        self._text(ttk.Label(rail, style="RailHint.TLabel", wraplength=215, justify="left"),
                   "first_run_help").pack(anchor="w", pady=(4, 7))
        self._text(ttk.Button(rail, style="Shortcut.TButton", command=lambda: self.workspace.select(connection_page)),
                   "open_connection").pack(fill="x")
        ttk.Separator(rail).pack(fill="x", pady=10)
        self._text(ttk.Label(rail, style="RailTitle.TLabel"), "desk_account").pack(anchor="w")
        self._text(ttk.Label(rail, style="RailHint.TLabel", wraplength=215, justify="left"),
                   "desk_account_help").pack(anchor="w", pady=(4, 7))
        self._text(ttk.Button(rail, style="Shortcut.TButton", command=lambda: self._open_account("inventory")),
                   "open_inventory").pack(fill="x")
        self._text(ttk.Button(rail, style="Shortcut.TButton", command=lambda: self._open_account("pet_plan")),
                   "open_pets").pack(fill="x", pady=(6, 0))

        self.mode = tk.StringVar(value=Mode.NORMAL.value)
        self._text(ttk.Label(frame, style="Section.TLabel"), "play_mode").grid(
            row=1, column=0, columnspan=4, sticky="w")
        mode_choices = ttk.Frame(frame)
        mode_choices.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(5, 13))
        self.mode_picker = ttk.Combobox(mode_choices, state="readonly", width=21)
        self.mode_picker.pack(side="left", fill="x", expand=True)
        self.mode_picker.bind("<<ComboboxSelected>>",
                              lambda _: self.mode.set(tuple(Mode)[self.mode_picker.current()].value))
        energy_row = ttk.Frame(mode_choices)
        self.energy_row = energy_row
        energy_row.pack(side="left", padx=(12, 0))
        self._text(ttk.Label(energy_row), "elite_energy").pack(side="left", padx=(0, 6))
        self.elite_energy = tk.StringVar(value="auto")
        self.elite_energy_name = tk.StringVar()
        self.elite_energy_picker = ttk.Combobox(energy_row, textvariable=self.elite_energy_name, width=12, state="disabled")
        self.elite_energy_picker.pack(side="left")
        self.elite_energy_picker.bind("<<ComboboxSelected>>", self._select_elite_energy)
        self.elite_energy.trace_add("write", lambda *_: self._show_elite_energy())
        self.mode.trace_add("write", lambda *_: self._toggle_elite_energy())
        self.mode.trace_add("write", lambda *_: self._show_party_options())

        self.source = tk.StringVar(value=LATEST)
        self.level_label = self._text(ttk.Label(frame, style="Section.TLabel"), "play_source")
        self.level_label.grid(row=3, column=0, columnspan=4, sticky="w")
        sources = ttk.Frame(frame)
        self.sources_row = sources
        sources.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(5, 0))
        self.source_picker = ttk.Combobox(sources, state="readonly", width=21)
        self.source_picker.pack(side="left", fill="x", expand=True)
        self.source_picker.bind("<<ComboboxSelected>>",
                                lambda _: self.source.set(tuple(SOURCE_OPTIONS)[self.source_picker.current()]))
        self.level_controls = ttk.Frame(sources)
        self._text(ttk.Label(self.level_controls), "play_level_number").pack(side="left", padx=(10, 6))
        self.level = tk.StringVar(value="1")
        self.level_entry = ttk.Spinbox(self.level_controls, from_=1, to=999, width=5,
                                       textvariable=self.level, state="disabled")
        self.level_entry.pack(side="left")
        self.source_hint = ttk.Label(frame, wraplength=425, style="Hint.TLabel")
        self.source_hint.grid(row=5, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.source.trace_add("write", lambda *_: self._toggle_level())

        self.party_role = tk.StringVar(value="striker")
        self.party_role_name = tk.StringVar()
        self.party_runs = tk.StringVar(value="20")
        self.party_label = self._text(ttk.Label(frame, style="Section.TLabel"), "party_options")
        self.party_row = ttk.Frame(frame)
        self._text(ttk.Label(self.party_row), "party_role").pack(side="left", padx=(0, 6))
        self.party_role_picker = ttk.Combobox(self.party_row, textvariable=self.party_role_name, state="readonly", width=16)
        self.party_role_picker.pack(side="left")
        self.party_role_picker.bind("<<ComboboxSelected>>", self._select_party_role)
        self._text(ttk.Label(self.party_row), "party_runs").pack(side="left", padx=(12, 6))
        ttk.Spinbox(self.party_row, from_=1, to=20, width=4, textvariable=self.party_runs).pack(side="left")
        self.party_help = self._text(ttk.Label(frame, wraplength=435, justify="left", style="Hint.TLabel"), "party_help")

        self.routine_panel = ttk.Frame(frame)
        self.routine_panel.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self._text(ttk.Label(self.routine_panel, style="Section.TLabel"), "play_activities").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))
        self.routine_options = {part: tk.BooleanVar(value=False) for part in ROUTINE_CHOICES}
        for index, (part, variable) in enumerate(self.routine_options.items()):
            self._text(ttk.Checkbutton(self.routine_panel, variable=variable), "play_activity_" + part).grid(
                row=1 + index % 4, column=index // 4, sticky="w", padx=(0, 18))

        self.run_options = ttk.Frame(frame)
        self.run_options.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        self.loop = tk.BooleanVar(value=False)
        self._text(ttk.Checkbutton(self.run_options, variable=self.loop), "play_loop").pack(side="left", padx=(0, 12))
        self.ads = tk.BooleanVar(value=False)
        self._text(ttk.Checkbutton(self.run_options, variable=self.ads), "play_ads").pack(side="left")
        frame.columnconfigure(3, weight=1)

        strategy_page = self.pages["strategy"]
        self._text(ttk.Label(strategy_page, style="PageTitle.TLabel"), "strategy_title").grid(sticky="w")
        self.build_box = self._build_section(strategy_page)
        self.build_box.grid(row=1, column=0, sticky="new", pady=(10, 0))
        strategy_page.columnconfigure(0, weight=1)

        ttk.Separator(footer).pack(fill="x", pady=(0, 10))
        actions = ttk.Frame(footer)
        actions.pack(side="right")
        self.preview_button = ttk.Button(actions, command=self._preview)
        self.preview_button.pack(side="left", padx=(0, 8))
        self.stop_button = self._text(ttk.Button(actions, command=self._stop, state="disabled"), "stop")
        self.stop_button.pack(side="left", padx=(0, 8))
        self.start = self._text(ttk.Button(actions, command=self._start, width=13, style="Primary.TButton"), "start")
        self.start.pack(side="left")
        self._text(ttk.Label(footer, style="Hint.TLabel"), "run_status").pack(anchor="w")
        self.status = ttk.Label(footer, style="Section.TLabel", wraplength=435)
        self.status.pack(anchor="w", fill="x", expand=True)

        activity_page = self.pages["activity"]
        self._page_intro(activity_page, "activity_title", "activity_intro")
        self.activity = ActivityPanel(activity_page, log)
        self.activity.pack(fill="both", expand=True)

        self._restore_options(saved)
        self.set_language(lang)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _page_intro(self, parent, title, detail):
        self._text(ttk.Label(parent, style="PageTitle.TLabel"), title).pack(anchor="w")
        self._text(ttk.Label(parent, style="Hint.TLabel", wraplength=680, justify="left"), detail).pack(
            anchor="w", pady=(3, 0))

    def _open_account(self, page):
        dialog = getattr(self, "account_dialog", None)
        if dialog and dialog.window.winfo_exists():
            dialog.show(page)
        else:
            self.account_dialog = AccountDialog(self, page=page)

    def _show_connection_details(self):
        if self.connection_details.get():
            self.info.pack_forget()
            self.manual_connection.pack(fill="x", before=self.connection_actions)
        else:
            self.manual_connection.pack_forget()
            self.info.pack(anchor="w", pady=(14, 0))

    def _build_section(self, parent) -> ttk.Frame:
        """Skill preferences: nature, damage type order (move up/down), support every N damage skills."""
        box = ttk.Frame(parent)
        box.columnconfigure(0, weight=1)
        self.loadout = Loadout()
        self.planner_facts = {}
        self.scanned_account = ""
        self.scan_at = ""
        self.auto_scan = tk.BooleanVar(value=True)
        self.use_scan_strategy = tk.BooleanVar(value=True)
        self.strategy = tk.StringVar(value="balanced")
        self.farm_objective = tk.StringVar(value="reliable")
        self.claim_events = tk.BooleanVar(value=False)
        self.burn_build = tk.BooleanVar(value=False)
        self.build_profile = tk.StringVar(value=CUSTOM)
        self.profile_name = tk.StringVar()
        self._text(ttk.Label(box, style="Section.TLabel"), "build_profile").grid(row=0, column=0, sticky="w")
        self.profile_picker = ttk.Combobox(box, textvariable=self.profile_name, width=33, state="readonly")
        self.profile_picker.grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.profile_picker.bind("<<ComboboxSelected>>", self._select_profile)
        self.burn_build.trace_add("write", lambda *_: self._legacy_burn_profile())
        self._text(ttk.Label(box, wraplength=625, style="Hint.TLabel", justify="left"), "build_focus_help").grid(
            row=2, column=0, sticky="w", pady=(6, 14))
        self._text(ttk.Button(box, command=lambda: self._open_account("strategy")), "desk_farm_settings").grid(
            row=3, column=0, sticky="w")
        details = ttk.Frame(box)
        details.grid(row=5, column=0, sticky="w", pady=(8, 0))
        details.grid_remove()
        show_details = tk.BooleanVar(value=False)
        self._text(ttk.Checkbutton(box, variable=show_details,
                   command=lambda: details.grid() if show_details.get() else details.grid_remove()),
                   "desk_skill_details").grid(row=4, column=0, sticky="w", pady=(16, 0))

        self.nature = tk.StringVar(value=PHYSICAL)
        self._text(ttk.Label(details), "build_nature").grid(row=0, column=0, sticky="w")
        self._text(ttk.Radiobutton(details, variable=self.nature, value=PHYSICAL), "physical").grid(row=0, column=1, sticky="w")
        self._text(ttk.Radiobutton(details, variable=self.nature, value=MAGIC), "magic").grid(row=0, column=2, sticky="w")

        self._text(ttk.Label(details), "build_order").grid(row=1, column=0, sticky="nw", pady=(6, 0), padx=(0, 10))
        self.damage_order = list(DAMAGE_TYPES)
        self.order_list = tk.Listbox(details, height=len(DAMAGE_TYPES), width=18, exportselection=False,
                                     background=SURFACE, foreground=INK, selectbackground=ACCENT,
                                     font=("Segoe UI", 10), relief="flat", highlightbackground=LINE,
                                     highlightcolor=ACCENT, highlightthickness=1)
        self.order_list.grid(row=1, column=1, columnspan=2, sticky="w", pady=(6, 0))
        moves = ttk.Frame(details)
        moves.grid(row=1, column=3, sticky="nw", padx=6, pady=(6, 0))
        self._text(ttk.Button(moves, command=lambda: self._move(-1)), "move_up").pack(fill="x")
        self._text(ttk.Button(moves, command=lambda: self._move(1)), "move_down").pack(fill="x", pady=(4, 0))

        self.support = tk.BooleanVar(value=False)
        self.support_every = tk.StringVar(value="3")
        support = ttk.Frame(details)
        support.grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self._text(ttk.Checkbutton(support, variable=self.support), "build_support").pack(side="left")
        ttk.Spinbox(support, from_=1, to=20, width=4, textvariable=self.support_every).pack(side="left", padx=4)
        self._text(ttk.Label(support), "build_support_after").pack(side="left")
        return box

    def _refresh_order(self, selected: int | None = None) -> None:
        self.order_list.delete(0, "end")
        for i, damage_type in enumerate(self.damage_order, 1):
            self.order_list.insert("end", f"{i}. {tr(self.lang, 'type_' + damage_type)}")
        if selected is not None:
            self.order_list.selection_set(selected)

    def _move(self, delta: int) -> None:
        """Move the selected damage type up (-1) or down (+1) in the priority list."""
        sel = self.order_list.curselection()
        if not sel or not 0 <= sel[0] + delta < len(self.damage_order):
            return
        i, j = sel[0], sel[0] + delta
        self.damage_order[i], self.damage_order[j] = self.damage_order[j], self.damage_order[i]
        self._refresh_order(j)

    def build(self) -> Build:
        support_every = positive_integer(self.support_every.get()) if self.support.get() else None
        return Build(self.nature.get(), tuple(self.damage_order), support_every, self.build_profile.get(),
                     self.strategy.get(), self.loadout)

    def options(self) -> dict:
        """Every user choice, as saved between sessions."""
        values = {"lang": self.lang, "mode": self.mode.get(), "source": self.source.get(), "level": self.level.get(),
                  "routine_parts": list(self._selected_activities()), "loop": self.loop.get(), "ads": self.ads.get(),
                  "nature": self.nature.get(), "damage_order": list(self.damage_order),
                  "support": self.support.get(), "support_every": self.support_every.get(),
                  "burn_build": self.burn_build.get(), "build_profile": self.build_profile.get(),
                  "party_role": self.party_role.get(), "party_runs": self.party_runs.get(),
                  "strategy": self.strategy.get(), "loadout": asdict(self.loadout),
                  "farm_objective": self.farm_objective.get(), "claim_events": self.claim_events.get(),
                  "planner_facts": self.planner_facts,
                  "auto_scan": self.auto_scan.get(), "use_scan_strategy": self.use_scan_strategy.get(),
                  "scanned_account": self.scanned_account, "scan_at": self.scan_at,
                  "elite_energy": None if self.elite_energy.get() == "auto" else int(self.elite_energy.get())}
        self._remember_connection()
        values.update(provider=self.provider.get(), adb_path=self.adb_path.get(),
                      device_serial=self.device_serial.get(), provider_connections=self._connections)
        if emulator.tools(self.mumu_folder.get() or "-"):
            values["mumu_folder"] = self.mumu_folder.get()
        return values

    def _selected_activities(self) -> tuple[str, ...]:
        return tuple(part for part, variable in self.routine_options.items() if variable.get())

    def _restore_options(self, saved: dict) -> None:
        """Last session's choices; anything missing or invalid keeps its default."""
        if isinstance(saved.get("provider"), str) and saved["provider"] in PROVIDERS:
            self.provider.set(saved["provider"])
            self.provider_name.set(PROVIDERS[saved["provider"]])
            if isinstance(saved.get("provider_connections"), dict):
                self._connections = saved["provider_connections"]
            for key in ("adb_path", "device_serial"):
                if isinstance(saved.get(key), str):
                    getattr(self, key).set(saved[key])
            self._show_provider()
        for var, key, choices in ((self.mode, "mode", tuple(m.value for m in Mode)),
                                  (self.source, "source", (LATEST, BEATEN, PENDING, FARM, STARS)),
                                  (self.nature, "nature", (PHYSICAL, MAGIC))):
            if saved.get(key) in choices:
                var.set(saved[key])
        for var, key in ((self.loop, "loop"), (self.ads, "ads"),
                         (self.support, "support"), (self.burn_build, "burn_build")):
            if isinstance(saved.get(key), bool):
                var.set(saved[key])
        selected = saved.get("routine_parts")
        if isinstance(selected, list):
            for part, variable in self.routine_options.items():
                variable.set(part in selected)
        elif saved.get("full") is True and "routine_parts" not in saved:
            for variable in self.routine_options.values():
                variable.set(True)
        if saved.get("build_profile") in PROFILES:
            self._set_profile(saved["build_profile"])
        if saved.get("strategy") in STRATEGIES:
            self.strategy.set(saved["strategy"])
        for name in ("auto_scan", "use_scan_strategy"):
            if type(saved.get(name)) is bool:
                getattr(self,name).set(saved[name])
        if "use_scan_strategy" not in saved and saved.get("build_profile",CUSTOM) != CUSTOM:
            self.use_scan_strategy.set(False)  # retain an existing explicit build preference
        for name in ("scanned_account", "scan_at"):
            if isinstance(saved.get(name),str):
                setattr(self,name,saved[name])
        if saved.get("farm_objective") in OBJECTIVES:
            self.farm_objective.set(saved["farm_objective"])
        if type(saved.get("claim_events")) is bool:
            self.claim_events.set(saved["claim_events"])
        if isinstance(saved.get("planner_facts"), dict):
            self.planner_facts = saved["planner_facts"]
        try:
            self.loadout = Loadout.from_dict(saved.get("loadout", {}))
        except (ValueError, TypeError):
            log.warning("Invalid saved loadout; keeping unknown equipment")
        if "elite_energy" in saved and (saved["elite_energy"] is None or
                type(saved["elite_energy"]) is int and saved["elite_energy"] in (5, 10, 15)):
            self.elite_energy.set("auto" if saved["elite_energy"] is None else str(saved["elite_energy"]))
        if saved.get("party_role") in ROLES:
            self.party_role.set(saved["party_role"])
        for var, key, maximum in ((self.party_runs, "party_runs", 20),
                                  (self.level, "level", None), (self.support_every, "support_every", None)):
            value = positive_integer(saved.get(key, ""))
            if value is not None and (maximum is None or value <= maximum):
                var.set(str(value))
        order = saved.get("damage_order")
        if isinstance(order, list) and all(isinstance(item, str) for item in order) and sorted(order) == sorted(DAMAGE_TYPES):
            self.damage_order = list(order)
        self._toggle_level()

    def _save_options(self) -> None:
        try:
            settings.save(self.options(), self.settings_path)
        except OSError as e:  # e.g. a read-only folder: the bot still works, it just forgets the choices
            log.error("Could not save the settings: %s", e)

    def _close(self) -> None:
        self._closed = True
        self.account_reader.cancel()
        self._preview_stop.set()
        if self._job_running and self.stop:
            self.stop()
        self._save_options()
        self.activity.close()
        self.root.destroy()

    def _text(self, widget, key: str):
        self._texts.append((widget, key))
        return widget

    def set_language(self, lang: str) -> None:
        self.lang = lang
        self.ui_lang.set(UI_LANGUAGES[lang])
        self._show_changelog_toggle()
        for widget, key in self._texts:
            widget.configure(text=tr(lang, key))
        for key, page in self.pages.items():
            self.workspace.tab(page, text=tr(lang, "desk_" + key))
        sel = self.order_list.curselection()
        self._refresh_order(sel[0] if sel else None)
        self._check_folder()
        self._show_elite_energy()
        self._show_profile()
        self._show_party_options()
        self._show_connection()
        self._show_status()
        self._show_observation()
        self._show_preview_button()

    def _toggle_changelog(self) -> None:
        self.activity.show_changelog(not self.activity.changelog_shown)
        if self.activity.changelog_shown:
            self.workspace.select(self.pages["activity"])
        self._show_changelog_toggle()

    def _show_changelog_toggle(self) -> None:
        arrow = "▾" if self.activity.changelog_shown else "▸"
        self.changelog_toggle.configure(text=f"{arrow} {tr(self.lang, 'changelog')}")
        self.activity.translate_heading(self.lang)

    def _show_live_activity(self) -> None:
        self.workspace.select(self.pages["activity"])
        if self.activity.changelog_shown:
            self._toggle_changelog()

    def mainloop(self) -> None:
        self.root.after(200, self._drain_logs)
        self.root.mainloop()

    def _browse(self) -> None:
        folder = filedialog.askdirectory(title=tr(self.lang, "mumu_folder"), initialdir=self.mumu_folder.get() or None)
        if folder:
            self.mumu_folder.set(folder)

    def _browse_adb(self) -> None:
        path = filedialog.askopenfilename(title=tr(self.lang, "adb_path"),
                                         filetypes=[("ADB", "adb.exe"), (tr(self.lang, "all_files"), "*")])
        if path:
            self.adb_path.set(path)

    def _remember_connection(self) -> None:
        self._connections[self.provider.get()] = {"adb_path": self.adb_path.get(), "device_serial": self.device_serial.get()}

    def _change_provider(self, _event=None) -> None:
        self._remember_connection()
        selected = next(key for key, name in PROVIDERS.items() if name == self.provider_name.get())
        self.provider.set(selected)
        connection = self._connections.get(selected, {})
        if not isinstance(connection, dict):
            connection = {}
        self.adb_path.set(connection.get("adb_path", "") if isinstance(connection.get("adb_path", ""), str) else "")
        self.device_serial.set(connection.get("device_serial", "") if isinstance(connection.get("device_serial", ""), str) else "")
        self._show_provider()
        self._invalidate_connection()
        self._save_options()

    def _show_provider(self) -> None:
        if self.provider.get() == "mumu":
            self.folder_row.pack(fill="x", pady=(6, 0), before=self.mumu_status)
        else:
            self.folder_row.pack_forget()
        self._check_folder()

    def _invalidate_connection(self) -> None:
        self._connection_result = None
        self._show_connection()

    def _connection_options(self) -> RunRequest:
        return RunRequest(Mode.NORMAL, None, mumu_folder=self.mumu_folder.get(), provider=self.provider.get(),
                          adb_path=self.adb_path.get(), device_serial=self.device_serial.get())

    def _check_connection(self) -> None:
        if self._checking_connection or self._preview_active or self._job_running:
            return
        request = self._connection_options()
        self._checking_connection = True
        self.check_button.configure(state="disabled")
        self.connection_status.configure(text=tr(self.lang, "checking_connection"), foreground="black")
        def check():
            try:
                result = inspect_emulator(request)
            except Exception as e:
                result = e
            self._connection_results.put((request, result))
        threading.Thread(target=check, daemon=True).start()
        self.root.after(100, self._poll_connection)

    def _poll_connection(self) -> None:
        try:
            request, result = self._connection_results.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_connection)
            return
        self._checking_connection = False
        self.check_button.configure(state="normal")
        if request == self._connection_options():
            self._connection_result = result
        self._show_connection()

    def _show_connection(self) -> None:
        result = self._connection_result
        if result is None:
            key = "connection_unknown_google" if self.provider.get() == "google_play_games" else "connection_unknown"
            self.connection_status.configure(text=tr(self.lang, key), foreground="black")
        elif isinstance(result, Exception):
            msg = tr(self.lang, result.key, **result.values) if isinstance(result, emulator.EmulatorError) else str(result)
            self.connection_status.configure(text=msg, foreground="red")
        else:
            v = result.viewport
            self.connection_status.configure(text=tr(self.lang, "connection_ok", serial=result.serial,
                width=v.display_width, height=v.display_height, left=v.left, top=v.top,
                vw=v.width, vh=v.height, installed=tr(self.lang, "installed" if result.installed else "missing")),
                foreground="green" if result.installed else "red")

    def _check_folder(self) -> None:
        if hasattr(self, "provider") and self.provider.get() == "google_play_games":
            found = find_adb()
            self.mumu_status.configure(text=tr(self.lang, "google_found" if found else "google_not_found"),
                                       foreground="green" if found else "darkorange")
            return
        ok = emulator.tools(self.mumu_folder.get() or "-") is not None
        self.mumu_status.configure(text=tr(self.lang, "mumu_ok" if ok else "mumu_bad"),
                                   foreground="green" if ok else "red")

    def _folder_changed(self) -> None:
        self._check_folder()
        if hasattr(self, "_connection_result"):
            self._invalidate_connection()

    def _toggle_level(self) -> None:
        source = self.source.get()
        self.source_picker.configure(values=[tr(self.lang, key) for key in SOURCE_OPTIONS.values()])
        self.source_picker.set(tr(self.lang, SOURCE_OPTIONS[source]))
        numbered = source == STARS and self.mode.get() in ("normal", "elite")
        self.level_entry.configure(state="normal" if numbered else "disabled")
        if numbered:
            self.level_controls.pack(side="left")
        else:
            self.level_controls.pack_forget()
        self.source_hint.configure(text=tr(self.lang, "source_hint_" + source))

    def _show_party_options(self) -> None:
        if not hasattr(self, "party_row"):
            return
        self.mode_picker.configure(values=[tr(self.lang, mode.value) for mode in Mode])
        self.mode_picker.set(tr(self.lang, self.mode.get()))
        self.party_role_picker.configure(values=[tr(self.lang, "party_role_" + role) for role in ROLES])
        self.party_role_name.set(tr(self.lang, "party_role_" + self.party_role.get()))
        party = self.mode.get() == Mode.PARTY_EXPEDITION.value
        event = self.mode.get() in ("chaos", "conquest")
        if party or event:
            self.energy_row.pack_forget()
            self.build_box.grid_remove() if party else self.build_box.grid()
            self.level_label.grid_remove()
            if party:
                self.party_label.grid(row=3, column=0, columnspan=4, sticky="w")
            else:
                self.party_label.grid_remove()
            self.sources_row.grid_remove()
            self.source_hint.grid_remove()
            self.run_options.grid_remove()
            if party:
                self.party_row.grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))
            else:
                self.party_row.grid_remove()
            self.routine_panel.grid_remove()
            self.party_help.grid(row=5, column=0, columnspan=4, sticky="w", pady=(6, 0))
            self.party_help.configure(text=tr(self.lang, "event_mode_help" if event else "party_help"))
        else:
            if self.mode.get() == Mode.ELITE.value:
                self.energy_row.pack(side="left", padx=(12, 0))
            else:
                self.energy_row.pack_forget()
            self.build_box.grid()
            self.party_label.grid_remove()
            self.level_label.grid()
            self.party_row.grid_remove()
            self.party_help.grid_remove()
            self.sources_row.grid()
            self.source_hint.grid()
            self.run_options.grid()
            self.routine_panel.grid()
        self._toggle_level()

    def _select_party_role(self, _event=None) -> None:
        self.party_role.set(next(role for role in ROLES if tr(self.lang, "party_role_" + role) == self.party_role_name.get()))

    def _show_elite_energy(self) -> None:
        self.elite_energy_picker.configure(values=[tr(self.lang, "elite_energy_auto"), "5", "10", "15"])
        self.elite_energy_name.set(tr(self.lang, "elite_energy_auto") if self.elite_energy.get() == "auto" else self.elite_energy.get())
        self._toggle_elite_energy()

    def _select_elite_energy(self, _event=None) -> None:
        value = self.elite_energy_name.get()
        self.elite_energy.set(value if value in ("5", "10", "15") else "auto")

    def _toggle_elite_energy(self) -> None:
        self.elite_energy_picker.configure(state="readonly" if self.mode.get() == Mode.ELITE.value else "disabled")

    def _show_profile(self) -> None:
        self.profile_picker.configure(values=[tr(self.lang, "profile_" + profile) for profile in PROFILES])
        self.profile_name.set(tr(self.lang, "profile_" + self.build_profile.get()))

    def _set_profile(self, profile: str) -> None:
        self.build_profile.set(profile)
        if self.burn_build.get() != (profile == BURN):
            self.burn_build.set(profile == BURN)
        self._show_profile()

    def _select_profile(self, _event=None) -> None:
        self._set_profile(next(profile for profile in PROFILES if tr(self.lang, "profile_" + profile) == self.profile_name.get()))

    def _legacy_burn_profile(self) -> None:
        if self.burn_build.get():
            self.build_profile.set(BURN)
        elif self.build_profile.get() == BURN:
            self.build_profile.set(CUSTOM)
        self._show_profile()

    def _set_status(self, key: str, color: str, **kwargs) -> None:
        self._status = (key, kwargs, color)
        self._show_status()

    def _show_status(self) -> None:
        key, kwargs, color = self._status
        if key == "report":
            text = render(kwargs["report"], self.lang)
        else:
            text = tr(self.lang, key, **kwargs)
        colors = {"black": INK, "green": "#13704c", "red": "#a12634", "darkorange": "#8a4c0c"}
        self.status.configure(text=text, foreground=colors.get(color, ACCENT))

    def _start(self) -> None:
        if self._preview_active or self._job_running or self._checking_connection:
            return
        self._save_options()
        try:
            request = build_request(self.mode.get(), self.source.get(), self.level.get(),
                                    build=self.build(), loop=self.loop.get(), mumu_folder=self.mumu_folder.get(),
                                    ads=self.ads.get(), provider=self.provider.get(), adb_path=self.adb_path.get(),
                                    device_serial=self.device_serial.get(), elite_energy=self.elite_energy.get(),
                                    party_role=self.party_role.get(), party_runs=self.party_runs.get(),
                                    farm_objective=self.farm_objective.get(), claim_events=self.claim_events.get(),
                                    routine_parts=self._selected_activities())
        except ValueError as e:
            self._set_status(str(e), "red")
            return
        self._show_live_activity()
        if self.auto_scan.get():
            self.account_reader.start(run_after=request)
            return
        self._launch_request(request)

    def _launch_request(self, request):
        self.start.configure(state="disabled")
        self._job_running = True
        self._observation_mode = "run"
        self.preview_button.configure(state="disabled")
        self.check_button.configure(state="disabled")
        self._observation = None
        self._show_observation()
        self._stopping = False
        if self.stop:
            self.stop_button.configure(state="normal")
        self._set_status("running", "black")
        threading.Thread(target=self._worker, args=(request,), daemon=True).start()
        self.root.after(0, self._poll_run)

    def _worker(self, request: RunRequest) -> None:
        try:
            result = self.run(request)
        except Exception as error:
            result = error
        self._run_results.put(result)

    def _poll_run(self) -> None:
        if self._closed:
            return
        try:
            result = self._run_results.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_run)
            return
        if isinstance(result, Exception):
            if self._stopping or isinstance(result, Stopped):
                log.info("Stopped by the user")
                status = ("stopped", {}, "darkorange")
            else:
                log.error("Run failed", exc_info=(type(result), result, result.__traceback__))
                msg = tr(self.lang, result.key, **result.values) if isinstance(result, emulator.EmulatorError) else str(result)
                status = ("error", {"msg": msg}, "red")
        else:
            status = ("report", {"report": result}, "green")
        self._finish(status)

    def _finish(self, status: tuple[str, dict, str]) -> None:
        self._job_running = False
        self._observation = None
        self._show_observation()
        key, kwargs, color = status
        self._set_status(key, color, **kwargs)
        self.start.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.preview_button.configure(state="normal")
        self.check_button.configure(state="normal")

    def _stop(self) -> None:
        self._stopping = True
        self.stop_button.configure(state="disabled")
        self._set_status("stopping", "darkorange")
        if self.account_reader.active:
            self.account_reader.cancel()
        elif self.stop:
            self.stop()

    def _drain_logs(self) -> None:
        if self._closed:
            return
        observation = self.activity.drain()
        if observation is not None and self._job_running:
            self._observation = observation
            self._show_observation()
        self.root.after(200, self._drain_logs)

    def _show_observation(self) -> None:
        self.activity.render(self._observation, self.lang, preview=self._observation_mode == "preview")

    def _show_preview_button(self) -> None:
        self.preview_button.configure(text=tr(self.lang, "preview_stop" if self._preview_active else "preview_start"))

    def _preview(self) -> None:
        if self._preview_active:
            self._preview_stop.set()
            self.preview_button.configure(state="disabled")
            self._set_status("preview_stopping", "black")
            return
        if self._job_running or self._checking_connection:
            return
        connection = self._connection_options()
        request = RunRequest(Mode(self.mode.get()), None, build=self.build(), ads=self.ads.get(),
                             mumu_folder=connection.mumu_folder, provider=connection.provider,
                             adb_path=connection.adb_path, device_serial=connection.device_serial)
        self._preview_stop.clear()
        self._preview_active = True
        self._observation_mode = "preview"
        self._observation = None
        self._show_observation()
        self._show_preview_button()
        self.start.configure(state="disabled")
        self.check_button.configure(state="disabled")
        self._show_live_activity()
        self._set_status("preview_running", "black")
        threading.Thread(target=self._preview_worker, args=(request,), daemon=True).start()
        self.root.after(100, self._poll_preview)

    def _preview_worker(self, request) -> None:
        try:
            watch_preview(request, self._preview_stop, self._preview_results.put)
        except Exception as error:
            if not self._preview_stop.is_set():
                self._preview_results.put(error)
        finally:
            self._preview_results.put(None)

    def _poll_preview(self) -> None:
        if not self._preview_active:
            return
        while True:
            try:
                item = self._preview_results.get_nowait()
            except queue.Empty:
                self.root.after(100, self._poll_preview)
                return
            if item is None:
                self._preview_active = False
                self._show_preview_button()
                self.preview_button.configure(state="normal")
                self.start.configure(state="normal")
                self.check_button.configure(state="normal")
                if self._status[0] != "error":
                    self._set_status("preview_finished", "black")
                return
            if isinstance(item, Exception):
                message = tr(self.lang, item.key, **item.values) if isinstance(item, emulator.EmulatorError) else str(item)
                self._set_status("error", "red", msg=message)
            else:
                self._observation = item
                self._show_observation()
