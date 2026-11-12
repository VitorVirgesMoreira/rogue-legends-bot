"""Activity panel with bounded log buffering and localized observations."""

import logging
from pathlib import Path
import queue
import tkinter as tk
from tkinter import ttk

from roguebot.desktop_theme import style_text
from roguebot.i18n import tr
from roguebot.observation import Observation

CHANGELOG = Path(__file__).parent.parent / "CHANGELOG.md"
LOG_VIEW_LINES = 2000
LOG_BATCH_SIZE = 200


class _QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self.q = q

    def emit(self, record: logging.LogRecord) -> None:
        if hasattr(record, "observation"):
            self._enqueue(record.observation)
        self._enqueue(self.format(record))

    def _enqueue(self, item) -> None:
        try:
            self.q.put_nowait(item)
        except queue.Full:
            # Keep recent messages without blocking the bot when the UI falls behind.
            try:
                self.q.get_nowait()
            except queue.Empty:
                pass
            try:
                self.q.put_nowait(item)
            except queue.Full:
                pass


class ActivityPanel(ttk.Frame):
    def __init__(self, parent, logger: logging.Logger):
        super().__init__(parent)
        self.changelog_shown = False
        monitor = ttk.Frame(self)
        monitor.pack(fill="x", pady=(12, 10))
        self.recognized = ttk.Label(monitor, wraplength=760)
        self.recognized.grid(row=0, column=0, sticky="w")
        self.next_action = ttk.Label(monitor, wraplength=760)
        self.next_action.grid(row=1, column=0, sticky="w")
        self.decision_reason = ttk.Label(monitor, wraplength=760)
        self.decision_reason.grid(row=2, column=0, sticky="w")

        self.log_heading = ttk.Label(self, style="Section.TLabel")
        self.log_heading.pack(anchor="w", pady=(0, 6))
        activity_stream = ttk.Frame(self)
        activity_stream.pack(fill="both", expand=True)
        activity_stream.columnconfigure(0, weight=1)
        activity_stream.rowconfigure(0, weight=1)
        self.log_box = ttk.Frame(activity_stream)
        self.log_box.grid(row=0, column=0, sticky="nsew")
        self.log_view = tk.Text(self.log_box, height=7, width=1, state="disabled", wrap="word")
        style_text(self.log_view, log=True)
        self.log_view.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(self.log_box, command=self.log_view.yview)
        scroll.pack(side="right", fill="y")
        self.log_view.configure(yscrollcommand=scroll.set)
        self.changelog = tk.Text(activity_stream, height=6, width=1, wrap="word")
        style_text(self.changelog)
        self.changelog.insert("1.0", CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else "")
        self.changelog.configure(state="disabled")

        self._messages: queue.Queue[str | Observation] = queue.Queue(maxsize=LOG_VIEW_LINES)
        self._logger = logger
        self._handler = _QueueHandler(self._messages)
        self._handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
        self._logger.addHandler(self._handler)

    def close(self) -> None:
        self._logger.removeHandler(self._handler)
        self._handler.close()

    def show_changelog(self, show: bool) -> None:
        self.changelog_shown = show
        if show:
            self.log_box.grid_remove()
            self.changelog.grid(row=0, column=0, sticky="nsew")
        else:
            self.changelog.grid_remove()
            self.log_box.grid()

    def translate_heading(self, lang: str) -> None:
        key = "changelog" if self.changelog_shown else "activity_log"
        self.log_heading.configure(text=tr(lang, key))

    def drain(self) -> Observation | None:
        observation, lines = None, []
        for _ in range(LOG_BATCH_SIZE):
            try:
                item = self._messages.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, Observation):
                observation = item
            else:
                lines.append(item)
        if lines:
            self.append(lines)
        return observation

    def append(self, lines: list[str]) -> None:
        self.log_view.configure(state="normal")
        self.log_view.insert("end", "\n".join(lines) + "\n")
        self.log_view.delete("1.0", f"end-{LOG_VIEW_LINES}l")
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def render(self, view: Observation | None, lang: str, *, preview: bool) -> None:
        if view is None:
            self.recognized.configure(text=tr(lang, "observation_empty"))
            self.next_action.configure(text="")
            self.decision_reason.configure(text="")
            return
        source = tr(lang, "read_" + view.source)
        screen = tr(lang, "screen_" + view.screen)
        evidence = f" · {view.score:.0%}" if view.score is not None else ""
        stable = f" · {tr(lang, 'observation_reads', count=view.stable)}" if view.stable else ""
        self.recognized.configure(text=tr(lang, "observation_screen", screen=screen, source=source+evidence+stable))
        content = tr(lang, "part_"+view.detail) if view.screen == "routine" and view.detail else view.detail
        detail = " — " + content if content else ""
        action_key = "observation_suggestion" if preview else "observation_action"
        self.next_action.configure(text=tr(lang, action_key, action=tr(lang, "action_"+view.action))+detail)
        self.decision_reason.configure(text=tr(lang, view.reason))
