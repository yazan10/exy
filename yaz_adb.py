#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YAZ adb — غلاف رسومي لأداة تفعيل ADB على أجهزة Samsung Exynos (Download/Odin)."""

import json
import hashlib
import glob
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
IS_LINUX = platform.system() == "Linux"

CONFIG_PATH = os.path.join(BASE, "config.json")


def AN(text):
    """نص للحوارات الأصيلة (messagebox) — على ويندوز تتكفّل نوافذ Win32
    بتشكيل النص العربي وترتيبه (bidi) بنفسها، لذا نمرّر النص الخام
    وإلا تُعاد المعالجة مرتين فيظهر مكسوراً/معكوسة. على لينكس نستخدم A()."""
    if not text:
        return text
    if IS_WINDOWS and _AR_RE.search(text):
        return text
    return A(text)


VCPP_X86_URL = ("https://download.visualstudio.microsoft.com/download/pr/"
                "40b59c73-1480-4caf-ab5b-4886f176bf71/"
                "435A0DE411B991E2BFC7FD1D5439639E7B32206960D3099370E36172018F52FE/"
                "VC_redist.x86.exe")
VCPP_X64_URL = ("https://download.visualstudio.microsoft.com/download/pr/"
                "40b59c73-1480-4caf-ab5b-4886f176bf71/"
                "D62841375B90782B1829483AC75695CCEF680A8F13E7DE569B992EF33C6CD14A/"
                "VC_redist.x64.exe")

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

        # أيقونة البرق الأخضر (عند التجميع من ملف بجانب السكربت)
        try:
            loc = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            ico = os.path.join(loc, "yaz_bolt.ico")
            if os.path.exists(ico):
                self.iconbitmap(ico)
        except Exception:
            pass

        self.serial_verified = False
        self.current_serial = ""
        self.device_imei = ""
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

        # ------------------ يسار (قابل للتمرير الرأسي) ------------------
        left_outer = tk.Frame(main, bg=bg, width=400)
        left_outer.pack(side="left", fill="y", padx=24, pady=20)
        left_outer.pack_propagate(False)
        self._left_canv = tk.Canvas(left_outer, bg=bg, highlightthickness=0,
                                    width=400)
        self._left_canv.pack(side="left", fill="both", expand=True)
        # شريط تمرير ظاهر (يمرر الأعلى/الأسفل) مع أزرار ▲/▼
        scroll_col = tk.Frame(left_outer, bg="#eef1f6")
        scroll_col.pack(side="right", fill="y")
        for grad, cmd in (("▲", -5), ("▼", 5)):
            b = tk.Button(scroll_col, text=grad, font=(AR, 9, "bold"),
                          bg="#dfe5ef", fg="#5a6f8f", relief="flat", bd=0,
                          activebackground="#c9d4e4", activeforeground="#023f92",
                          command=lambda c=cmd: self._left_canv.yview_scroll(c, "units"))
            b.pack(fill="x")
        lbar = ttk.Scrollbar(scroll_col, orient="vertical",
                             command=self._left_canv.yview)
        lbar.pack(fill="y", side="right", expand=True)
        self._left_canv.configure(yscrollcommand=lbar.set)
        # تمرير بالعجلة داخل العمود الأيسر
        def _wheel(e):
            try:
                self._left_canv.yview_scroll(-1 * (e.delta // 120), "units")
            except Exception:
                pass
        self._left_canv.bind("<MouseWheel>", _wheel)
        left = tk.Frame(self._left_canv, bg=bg, width=400)
        left.pack(fill="x")
        wid = self._left_canv.create_window((0, 0), window=left,
                                            anchor="nw", width=400)

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

        # مربعا (الجهاز المتصل) و(البورت المتصل) تحت دائرة النسبة — بعضهما تحت بعض
        devframe = tk.Frame(left, bg="#EAF7EC", bd=2, relief="solid",
                            highlightbackground="#27C93F", highlightthickness=1)
        devframe.pack(fill="x", pady=(10, 0))
        L(devframe, "⚡ الجهاز المتصل", 10, True, color="#0a7d33").pack(anchor="w",
                                                                       padx=10, pady=(6, 0))
        self._dev_value = tk.Label(devframe, text=A("غير متصل — اضغط (قراءة معلومات الجهاز)"),
                                   font=(AR, 10, "bold"), bg="#EAF7EC", fg="#333333",
                                   anchor="w", wraplength=330, justify="left")
        self._dev_value.pack(fill="x", padx=10, pady=(2, 8))

        portframe = tk.Frame(left, bg="#F2F7FF", bd=2, relief="solid",
                             highlightbackground="#023f92", highlightthickness=1)
        portframe.pack(fill="x", pady=(6, 0))
        L(portframe, "🔌 البورت المتصل", 10, True, color="#023f92").pack(anchor="w",
                                                                        padx=10, pady=(6, 0))
        self._port_value = tk.Label(portframe, text=A("—"),
                                    font=(AR, 10, "bold"), bg="#F2F7FF", fg="#333333",
                                    anchor="w", wraplength=330, justify="left")
        self._port_value.pack(fill="x", padx=10, pady=(2, 0))
        self._port_type_value = tk.Label(portframe, text="",
                                         font=(AR, 9), bg="#F2F7FF", fg="#5a7ab8",
                                         anchor="w", wraplength=330, justify="left")
        self._port_type_value.pack(fill="x", padx=10, pady=(0, 8))

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

        # خانة تفاصيل إضافية
        info = tk.Frame(left, bg="#F7F7F7", bd=1, relief="solid")
        info.pack(fill="x", pady=(6, 0))
        L(info, "تفاصيل إضافية", 10, True).pack(anchor="w", padx=8, pady=(6, 2))
        self._info_rows = {}
        self._device_info = {}
        for key, label in (("vidpid", "VID:PID"), ("class", "نوع / الدور"),
                           ("driver", "التعريف"), ("state", "الحالة"),
                           ("mode", "الوضع"), ("model", "النموذج")):
            row = tk.Frame(info, bg="#F7F7F7")
            row.pack(fill="x", padx=8, pady=1)
            tk.Label(row, text=A(label + ":"), font=(AR, 9, "bold"),
                     bg="#F7F7F7", fg="#666666", width=10, anchor="e").pack(side="left")
            val = tk.Label(row, text="—", font=(AR, 9), bg="#F7F7F7", fg="#000000",
                           anchor="w")
            val.pack(side="left", padx=(6, 0), fill="x", expand=True)
            self._info_rows[key] = val
        self._set_device_info({})

        # مساحة التمرير للعمود الأيسر (يظهر عند الحاجة)
        def _sync_scroll(_e=None):
            self._left_canv.configure(
                scrollregion=self._left_canv.bbox("all"))
        self._left_canv.bind("<Configure>", _sync_scroll)
        left.bind("<Configure>", _sync_scroll)
        # ربط عجلة الفأرة لكل عنصر داخل العمود الأيسر ليعمل التمرير في أي مكان
        def _bind_wheel(w):
            try:
                w.bind("<MouseWheel>", _wheel, add="+")
            except Exception:
                pass
            for c in w.winfo_children():
                _bind_wheel(c)
        try:
            _bind_wheel(left)
        except Exception:
            pass
        _sync_scroll()

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
        # ألوان متعددة للتيرمنال — كل فئة بلون
        self._term.tag_configure("info", foreground="#111111", font=(MONO, 11))
        self._term.tag_configure("ok", foreground="#0a7d33", font=(MONO, 11, "bold"))
        self._term.tag_configure("err", foreground="#d62828", font=(MONO, 11, "bold"))
        self._term.tag_configure("warn", foreground="#b26b00", font=(MONO, 11))
        self._term.tag_configure("cmd", foreground="#023f92", font=(MONO, 11, "bold"))
        self._term.tag_configure("red", foreground="#d62828", font=(MONO, 11, "bold"))
        self._term.tag_configure("green", foreground="#0a7d33", font=(MONO, 11, "bold"))
        self._term.tag_configure("blue", foreground="#023f92", font=(MONO, 11, "bold"))
        self._term.tag_configure("yellow", foreground="#b26b00", font=(MONO, 11, "bold"))
        self._term.tag_configure("purple", foreground="#6a1fb8", font=(MONO, 11, "bold"))
        self._term.tag_configure("cyan", foreground="#00838f", font=(MONO, 11, "bold"))
        self._term.tag_configure("gray", foreground="#757575", font=(MONO, 10))
        self._term.tag_configure("black", foreground="#111111", font=(MONO, 11))
        # قائمة النسخ: السيريال ومعلومات الجهاز قابلة للنسخ من التيرمنال
        self._term_menu = tk.Menu(self._term, tearoff=0)
        dev_summary = self._device_info if hasattr(self, "_device_info") else {}
        self._term_menu.add_command(label="Copy serial", command=self._copy_term_serial)
        self._term_menu.add_command(label="Copy device info",
                                    command=self._copy_term_device_info)
        self._term_menu.add_separator()
        self._term_menu.add_command(label="Copy selection", command=self._copy_term_selection)
        self._term.bind("<Button-3>", self._show_term_menu)
        self._term.bind("<Control-c>", lambda e: self._copy_term_selection() or "break")
        sb = ttk.Scrollbar(term, command=self._term.yview)
        self._term.configure(yscrollcommand=sb.set)
        self._term.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # ------------------ الشريط السفلي ------------------
        bottom = tk.Frame(self, bg=bg)
        bottom.pack(fill="x", padx=24, pady=(0, 16))

        self._btn_drivers = tk.Button(bottom, text=A("إصلاح التعريفات"),
                                      command=self.on_fix_drivers,
                                      font=(AR, 9), bg="#FFFFFF", fg="#000000",
                                      relief="solid", bd=1, padx=10, pady=4)
        self._btn_drivers.pack(side="left")

        # زر VC++ بقائمة منسدلة صغيرة (x86 / x64)
        self._btn_vcpp = tk.Menubutton(bottom, text="VC++ ▾",
                                       font=(AR, 9, "bold"),
                                       bg="#FFFFFF", fg="#000000",
                                       relief="solid", bd=1, padx=10, pady=4)
        self._vcpp_menu = tk.Menu(self._btn_vcpp, tearoff=0, bg="#FFFFFF",
                                  fg="#000000", activebackground="#e8e8e8",
                                  activeforeground="#000000", font=(AR, 9))
        self._vcpp_menu.add_command(label="(x86)  32-bit", font=(AR, 9),
                                    command=lambda: self._open_vcpp("x86"))
        self._vcpp_menu.add_command(label="(x64)  64-bit", font=(AR, 9),
                                    command=lambda: self._open_vcpp("x64"))
        self._btn_vcpp.configure(menu=self._vcpp_menu)
        self._btn_vcpp.pack(side="left", padx=(8, 0))

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
        self._model_tokens = {}
        if presets_dir:
            try:
                for fn in sorted(os.listdir(presets_dir)):
                    if not fn.endswith(".json"):
                        continue
                    chip = fn.split("_")[0]
                    dev_model = ""
                    try:
                        with open(os.path.join(presets_dir, fn),
                                  "r", encoding="utf-8") as f:
                            d = json.load(f)
                        if isinstance(d, dict):
                            if d.get("chipset"):
                                chip = str(d["chipset"])
                            if d.get("deviceModel"):
                                dev_model = str(d["deviceModel"])
                    except Exception:
                        pass
                    self._chip_map.setdefault(chip, []).append(fn)
                    # احفظ أسماء الموديلات (توكينات) لربط وصف USB بالمعالج
                    if dev_model:
                        for part in re.split(r"[,(/]+", dev_model):
                            for t in re.findall(r"[A-Za-z]\d{1,4}", part):
                                toy = t.lower()
                                if 2 <= len(toy) <= 6:
                                    self._model_tokens.setdefault(toy, set())
                                    self._model_tokens[toy].add(chip)
            except Exception:
                pass
        items = ["Auto (detect)"]
        items += sorted(self._chip_map.keys())
        self.preset_items = items
        self._preset_combo["values"] = tuple(items)
        self._preset_combo.current(0)

    def _detect_chip_from_usb(self, text, model=""):
        """يختار المعالج حسب ما يعرضه USB بالضبط: يطابق أسماء الموديلات
        الموجودة في وصف الجهاز (وصف USB + النموذج) مع ملفات presets،
        ويعيد اسم المعالج أو "" إذا لم يتطابق."""
        if not text and not model:
            return ""
        hay = text.lower() + " " + model.lower()
        best = {}
        for tok, chips in self._model_tokens.items():
            if re.search(r"\b" + re.escape(tok) + r"\b", hay):
                for c in chips:
                    best[c] = best.get(c, 0) + 1
        if not best:
            return ""
        return max(best.items(), key=lambda kv: kv[1])[0]

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
        disp = A(msg) if _AR_RE.search(msg) else msg
        self._term.insert("end", disp + "\n", kind)
        self._term.see("end")

    def _show_term_menu(self, event):
        try:
            self._term_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._term_menu.grab_release()
            except Exception:
                pass

    def _copy_term_selection(self):
        try:
            self._term.focus_set()
            sel = self._term.get("sel.first", "sel.last")
            if not sel:
                self._term.tag_add("sel", "insert wordstart", "insert wordend")
                sel = self._term.get("sel.first", "sel.last")
                self._term.tag_remove("sel", "1.0", "end")
        except Exception:
            sel = ""
        if sel:
            self.clipboard_clear()
            self.clipboard_append(sel)
            self.log(f"تم نسخ النص إلى الحافظة ✓", "green")

    def _copy_term_serial(self):
        info = getattr(self, "_device_info", {}) or {}
        val = (self.current_serial or info.get("serial") or "")
        if not val or val == "—":
            val = ""
        if not val:
            try:
                val = self._serial_var.get().strip()
            except Exception:
                pass
        if val:
            self.clipboard_clear()
            self.clipboard_append(val)
            self.log(f"السيريال نُسخ إلى الحافظة ✓ ({val})", "green")
        else:
            self.log("لا يوجد سيريال معروف بعد — سجّل السيريال أولاً", "warn")

    def _copy_term_device_info(self):
        info = getattr(self, "_device_info", {}) or {}
        rows = []
        for label, key in (("IMEI", "imei"), ("SERIAL", "serial"),
                           ("DEVICE", "device"), ("MODEL", "model"),
                           ("CHIPSET", "chip"), ("VID:PID", "vidpid"),
                           ("PORT", "port"), ("PORT TYPE", "port_type"),
                           ("CLASS", "class"), ("DRIVER", "driver"),
                           ("STATE", "state"), ("MODE", "mode"),
                           ("PROTECTION", "protection")):
            val = info.get(key)
            if val and val != "—":
                rows.append(f"{label}: {val}")
        if rows:
            txt = "\n".join(rows)
            self.clipboard_clear()
            self.clipboard_append(txt)
            self.log("معلومات الجهاز نُسخت إلى الحافظة ✓", "green")
        else:
            self.log("لا توجد معلومات جهاز بعد — اقرأ معلومات الجهاز أولاً", "warn")

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

    def _set_device_info(self, info):
        """يحفظ تفاصيل الجهاز وتعبئة مربعي (الجهاز المتصل) و(البورت المتصل)
        وخانة التفاصيل الإضافية على الشاشة."""
        keys = ("port", "port_type", "device", "vidpid", "class", "driver",
                "state", "mode", "model", "chip", "protection", "version",
                "imei", "serial", "usb_raw")
        self._device_info = {k: (info.get(k) or "—") for k in keys}

        def _do():
            for k, val in self._info_rows.items():
                val.config(text=A(str(self._device_info.get(k, "—"))))
            dev = self._device_info.get("device", "—")
            self._dev_value.config(
                text=A(str(dev)),
                bg="#EAF7EC",
                fg=("#0a7d33" if dev not in ("—", "غير متصل") else "#999999"))
            port = self._device_info.get("port", "—")
            self._port_value.config(
                text=A(str(port)),
                bg="#F2F7FF",
                fg=("#023f92" if port not in ("—", "") else "#999999"))
            ptype = self._device_info.get("port_type", "")
            if ptype and ptype != "—":
                self._port_type_value.config(text=A("النوع: " + str(ptype)))
            else:
                self._port_type_value.config(text="")
        self._schedule(_do)

    # ألوان ملحوظة للأسطر حسب الفئة
    _SUMMARY_COLORS = {
        "port": "blue", "port_type": "blue", "device": "green", "vidpid": "purple",
        "class": "cyan", "driver": "yellow", "state": "black",
        "mode": "red", "model": "purple", "chip": "cyan",
        "protection": "yellow", "version": "green",
        "imei": "purple", "serial": "green",
    }

    def _log_device_summary(self):
        """يعرض ملخص الجهاز في التيرمنال بتنسيق منظم وكل حقل بلون مختلف
        (IMEI، سيريال، حرف الحماية، الوضع، وأدق تفاصيل المعالج)."""
        info = self._device_info
        sep = "=" * 46
        self.log(sep, "cmd")
        self.log(" ⚡ DEVICE INFORMATION — Samsung (Download/Odin)", "cmd")
        self.log(sep, "cmd")
        for label, key in (("IMEI", "imei"), ("SERIAL", "serial"),
                           ("DEVICE", "device"), ("MODEL", "model"),
                           ("CHIPSET", "chip"), ("VID:PID", "vidpid"),
                           ("PORT", "port"), ("PORT TYPE", "port_type"),
                           ("CLASS", "class"), ("DRIVER", "driver"),
                           ("STATE", "state"), ("MODE", "mode"),
                           ("PROTECTION", "protection"),
                           ("VERSION", "version")):
            val = info.get(key)
            if val and val != "—":
                kind = self._SUMMARY_COLORS.get(key, "info")
                self.log("  {:<12}: {}".format(label, val), kind)
        # أدق تفاصيل المعالج (من ملف preset إذا توفر)
        det = self._chip_details()
        if det:
            self.log("  " + "-" * 34, "gray")
            for k, v in det:
                self.log("  {:<12}: {}".format(k, v), "cyan")
        self.log(sep, "cmd")

    def _chip_details(self):
        """يستخرج تفاصيل المعالج الدقيقة من ملفات presets."""
        # حدد المعالج: اختيار واضح أو كشف تلقائي من USB
        chip = ""
        try:
            sel = self._preset_combo.get() or ""
            chip = sel.split(" (")[0] if sel and not sel.startswith("Auto") else ""
        except Exception:
            chip = ""
        files = []
        if chip and chip in self._chip_map:
            files = [os.path.join(self._presets_dir, f)
                     for f in self._chip_map[chip]]
        if not files:
            try:
                det = self._device_info.get("usb_raw", "") + " " + \
                    self._device_info.get("device", "")
                c = self._detect_chip_from_usb(det,
                                               self._device_info.get("model", ""))
                if c in self._chip_map:
                    files = [os.path.join(self._presets_dir, f)
                             for f in self._chip_map[c]]
            except Exception:
                files = []
        if not files:
            try:
                files = self._select_presets("Auto") or []
            except Exception:
                files = []
        if not files:
            return []
        chip = None
        try:
            f = os.path.join(self._presets_dir, os.path.basename(files[0]))
            with open(f, "r", encoding="utf-8") as fh:
                chip = json.load(fh)
        except Exception:
            return []
        if not isinstance(chip, dict):
            return []
        out = []
        if chip.get("chipset"):
            out.append(("SOC / CHIP", str(chip["chipset"]).upper()))
        if chip.get("deviceModel"):
            pass  # يظهر عند MODEL
        if chip.get("exploitMethod"):
            out.append(("EXPLOIT", chip["exploitMethod"]))
        fp = chip.get("firmwareParams")
        if isinstance(fp, dict):
            if fp.get("base"):
                out.append(("BASE ADDR", fp["base"]))
            if fp.get("offset"):
                out.append(("OFFSET", fp["offset"]))
            if fp.get("variant"):
                out.append(("VARIANT", fp["variant"]))
            if fp.get("cpdnUsbBufBase"):
                out.append(("CPDN USB", fp["cpdnUsbBufBase"]))
        if chip.get("status"):
            out.append(("STATUS", chip["status"]))
        return out

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

    def _open_vcpp(self, arch):
        vcpp = self.cfg.get("vcpp", {}) or {}
        url = vcpp.get(arch) or (VCPP_X86_URL if arch == "x86" else VCPP_X64_URL)
        self.log(f"Opening VC++ Redistributable ({arch}) download page...", "cmd")
        self._open(url)

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
        pop.title(AN("نسخة الادمن"))
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
                    messagebox.showerror(AN("تم الإيقاف"),
                                         AN("كلمة مرور خاطئة ثلاث مرات. سيتم إغلاق الاداة."),
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
        # نبني النص الخام كاملاً ثم نشكّله مرة واحدة (لا نركّب قطعاً معكوسة)
        msg = (f"تتوفر نسخة جديدة v{remote_v}\n\n"
               "تحديث إجباري — ستتوقف الاداة الآن.\n"
               "سيفتح صفحة التحميل، قم بتحميل النسخة الجديدة.")
        pop = tk.Toplevel(self)
        pop.configure(bg="#FFFFFF")
        pop.title(AN("تحديث متوفر"))
        pop.transient(self)
        pop.grab_set()
        pop.geometry("440x250")
        tk.Label(pop, text=A("تحديث إجباري"),
                 font=(self.AR, 14, "bold"), bg="#FFFFFF",
                 fg="#c1272d").pack(pady=(16, 4))
        tk.Label(pop, text=A(msg), font=(self.AR, 10), bg="#FFFFFF", fg="#000000",
                 wraplength=400, justify="right").pack(padx=18)
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
        # انسخ السيريال تلقائياً للحافظة عند ظهور المنبثق
        serial_copied = self.current_serial or ""
        try:
            if not serial_copied:
                serial_copied = self._serial_var.get().strip()
        except Exception:
            pass
        self.log("Error: please verify your serial first", "err")
        if serial_copied:
            try:
                self.clipboard_clear()
                self.clipboard_append(serial_copied)
                self.log(f"Copied serial ({serial_copied}) to clipboard — paste it to register", "cmd")
            except Exception:
                pass
        messagebox.showwarning(AN("قم بتسجيل السيريال اولا"),
                               AN("عذراً، يرجى تسجيل السيريال الخاص بجهازك والتحقق منه أولاً."),
                               parent=self)
        return False

    def on_check_serial(self):
        serial = self._serial_var.get().strip()
        if not serial:
            messagebox.showwarning(AN("السيريال"), AN("يرجى إدخال السيريال أولاً."),
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
        pop.title(AN("السيريال غير مسجل"))
        pop.transient(self)
        pop.grab_set()
        pop.geometry("460x240")
        tk.Label(pop, text=A("عذراً، يرجى تسجيل السيريال"),
                 font=(self.AR, 14, "bold"), bg="#FFFFFF",
                 fg="#c1272d").pack(pady=(18, 6))
        tk.Label(pop, text=A("هذا السيريال غير مسجل في السيرفر.\n"
                             "اضغط (تسجيل) لفتح صفحة التسجيل ثم أعد التحقق بعد التسجيل."),
                 font=(self.AR, 10), bg="#FFFFFF", fg="#000000",
                 justify="right", wraplength=420).pack(padx=20)
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
        # قراءة معلومات الجهاز لا تتطلب تسجيلاً للسيريال —
        # التحقق من السيريال يكون فقط عند الضغط على (تفعيل ADB)
        self.log("Working: reading device info...", "info")
        self.set_progress(20, "Scanning device...")
        self._set_busy(True)
        self._run_async(self._read_info_worker)

    def _read_info_worker(self):
        try:
            if self.dryrun:
                time.sleep(1.0)
                self.device_name = "SM-S901B (dryrun)"
                self.device_port = "COM19"
                self._set_device_info({"port": "COM19",
                                       "device": "SM-S901B (dryrun)",
                                       "vidpid": "04E8:685D", "class": "modem",
                                       "driver": "usbser", "state": "OK",
                                       "mode": "Download (Odin)",
                                       "model": "Samsung Galaxy S22",
                                       "chip": "Exynos 2200",
                                       "imei": "351928110012345",
                                       "serial": "R5CTA0000000",
                                       "protection": "D",
                                       "version": self.local_version})
                self._log_device_summary()
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
        self.device_port = ""
        info = {"device": "", "port": "", "vidpid": "", "class": "",
                "driver": "", "state": "", "mode": "", "model": ""}
        # PowerShell: يعدّ كل أجهزة Samsung بخصائص كاملة (بما فيها المنفذ الحقيقي
        # عبر Win32_PnPEntity + Win32_SerialPort) — يحل مشكلة عدم قراءة الـ port
        ps = r'''
$res=@();
# 1) كل أجهزة Samsung عبر Win32_PnPEntity (أشمل من Get-PnpDevice)
$all = Get-CimInstance Win32_PnPEntity 2>$null | Where-Object {
  $_.Name -match 'Samsung|04E8' -or $_.DeviceID -match 'VID_04E8'
};
foreach($x in $all){
  $pidRaw=''; $vidRaw='';
  if($x.DeviceID -match 'VID_04E8&PID_([0-9A-F]{4})'){ $pidRaw='04E8:'+$Matches[1] }
  $com='';
  if($x.Name -match '(COM\d+)'){ $com=$Matches[1] }
  if(-not $com -and $x.DeviceID -match '(COM\d+)'){ $com=$Matches[1] }
  $res += [pscustomobject]@{Name=$x.Name; DevID=$x.DeviceID; Status=$x.Status; Class=''; Driver=''; Com=$com; VidPid=$pidRaw}
} | Out-Null
# 2) احصل كل منافذ COM الموجودة فعلياً في النظام
$serials = @(Get-CimInstance Win32_SerialPort 2>$null | ForEach-Object { $_.DeviceID + '|' + $_.Name })
$serials | ForEach-Object { $res += $_ }
# 3) ابحث عن تعريفات Samsung (Driver + Class الحقيقي)
$drv = @(Get-CimInstance Win32_PnPSignedDriver 2>$null | Where-Object {
  $_.DeviceID -match 'VID_04E8' -or $_.DeviceName -match 'Samsung|Gadget|Modem'
})
$drv | ForEach-Object {
  $res += [pscustomobject]@{
    Name=$_.DeviceName; DevID=$_.DeviceID; Status='';
    Class=$_.DeviceClass; Driver=$_.DriverName; Com=''; VidPid=($_ -match 'VID_04E8&PID_([0-9A-F]{4})' | ForEach-Object { if($_){ $matches[1] } })
  }
} | Out-Null
$res | ForEach-Object {
  if($_ -is [string]){ $_ } else { $_.Name+'|'+$_.Status+'|'+$_.Class+'|'+$_.Com+'|'+$_.Driver+'|'+$_.DevID+'|'+$_.VidPid }
} | Out-String
'''
        try:
            out = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=30,
                creationflags=0x08000000 if IS_WINDOWS else 0,
                encoding="utf-8", errors="replace")
            candidates = []
            for line in (out.stdout or "").splitlines():
                line = line.strip()
                if not line:
                    continue
                if "|" in line:
                    candidates.append(line)
            # مفضّلون: أجهزة فيها COM (class port/modem) ثم اسم فيه Samsung
            def score(item):
                s = 0
                if re.search(r"COM\d+", item, re.IGNORECASE):
                    s += 10
                if "samsung" in item.lower() or "gadget" in item.lower():
                    s += 5
                if "composite" in item.lower():
                    s += 2
                if "modem" in item.lower():
                    s += 1
                return s
            candidates.sort(key=score, reverse=True)
            for line in candidates:
                if re.match(r"^'.*'|^\S.*\|\|", line) and "COM" not in line.upper() and "samsung" not in line.lower():
                    continue
                if not any(k in line.lower() for k in
                           ("samsung", "04e8", "com", "modem", "gadget", "adb")):
                    continue
                self.log("  - " + line, "cyan")
                port = ""
                m = re.search(r"COM\d+", line, re.IGNORECASE)
                if m:
                    port = m.group(0)
                m2 = re.search(r"VID_04E8&PID_([0-9A-F]{4})", line, re.IGNORECASE)
                vidpid = ""
                if m2:
                    vidpid = "04E8:" + m2.group(1).upper()
                if not info["port"] and port:
                    info["port"] = port
                if not info["vidpid"] and vidpid:
                    info["vidpid"] = vidpid
                if not info["device"] and "samsung" in line.lower():
                    name = line.split("|")[0].strip()
                    if name and len(name) > 3:
                        info["device"] = name
                if not info["class"]:
                    m3 = re.search(r"\|([A-Za-z ]+)\|", line)
                    if m3:
                        info["class"] = m3.group(1).strip()
                if not info["driver"]:
                    m4 = re.search(r"\|([^|]*\.sys|[^|]*\.inf|[^|]*driver)", line, re.IGNORECASE)
                    if m4:
                        info["driver"] = m4.group(1).strip()
                if not info["state"]:
                    m5 = re.search(r"\|(OK|Error|Unknown)\|", line)
                    if m5:
                        info["state"] = m5.group(1)
            info["usb_raw"] = " ".join(
                l.split("|")[0] for l in candidates if "samsung" in l.lower())
        except Exception as e:
            self.log("Could not enumerate devices: " + str(e), "warn")

        # تحديد وضع الجهاز من VID:PID والفئة
        mode = self._detect_mode(info)
        if mode:
            info["mode"] = mode
        # النموذج غير متاح عبر USB مباشرة — يُملأ من preset عند التفعيل
        if not info["device"]:
            try:
                out = subprocess.run(["pnputil", "/enum-devices"],
                                     capture_output=True, text=True, timeout=25,
                                     errors="replace", encoding="utf-8")
                for line in (out.stdout or "").splitlines():
                    if SAMSUNG_VID in line.lower() or "samsung" in line.lower():
                        self.log("  " + line, "cyan")
                        m = re.search(r"COM\d+", line, re.IGNORECASE)
                        if m and not info["port"]:
                            info["port"] = m.group(0)
                if info["port"] or any("04e8" in l.lower() for l in (out.stdout or "").splitlines()):
                    info["device"] = "Samsung USB device (Download/Odin)"
            except Exception:
                pass

        self.device_name = info["device"]
        self.device_port = info["port"]
        info["port"] = self.device_port
        # نوع المنفذ على ويندوز
        if "port_type" not in info or not info.get("port_type"):
            info["port_type"] = ("ComPort (Serial)" if self.device_port else
                                 ("USB مباشر (libusb — لا يحتاج COM)" if self.device_name else ""))
        info["model"] = self._resolve_model(info)
        info["chip"] = self._current_chip()
        info["version"] = self.local_version
        info["protection"] = "—"
        self._set_device_info(info)
        if self.device_name or self.device_port:
            self._log_device_summary()
            if not self.device_port:
                self.log("Warning: no COM port found — install Samsung USB driver then retry", "warn")
                self.log("ملاحظة: لم يُعثر على منفذ COM، لكن الجهاز ظاهر — ثبّت تعريفة Samsung وأعد المحاولة", "yellow")
            self.set_progress(40, "Device found")
            self.mark_step(1, True)
            self.log_done(True if (self.device_name or self.device_port) else False)
        else:
            self.log("No Samsung device found — check Download mode and cable ✗", "err")
            self.log("جهازك غير متصل أو غير مدعوم — أدخل وضع Download ثم حاول مجدداً", "red")
            self.set_progress(20, "Device not recognized")
            self.log_done(False)
        self._set_busy(False)

    @staticmethod
    def _detect_mode(info):
        """يحدد وضع الجهاز: Download/Odin، MTP، ADB، Unknown."""
        vidpid = (info.get("vidpid") or "").upper()
        cls = (info.get("class") or "").lower()
        if "04E8:685D" in vidpid or "modem" in cls or "serial" in cls:
            return "Download (Odin)"
        if "adb" in vidpid or "android" in cls or "adb" in (info.get("device") or "").lower():
            return "ADB (Android)"
        if "mtp" in vidpid or "mtp" in cls or "mtp" in (info.get("device") or "").lower():
            return "MTP / Transfer"
        if "composite" in cls:
            return "Composite (Download/ADB)"
        if vidpid:
            return "Samsung USB"
        return "Unknown"

    def _resolve_model(self, info):
        """يكمل النموذج من ملفات presets حسب المعالج المكتشف من USB."""
        chip = info.get("chip") or (self._preset_combo.get()
                                    if hasattr(self, "_preset_combo") else "") or ""
        if chip and chip.startswith("Auto"):
            chip = ""
        if not chip:
            chip = self._detect_chip_from_usb(
                (info.get("device") or "") + " " + (info.get("usb_raw") or ""),
                info.get("model") or "")
        if chip and chip in self._chip_map:
            try:
                fn = self._chip_map[chip][0]
                p = os.path.join(self._presets_dir, fn)
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict) and d.get("deviceModel"):
                    return d["deviceModel"]
            except Exception:
                pass
        return ""

    def _current_chip(self):
        """يعيد اسم المعالج: من USB إن توفر، وإلا المختار في القائمة."""
        try:
            chip = (self._preset_combo.get() or "").strip()
        except Exception:
            return ""
        if chip and not chip.startswith("Auto"):
            return chip
        # Auto: كشف حسب وصف USB (النموذج/اسم الجهاز)
        try:
            dev = self._device_info.get("device", "") or ""
            usb = self._device_info.get("usb_raw", "") or ""
            mdl = self._device_info.get("model", "") or ""
            if dev or usb or mdl:
                det = self._detect_chip_from_usb(dev + " " + usb, mdl)
                if det:
                    return det + " (auto)"
        except Exception:
            pass
        # لا جهاز صريح بعد: المعالج الافتراضي (أول موجود)
        presence = list(self._chip_map.keys())
        return (presence[0] + " (auto)") if presence else "Auto (any)"

    def _read_info_linux(self):
        self.device_name = ""
        self.device_port = ""
        info = {"device": "", "port": "", "vidpid": "", "class": "",
                "driver": "linux", "state": "", "mode": "", "model": ""}

        # 1) افحص lsusb لإيجاد جهاز Samsung (04e8)
        usb_raw = ""
        try:
            out = subprocess.run(["lsusb"], capture_output=True, text=True,
                                 timeout=15)
            text = out.stdout or ""
            for line in text.splitlines():
                if "04e8" in line.lower():
                    self.log("  " + line, "cyan")
                    info["state"] = "present"
                    usb_raw += line + "\n"
                    # مثال: Bus 001 Device 002: ID 04e8:685d Samsung ...
                    m = re.search(r"ID\s+04e8:([0-9a-f]{4})", line, re.IGNORECASE)
                    if m and not info["vidpid"]:
                        info["vidpid"] = "04E8:" + m.group(1).upper()
                    if not info["device"]:
                        name = re.sub(r"^.*?ID\s+[0-9a-f]{4}:[0-9a-f]{4}\s+",
                                      "", line, flags=re.IGNORECASE).strip()
                        if name:
                            info["device"] = name
                    if not info["device"]:
                        info["device"] = "Samsung device (Download/Odin)"
        except Exception:
            pass
        info["usb_raw"] = usb_raw.strip()

        # 2) ابحث عن منفذ tty: اربط كل tty بجهاز Samsung عبر sysfs
        try:
            seats = []
            for pat in ("/dev/ttyUSB*", "/dev/ttyACM*"):
                try:
                    seats += glob.glob(pat)
                except Exception:
                    pass
            for tty in seats:
                base = tty.rsplit("/", 1)[-1]
                try:
                    link = os.path.realpath("/sys/class/tty/" + base + "/device")
                    # تتبّع للأعلى حتى نجد idVendor يخص Samsung (04e8)
                    cur = link
                    vid = ""
                    while cur and cur != "/":
                        vf = os.path.join(cur, "idVendor")
                        if os.path.exists(vf):
                            try:
                                with open(vf, "r") as f:
                                    vid = (f.read().strip() or "").lower()
                            except Exception:
                                vid = ""
                            break
                        cur = os.path.dirname(cur)
                    if vid and vid == SAMSUNG_VID.lower() and not info["port"]:
                        info["port"] = tty
                except Exception:
                    pass
        except Exception:
            pass

        # 3) إن لم يوجد tty، حاول إدراج cdc_acm وتحديث قائمة /dev
        if not info["port"] and IS_LINUX:
            try:
                subprocess.run(["modprobe", "cdc_acm"], capture_output=True,
                               text=True, timeout=10)
            except Exception:
                pass
            try:
                text = (subprocess.run(["ls", "/dev/ttyACM*", "/dev/ttyUSB*"],
                                       capture_output=True, text=True,
                                       timeout=10).stdout or "")
                for m in re.finditer(r"tty(?:ACM|USB)\d+", text):
                    if not info["port"]:
                        info["port"] = "/dev/" + m.group(0)
            except Exception:
                pass

        # نوع المنفذ: تتابع النواة (ACM/USB) إن وجد، وإلا اتصال USB مباشر (libusb)
        port_type = ""
        if info["port"]:
            if re.search(r"ttyACM", info["port"]):
                port_type = "USB CDC ACM (serial)"
            elif re.search(r"ttyUSB", info["port"]):
                port_type = "USB serial / FTDI (ttyUSB)"
            else:
                port_type = "سيريال"
        elif info["device"]:
            port_type = "USB مباشر (libusb — لا يحتاج COM)"
        info["port_type"] = port_type

        if info["device"] and not info["vidpid"]:
            info["vidpid"] = "04E8:????"
        self.device_name = info["device"]
        self.device_port = info["port"]
        info["port"] = self.device_port
        info["mode"] = self._detect_mode(info)
        info["model"] = self._resolve_model(info)
        info["chip"] = self._current_chip()
        info["version"] = self.local_version
        info["protection"] = "—"
        self._set_device_info(info)
        if self.device_name:
            self._log_device_summary()
            if not self.device_port:
                self.log("ملاحظة: لا يوجد منفذ COM ظاهر — الاتصال على Linux يتم عبر USB مباشرة (libusb) وليس عبر منفذ تسلسلي", "yellow")
                self.log("ملاحظة: هذا طبيعي في وضع Download — الزر (تفعيل ADB) يتصل مباشرة بالجهاز عبر USB", "yellow")
            self.set_progress(40, "Device found")
            self.mark_step(1, True)
            self.log_done(True)
        else:
            self.log("No Samsung device found ✗", "err")
            self.log("جهازك غير متصل أو غير مدعوم — أدخل وضع Download ثم حاول مجدداً", "red")
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
            # حل مشكلة البورت: إن لم يكن معروفاً اقرأ معلومات الجهاز أولاً
            if not self.device_port and not self.dryrun:
                if IS_WINDOWS:
                    self._read_info_windows()
                else:
                    self._read_info_linux()
                self._set_device_info(self._device_info)
            else:
                self._set_device_info(self._device_info)

            # كشف المعالج: اختيار واضح من القائمة → ملفه، أو Auto → حسب USB
            selection = (self._preset_combo.get() or "") if not selection else selection
            chosen = selection.split(" (")[0] if selection and not selection.startswith("Auto") else ""
            if not chosen:
                det = (self._device_info.get("usb_raw", "") + " " +
                       self._device_info.get("device", ""))
                chosen = self._detect_chip_from_usb(det,
                                                    self._device_info.get("model", ""))
            # إن لم يتوفر كشف من USB: لا تشغّل كل الملفات، استخدم أول معالج فقط
            # (المستخدم يختار معالجه الأصح من القائمة لاحقاً لتفعيل أفضل)
            auto_mode = bool(selection.startswith("Auto"))
            if not chosen and auto_mode and self._chip_map:
                chosen = sorted(self._chip_map.keys())[0]
                self.log("auto: لم يظهر موديل صريح في USB — سيُستخدم المعالج "
                         f"العام ({chosen}). اختر معالجك من القائمة لدقة أعلى.", "yellow")

            # استخدم ملفات المعالج المكتشف فقط (لا كل الملفات)
            if chosen and chosen in self._chip_map:
                presets = [os.path.join(self._presets_dir, f)
                           for f in self._chip_map[chosen]]
            else:
                presets = self._select_presets("Auto" if auto_mode else selection)

            # فحص دعم الجهاز: يوجد ملف تفعيل → مدعوم، وإلا → غير مدعوم
            if presets is None:
                self.log("Error: presets/ folder not found next to the tool ✗", "err")
                self.set_progress(85, "Exploit failed")
                self._set_busy(False)
                self.log_done(False)
                return
            if not presets:
                self.log("جهازك غير مدعوم ✗ — لا يوجد ملف تفعيل لمعالجك", "red")
                self.log("Unsupported device — no activation file found for your SoC", "err")
                self.set_progress(85, "Unsupported")
                self._set_busy(False)
                self.log_done(False)
                return

            chip_label = (chosen or (selection.split(" (")[0] if selection else "") or "generic")
            self.log("=" * 46, "green")
            self.log(f"الجهاز مدعوم ✓ — ملف المعالج ({chip_label}) متاح", "green")
            self.log(f"Supported device — starting process on {chip_label}", "green")
            self.log("=" * 46, "green")

            total = max(1, len(presets))
            colors = ("blue", "purple", "cyan", "yellow")
            for i, p in enumerate(presets):
                pct = 55 + (30 * (i + 1)) // total
                self.set_progress(pct, f"Exploiting: {chip_label}")
                c = colors[i % len(colors)]
                if len(presets) == 1:
                    self.log(f"→ جارٍ تفعيل المعالج {chip_label} ...", c)
                else:
                    self.log(f"→ جارٍ تفعيل المعالج {chip_label} (نسخة {i + 1})...", c)
                ok, out = self._run_tool("boot", p)
                depth = 0
                all_out = []
                for chunk in out:
                    self.log("  " + chunk, ("gray" if depth % 2 else "info"))
                    all_out.append(chunk)
                    depth += 1
                self._parse_cli_device_info(out)
                if ok:
                    self._adb_success(chip_label)
                    return
            self.set_progress(85, "Exploit failed")
            self._log_boot_failure(chip_label, all_out)
            self._set_busy(False)
            self.log_done(False)
        except Exception as e:
            self.log(f"Error enabling ADB ✗ — {e}", "err")
            self.set_progress(85, "Exploit failed")
            self._set_busy(False)
            self.log_done(False)

    def _log_boot_failure(self, chip_label, out):
        """يعرض سبب فشل التفعيل بدقة: wine على لينكس / رفض المحرك / غير ذلك."""
        text = "\n".join(out or [])
        low = text.lower()
        self.log("None of the presets succeeded ✗", "err")
        if "wine32" in low or "multiarch" in low or "apt-get install wine32" in low:
            self.log("على Linux: بيئة wine32 غير مكتملة — ثبّتها كجذر بالأمر:", "red")
            self.log('  dpkg --add-architecture i386 && apt-get update && '
                     'apt-get install wine32:i386', "cmd")
        if "unauthorized" in low or "invalid execution context" in low:
            self.log("المحرك يرفض العمل تحت Wine (حماية المحرك من المحاكاة).", "red")
            self.log("الحل: شغّل الأداة على نظام Windows حقيقي — لا تفعيل تحت Linux/Wine.", "red")
            self.log(f"المعالج: {chip_label} — الجهاز مدعوم لكن البيئة الحالية غير كافية.", "yellow")
        if "permission" in low or "denied" in low:
            self.log("امنح صلاحية التنفيذ للملف أولاً: chmod +x ExynosCli.exe", "red")
        if "timeout" in low or "not respond" in low:
            self.log("الجهاز لم يستجب — تأكد من كابل جيد ووضع Download", "red")
        self.log("للتفعيل الحقيقي: Windows + كابل أصلي + وضع Download + سيريال مسجّل", "yellow")

    def _select_presets(self, selection):
        if not self._presets_dir:
            return None
        if selection and selection.startswith("Auto"):
            files = sorted(f for f in os.listdir(self._presets_dir) if f.endswith(".json"))
            files.sort(key=lambda f: (1 if f.startswith("generic") else 0, f))
        else:
            files = self._chip_map.get(selection, [])
        return [os.path.join(self._presets_dir, f) for f in files if f]

    def _parse_cli_device_info(self, lines):
        """يستخرج IMEI/السيريال/حرف الحماية/النموذج من مخرجات ExynosCli
        ويعرض ملخصاً محدّثاً في التيرمنال (البيانات قابلة للنسخ)."""
        text = "\n".join(lines or [])
        found = {}
        # أنماط الاحتمال: IMEI, Serial Number, Serial, Protection, Model
        patterns = {
            "imei": [r"(?i)IMEI\s*[:\-=]\s*([0-9]{15,})",
                     r"(?i)\bIMEI\b[^\n]{0,4}([0-9]{15})"],
            "serial": [r"(?i)(?:Serial(?: Number)?|SN)\s*[:\-=]\s*([A-Z0-9_\-]{5,20})",
                       r"(?i)\bSerial\b[^\n]{0,5}([A-Z0-9]{4,20})"],
            "protection": [r"(?i)(?:Protection|FRP|Knox)\s*[:\-=]\s*([A-Z0-9]{1,4})"],
            "model": [r"(?i)(?:Model|MODEL)\s*[:\-=]\s*(SM-[A-Z0-9]{3,8}[A-Z0-9]?)",
                      r"(?i)\b(SM-[A-Z0-9]{3,9})\b"],
        }
        for key, pats in patterns.items():
            for pat in pats:
                m = re.search(pat, text)
                if m:
                    found[key] = m.group(1).strip()
                    break
        if not found:
            return
        for k, v in found.items():
            if v and self._device_info.get(k) in ("—", "", None):
                self._device_info[k] = v
        # إذا وُجد سيريال/IMEI من الجهاز ولم يكن المسجّل معروفاً، احفظهما
        if found.get("serial") and not self.current_serial:
            self.current_serial = found["serial"]
        if found.get("imei") and not self.device_imei:
            self.device_imei = found["imei"]
        # تعبئة الواجهة + ملخص ملون محدّث
        self._set_device_info(self._device_info)
        self.log("=" * 46, "green")
        self.log(" ✓ Device details extracted (copy ready below)", "green")
        self.log("=" * 46, "green")
        colors = {"imei": "purple", "serial": "green", "protection": "yellow",
                  "model": "cyan"}
        for key in ("imei", "serial", "protection", "model"):
            val = self._device_info.get(key)
            if val and val != "—":
                kind = colors.get(key, "info")
                self.log("  {:<12}: {}".format(key.upper(), val), kind)
                if key == "serial":
                    self.clipboard_clear()
                    self.clipboard_append(str(val))
                    self.log("  (السيريال نُسخ إلى الحافظة ✓)", "green")
        self.log("=" * 46, "green")

    def _run_tool(self, action, preset_path):
        exe = find(TOOL_CANDIDATES)
        if not exe:
            return False, ["ExynosCli.exe not found — place the tool next to engine files."]
        if self.dryrun:
            time.sleep(1.2)
            return True, [f"[dryrun] {action} completed OK"]
        cmd = [exe, action]
        # تشغيل ملحق ويندوز (.exe) على لينكس عبر wine
        if not IS_WINDOWS and exe.lower().endswith(".exe"):
            wine_exe = find(["wine", "wine64", "/usr/bin/wine"])
            if not wine_exe:
                return False, ["wine is required on Linux to run ExynosCli.exe — install wine and retry."]
            cmd = [wine_exe, exe, action]
            exe_base = "/" + exe.lstrip("/")
        if IS_WINDOWS:
            exe_base = exe
        try:
            os.chmod(exe_base, (os.stat(exe_base).st_mode | 0o111))
        except Exception:
            pass
        if preset_path:
            cmd += ["--preset", preset_path]
        if self.device_port:
            # على لينكس/ويندوز: صيغة المنفذ المتوقعة من ExynosCli
            port_arg = self.device_port
            if not IS_WINDOWS and self.device_port.startswith("/dev/"):
                port_arg = self.device_port
            cmd += ["--port", port_arg]
        token = self.cfg.get("cli_token", "")
        if token:
            cmd += ["--token", token]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    errors="replace", cwd=os.path.dirname(exe_base))
            output = [raw.rstrip() for raw in proc.stdout if raw.rstrip()]
            proc.wait(timeout=300)
            return proc.returncode == 0, output
        except subprocess.TimeoutExpired:
            proc.kill()
            return False, ["Timeout reached — device did not respond."]
        except PermissionError:
            return False, ["Permission denied on " + exe_base +
                           " — fix file permissions and retry."]
        except Exception as e:
            return False, [f"Failed to run tool: {e}"]

    def _adb_success(self, chip_label):
        self.set_progress(100, "ADB enabled — device ready ✓")
        self.mark_step(3, True)
        self.log(f"ADB enabled successfully on {chip_label} ✓", "ok")
        self.log("Device is now in COMPELSON RECOVERY — ROOTED ADB active", "ok")
        self.log_done(True)
        self._set_busy(False)

    # ---------------------------------------------------------------- تعريفات
    def on_fix_drivers(self):
        self.log("Working: driver repair...", "info")
        pop = tk.Toplevel(self)
        pop.configure(bg="#FFFFFF")
        pop.title(AN("إصلاح التعريفات"))
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
        lines.append("arabic_reshape: " + str(_RESHAPE))
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