#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""بيّن hardened للـ exe الواحد:
  1) جهّز مجلد مؤقت: config.json (عادي أو أدمن) + ExynosCli.exe + DLLs + presets + data
  2) ضغّطه وشفّره في payload.bin عبر _bundle.build_payload
  3) شغّل PyInstaller --onefile --windowed --key <AES> مع تضمين payload.bin فقط
Invoke (Windows):  py -3 build_hardened.py [normal|admin]
Invoke (Wine)  :  wine C:\\python31\\python.exe build_hardened.py normal
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_ROOT = os.path.normpath(os.path.join(HERE, ".."))  # مجلد حزمة المحرك (جوار YAZ_adb)
OUTROOT = os.path.join(HERE, "dist_hardened")
WORK = os.path.join(HERE, "build_hardened")
AES_KEY = "YAZ-ADB-H7G3X9KQ-MN2P4WVZ-B8C6D1F0-5A7E9J3L"


def log(msg):
    print("[build]", msg)


def find_py():
    # أولوية: مفسّر ويندوز ضمن Wine (قيد التشغيل على الـ bat) أوسطر الأوامر
    candidates = [
        sys.executable,
        os.environ.get("PYTHON"),
    ]
    for c in candidates:
        if c:
            return c
    return sys.executable


def build(mode="normal"):
    if mode not in ("normal", "admin"):
        log("Usage: build_hardened.py [normal|admin]")
        return 2

    if not os.path.exists(os.path.join(ENGINE_ROOT, "ExynosCli.exe")):
        log("ERROR: engine files not found at %s" % ENGINE_ROOT)
        return 1
    if not os.path.exists(os.path.join(ENGINE_ROOT, "presets")):
        log("ERROR: presets/ not found")
        return 1
    if not os.path.exists(os.path.join(ENGINE_ROOT, "data")):
        log("ERROR: data/ not found")
        return 1

    cfg_src = "config_admin.json" if mode == "admin" else "config.json"
    if not os.path.exists(os.path.join(HERE, cfg_src)):
        log("ERROR: %s not found in %s" % (cfg_src, HERE))
        return 1

    stage = tempfile.mkdtemp(prefix="yazadb_stage_")
    try:
        # 1) تجميع كل شيء في مجلد مؤقت
        log("staging engine files -> %s" % stage)
        shutil.copy2(os.path.join(ENGINE_ROOT, "ExynosCli.exe"), stage)
        for fn in os.listdir(ENGINE_ROOT):
            if fn.lower().endswith(".dll"):
                shutil.copy2(os.path.join(ENGINE_ROOT, fn), stage)
        shutil.copytree(os.path.join(ENGINE_ROOT, "presets"),
                        os.path.join(stage, "presets"))
        shutil.copytree(os.path.join(ENGINE_ROOT, "data"),
                        os.path.join(stage, "data"))
        shutil.copy2(os.path.join(HERE, cfg_src),
                     os.path.join(stage, "config.json"))
        # FRP ADB (hh): adb.exe + dlls + Frp.bin — ضمن نفس الحزمة
        hh = os.path.join(ENGINE_ROOT, "hh")
        if os.path.exists(hh):
            for fn in ("adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll", "Frp.bin"):
                src = os.path.join(hh, fn)
                if os.path.exists(src):
                    shutil.copy2(src, stage)
                    log("staging FRP: %s" % fn)
                else:
                    log("warn: FRP file missing %s" % fn)

        # 2) تشفير الحزمة
        sys.path.insert(0, HERE)
        import _bundle
        payload_path = os.path.join(stage, _bundle.PAYLOAD_NAME)
        _bundle.build_payload(stage, payload_path)
        log("payload built: %s (%.1f KB)" % (
            payload_path, os.path.getsize(payload_path) / 1024.0))

        # 3) PyInstaller
        name = "YAZ adb ADMIN" if mode == "admin" else "YAZ adb"
        os.makedirs(OUTROOT, exist_ok=True)
        target_exe = os.path.join(OUTROOT, name + ".exe")
        if os.path.exists(target_exe):
            os.remove(target_exe)
        for stale in os.listdir(OUTROOT):
            if stale.startswith(name):
                s = os.path.join(OUTROOT, stale)
                if os.path.isdir(s):
                    shutil.rmtree(s, ignore_errors=True)

        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean",
            "--onefile", "--windowed",
            "--uac-admin",
            "--name", name,
            "--key", AES_KEY,
            "--icon", os.path.join(HERE, "yaz_bolt.ico"),
            "--hidden-import", "arabic_reshaper",
            "--hidden-import", "bidi",
            "--hidden-import", "bidi.algorithm",
            "--add-binary", payload_path + ";.",
            "--add-data", os.path.join(HERE, "yaz_bolt.ico") + ";.",
            "--distpath", OUTROOT,
            "--workpath", WORK,
            "--specpath", WORK,
            os.path.join(HERE, "yaz_adb.py"),
        ]
        log("running: " + " ".join(cmd))
        env = dict(os.environ)
        env["PYTHONPATH"] = HERE
        code = subprocess.call(cmd, cwd=HERE, env=env)
        if code != 0:
            log("PyInstaller failed with code %d" % code)
            return code

        exe_out = os.path.join(OUTROOT, name + ".exe")
        log("DONE: %s (%d bytes)" % (
            exe_out, os.path.getsize(exe_out) if os.path.exists(exe_out) else 0))
        return 0
    finally:
        shutil.rmtree(stage, ignore_errors=True)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("YAZADB_MODE", "normal")
    sys.exit(build(mode))