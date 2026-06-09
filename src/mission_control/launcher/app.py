"""Tkinter launcher — Canvas-drawn UI, identical look to v1.

The only behavioural changes from v1:
  - Service start/stop drives ThreadedUvicorn instead of ThreadedHTTPServer.
  - Quit properly drains uvicorn (should_exit) instead of the 500ms race.
  - Auto-update backs up the old .app before replacing it.
  - Logging routes through logging_conf rather than being silenced.
  - Repo / version constants point at v2.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
import zipfile
from collections import deque
from pathlib import Path

import tkinter as tk

from ..config import Settings, get_settings
from ..logging_conf import configure as configure_logging
from .supervisor import ServiceDescriptor, make_services

CURRENT_VERSION = "2.3.0"
GITHUB_REPO     = "pavelklus630/alien-mission-control-v2"

# ── palette (identical to v1) ─────────────────────────────────────────────────
BG       = "#060906"
CARD     = "#0b110c"
CARD2    = "#070d08"
ICONBG   = "#060d07"
BORD_OFF = "#173a1e"
BORD_ON  = "#33dd55"
GLOW_ON  = "#1c5e2e"
GLOW_WT  = "#5a4a10"
GREEN    = "#3ce05a"
GREEN2   = "#8dffae"
DIM      = "#5d8064"
FAINT    = "#3a5540"
RED      = "#e0392b"
RED_BG   = "#190705"
WAIT     = "#d4b020"
TXT      = "#cfe6d2"

FONT = "Courier New"

W, MX = 720, 22
CARD_H, GAP = 196, 15
HEADER_Y = 116
CARDS_Y  = 132


def _get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def _rrect(cv, x1, y1, x2, y2, r, **kw):
    pts = [x1+r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y2-r, x2, y2,
           x2-r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y1+r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


def _check_update():
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "AlienMissionControl"})
        with urllib.request.urlopen(req, timeout=6) as r:
            import json
            data = json.load(r)
        latest = data.get("tag_name", "").lstrip("v")
        if latest and latest != CURRENT_VERSION:
            for asset in data.get("assets", []):
                if asset["name"].endswith(".zip"):
                    return latest, asset["browser_download_url"]
    except Exception:
        pass
    return None, None


def _get_app_path():
    if not getattr(sys, "frozen", False):
        return None
    return os.path.dirname(os.path.dirname(os.path.dirname(sys.executable)))


def _assets_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets"
    # dev: app.py is at src/mission_control/launcher/app.py → 4 levels up = repo root
    return Path(__file__).resolve().parent.parent.parent.parent / "assets"


def _icon_path() -> str:
    return str(_assets_dir() / "alien_avatar.png")


def _dock_icon_path() -> str:
    """macOS dock icon — use the .icns file which carries the correct icon mask
    so macOS applies proper rounded-rectangle shaping in the dock."""
    return str(_assets_dir() / "AlienMissionControl.icns")


class Launcher(tk.Tk):
    def __init__(self, settings: Settings | None = None):
        super().__init__()
        self._settings = settings or get_settings()
        self._lan_ip   = _get_lan_ip()
        self._services  = make_services(self._settings, self._lan_ip)
        self._logs      = {s.name: deque(maxlen=6) for s in self._services}
        self._card: dict[str, dict] = {}
        self._port_online = {s.port: False for s in self._services}
        self._alive = True

        self.title("ALIEN — Mission Control")
        self.configure(bg=BG)

        H = CARDS_Y + len(self._services) * (CARD_H + GAP) + 78
        screen_h = self.winfo_screenheight()
        win_h = min(H, screen_h - 80)

        sb = tk.Scrollbar(self, orient="vertical", bg=BG, troughcolor="#040804",
                          activebackground=GLOW_ON, highlightthickness=0, width=12)
        self.cv = tk.Canvas(self, width=W, bg=BG, highlightthickness=0,
                            scrollregion=(0, 0, W, H))
        self.cv.configure(yscrollcommand=sb.set)
        sb.configure(command=self.cv.yview)
        sb.pack(side="right", fill="y")
        self.cv.pack(side="left", fill="y", expand=True)

        self.geometry(f"{W + 14}x{win_h}")
        self.resizable(False, True)
        self.minsize(W + 14, 400)
        self.bind_all("<MouseWheel>",
                      lambda e: self.cv.yview_scroll(-1 if e.delta > 0 else 1, "units"))

        self._load_icon()
        self._build_header()
        for i, s in enumerate(self._services):
            self._build_card(i, s)
        self._build_footer(H)

        self.protocol("WM_DELETE_WINDOW", self._quit)
        threading.Thread(target=self._port_watcher, daemon=True).start()
        threading.Thread(target=self._update_check, daemon=True).start()
        self._poll()
        self._tick()

    # ── icon ──────────────────────────────────────────────────────────────────
    def _load_icon(self):
        self.icon = None
        path = _icon_path()
        try:
            img = tk.PhotoImage(file=path)
            self.icon = img.subsample(2, 2)
            # Set window icon (title-bar corner on Linux; no-op on macOS but harmless).
            self.iconphoto(False, img)
        except Exception:
            pass
        # Set the macOS dock icon and app name (dev mode; .app bundle sets these via Info.plist).
        try:
            from AppKit import NSApplication, NSBundle, NSImage  # type: ignore[import]
            ns_app = NSApplication.sharedApplication()
            # Dock icon — use .icns which carries the correct rounded icon mask.
            ns_img = NSImage.alloc().initWithContentsOfFile_(_dock_icon_path())
            if ns_img:
                ns_app.setApplicationIconImage_(ns_img)
            # Dock label — override CFBundleName so the dock reads the app name,
            # not the Python interpreter name.
            info = NSBundle.mainBundle().infoDictionary()
            if info is not None:
                info["CFBundleName"] = "Mission Control"
                info["CFBundleDisplayName"] = "ALIEN — Mission Control"
        except Exception:
            pass

    # ── header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        cv = self.cv
        _rrect(cv, MX, 20, MX+78, 98, 12, fill=ICONBG, outline="#2a5232", width=1)
        if self.icon:
            cv.create_image(MX+39, 59, image=self.icon)
        tx = MX + 96
        cv.create_text(tx, 26, text="WEYLAND-YUTANI CORP.", anchor="w",
                       fill=DIM, font=(FONT, 10))
        cv.create_text(tx, 52, text="MISSION CONTROL", anchor="w",
                       fill=GREEN2, font=(FONT, 25, "bold"))
        cv.create_text(tx, 84, text=f"HEART OF DARKNESS   ·   GM CONSOLE   ·   v{CURRENT_VERSION}",
                       anchor="w", fill=FAINT, font=(FONT, 9))
        self.clock_id = cv.create_text(W-MX, 30, text="--:--:--", anchor="e",
                                       fill=GREEN2, font=(FONT, 23, "bold"))
        cv.create_text(W-MX, 60, text=f"◉ {self._lan_ip}", anchor="e",
                       fill=GREEN, font=(FONT, 9))
        cv.create_text(W-MX, 76, text="LAN ADDRESS", anchor="e",
                       fill=FAINT, font=(FONT, 8))
        cv.create_line(MX, HEADER_Y, W-MX, HEADER_Y, fill="#16301c")

    # ── card ──────────────────────────────────────────────────────────────────
    def _build_card(self, i: int, s: ServiceDescriptor):
        cv = self.cv
        x1, x2 = MX, W-MX
        y1 = CARDS_Y + i * (CARD_H + GAP)
        y2 = y1 + CARD_H
        ids: dict = {}

        ids["glow"] = _rrect(cv, x1-2, y1-2, x2+2, y2+2, 15, fill="", outline=BG, width=3)
        ids["card"] = _rrect(cv, x1, y1, x2, y2, 14, fill=CARD, outline=BORD_OFF, width=1)

        ix1, iy1 = x1+18, y1+18
        _rrect(cv, ix1, iy1, ix1+52, iy1+52, 9, fill=ICONBG, outline="#224a2a", width=1)
        self._draw_icon(s.icon, ix1, iy1, 52)

        tx = ix1 + 52 + 16
        ids["dot"] = cv.create_oval(tx, y1+27, tx+10, y1+37, fill=FAINT, outline="")
        cv.create_text(tx+18, y1+32, text=s.name, anchor="w",
                       fill=GREEN2, font=(FONT, 15, "bold"))
        cv.create_text(tx+18, y1+52, text=s.tag, anchor="w",
                       fill=FAINT, font=(FONT, 9))

        bx2, by1, by2 = x2-18, y1+16, y1+52
        bx1 = bx2-94
        ids["btn_box"] = _rrect(cv, bx1, by1, bx2, by2, 8, fill=CARD, outline="#2c6a3a", width=1)
        ids["btn_txt"] = cv.create_text((bx1+bx2)//2, (by1+by2)//2, text="START",
                                        fill=GREEN, font=(FONT, 11, "bold"))
        cv.create_text(bx1-12, y1+34, text=f":{s.port}", anchor="e",
                       fill=DIM, font=(FONT, 11))
        tag = f"btn{i}"
        for it in (ids["btn_box"], ids["btn_txt"]):
            cv.addtag_withtag(tag, it)
        cv.tag_bind(tag, "<Button-1>", lambda e, n=s.name: self._toggle(n))
        self._cursor(tag)

        ids["status"] = cv.create_text(tx, y1+88, text="○ OFFLINE", anchor="w",
                                       fill=DIM, font=(FONT, 10))
        ly, lx = y1+114, tx
        for j, (label, url) in enumerate(s.url_labels):
            lid = cv.create_text(lx, ly, text=f"↗ {label}", anchor="w",
                                 fill=DIM, font=(FONT, 9))
            ltag = f"lnk{i}_{j}"
            cv.addtag_withtag(ltag, lid)
            cv.tag_bind(ltag, "<Button-1>", lambda e, u=url: webbrowser.open(u))
            cv.tag_bind(ltag, "<Enter>", lambda e, l=lid: (cv.itemconfig(l, fill=GREEN2), cv.config(cursor="hand2")))
            cv.tag_bind(ltag, "<Leave>", lambda e, l=lid: (cv.itemconfig(l, fill=DIM), cv.config(cursor="")))
            lx += 150

        lx1, ly1 = tx, y1+132
        lx2, ly2 = x2-18, y2-16
        _rrect(cv, lx1, ly1, lx2, ly2, 7, fill=CARD2, outline="#102a16", width=1)
        cv.create_text(lx2-12, ly1+10, text="⋯", anchor="e", fill="#2c4a30", font=(FONT, 11))
        ids["log"] = cv.create_text(lx1+12, ly1+9, text="", anchor="nw",
                                    fill="#5f8466", font=(FONT, 9), width=lx2-lx1-30)
        self._card[s.name] = ids

    def _draw_icon(self, kind: str, x: int, y: int, sz: int):
        cv, cx, cy = self.cv, x+sz/2, y+sz/2
        if kind == "term":
            cv.create_text(cx, cy, text=">_", fill=GREEN, font=(FONT, 17, "bold"))
        elif kind == "map":
            cv.create_text(cx, cy, text="⌖", fill=GREEN, font=(FONT, 22, "bold"))
        else:
            pts = [x+10, cy, x+16, cy, x+19, cy-10, x+23, cy+13, x+27, cy-16,
                   x+31, cy+10, x+34, cy, x+sz-10, cy]
            cv.create_line(*pts, fill=GREEN, width=2,
                           capstyle="round", joinstyle="round", smooth=False)

    # ── footer ────────────────────────────────────────────────────────────────
    def _build_footer(self, H: int):
        y1, y2 = H - 64, H - 20
        self._big_btn("▶  LAUNCH ALL", MX, y1, MX+210, y2,
                      GREEN2, "#2c6a3a", "#0c2415", self._launch_all)
        self._big_btn("■  STOP ALL", MX+222, y1, MX+222+190, y2,
                      RED, "#6a1f18", RED_BG, self._stop_all)
        self._big_btn("✕  QUIT", W-MX-150, y1, W-MX, y2,
                      DIM, "#233226", "#101010", self._quit)

    def _big_btn(self, text, x1, y1, x2, y2, fg, outline, fill, cmd):
        cv = self.cv
        box = _rrect(cv, x1, y1, x2, y2, 9, fill=fill, outline=outline, width=1)
        txt = cv.create_text((x1+x2)//2, (y1+y2)//2, text=text,
                             fill=fg, font=(FONT, 12, "bold"))
        tag = f"big{x1}"
        for it in (box, txt):
            cv.addtag_withtag(tag, it)
        cv.tag_bind(tag, "<Button-1>", lambda e: cmd())
        self._cursor(tag)

    def _cursor(self, tag):
        cv = self.cv
        cv.tag_bind(tag, "<Enter>", lambda e: cv.config(cursor="hand2"))
        cv.tag_bind(tag, "<Leave>", lambda e: cv.config(cursor=""))

    # ── service control ───────────────────────────────────────────────────────
    def _svc(self, name: str) -> ServiceDescriptor:
        return next(s for s in self._services if s.name == name)

    def _toggle(self, name: str):
        if self._svc(name).running:
            self._stop(name)
        else:
            self._start(name)

    def _start(self, name: str):
        svc = self._svc(name)
        if svc.running:
            return

        def on_crash():
            self.after(0, lambda: self._on_crash(name))

        try:
            svc.start(self._settings, on_crash=on_crash)
        except OSError as e:
            self._logs[name].append(f"[ERROR] port {svc.port} busy: {e}")
            return
        except Exception as e:
            self._logs[name].append(f"[ERROR] {e}")
            return

        self._logs[name].clear()
        self._logs[name].append(f"Listening on :{svc.port}")

    def _stop(self, name: str):
        svc = self._svc(name)

        def _do():
            svc.stop()
            self.after(0, lambda: self._logs[name].append("Stopped."))

        threading.Thread(target=_do, daemon=True).start()

    def _on_crash(self, name: str):
        self._svc(name)._server = None
        self._logs[name].append("[CRASH] service exited unexpectedly")

    def _launch_all(self):
        for s in self._services:
            self._start(s.name)

    def _stop_all(self):
        for s in self._services:
            self._stop(s.name)

    def _quit(self):
        self._alive = False
        # Signal all uvicorn servers to exit gracefully before destroying the window.
        for s in self._services:
            if s._server:
                s._server.server.should_exit = True
        self.after(600, self.destroy)

    # ── live updates ──────────────────────────────────────────────────────────
    def _port_watcher(self):
        while self._alive:
            for s in self._services:
                self._port_online[s.port] = _port_open(s.port)
            time.sleep(0.8)

    def _poll(self):
        if not self._alive:
            return
        cv = self.cv
        for s in self._services:
            ids = self._card[s.name]
            online  = self._port_online[s.port]
            running = s.running or s._server is not None
            if online:
                cv.itemconfig(ids["card"],    outline=BORD_ON)
                cv.itemconfig(ids["glow"],    outline=GLOW_ON)
                cv.itemconfig(ids["dot"],     fill=GREEN)
                cv.itemconfig(ids["status"],
                              text=f"● ONLINE    ·    port {s.port} responding", fill=GREEN)
                cv.itemconfig(ids["btn_box"], outline=RED, fill=RED_BG)
                cv.itemconfig(ids["btn_txt"], text="STOP", fill=RED)
            elif running:
                cv.itemconfig(ids["card"],    outline="#4a3a10")
                cv.itemconfig(ids["glow"],    outline=GLOW_WT)
                cv.itemconfig(ids["dot"],     fill=WAIT)
                cv.itemconfig(ids["status"],  text="◌ STARTING    ·    binding port…", fill=WAIT)
                cv.itemconfig(ids["btn_box"], outline=RED, fill=RED_BG)
                cv.itemconfig(ids["btn_txt"], text="STOP", fill=RED)
            else:
                cv.itemconfig(ids["card"],    outline=BORD_OFF)
                cv.itemconfig(ids["glow"],    outline=BG)
                cv.itemconfig(ids["dot"],     fill=FAINT)
                cv.itemconfig(ids["status"],  text="○ OFFLINE", fill=DIM)
                cv.itemconfig(ids["btn_box"], outline="#2c6a3a", fill=CARD)
                cv.itemconfig(ids["btn_txt"], text="START", fill=GREEN)
            cv.itemconfig(ids["log"], text="\n".join(self._logs[s.name]))
        self.after(1000, self._poll)

    def _tick(self):
        if not self._alive:
            return
        self.cv.itemconfig(self.clock_id, text=time.strftime("%H:%M:%S"))
        self.after(1000, self._tick)

    # ── auto-update ───────────────────────────────────────────────────────────
    def _update_check(self):
        version, url = _check_update()
        if version and self._alive:
            self.after(0, lambda: self._show_update_banner(version, url))

    def _show_update_banner(self, version: str, url: str):
        self._upd_bar = tk.Frame(self, bg="#1a1000",
                                 highlightthickness=1, highlightbackground=WAIT, bd=0)
        self._upd_lbl = tk.Label(
            self._upd_bar,
            text=f"◉  UPDATE v{version} AVAILABLE  —  CLICK TO INSTALL",
            bg="#1a1000", fg=WAIT, font=(FONT, 10, "bold"), cursor="hand2", padx=12)
        self._upd_lbl.pack(fill="both", expand=True)
        self._upd_lbl.bind("<Button-1>", lambda e: self._start_update(version, url))
        self._upd_bar.bind("<Button-1>",  lambda e: self._start_update(version, url))
        self._upd_bar.place(x=0, y=0, relwidth=1, height=26)

    def _start_update(self, version: str, url: str):
        app_path = _get_app_path()
        if not app_path:
            webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases/latest")
            return
        self._upd_lbl.config(text="⬇  DOWNLOADING…  PLEASE WAIT")
        threading.Thread(target=self._do_update, args=(version, url, app_path),
                         daemon=True).start()

    def _do_update(self, version: str, url: str, app_path: str):
        try:
            tmp = tempfile.mkdtemp()
            zip_path = os.path.join(tmp, "update.zip")

            with urllib.request.urlopen(url) as r:
                total = int(r.headers.get("Content-Length", 0))
                done = 0
                with open(zip_path, "wb") as f:
                    while True:
                        chunk = r.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if total and self._alive:
                            pct = int(done * 100 / total)
                            self.after(0, lambda p=pct: self._upd_lbl.config(
                                text=f"⬇  DOWNLOADING…  {p}%"))

            extract_dir = os.path.join(tmp, "extracted")
            os.makedirs(extract_dir)
            subprocess.run(["ditto", "-x", "-k", "--sequesterRsrc",
                            zip_path, extract_dir], check=True)

            new_app = next(
                (os.path.join(extract_dir, n)
                 for n in os.listdir(extract_dir) if n.endswith(".app")),
                None)
            if not new_app:
                raise FileNotFoundError("No .app found in zip")

            app_parent = os.path.dirname(app_path)
            app_name   = os.path.basename(app_path)
            dest       = os.path.join(app_parent, app_name)
            backup     = dest + ".bak"

            # v2 improvement: back up the running .app before replacing it.
            script = (
                "#!/bin/bash\n"
                "sleep 1\n"
                f'cp -a "{dest}" "{backup}"\n'
                f'rm -rf "{dest}"\n'
                f'ditto "{new_app}" "{dest}"\n'
                f'xattr -dr com.apple.quarantine "{dest}" 2>/dev/null\n'
                f'rm -rf "{backup}"\n'
                f'open "{dest}"\n'
            )
            script_path = os.path.join(tmp, "do_update.sh")
            with open(script_path, "w") as f:
                f.write(script)
            os.chmod(script_path, 0o755)

            subprocess.Popen(["/bin/bash", script_path],
                             close_fds=True, start_new_session=True)
            self.after(0, lambda: self._upd_lbl.config(text="✓  DOWNLOADED — RESTARTING…"))
            time.sleep(0.8)
            self.after(0, self._quit)

        except Exception as exc:
            self.after(0, lambda: self._upd_lbl.config(text=f"✗  UPDATE FAILED: {exc}"))


def run() -> None:
    configure_logging()
    app = Launcher()
    app.mainloop()
