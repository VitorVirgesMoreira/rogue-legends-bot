"""Native account settings, local history and read-only progression advice."""

from dataclasses import asdict, replace
from datetime import datetime
import tkinter as tk
from tkinter import ttk

from roguebot.build import STRATEGIES
from roguebot.combat_context import Loadout
from roguebot.desktop_theme import CANVAS, style_text
from roguebot.farming import OBJECTIVES
from roguebot.i18n import TEXTS, tr
from roguebot.metrics import History
from roguebot.pet_upgrades import Pet, optimize, supported
from roguebot.progression_plan import recommend
from roguebot.account_state import scan_history

RARITIES = ("common", "rare", "epic", "legendary", "mythic")


def pairs(value, *, numbers=False):
    result = {}
    for entry in value.split(","):
        if not entry.strip():
            continue
        name, separator, number = entry.strip().partition("=")
        if not separator or not name.strip():
            raise ValueError("bad_loadout")
        result[name.strip()] = float(number) if numbers else int(number)
    return result


class AccountDialog:
    def __init__(self, app, *, page="inventory"):
        self.app, self.lang = app, app.lang
        self.window = tk.Toplevel(app.root)
        self.window.title(tr(self.lang, "account_title"))
        self.window.configure(background=CANVAS)
        self.window.transient(app.root)
        self.window.minsize(720, 610)
        self.window.geometry("820x670")
        body = ttk.Frame(self.window, padding=(22, 14))
        body.pack(fill="both", expand=True)
        toolbar = ttk.Frame(body)
        toolbar.pack(fill="x", pady=(0, 8))
        heading = ttk.Frame(toolbar)
        heading.pack(side="left")
        ttk.Label(heading, text=tr(self.lang, "account_heading"), style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(heading, text=tr(self.lang, "account_intro"), style="Hint.TLabel",
                  wraplength=410).pack(anchor="w", pady=(2, 0))
        self.scan_button = ttk.Button(toolbar, text=tr(self.lang, "account_scan_short"), command=self._scan)
        self.scan_button.pack(side="right")
        self.scan_status = ttk.Label(body, wraplength=665, style="Hint.TLabel")
        self.scan_status.pack(fill="x", pady=(0, 5))

        footer = ttk.Frame(body)
        footer.pack(side="bottom", fill="x", pady=(10, 0))
        self.error = ttk.Label(footer, foreground="#a12634", wraplength=665)
        self.error.pack(fill="x")
        buttons = ttk.Frame(footer)
        buttons.pack(fill="x")
        self.cancel_scan_button = ttk.Button(buttons, text=tr(self.lang, "account_cancel_scan"), state="disabled",
                                             command=self.app.account_reader.cancel)
        self.cancel_scan_button.pack(side="left")
        ttk.Button(buttons, text=tr(self.lang, "account_close"), command=self._close).pack(side="right")
        self.save_button = ttk.Button(buttons, text=tr(self.lang, "save"), command=self._save, style="Primary.TButton")
        self.save_button.pack(side="right", padx=8)

        tabs = ttk.Notebook(body)
        self.notebook = tabs
        tabs.pack(fill="both", expand=True)
        tabs.enable_traversal()
        self.tabs = {}
        for key in ("inventory", "pet_plan", "planner", "history", "strategy", "loadout"):
            frame = ttk.Frame(tabs, padding=12)
            tabs.add(frame, text=tr(self.lang, key + "_tab"))
            frame.columnconfigure(1, weight=1)
            self.tabs[key] = frame
        self.values = {}
        loadout = asdict(app.loadout)
        self._help(self.tabs["loadout"], "loadout_help")
        fields = ("hero", "hero_stars", "weapon", "weapon_rarity", "companions", "pets", "mounts",
                  "sentinels", "equipment", "tree_skills", "game_version", "stats")
        equipment = ttk.Frame(self.tabs["loadout"])
        equipment.grid(row=1, column=0, columnspan=2, sticky="ew")
        equipment.columnconfigure((0, 1, 2), weight=1, uniform="fields")
        for index, name in enumerate(fields):
            value = loadout[name]
            if name == "stats":
                value = ", ".join(f"{k}={v}" for k, v in value)
            elif isinstance(value, (list, tuple)):
                value = ", ".join(value)
            label = "pets_config" if name == "pets" else name
            field = ttk.Frame(equipment)
            field.grid(row=index // 3, column=index % 3, sticky="ew", padx=(0, 12), pady=(0, 7))
            ttk.Label(field, text=tr(self.lang, label)).pack(anchor="w")
            if name == "weapon_rarity":
                self.rarity = self._picker(field, ("unknown", *RARITIES), value or "unknown", "rarity_", stacked=True)
            else:
                self.values[name] = tk.StringVar(value=value)
                ttk.Entry(field, textvariable=self.values[name], width=20).pack(fill="x")
        ttk.Label(self.tabs["loadout"], text=tr(self.lang, "stats_help"), wraplength=700).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        frame = self.tabs["strategy"]
        self._help(frame, "strategy_help")
        self.strategy = self._choice(frame, 1, "strategy", STRATEGIES, app.strategy.get(), "strategy_")
        self.objective = self._choice(frame, 2, "farm_objective", OBJECTIVES, app.farm_objective.get(), "objective_")
        self.claims = tk.BooleanVar(value=app.claim_events.get())
        self.auto_scan = tk.BooleanVar(value=app.auto_scan.get())
        self.use_scan_strategy = tk.BooleanVar(value=app.use_scan_strategy.get())
        ttk.Checkbutton(frame, text=tr(self.lang, "claim_events"), variable=self.claims).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=12)
        ttk.Checkbutton(frame,text=tr(self.lang,"scan_on_start"),variable=self.auto_scan).grid(
            row=4,column=0,columnspan=2,sticky="w",pady=8)
        ttk.Checkbutton(frame,text=tr(self.lang,"scan_use_strategy"),variable=self.use_scan_strategy).grid(
            row=5,column=0,columnspan=2,sticky="w",pady=8)
        frame = self.tabs["history"]
        ttk.Button(frame, text=tr(self.lang, "refresh_history"), command=self._history).pack(anchor="w", pady=(0, 8))
        self.history = tk.Text(frame, wrap="word", width=75, height=20)
        style_text(self.history)
        self.history.pack(fill="both", expand=True)
        self._history()
        frame = self.tabs["planner"]
        self._help(frame, "planner_help")
        for row, name in enumerate(("chapter", "elite_chapter", "hero_levels", "resources"), 1):
            value = app.planner_facts.get(name, "")
            if isinstance(value, dict):
                value = ", ".join(f"{k}={v}" for k, v in value.items())
            self._entry(frame, row, name, name, value)
        ttk.Button(frame, text=tr(self.lang, "show_recommendations"), command=self._plan).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=8)
        self.plan = tk.Text(frame, wrap="word", width=75, height=12)
        style_text(self.plan)
        self.plan.grid(row=6, column=0, columnspan=2, sticky="nsew")
        frame.rowconfigure(6, weight=1)
        frame = self.tabs["pet_plan"]
        self._help(frame, "pet_plan_help")
        self.pet_button = ttk.Button(frame, text=tr(self.lang, "account_pet_scan"), command=self._scan_pets,
                                     style="Primary.TButton")
        self.pet_button.grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.pet_plan = tk.Text(frame, wrap="word", width=75, height=12)
        style_text(self.pet_plan)
        self.pet_plan.grid(row=2, column=0, columnspan=2, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, command=self.pet_plan.yview)
        scrollbar.grid(row=2, column=2, sticky="ns")
        self.pet_plan.configure(yscrollcommand=scrollbar.set)
        frame.rowconfigure(2, weight=1)
        self.show_pet_plan()
        frame = self.tabs["inventory"]
        self.inventory = tk.Text(frame, wrap="word", width=75, height=20)
        style_text(self.inventory)
        self.inventory.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(frame, command=self.inventory.yview)
        scrollbar.pack(side="right", fill="y")
        self.inventory.configure(yscrollcommand=scrollbar.set)
        self.show_inventory()
        self.window.bind("<Escape>", lambda _: self._close())
        self.window.protocol("WM_DELETE_WINDOW", self._close)
        self.show(page)

    def show(self, page):
        self.notebook.select(self.tabs[page])
        self.window.lift()

    def _close(self):
        if self.app.account_reader.active and self.app.account_reader.dialog is self:
            self.app.account_reader.cancel()
        self.window.destroy()

    def _scan(self):
        self.app.auto_scan.set(self.auto_scan.get())
        self.app.use_scan_strategy.set(self.use_scan_strategy.get())
        self.app.account_reader.start(dialog=self)

    def _scan_pets(self):
        self.app.account_reader.start(dialog=self, pets_only=True)

    def show_pet_plan(self):
        snapshot = self.app.planner_facts.get("pet_collection", {})
        lines = []
        if snapshot:
            pets = [Pet(**row) for row in snapshot["pets"]]
            food = snapshot["food"]
            if type(food) is int:
                plan = optimize(pets, food)
                left = food - sum(step.food for step in plan)
                gains = {stat: sum(getattr(step, stat) for step in plan)
                         for stat in ("hp", "atk", "defense", "skills")}
                lines.append(tr(self.lang, "pet_plan_total", food=food, left=left, **gains))
                lines.extend(tr(self.lang, "pet_plan_step", **asdict(step)) for step in plan)
                if not plan:
                    lines.append(tr(self.lang, "pet_plan_unaffordable"))
            else:
                lines.append(tr(self.lang, "pet_plan_no_food"))
            if not snapshot["complete"] or any(not supported(pet) for pet in pets):
                lines.append(tr(self.lang, "pet_plan_partial"))
            lines.append(tr(self.lang, "pet_inventory_summary", count=len(pets),
                            at=snapshot["at"][:16].replace("T", " ")))
            lines.extend(tr(self.lang, "pet_inventory_row", name=pet.name,
                            level=pet.level if pet.level is not None else "—",
                            copies=pet.copies if pet.copies is not None else "—") for pet in pets)
        self.pet_plan.configure(state="normal")
        self.pet_plan.delete("1.0", "end")
        self.pet_plan.insert("1.0", "\n\n".join(lines) or tr(self.lang, "pet_plan_empty"))
        self.pet_plan.configure(state="disabled")

    def fill_from_account(self):
        data = asdict(self.app.loadout)
        for name,var in self.values.items():
            value = data.get(name,self.app.planner_facts.get(name,""))
            if isinstance(value,dict):
                value = ", ".join(f"{k}={v}" for k,v in value.items())
            elif name == "stats":
                value = ", ".join(f"{k}={v}" for k,v in value)
            elif isinstance(value,(list,tuple)):
                value = ", ".join(value)
            var.set("" if value is None else value)
        self.rarity[0].set(tr(self.lang,"rarity_"+(data["weapon_rarity"] or "unknown")))
        self.strategy[0].set(tr(self.lang,"strategy_"+self.app.strategy.get()))
        self.show_inventory()

    def show_inventory(self):
        facts = self.app.planner_facts
        sections = (
            ("inventory_achievements", [
                f"{tr(self.lang, name)} · {facts[name]}" for name in ("chapter", "elite_chapter")
                if facts.get(name) is not None
            ] + [f"{name} · {tr(self.lang, 'inventory_level', level=level)}"
                 for name, level in sorted(facts.get("hero_levels", {}).items())]),
            ("inventory_equipped", [
                f"{item['name']} · {tr(self.lang, 'rarity_' + item['rarity'])} · "
                + tr(self.lang, "inventory_level", level=item["level"] or "—")
                for item in facts.get("equipped_items", ())
            ]),
            ("inventory_bag", [f"{name} · {count}" for name, count in facts.get("bag_items", ())]),
        )
        lines = [tr(self.lang, "inventory_help")]
        lines.extend("\n".join((tr(self.lang, label), *(rows or [tr(self.lang, "inventory_pending")])))
                     for label, rows in sections)
        self.inventory.configure(state="normal")
        self.inventory.delete("1.0", "end")
        self.inventory.insert("1.0", "\n\n".join(lines))
        self.inventory.configure(state="disabled")

    def _help(self, frame, key):
        ttk.Label(frame, text=tr(self.lang, key), wraplength=700, justify="left").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

    def _entry(self, frame, row, name, label, value):
        ttk.Label(frame, text=tr(self.lang, label)).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 12))
        variable = tk.StringVar(value="" if value is None else value)
        self.values[name] = variable
        ttk.Entry(frame, textvariable=variable, width=48).grid(row=row, column=1, sticky="ew", pady=4)

    def _choice(self, frame, row, label, choices, selected, prefix):
        ttk.Label(frame, text=tr(self.lang, label)).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=8)
        return self._picker(frame, choices, selected, prefix, row=row)

    def _picker(self, frame, choices, selected, prefix, *, row=0, stacked=False):
        names = {tr(self.lang, prefix + key): key for key in choices}
        variable = tk.StringVar(value=tr(self.lang, prefix + selected))
        picker = ttk.Combobox(frame, state="readonly", textvariable=variable, values=list(names), width=22)
        if stacked:
            picker.pack(fill="x")
        else:
            picker.grid(row=row, column=1, sticky="ew", pady=8)
        return variable, names

    def _loadout(self):
        data = {name: self.values[name].get().strip() for name in Loadout.__dataclass_fields__
                if name not in ("weapon_rarity", "tree_skills_partial")}
        rarity = self.rarity[1][self.rarity[0].get()]
        data["weapon_rarity"] = "" if rarity == "unknown" else rarity
        data["hero_stars"] = int(data["hero_stars"])
        for name in ("companions", "pets", "mounts", "sentinels", "equipment", "tree_skills"):
            data[name] = [item.strip() for item in data[name].split(",") if item.strip()]
        data["tree_skills_partial"] = (self.app.loadout.tree_skills_partial and
                                       tuple(data["tree_skills"]) == self.app.loadout.tree_skills)
        data["stats"] = pairs(data["stats"], numbers=True)
        return Loadout.from_dict(data)

    def _facts(self):
        values = {name: self.values[name].get().strip() for name in ("chapter", "elite_chapter", "hero_levels", "resources")}
        for name in ("chapter", "elite_chapter"):
            values[name] = int(values[name]) if values[name] else None
            if values[name] is not None and values[name] < 0:
                raise ValueError("bad_loadout")
        for name in ("hero_levels", "resources"):
            values[name] = pairs(values[name])
            if any(v < 0 for v in values[name].values()):
                raise ValueError("bad_loadout")
        return values

    def _history(self):
        mode_keys = {"dojo": "part_dojo", "raid": "part_raid", "party": "party_expedition"}
        translations = TEXTS[self.lang]
        lines = []
        for r in History().summary():
            mode = translations.get(mode_keys.get(r["mode"], r["mode"]), r["mode"])
            profile = translations.get("profile_" + r["profile"], r["profile"])
            equipment = r["loadout"]
            strategy = str(r["build_config"].get("strategy", "balanced"))
            lines.append(f"{mode} · {r['level'] or '—'} · {profile} · {r['wins']}/{r['runs']} · "
                         f"{r['seconds_per_run']:.0f}s · {r['mean_damage'] if r['mean_damage'] is not None else '—'}\n"
                         f"  {equipment.get('hero') or '—'} / {equipment.get('weapon') or '—'} · "
                         f"{translations.get('strategy_' + strategy, strategy)} · {equipment.get('game_version') or '—'}")
            energy = r["rewards_per_energy"].get("gold")
            minute = r["rewards_per_minute"].get("gold")
            if energy is not None or minute is not None:
                lines[-1] += "\n  " + tr(self.lang, "history_gold_rate",
                    energy="—" if energy is None else f"{energy:.1f}",
                    minute="—" if minute is None else f"{minute:.1f}")
        self.history.configure(state="normal")
        self.history.delete("1.0", "end")
        scans = []
        for row in scan_history():
            try:
                at = datetime.fromisoformat(row["at"]).astimezone().strftime("%Y-%m-%d %H:%M %z")
            except (ValueError, TypeError, KeyError):
                continue
            data = row.get("loadout")
            if not isinstance(data, dict):
                continue
            scans.append(f"{at} · {data.get('hero') or '—'} · {data.get('weapon') or '—'}")
        content = (tr(self.lang,"history_columns")+"\n\n"+"\n\n".join(lines)) if lines else tr(self.lang,"history_empty")
        if scans:
            content += "\n\n"+tr(self.lang,"scan_history_title")+"\n"+"\n".join(scans[-10:])
        self.history.insert("1.0",content)
        self.history.configure(state="disabled")

    def _plan(self):
        try:
            facts = self._facts()
            build = replace(self.app.build(), loadout=self._loadout())
            rows = recommend(build, chapter=facts["chapter"], elite=facts["elite_chapter"],
                             hero_levels=facts["hero_levels"], resources=facts["resources"])
            lines = []
            for r in rows:
                line = f"{r.target}: {tr(self.lang, 'advice_' + r.category)}\n{tr(self.lang, 'reason_' + r.category)}"
                if r.costs:
                    costs = ", ".join(f"{amount} {name}" for name, amount in r.costs)
                    balance = "unknown" if r.affordable is None else "sufficient" if r.affordable else "insufficient"
                    line += "\n" + tr(self.lang, "plan_costs", costs=costs, balance=tr(self.lang, balance))
                lines.append(line + "\n" + r.source)
        except (ValueError, TypeError):
            self.error.configure(text=tr(self.lang, "bad_loadout"))
            return
        self.error.configure(text="")
        self.plan.configure(state="normal")
        self.plan.delete("1.0", "end")
        self.plan.insert("1.0", "\n\n".join(lines) or tr(self.lang, "planner_no_data"))
        self.plan.configure(state="disabled")

    def _save(self):
        try:
            loadout, facts = self._loadout(), self._facts()
        except (ValueError, TypeError):
            self.error.configure(text=tr(self.lang, "bad_loadout"))
            return
        self.app.loadout = loadout
        self.app.planner_facts.update(facts)
        self.app.strategy.set(self.strategy[1][self.strategy[0].get()])
        self.app.farm_objective.set(self.objective[1][self.objective[0].get()])
        self.app.claim_events.set(self.claims.get())
        self.app.auto_scan.set(self.auto_scan.get())
        self.app.use_scan_strategy.set(self.use_scan_strategy.get())
        self.app._save_options()
        self.window.destroy()
