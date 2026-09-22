#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YAZ adb — غلاف رسومي لأداة تفعيل ADB على أجهزة Samsung Exynos (Download/Odin)."""

import json
import hashlib
import os
import platform
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.error
import urllib.request
import webbrowser
from tkinter import ttk, messagebox

# ===================================================================== نص عربي
# Tk لا يعرض العربية تشكيلاً واتجاه صحيح في بعض الأنظمة، لذلك نشكّل النص
# (Reshape) ونعيد ترتيبه (Bidi) في بايثون قبل العرض.
try:
    import arabic_reshaper
    from bidi.algorithm import get_display as _bidi
    _RESHAPE = True
except Exception:
    _RESHAPE = False

_AR_RE = re.compile("[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+")


def A(text):
    """يعيد النص العربي مشكّلاً ومرتّباً للعرض الصحيح؛ النص الإنجليزي يبقى دون تغيير."""
    if not text:
        return text
    if _RESHAPE and _AR_RE.search(text):
        try:
            return _bidi(arabic_reshaper.reshape(text))
        except Exception:
            pass
    return text


def pick_font(names, fallback="TkDefaultFont"):
    try:
        fams = set(tkfont.families())
    except Exception:
        fams = set()
    for n in names:
        if n in fams:
            return n
    return fallback


