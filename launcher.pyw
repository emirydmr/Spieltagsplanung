"""Spieltagsplaner – GUI Launcher.

Startet den Server und öffnet den Browser.
Zeigt ein kleines Fenster mit Logo und Status.
Wird als .pyw ausgeführt (kein Terminal-Fenster).
"""

import os
import sys
import subprocess
import threading
import webbrowser
import socket
import time
import signal
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────
ROOT = Path(__file__).parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
LOGO_PATH = ROOT / "ui" / "assets" / "wfv-logo.jpg"
ICO_PATH = ROOT / "ui" / "assets" / "app.ico"
URL = "http://localhost:8000/app"

# ─── Tkinter GUI ──────────────────────────────────────────────
import tkinter as tk
from tkinter import font as tkfont

class LauncherApp:
    def __init__(self):
        self.server_process = None
        self.running = False

        # ── Window ──
        self.root = tk.Tk()
        self.root.title("Spieltagsplaner")
        self.root.geometry("420x340")
        self.root.resizable(False, False)
        self.root.configure(bg="#ffffff")

        # Icon
        if ICO_PATH.exists():
            try:
                self.root.iconbitmap(str(ICO_PATH))
            except Exception:
                pass

        # Center on screen
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 420) // 2
        y = (self.root.winfo_screenheight() - 340) // 2
        self.root.geometry(f"420x340+{x}+{y}")

        # Fonts
        title_font = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        subtitle_font = tkfont.Font(family="Segoe UI", size=9)
        status_font = tkfont.Font(family="Segoe UI", size=10)
        btn_font = tkfont.Font(family="Segoe UI", size=10, weight="bold")

        # ── Logo ──
        self.logo_image = None
        if LOGO_PATH.exists():
            try:
                from tkinter import PhotoImage
                # Use PIL if available, otherwise skip
                try:
                    from PIL import Image, ImageTk
                    img = Image.open(str(LOGO_PATH))
                    img = img.resize((180, 135), Image.LANCZOS)
                    self.logo_image = ImageTk.PhotoImage(img)
                except ImportError:
                    pass
            except Exception:
                pass

        if self.logo_image:
            logo_label = tk.Label(self.root, image=self.logo_image, bg="#ffffff")
            logo_label.pack(pady=(20, 5))
        else:
            # Fallback: text logo
            tk.Label(self.root, text="WFV", font=tkfont.Font(family="Segoe UI", size=32, weight="bold"),
                     fg="#c41230", bg="#ffffff").pack(pady=(20, 0))

        # ── Title ──
        tk.Label(self.root, text="Spieltagsplaner", font=title_font,
                 fg="#1a1a1a", bg="#ffffff").pack(pady=(5, 0))
        tk.Label(self.root, text="Bezirk Franken · Jugend",
                 font=subtitle_font, fg="#888888", bg="#ffffff").pack(pady=(0, 15))

        # ── Status ──
        self.status_frame = tk.Frame(self.root, bg="#ffffff")
        self.status_frame.pack(fill="x", padx=40)

        self.status_dot = tk.Canvas(self.status_frame, width=12, height=12,
                                     bg="#ffffff", highlightthickness=0)
        self.status_dot.pack(side="left", padx=(0, 8))
        self._draw_dot("#cccccc")

        self.status_label = tk.Label(self.status_frame, text="Bereit zum Starten",
                                      font=status_font, fg="#666666", bg="#ffffff",
                                      anchor="w")
        self.status_label.pack(side="left", fill="x")

        # ── Buttons ──
        btn_frame = tk.Frame(self.root, bg="#ffffff")
        btn_frame.pack(pady=(20, 15))

        self.btn_start = tk.Button(
            btn_frame, text="  Starten  ", font=btn_font,
            bg="#c41230", fg="#ffffff", activebackground="#a00f28",
            activeforeground="#ffffff", relief="flat", cursor="hand2",
            padx=20, pady=6, command=self.on_start,
        )
        self.btn_start.pack(side="left", padx=5)

        self.btn_browser = tk.Button(
            btn_frame, text="  Browser öffnen  ", font=btn_font,
            bg="#e5e7eb", fg="#333333", activebackground="#d1d5db",
            relief="flat", cursor="hand2", padx=12, pady=6,
            command=self.open_browser, state="disabled",
        )
        self.btn_browser.pack(side="left", padx=5)

        self.btn_stop = tk.Button(
            btn_frame, text="  Beenden  ", font=btn_font,
            bg="#e5e7eb", fg="#666666", activebackground="#d1d5db",
            relief="flat", cursor="hand2", padx=12, pady=6,
            command=self.on_stop,
        )
        self.btn_stop.pack(side="left", padx=5)

        # ── Version ──
        tk.Label(self.root, text="v1.0 · WFV Bezirk Franken",
                 font=tkfont.Font(family="Segoe UI", size=8),
                 fg="#bbbbbb", bg="#ffffff").pack(side="bottom", pady=(0, 8))

        # Close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_stop)

        # Auto-start if venv exists
        if VENV_PYTHON.exists():
            self.root.after(500, self.on_start)
        else:
            self.set_status("Setup erforderlich – setup.bat ausführen", "#d97706")

    def _draw_dot(self, color):
        self.status_dot.delete("all")
        self.status_dot.create_oval(2, 2, 10, 10, fill=color, outline=color)

    def set_status(self, text, color="#666666"):
        self.status_label.configure(text=text, fg=color)
        dot_colors = {
            "#059669": "#059669",  # green
            "#c41230": "#c41230",  # red
            "#d97706": "#d97706",  # orange
        }
        self._draw_dot(dot_colors.get(color, "#cccccc"))
        self.root.update_idletasks()

    def is_port_in_use(self, port=8000):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) == 0

    def on_start(self):
        if self.running:
            self.open_browser()
            return

        if not VENV_PYTHON.exists():
            self.set_status("Fehler: .venv nicht gefunden – setup.bat ausführen", "#c41230")
            return

        # Check if already running
        if self.is_port_in_use():
            self.running = True
            self.set_status("Server läuft bereits", "#059669")
            self.btn_start.configure(state="disabled")
            self.btn_browser.configure(state="normal")
            self.open_browser()
            return

        self.set_status("Server wird gestartet...", "#d97706")
        self.btn_start.configure(state="disabled")

        # Start server in background thread
        thread = threading.Thread(target=self._start_server, daemon=True)
        thread.start()

    def _start_server(self):
        try:
            env = os.environ.copy()
            log_file = ROOT / "output" / "server.log"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = open(log_file, "w", encoding="utf-8")
            self.server_process = subprocess.Popen(
                [str(VENV_PYTHON), "-m", "uvicorn",
                 "src.api.server:app", "--host", "127.0.0.1", "--port", "8000"],
                cwd=str(ROOT),
                env=env,
                stdout=self._log_handle,
                stderr=self._log_handle,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            # Wait for server to be ready
            for _ in range(60):
                if self.is_port_in_use():
                    self.running = True
                    self.root.after(0, lambda: self.set_status("Server läuft", "#059669"))
                    self.root.after(0, lambda: self.btn_browser.configure(state="normal"))
                    self.root.after(500, self.open_browser)
                    return
                time.sleep(0.5)

            self.root.after(0, lambda: self.set_status("Server-Start fehlgeschlagen", "#c41230"))
            self.root.after(0, lambda: self.btn_start.configure(state="normal"))

        except Exception as e:
            self.root.after(0, lambda: self.set_status(f"Fehler: {e}", "#c41230"))
            self.root.after(0, lambda: self.btn_start.configure(state="normal"))

    def open_browser(self):
        webbrowser.open(URL)

    def on_stop(self):
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
            except Exception:
                try:
                    self.server_process.kill()
                except Exception:
                    pass
        self.root.destroy()
        sys.exit(0)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = LauncherApp()
    app.run()
