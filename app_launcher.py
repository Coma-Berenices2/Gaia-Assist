"""Desktop mode selection, separate from either calculation pipeline."""
import tkinter as tk
from tkinter import ttk


def choose_startup_mode(root):
    """Return an explicit mode choice, or None when the chooser is closed."""
    root.title("Gaia Assist — Choose a Mode")
    root.geometry("620x340")
    root.minsize(540, 320)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    choice = tk.StringVar(root, value="")
    frame = ttk.Frame(root, padding=28)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)
    ttk.Label(frame, text="Welcome to Gaia Assist", font=("Segoe UI", 20, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w")
    ttk.Label(frame, text="Choose how you want to explore the data.", font=("Segoe UI", 11)).grid(
        row=1, column=0, columnspan=2, sticky="w", pady=(8, 24))
    for column, mode, description in (
        (0, "Explorer", "A simple, friendly interface for looking up objects and exploring their properties."),
        (1, "Scientist", "Compare temperature estimates, inspect uncertainties and assumptions, and review classifications."),
    ):
        card = ttk.LabelFrame(frame, text=mode, padding=16)
        card.grid(row=2, column=column, sticky="nsew", padx=(0, 8) if column == 0 else (8, 0))
        ttk.Label(card, text=description, wraplength=225, justify="left").pack(anchor="w", pady=(0, 16))
        button = ttk.Button(card, text=mode, command=lambda value=mode: choice.set(value))
        button.pack(anchor="w")
        button.bind("<Return>", lambda _event, target=button: target.invoke())
        if column == 0:
            button.focus_set()
    root.protocol("WM_DELETE_WINDOW", lambda: choice.set("cancel"))
    try:
        root.wait_variable(choice)
        return choice.get() if choice.get() in ("Explorer", "Scientist") else None
    finally:
        frame.destroy()
        root.rowconfigure(0, weight=0)
        root.protocol("WM_DELETE_WINDOW", root.destroy)


class DesktopSession:
    """Keep each mode alive while showing only the selected workspace."""
    def __init__(self, root):
        self.root = root
        self.apps = {}
        self.current = None

    def show(self, mode):
        import importlib
        from tkinter import messagebox
        if mode not in self.apps:
            window = None
            try:
                module = importlib.import_module("Main" if mode == "Explorer" else "Main_temperature")
                module.load_desktop_gui()
                window = tk.Toplevel(self.root)
                window.withdraw()
                app = module.GaiaAssistApp(window)
                other = "Scientist" if mode == "Explorer" else "Explorer"
                bar = ttk.Frame(window, padding=(24, 6))
                bar.grid(row=5, column=0, sticky="ew")
                ttk.Label(bar, text=f"Mode: {mode}").pack(side="left")
                ttk.Button(bar, text=f"Switch to {other}",
                           command=lambda: self.show(other)).pack(side="right")
                window.title(f"Gaia Assist — {mode}")
                window.protocol("WM_DELETE_WINDOW", self.close)
                self.apps[mode] = app
            except Exception as error:
                if window is not None:
                    window.destroy()
                messagebox.showerror("Mode could not be opened", str(error), parent=self.root)
                return False
        if self.current:
            self.apps[self.current].root.withdraw()
        self.current = mode
        self.apps[mode].root.deiconify()
        self.apps[mode].root.lift()
        return True

    def close(self):
        import sys
        import time
        scientist = self.apps.get("Scientist")
        if scientist:
            scientist.query_cancel.set()
            scientist.query_generation += 1
        network = sys.modules.get("scientist_network")
        if network:
            network.cancel_all()
        deadline = time.monotonic() + 4
        def finish():
            if network and network.active_queries() and time.monotonic() < deadline:
                self.root.after(50, finish)
            else:
                self.root.destroy()
        finish()


def run_desktop(initial_mode=None):
    root = tk.Tk()
    session = DesktopSession(root)
    mode = initial_mode
    while True:
        mode = mode or choose_startup_mode(root)
        if mode is None:
            root.destroy()
            return
        if session.show(mode):
            break
        mode = None
    root.withdraw()
    root.mainloop()