# ===================================================================== مسارات
def app_dir():
    """مجلد المورد الحقيقي: عند التجميع (frozen) يكون sys._MEIPASS
    حيث تُستخرج الحزمة المضمّنة (config, presets, data, ExynosCli...) مؤقتاً."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return meipass
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _unpack_embedded():
    """عند التجميع: يفك payload.bin المشفّر من داخل الـ exe إلى مجلد مؤقت
    ويعيد مساره ليكون هو BASE الحقيقي (يحتوي config/ExynosCli/presets/data)."""
    if not getattr(sys, "frozen", False):
        return None
    try:
        import _bundle
    except Exception:
        return None
    src = os.path.join(app_dir(), _bundle.PAYLOAD_NAME)
    if not os.path.exists(src):
        return None
    tmp = os.path.join(os.environ.get("TEMP", os.getcwd()),
                       "yazadb_" + hashlib.md5(str(os.getpid()).encode()).hexdigest()[:10])
    try:
        os.makedirs(tmp, exist_ok=True)
        if _bundle.unpack_payload(src, tmp):
            return tmp
    except Exception:
        pass
    return None


# عند التجميع نستخدم مجلد المستخرج المؤقت؛ وإلا مجلد السكربت العادي.
_EMBEDDED_DIR = _unpack_embedded()
if _EMBEDDED_DIR:
    BASE = _EMBEDDED_DIR
else:
    BASE = app_dir()
PARENT = os.path.dirname(BASE)
IS_WINDOWS = platform.system() == "Windows"

CONFIG_PATH = os.path.join(BASE, "config.json")

TOOL_CANDIDATES = [
    os.path.join(BASE, "ExynosCli.exe"),
    os.path.join(PARENT, "ExynosCli.exe"),
]
PRESETS_CANDIDATES = [
    os.path.join(BASE, "presets"),
    os.path.join(PARENT, "presets"),
]

SAMSUNG_VID = "04E8"


def find(path_candidates):
    for p in path_candidates:
        if os.path.exists(p):
            return p
    return None


class YazAdbApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = self._load_config()
        self.local_version = self.cfg.get("version", "1.0.0")

        # خطوط
        self.AR = pick_font(["Segoe UI", "Noto Sans Arabic", "DejaVu Sans",
                             "Tahoma", "Arial"])
        self.MONO = pick_font(["SF Mono", "Menlo", "Cascadia Mono", "Consolas",
                               "DejaVu Sans Mono", "Liberation Mono",
                               "Courier New"], "TkFixedFont")

        self.title(self.cfg.get("app_name", "YAZ adb"))
        self.configure(bg="#FFFFFF")
        self.geometry("1080x640")
        self.minsize(980, 560)

        self.serial_verified = False
        self.current_serial = ""
        self.device_port = ""
        self.device_name = ""
        self.busy = False
        self.dryrun = "--dryrun" in sys.argv
        self._chip_map = {}

        self._q = queue.Queue()
        self.after(50, self._poll_queue)

        self._build_ui()
        self.after(200, self._start_engine)

    # ---------------------------------------------------------------- config
    def _load_config(self):
        cfg = {
            "app_name": "YAZ adb",
            "version": "1.0.0",
            "serial_required": True,
            "registration_url": "https://yaz-blog.blogspot.com/p/serial-re.html",
            "server": {"serials_url": "", "version_url": ""},
            "social": {},
            "drivers": {"samsung_driver_url": ""},
        }
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
        except Exception:
            pass
        return cfg

    # ---------------------------------------------------------------- ناقل UI
    def _schedule(self, fn):
        try:
            self._q.put(fn)
        except Exception:
            pass

    def _poll_queue(self):
        try:
            while True:
                fn = self._q.get_nowait()
                try:
                    fn()
                except Exception as e:
                    print("UI task error:", e)
        except queue.Empty:
            pass
        try:
            self.after(50, self._poll_queue)
        except Exception:
            pass

    def _stop(self):
        try:
            self.after(300, self.destroy)
        except Exception:
            pass

    def _run_async(self, fn):
        t = threading.Thread(target=fn, daemon=True)
        t.start()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        bg = "#FFFFFF"
        fg = "#000000"
        AR = self.AR
        MONO = self.MONO

        def L(parent, text, size=10, bold=False, color=fg, wrap=None, anchor=None, pady=0):
            w = tk.Label(parent, text=A(text), font=(AR, size, "bold" if bold else "normal"),
                         bg=bg, fg=color, wraplength=wrap, justify="left")
            return w

        main = tk.Frame(self, bg=bg)
        main.pack(fill="both", expand=True)

        # ------------------ يسار ------------------
        left = tk.Frame(main, bg=bg, width=400)
        left.pack(side="left", fill="y", padx=24, pady=20)
        left.pack_propagate(False)

        head = tk.Frame(left, bg=bg)
        head.pack(fill="x")
        tk.Label(head, text=self.cfg.get("app_name", "YAZ adb"),
                 font=(AR, 26, "bold"), bg=bg, fg=fg).pack(side="left")
        tk.Label(head, text="v" + self.local_version,
                 font=(AR, 10), bg=bg, fg="#8a8a8a").pack(side="left",
                                                          padx=(8, 0),
                                                          pady=(14, 0))

        # دائرة النسبة
        self._cwrap = tk.Frame(left, bg=bg, width=200, height=200)
        self._cwrap.pack(pady=(12, 0))
        self._cwrap.pack_propagate(False)
        self._canvas = tk.Canvas(self._cwrap, width=200, height=200, bg=bg,
                                 highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)
        self._progress = 0
        self._draw_progress()
        self._progress_label = tk.Label(self._cwrap, text="0%",
                                        font=(AR, 22, "bold"), bg=bg, fg=fg)
        self._progress_label.place(relx=0.5, rely=0.5, anchor="center", y=-12)

        self._progress_status = tk.Label(left, text=A("بانتظار البدء..."),
                                         font=(AR, 9), bg=bg, fg="#8a8a8a")
        self._progress_status.pack(pady=(4, 0))

        # الخطوات المرقمة
        steps = tk.Frame(left, bg=bg)
        steps.pack(fill="x", pady=(14, 4))
        L(steps, "كيفية الاستخدام", 12, True).pack(anchor="w", pady=(0, 4))
        self._step_labels = []
        step_texts = [
            "أطفئ جهازك تماماً باستثناء توصيل الكابل",
            "اضغط Volume Down + Volume Up مع توصيل الكابل لتدخل وضع الـ Download ثم اضغط Volume Up",
            "أدخل سيريال الجهاز، ثم اضغط (قراءة معلومات الجهاز) ثم (تفعيل ADB)",
        ]
        for i, t in enumerate(step_texts, start=1):
            row = tk.Frame(steps, bg=bg)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"{i} -", font=(AR, 10, "bold"), bg=bg,
                     fg="#b0b0b0", width=4, anchor="e").pack(side="left")
            lbl = L(row, t, 9, wrap=300)
            lbl.pack(side="left", fill="x", expand=True)
            self._step_labels.append(lbl)

        # اختيار المعالج (اختصارات فقط)
        dev = tk.Frame(left, bg=bg)
        dev.pack(fill="x", pady=(12, 2))
        L(dev, "نوع المعالج:", 9, True).pack(anchor="w")
        self._preset_combo = ttk.Combobox(dev, state="readonly",
                                          font=(AR, 9))
        self._preset_combo.pack(fill="x", pady=(2, 0))
        self._apply_combobox_style()
        self._load_preset_list()

        # الأزرار الرئيسية
        btns = tk.Frame(left, bg=bg)
        btns.pack(fill="x", pady=(12, 0))
        self._btn_info = tk.Button(btns, text=A("قراءة معلومات الجهاز"),
                                   command=self.on_read_info,
                                   font=(AR, 10, "bold"),
                                   bg="#FFFFFF", fg="#000000", relief="solid",
                                   bd=1, padx=8, pady=6, activebackground="#f2f2f2")
        self._btn_info.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self._btn_adb = tk.Button(btns, text=A("تفعيل ADB"),
                                  command=self.on_enable_adb,
                                  font=(AR, 10, "bold"),
                                  bg="#000000", fg="#FFFFFF", relief="flat",
                                  bd=0, padx=8, pady=6, activebackground="#333333",
                                  activeforeground="#FFFFFF")
        self._btn_adb.pack(side="left", expand=True, fill="x")

        # ------------------ تيرمنال (يمين) — إنجليزي، خط كود ------------------
        right = tk.Frame(main, bg=bg)
        right.pack(side="left", fill="both", expand=True, padx=(0, 18), pady=18)

        term_outer = tk.Frame(right, bg="#e4e4e4", bd=1, relief="solid")
        term_outer.pack(fill="both", expand=True)

        bar = tk.Frame(term_outer, bg="#ECECEC")
        bar.pack(fill="x")
        for color in ("#FF5F56", "#FFBD2E", "#27C93F"):
            tk.Label(bar, bg=color, width=2, height=1).pack(side="left",
                                                            padx=(6, 0), pady=5)
        tk.Label(bar, text="YAZ adb — terminal", font=(MONO, 9),
                 bg="#ECECEC", fg="#5a5a5a").pack(side="left", padx=10)

        term = tk.Frame(term_outer, bg="#FFFFFF")
        term.pack(fill="both", expand=True)
        self._term = tk.Text(term, bg="#FFFFFF", fg="#111111",
                             font=(MONO, 11), wrap="word", relief="flat",
                             bd=0, padx=12, pady=10, insertbackground="#111111",
                             selectbackground="#b7d7ff", spacing1=1, spacing3=1)
        self._term.tag_configure("info", foreground="#111111", font=(MONO, 11))
        self._term.tag_configure("ok", foreground="#0a7d33", font=(MONO, 11, "bold"))
        self._term.tag_configure("err", foreground="#c1272d", font=(MONO, 11, "bold"))
        self._term.tag_configure("warn", foreground="#b26b00", font=(MONO, 11))
        self._term.tag_configure("cmd", foreground="#023f92", font=(MONO, 11, "bold"))
        sb = ttk.Scrollbar(term, command=self._term.yview)
        self._term.configure(yscrollcommand=sb.set)
        self._term.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # ------------------ الشريط السفلي ------------------
        bottom = tk.Frame(self, bg=bg)
        bottom.pack(fill="x", padx=24, pady=(0, 16))

        tk.Button(bottom, text=A("إصلاح التعريفات"),
                  command=self.on_fix_drivers,
                  font=(AR, 9), bg="#FFFFFF", fg="#000000",
                  relief="solid", bd=1, padx=10, pady=4).pack(side="left")

        right_side = tk.Frame(bottom, bg=bg)
        right_side.pack(side="right")

        social = tk.Frame(right_side, bg=bg)
        social.pack(side="right")
        self._icon_tg = self._make_icon(social, "telegram",
                                        self.cfg.get("social", {}).get("telegram",
                                                                       "https://t.me/Yazunlo"))
        self._icon_ig = self._make_icon(social, "instagram",
                                        self.cfg.get("social", {}).get("instagram",
                                                                       "https://instagram.com/yaz.salaqq"))
        self._icon_fb = self._make_icon(social, "facebook",
                                        self.cfg.get("social", {}).get("facebook",
                                                                       "https://facebook.com/yazsalaq"))
        self._icon_tg.pack(side="right", padx=4)
        self._icon_ig.pack(side="right", padx=4)
        self._icon_fb.pack(side="right", padx=5)

        tk.Label(right_side, text="  ", bg=bg).pack(side="right")

        tok = tk.Frame(right_side, bg=bg)
        tok.pack(side="right")
        tk.Label(tok, text=A("السيريال:"), font=(AR, 9, "bold"), bg=bg,
                 fg=fg).pack(side="left")
        self._serial_var = tk.StringVar()
        self._serial_entry = tk.Entry(tok, textvariable=self._serial_var, width=18,
                                      font=(AR, 9), relief="solid", bd=1,
                                      justify="center", bg="#FFFFFF", fg="#000000")
        self._serial_entry.pack(side="left", padx=6)
        self._serial_entry.bind("<Return>", lambda e: self.on_check_serial())
        self._btn_check = tk.Button(tok, text=A("تحقق"), command=self.on_check_serial,
                                    font=(AR, 9, "bold"),
                                    bg="#FFFFFF", fg="#000000", relief="solid",
                                    bd=1, padx=8, pady=3)
        self._btn_check.pack(side="left", padx=(0, 4))
        self._btn_register = tk.Button(tok, text=A("تسجيل"), command=self.on_register_serial,
                                       font=(AR, 9, "bold"),
                                       bg="#FFFFFF", fg="#023f92", relief="flat",
                                       bd=0, padx=6, pady=3)
        self._btn_register.pack(side="left")

    def _apply_combobox_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TCombobox",
                    fieldbackground="#FFFFFF", background="#FFFFFF",
                    foreground="#000000", bordercolor="#cccccc",
                    arrowcolor="#000000")
        s.configure("TCombobox.Listbox", background="#FFFFFF",
                    foreground="#000000")

    def _load_preset_list(self):
        presets_dir = find(PRESETS_CANDIDATES)
        self._presets_dir = presets_dir
        self._chip_map = {}
        if presets_dir:
            try:
                for fn in sorted(os.listdir(presets_dir)):
                    if not fn.endswith(".json"):
                        continue
                    chip = fn.split("_")[0]
                    try:
                        with open(os.path.join(presets_dir, fn),
                                  "r", encoding="utf-8") as f:
                            d = json.load(f)
                        if isinstance(d, dict) and d.get("chipset"):
                            chip = str(d["chipset"])
                    except Exception:
                        pass
                    self._chip_map.setdefault(chip, []).append(fn)
            except Exception:
                pass
        items = ["Auto (detect)"]
        items += sorted(self._chip_map.keys())
        self.preset_items = items
        self._preset_combo["values"] = tuple(items)
        self._preset_combo.current(0)

    # ---------------------------- أيقونات رسم بالـ Canvas ------------------
    def _make_icon(self, parent, kind, url):
        c = tk.Canvas(parent, width=26, height=26, bg="#FFFFFF",
                      highlightthickness=0, cursor="hand2")
        if kind == "telegram":
            c.create_polygon(3, 14, 21, 4, 17, 23, 12, 17, 8, 20, 10, 14,
                             fill="#0088CC", outline="")
            c.create_polygon(10, 14, 12, 17, 17, 23, 21, 19, 8, 20,
                             fill="#0088CC", outline="")
        elif kind == "instagram":
            c.create_oval(3, 3, 23, 23, outline="#000000", width=2)
            c.create_oval(8, 8, 18, 18, outline="#000000", width=2)
            c.create_oval(17, 6, 19, 8, fill="#000000", outline="")
        elif kind == "facebook":
            c.create_oval(3, 3, 23, 23, outline="#000000", width=2)
            c.create_text(13, 13, text="f", font=(self.MONO, 12, "bold"),
                          fill="#000000")
        c.bind("<Button-1>", lambda e: self._open(url))
        c.bind("<Enter>", lambda e: c.config(bg="#f0f0f0"))
        c.bind("<Leave>", lambda e: c.config(bg="#FFFFFF"))
        return c

    # ---------------------------------------------------------------- تيرمنال
    def log(self, msg, kind="info"):
        self._schedule(lambda: self._log_now(msg, kind))

    def _log_now(self, msg, kind="info"):
        stamp = time.strftime("[%H:%M:%S]")
        self._term.insert("end", stamp + " ", ("warn" if kind == "warn" else "cmd"))
        self._term.insert("end", msg + "\n", kind)
        self._term.see("end")

    def log_done(self, ok):
        self.log("Ready • DONE ✓", "ok") if ok else self.log("Error • FAILED ✗", "err")

    # ---------------------------------------------------------------- نسبة
    def _draw_progress(self):
        c = self._canvas
        c.delete("prog")
        x0, x1, y0, y1 = 8, 192, 8, 192
        c.create_oval(x0, y0, x1, y1, outline="#e6e6e6", width=12, tags="prog")
        pct = max(0, min(100, self._progress))
        if pct > 0:
            c.create_arc(x0, y0, x1, y1, start=90, extent=-pct * 3.6,
                         style="arc", outline="#111111", width=12, tags="prog")

    def set_progress(self, value, status=None):
        def _do():
            self._progress = int(value)
            self._draw_progress()
            self._progress_label.config(text=f"{self._progress}%")
            if status is not None:
                self._progress_status.config(text=A(status))
        self._schedule(_do)

    def mark_step(self, index, done):
        def _do():
            idx = index - 1
            if 0 <= idx < len(self._step_labels):
                base = self._step_labels[idx].cget("text").split("✓")[0].split("✗")[0].rstrip()
                color = "#0a7d33" if done else "#b00020"
                self._step_labels[idx].config(text=base + (" ✓" if done else " ✗"),
                                              fg=color)
        self._schedule(_do)

    def _set_busy(self, flag, adb=False):
        self.busy = flag

        def _do():
            state = "disabled" if flag else "normal"
            self._btn_info.config(state=state)
            if not adb:
                self._btn_adb.config(state=state)
            self._btn_check.config(state=state)
        self._schedule(_do)

    def _open(self, url):
        try:
            webbrowser.open_new_tab(url)
        except Exception:
            pass

    def _fetch_json(self, url, timeout=10):
        if not url or not url.startswith("http"):
            raise ValueError("server URL not configured")
        req = urllib.request.Request(url, headers={"User-Agent": "YAZ-adb/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    # ---------------------------------------------------------------- بدء
    def _start_engine(self):
        self._verify_orientation()
        self.set_progress(2, "Starting engine...")
        if not self._maybe_admin_auth():
            return
        self._run_async(self._check_update_worker)
        if self.dryrun:
            self.log("DRY-RUN mode active — ExynosCli.exe will not be executed", "warn")

    def _maybe_admin_auth(self):
        """نسخة الادمن محمية بكلمة مرور — إن لم تُدخل الصحيحة تتوقف الاداة."""
        if not self.cfg.get("admin"):
            return True
        expected = self.cfg.get("admin_password_hash", "").strip().lower()
        if not expected:
            return True
        self.admin_attempts = 0
        self._admin_auth_dialog(expected)
        return self.admin_attempts < 3

    def _admin_auth_dialog(self, expected):
        pop = tk.Toplevel(self)
        pop.configure(bg="#FFFFFF")
        pop.title(A("نسخة الادمن"))
        pop.transient(self)
        pop.grab_set()
        pop.geometry("420x240")
        tk.Label(pop, text=A("نسخة الادمن — محمية"),
                 font=(self.AR, 14, "bold"), bg="#FFFFFF",
                 fg="#c1272d").pack(pady=(18, 4))
        tk.Label(pop, text=A("أدخل كلمة مرور الادمن للاستمرار:"),
                 font=(self.AR, 10), bg="#FFFFFF", fg="#000000").pack()
        pwdvar = tk.StringVar()
        ent = tk.Entry(pop, textvariable=pwdvar, show="*", width=20,
                       font=(self.AR, 11), justify="center", relief="solid", bd=1)
        ent.pack(pady=(10, 4))
        stat = tk.Label(pop, text="", font=(self.AR, 9), bg="#FFFFFF", fg="#c1272d")
        stat.pack()
        def verify(_=None):
            h = hashlib.sha256(pwdvar.get().encode()).hexdigest().lower()
            if h == expected:
                pop.destroy()
                self.log("Admin authentication OK ✓", "ok")
            else:
                self.admin_attempts += 1
                if self.admin_attempts >= 3:
                    pop.destroy()
                    self.log("Admin auth failed (3 attempts) — stopping ✗", "err")
                    messagebox.showerror(A("تم الإيقاف"),
                                         A("كلمة مرور خاطئة ثلاث مرات. سيتم إغلاق الاداة."),
                                         parent=self)
                    self._stop()
                else:
                    pwdvar.set("")
                    stat.config(text=A(f"كلمة مرور خاطئة — المتبقي {3 - self.admin_attempts}"))
                    ent.focus_set()
        ent.bind("<Return>", verify)
        tk.Button(pop, text=A("دخول"), command=verify,
                  font=(self.AR, 10, "bold"), bg="#111111", fg="#FFFFFF",
                  relief="flat", padx=24, pady=6).pack(pady=(14, 4))
        ent.focus_set()

    def _verify_orientation(self):
        try:
            found = find(TOOL_CANDIDATES)
            if found:
                self.log("Exploit engine found: " + os.path.basename(found), "info")
            else:
                self.log("Warning: ExynosCli.exe not found — place tool next to engine files", "warn")
        except Exception:
            pass

    # ---------------------------------------------------------------- تحديث
    def _check_update_worker(self):
        url = self.cfg.get("server", {}).get("version_url", "")
        try:
            remote = self._fetch_json(url)
            remote_v = str(remote.get("version", self.local_version))
            if remote_v != self.local_version:
                self._schedule(lambda: self._do_forced_update(remote_v,
                                                              remote.get("url", "")))
                return
            self.log("No updates available — version is up to date ✓", "ok")
        except Exception as e:
            self.log("Could not reach update server, continuing offline"
                     + (f" ({e})" if self.dryrun else "") + " ⚠", "warn")

    def _do_forced_update(self, remote_v, url):
        msg = (A("تتوفر نسخة جديدة") + f" v{remote_v}\n\n" +
               A("تحديث إجباري — ستتوقف الاداة الآن.\n"
                 "سيفتح صفحة التحميل، قم بتحميل النسخة الجديدة."))
        pop = tk.Toplevel(self)
        pop.configure(bg="#FFFFFF")
        pop.title(A("تحديث متوفر"))
        pop.transient(self)
        pop.grab_set()
        pop.geometry("440x250")
        tk.Label(pop, text=A("تحديث إجباري"),
                 font=(self.AR, 14, "bold"), bg="#FFFFFF",
                 fg="#c1272d").pack(pady=(16, 4))
        tk.Label(pop, text=msg, font=(self.AR, 10), bg="#FFFFFF", fg="#000000",
                 wraplength=400, justify="left").pack(padx=18)
        def do_open():
            if url and url.startswith("http"):
                self._open(url)
            pop.destroy()
            self.log("System stopped due to mandatory update", "err")
            self._stop()
        def do_close():
            pop.destroy()
            self.log("System stopped due to mandatory update", "err")
            self._stop()
        tk.Button(pop, text=A("فتح صفحة التحديث"), command=do_open,
                  font=(self.AR, 10, "bold"), bg="#111111", fg="#FFFFFF",
                  relief="flat", padx=18, pady=6).pack(pady=(16, 6))
        tk.Button(pop, text=A("خروج"), command=do_close,
                  font=(self.AR, 9), bg="#FFFFFF", fg="#000000",
                  relief="solid", bd=1, padx=18, pady=4).pack()

    # ---------------------------------------------------------------- سيريال
    def _require_serial(self):
        if not self.cfg.get("serial_required", True):
            return True
        if self.serial_verified:
            return True
        self.log("Error: please verify your serial first", "err")
        messagebox.showwarning(A("السيريال مطلوب"),
                               A("عذراً، يرجى إدخال السيريال الخاص بجهازك والتحقق منه أولاً."),
                               parent=self)
        return False

    def on_check_serial(self):
        serial = self._serial_var.get().strip()
        if not serial:
            messagebox.showwarning(A("السيريال"), A("يرجى إدخال السيريال أولاً."),
                                   parent=self)
            return
        self.log("Working: verifying serial (" + serial + ")...", "info")
        self._schedule(lambda: self._btn_check.config(state="disabled"))
        self._run_async(lambda: self._verify_serial_worker(serial))

    def _verify_serial_worker(self, serial):
        url = self.cfg.get("server", {}).get("serials_url", "")
        try:
            data = self._fetch_json(url)
            serials = [str(s).strip().upper() for s in data.get("serials", [])]
            ok = serial.strip().upper() in serials
        except Exception:
            self.log("Error: could not contact serial server ✗", "err")
            self._schedule(lambda: self._btn_check.config(state="normal"))
            return
        if ok:
            self.serial_verified = True
            self.current_serial = serial
            self.log("Serial verified ✓", "ok")
            self.set_progress(15, "Serial verified")
            self._schedule(lambda: self._serial_entry.config(fg="#0a7d33"))
            self._schedule(lambda: self._btn_check.config(state="normal"))
        else:
            self._schedule(lambda: self._serial_entry.config(fg="#c1272d"))
            self.log("Serial not registered ✗", "err")
            self._schedule(lambda: self._btn_check.config(state="normal"))
            self._schedule(self._ask_register_serial)

    def _ask_register_serial(self):
        pop = tk.Toplevel(self)
        pop.configure(bg="#FFFFFF")
        pop.title(A("السيريال غير مسجل"))
        pop.transient(self)
        pop.grab_set()
        pop.geometry("460x240")
        tk.Label(pop, text=A("عذراً، يرجى تسجيل السيريال"),
                 font=(self.AR, 14, "bold"), bg="#FFFFFF",
                 fg="#c1272d").pack(pady=(18, 6))
        tk.Label(pop, text=A("هذا السيريال غير مسجل في السيرفر.\n"
                             "اضغط (تسجيل) لفتح صفحة التسجيل ثم أعد التحقق بعد التسجيل."),
                 font=(self.AR, 10), bg="#FFFFFF", fg="#000000",
                 justify="left", wraplength=420).pack(padx=20)
        def reg():
            self._open(self.cfg.get("registration_url",
                                    "https://yaz-blog.blogspot.com/p/serial-re.html"))
        tk.Button(pop, text=A("تسجيل السيريال"), command=reg,
                  font=(self.AR, 10, "bold"), bg="#111111", fg="#FFFFFF",
                  relief="flat", padx=20, pady=6).pack(pady=(16, 4))
        tk.Button(pop, text=A("إغلاق"), command=pop.destroy,
                  font=(self.AR, 9), bg="#FFFFFF", fg="#000000",
                  relief="solid", bd=1, padx=20, pady=4).pack()

    def on_register_serial(self):
        self._open(self.cfg.get("registration_url",
                                "https://yaz-blog.blogspot.com/p/serial-re.html"))

    # ---------------------------------------------------------------- معلومات
    def on_read_info(self):
        if self.busy:
            return
        if not self._require_serial():
            return
        self.log("Working: reading device info...", "info")
        self.set_progress(20, "Scanning device...")
        self._set_busy(True)
        self._run_async(self._read_info_worker)

    def _read_info_worker(self):
        try:
            if self.dryrun:
                time.sleep(1.0)
                self.device_name = "Samsung Galaxy (dryrun)"
                self.device_port = "COM19"
                self.log("Device: Samsung Galaxy (dryrun)", "info")
                self.log("Port: COM19", "info")
                self.set_progress(40, "Device found")
                self.mark_step(1, True)
                self.log_done(True)
                self._set_busy(False)
                return
            if IS_WINDOWS:
                self._read_info_windows()
            else:
                self._read_info_linux()
        except Exception as e:
            self.log(f"Error reading device info ✗ — {e}", "err")
            self.set_progress(20, "Device not recognized")
            self._set_busy(False)
            self.log_done(False)

    def _read_info_windows(self):
        self.device_name = ""
        ports = []
        script = (
            "$res=@();"
            "$d=Get-PnpDevice -PresentOnly 2>$null;"
            "foreach($x in $d){ "
            "if($x.InstanceId -match 'USB.*" + SAMSUNG_VID + "'){ "
            "$res += ($x.Status+'|'+$x.Class+'|'+$x.FriendlyName+'|'+$x.InstanceId) } };"
            "$res | Out-String"
        )
        try:
            out = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", script],
                capture_output=True, text=True, timeout=20,
                creationflags=0x08000000 if IS_WINDOWS else 0)
            lines = [l for l in (out.stdout or "").splitlines() if l.strip()]
            for line in lines:
                self.log("  " + line, "cmd")
                m = re.search(r"COM\d+", line, re.IGNORECASE)
                if m:
                    ports.append(m.group(0))
                if not self.device_name and len(line.split("|")) > 2:
                    self.device_name = line.split("|")[2]
        except Exception as e:
            self.log("Could not enumerate devices: " + str(e), "warn")

        if not self.device_name:
            try:
                out = subprocess.run(["pnputil", "/enum-devices"],
                                     capture_output=True, text=True, timeout=25)
                found = False
                for line in (out.stdout or "").splitlines():
                    if SAMSUNG_VID in line.lower() or "samsung" in line.lower():
                        found = True
                        self.log("  " + line, "cmd")
                        m = re.search(r"COM\d+", line, re.IGNORECASE)
                        if m:
                            ports.append(m.group(0))
                if found:
                    self.device_name = "Samsung USB device (Download/Odin)"
            except Exception:
                pass

        self.device_port = ports[0] if ports else ""
        if self.device_name or self.device_port:
            self.log("Device: " + (self.device_name or "Unknown"), "info")
            if self.device_port:
                self.log("Port: " + self.device_port, "info")
            else:
                self.log("Warning: no COM port found — check Driver Repair button", "warn")
            self.set_progress(40, "Device found")
            self.mark_step(1, True)
            self.log_done(True if self.device_port else False)
        else:
            self.log("No Samsung device found — check Download mode and cable ✗", "err")
            self.set_progress(20, "Device not recognized")
            self.log_done(False)
        self._set_busy(False)

    def _read_info_linux(self):
        self.device_name = ""
        self.device_port = ""
        for cmd in (["lsusb"], ["ls", "/dev/ttyUSB*", "/dev/ttyACM*"]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True)
                text = out.stdout or ""
                for line in text.splitlines():
                    if "04e8" in line.lower() or "ttyUSB" in line or "ttyACM" in line:
                        self.log("  " + line, "cmd")
                        if re.search(r"ttyUSB\d+|ttyACM\d+", line):
                            self.device_port = line
                if "04e8" in text.lower():
                    self.device_name = "Samsung device (Download/Odin)"
            except Exception:
                continue
        if self.device_name:
            self.log("Device: " + self.device_name, "info")
            if self.device_port:
                self.log("Port: " + self.device_port, "info")
            self.set_progress(40, "Device found")
            self.mark_step(1, True)
            self.log_done(True if self.device_port else False)
        else:
            self.log("No Samsung device found ✗", "err")
            self.set_progress(20, "Device not recognized")
            self.log_done(False)
        self._set_busy(False)

    # ---------------------------------------------------------------- ADB
    def on_enable_adb(self):
        if self.busy:
            return
        if not self._require_serial():
            return
        self.log("Working: enabling ADB...", "info")
        self.set_progress(45, "Preparing exploit...")
        self._set_busy(True, adb=True)
        selection = self._preset_combo.get()
        self._run_async(lambda: self._enable_adb_worker(selection))

    def _enable_adb_worker(self, selection):
        try:
            if not self.device_port and not self.dryrun and IS_WINDOWS:
                self._read_info_windows()
            presets = self._select_presets(selection)
            if not presets:
                self.log("Error: no preset files found next to the tool ✗", "err")
                self.set_progress(85, "Exploit failed")
                self._set_busy(False)
                self.log_done(False)
                return
            total = max(1, len(presets))
            for i, p in enumerate(presets):
                pct = 55 + (30 * (i + 1)) // total
                self.set_progress(pct, f"Exploiting: {os.path.basename(p)}")
                self.log("Starting on: " + os.path.basename(p), "cmd")
                ok, out = self._run_tool("boot", p)
                for chunk in out:
                    self.log("  " + chunk, "info")
                if ok:
                    self._adb_success(os.path.basename(p))
                    return
            self.set_progress(85, "Exploit failed")
            self.log("None of the presets succeeded — check Download mode and cable ✗", "err")
            self._set_busy(False)
            self.log_done(False)
        except Exception as e:
            self.log(f"Error enabling ADB ✗ — {e}", "err")
            self.set_progress(85, "Exploit failed")
            self._set_busy(False)
            self.log_done(False)

    def _select_presets(self, selection):
        if not self._presets_dir:
            return None
        if selection and selection.startswith("Auto"):
            files = sorted(f for f in os.listdir(self._presets_dir) if f.endswith(".json"))
            files.sort(key=lambda f: (1 if f.startswith("generic") else 0, f))
        else:
            files = self._chip_map.get(selection, [])
        return [os.path.join(self._presets_dir, f) for f in files if f]

    def _run_tool(self, action, preset_path):
        exe = find(TOOL_CANDIDATES)
        if not exe:
            return False, ["ExynosCli.exe not found — place the tool next to engine files."]
        if self.dryrun:
            time.sleep(1.2)
            return True, [f"[dryrun] {action} completed on {os.path.basename(preset_path)}"]
        cmd = [exe, action]
        if preset_path:
            cmd += ["--preset", preset_path]
        if self.device_port:
            cmd += ["--port", self.device_port]
        token = self.cfg.get("cli_token", "")
        if token:
            cmd += ["--token", token]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    errors="replace", cwd=os.path.dirname(exe))
            output = [raw.rstrip() for raw in proc.stdout if raw.rstrip()]
            proc.wait(timeout=300)
            return proc.returncode == 0, output
        except subprocess.TimeoutExpired:
            proc.kill()
            return False, ["Timeout reached — device did not respond."]
        except Exception as e:
            return False, [f"Failed to run tool: {e}"]

    def _adb_success(self, preset):
        self.set_progress(100, "ADB enabled — device ready ✓")
        self.mark_step(3, True)
        self.log(f"ADB enabled successfully via {preset} ✓", "ok")
        self.log("Device is now in COMPELSON RECOVERY — ROOTED ADB active", "ok")
        self.log_done(True)
        self._set_busy(False)

    # ---------------------------------------------------------------- تعريفات
    def on_fix_drivers(self):
        self.log("Working: driver repair...", "info")
        pop = tk.Toplevel(self)
        pop.configure(bg="#FFFFFF")
        pop.title(A("إصلاح التعريفات"))
        pop.transient(self)
        pop.grab_set()
        pop.geometry("460x240")
        tk.Label(pop, text=A("إصلاح التعريفات"),
                 font=(self.AR, 13, "bold"), bg="#FFFFFF", fg="#000000").pack(pady=(18, 4))
        tk.Label(pop, text=A("اختر العملية المطلوبة:"),
                 font=(self.AR, 10), bg="#FFFFFF", fg="#444444").pack()
        url = self.cfg.get("drivers", {}).get("samsung_driver_url", "")
        def dl():
            if url:
                self._open(url)
            self.log("Opening Samsung driver download page...", "cmd")
            pop.destroy()
        def fix():
            pop.destroy()
            self._run_async(self._fix_drivers_worker)
        tk.Button(pop, text=A("تحميل التعريفات"), command=dl,
                  font=(self.AR, 10, "bold"), bg="#111111", fg="#FFFFFF",
                  relief="flat", padx=24, pady=6).pack(pady=(12, 8))
        tk.Button(pop, text=A("إصلاح / فحص التعريفات"), command=fix,
                  font=(self.AR, 10, "bold"), bg="#FFFFFF", fg="#000000",
                  relief="solid", bd=1, padx=24, pady=6).pack(pady=(0, 8))
        tk.Button(pop, text=A("إلغاء"), command=pop.destroy,
                  font=(self.AR, 8), bg="#FFFFFF", fg="#888888", relief="flat").pack()

    def _fix_drivers_worker(self):
        self.log("Scanning and fixing drivers...", "info")
        try:
            if self.dryrun:
                time.sleep(1.0)
                self.log("Driver check completed — no issues found ✓", "ok")
                self.log_done(True)
                return
            if IS_WINDOWS:
                for cmd in (["pnputil", "/scan-devices"],
                            ["pnputil", "/enum-devices", "/class", "Ports"]):
                    self.log("  > " + " ".join(cmd), "cmd")
                    out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    for line in (out.stdout or "").splitlines()[:40]:
                        self.log("  " + line, "info")
                self.log("Port driver scan completed ✓", "ok")
            else:
                self.log("Driver repair requires Windows ✗", "warn")
        except Exception as e:
            self.log(f"Driver repair failed ✗ — {e}", "err")
        self.log_done(True)


def main():
    if "--diagnose" in sys.argv:
        lines = []
        lines.append("YAZ adb diagnostic")
        lines.append("frozen: " + str(getattr(sys, "frozen", False)))
        lines.append("meipass: " + str(getattr(sys, "_MEIPASS", "<none>")))
        lines.append("BASE: " + str(BASE))
        lines.append("CONFIG_PATH: " + str(CONFIG_PATH))
        lines.append("config exists: " + str(os.path.exists(CONFIG_PATH)))
        lines.append("ExynosCli: " + str(find(TOOL_CANDIDATES)))
        lines.append("presets_dir: " + str(find(PRESETS_CANDIDATES)))
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    lines.append("config keys: " + str(list(json.load(f).keys())))
            except Exception as e:
                lines.append("config read error: " + str(e))
        report = "\n".join(lines) + "\n"
        try:
            with open(os.path.join(os.environ.get("TEMP", "."), "yaz_diag.txt"),
                      "w", encoding="utf-8") as f:
                f.write(report)
        except Exception:
            pass
        try:
            print(report)
        except Exception:
            pass
        return
    try:
        app = YazAdbApp()
        app.mainloop()
    except Exception as e:
        try:
            messagebox.showerror("Error", "Unexpected error:\n" + str(e))
        except Exception:
            print("Fatal:", e)


if __name__ == "__main__":
    main()