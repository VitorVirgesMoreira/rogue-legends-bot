"""Main-thread application of account scans; workers never touch Tk widgets."""

from dataclasses import replace
import queue
import threading

from roguebot.account_scan import scan_account, AccountScanError
from roguebot.account_state import save_snapshot
from roguebot.device import Stopped
from roguebot.emulator import EmulatorError
from roguebot.i18n import tr


class AccountScanCoordinator:
    def __init__(self, app):
        self.app = app
        self.active = False
        self.stop = threading.Event()
        self.messages = queue.Queue()
        self.dialog = None
        self.after = None

    def start(self, *, dialog=None, run_after=None, pets_only=False):
        app = self.app
        if self.active or app._job_running or app._preview_active or app._checking_connection:
            return False
        self.connection = app._connection_options()
        self.dialog, self.after = dialog, run_after
        self.pets_only = pets_only
        self.stop.clear()
        self.active = app._job_running = True
        app.start.configure(state="disabled")
        app.preview_button.configure(state="disabled")
        app.check_button.configure(state="disabled")
        app.stop_button.configure(state="normal")
        app._set_status("scan_running", "black", section=tr(app.lang,"scan_section_prepare"))
        if dialog:
            dialog.scan_status.configure(
                text=tr(dialog.lang, "scan_running", section=tr(dialog.lang, "scan_section_prepare")))
            dialog.scan_button.configure(state="disabled")
            dialog.save_button.configure(state="disabled")
            dialog.pet_button.configure(state="disabled")
            dialog.cancel_scan_button.configure(state="normal")
        def work():
            try:
                options = {"pets_only": True} if pets_only else {}
                result = scan_account(self.connection,self.stop,lambda section:self.messages.put(("progress",section)),
                                      fresh=run_after is None,launch=run_after is not None, **options)
            except Exception as exc:
                result = exc
            self.messages.put(("result",result))
        threading.Thread(target=work,daemon=True).start()
        app.root.after(100,self.poll)
        return True

    def cancel(self):
        self.stop.set()

    def _dialog_alive(self):
        return self.dialog is not None and self.dialog.window.winfo_exists()

    def poll(self):
        app = self.app
        if app._closed:
            return
        try:
            kind,value = self.messages.get_nowait()
        except queue.Empty:
            app.root.after(100,self.poll)
            return
        if kind == "progress":
            section = tr(app.lang,"scan_section_"+value)
            app._set_status("scan_running","black",section=section)
            if self._dialog_alive():
                self.dialog.scan_status.configure(text=tr(self.dialog.lang,"scan_running",section=section))
            app.root.after(50,self.poll)
            return
        self.active = False
        if self._dialog_alive():
            self.dialog.scan_button.configure(state="normal")
            self.dialog.save_button.configure(state="normal")
            self.dialog.pet_button.configure(state="normal")
            self.dialog.cancel_scan_button.configure(state="disabled")
        if self.stop.is_set() or isinstance(value,Stopped):
            app._finish(("stopped",{},"darkorange"))
            if self._dialog_alive():
                self.dialog.scan_status.configure(text=tr(self.dialog.lang, "stopped"))
            return
        if self.connection != app._connection_options():
            value = AccountScanError("scan_connection_changed")
        if isinstance(value,Exception):
            if self.after and isinstance(value,AccountScanError) and str(value)=="scan_in_adventure":
                app._finish(("idle",{},"black"))
                app._launch_request(self.after)  # the normal runner owns existing-adventure recovery
                return
            message = (tr(app.lang,value.key,**value.values) if isinstance(value,EmulatorError) else
                       tr(app.lang,str(value)) if isinstance(value,AccountScanError) else str(value))
            app._finish(("error",{"msg":message},"red"))
            if self._dialog_alive():
                self.dialog.scan_status.configure(text=message)
            return
        app.loadout, app.planner_facts = value.merge(app.loadout,app.planner_facts,previous_account=app.scanned_account)
        app.scanned_account = value.account
        app.scan_at = value.at
        if app.use_scan_strategy.get() and value.reason != "scan_strategy_unknown":
            app._set_profile(value.profile)
            app.strategy.set(value.strategy)
        app._save_options()
        if not self.pets_only:
            try:
                save_snapshot(value)
            except OSError:
                value.warnings.append("scan_save_failed")
        count = len(value.loadout)
        message = tr(app.lang,"scan_complete",count=count)
        if value.warnings:
            message += " " + " ".join(tr(app.lang,key) for key in dict.fromkeys(value.warnings))
        app._finish(("scan_complete",{"count":count},"green"))
        if self._dialog_alive():
            self.dialog.fill_from_account()
            self.dialog.scan_status.configure(text=message)
            self.dialog._history()
            self.dialog.show_pet_plan()
        if self.after:
            app._launch_request(replace(self.after,build=app.build()))
