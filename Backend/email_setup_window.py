"""Local Gmail sender setup. Passwords stay in the local process and .env file."""
from queue import Empty, Queue
import re
import smtplib
from threading import Thread
import tkinter as tk
from tkinter import ttk


def show_gmail_setup(sender, check_and_save):
    root = tk.Tk()
    root.title("CodeCheck AI - Paste Gmail App Password")
    root.resizable(False, False)
    panel = ttk.Frame(root, padding=24)
    panel.grid()
    ttk.Label(panel, text="Set up verification emails", font=("Segoe UI", 16, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
    ttk.Label(panel, text=f"Sender: {sender}").grid(row=1, column=0, columnspan=2, sticky="w")
    ttk.Label(panel, text="Paste the 16-character app password you copied from Google.\n"
              "Dots below confirm that it was pasted.").grid(
        row=2, column=0, columnspan=2, sticky="w", pady=(12, 8))
    password = tk.StringVar()
    entry = ttk.Entry(panel, textvariable=password, show="\u2022", width=40)
    entry.grid(row=3, column=0, sticky="ew", padx=(0, 8))

    def paste():
        entry.delete(0, tk.END)
        entry.event_generate("<<Paste>>")
        entry.focus_set()

    paste_button = ttk.Button(panel, text="Paste", command=paste)
    paste_button.grid(row=3, column=1)
    count = tk.StringVar(value="0 of 16 characters entered")
    ttk.Label(panel, textvariable=count).grid(row=4, column=0, columnspan=2, sticky="w", pady=(5, 12))
    status = tk.StringVar(value="Your app password has not been saved yet.")
    ttk.Label(panel, textvariable=status, wraplength=460).grid(
        row=5, column=0, columnspan=2, sticky="w", pady=(0, 12))
    results = Queue()
    busy = False
    saved = False

    def update_count(*_):
        secret = password.get().replace(" ", "").strip()
        count.set(f"{len(secret)} of 16 characters entered")
        save_button.configure(state="normal" if not busy and not saved and re.fullmatch(r"[A-Za-z0-9]{16}", secret) else "disabled")

    def save():
        nonlocal busy
        secret = password.get().replace(" ", "").strip()
        if busy or saved or not re.fullmatch(r"[A-Za-z0-9]{16}", secret):
            return
        busy = True
        save_button.configure(state="disabled")
        paste_button.configure(state="disabled")
        entry.configure(state="disabled")
        status.set("Checking Gmail sign-in. This may take up to 15 seconds...")
        values = {"SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "465", "SMTP_SECURITY": "ssl",
                  "SMTP_USERNAME": sender, "SMTP_PASSWORD": secret, "SMTP_FROM": sender}

        def worker():
            try:
                check_and_save(values)
            except smtplib.SMTPAuthenticationError:
                results.put((False, "Google rejected the login. Check that this app password belongs to the sender shown above."))
            except (OSError, smtplib.SMTPException, ValueError):
                results.put((False, "Could not check or save the sender. Check your internet connection and try again."))
            except Exception:
                results.put((False, "Setup could not complete. Return to Codex with this message; keep the password private."))
            else:
                results.put((True, "Settings saved. Return to Codex and say SAVED to restart the backend."))

        Thread(target=worker, daemon=True).start()
        root.after(100, poll)

    def poll():
        nonlocal busy, saved
        try:
            saved, message = results.get_nowait()
        except Empty:
            root.after(100, poll)
            return
        busy = False
        status.set(message)
        if saved:
            password.set("")
            count.set("Sender checked and settings saved")
        else:
            entry.configure(state="normal")
            paste_button.configure(state="normal")
            update_count()
            entry.focus_set()

    save_button = ttk.Button(panel, text="Check & Save", command=save, state="disabled")
    save_button.grid(row=6, column=0, sticky="w")
    ttk.Button(panel, text="Close", command=root.destroy).grid(row=6, column=1)
    ttk.Label(panel, text="Saved in Backend/.env on this PC; excluded from Git.\n"
              "This setup does not change payment plans or read your inbox.", foreground="#555555").grid(
        row=7, column=0, columnspan=2, sticky="w", pady=(16, 0))
    password.trace_add("write", update_count)
    root.bind("<Return>", lambda _: save())
    root.attributes("-topmost", True)
    root.after(1500, lambda: root.attributes("-topmost", False))
    entry.focus_set()
    root.mainloop()
