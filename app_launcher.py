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
