# -*- coding: utf-8 -*-
"""حزمة مشفرة (payload.bin) — كل ملفات المحرك والـ presets وdata وconfig
تُضغط ثم تُشفّر AES-GCM قبل دمجها داخل الـ exe الواحد.

المفتاح يستمد عبر PBKDF2-HMAC-SHA256 من كلمة سر ثابتة + ملح ثابت.
الملف نفسه (payload.bin) يُضمّن داخل الـ exe ثم يُفك ويُستخرج مؤقتاً عند التشغيل.

هذه الوحدة مشتركة بين أداة البناء (build_hardened.py) والتطبيق (yaz_adb.py).
"""

import hashlib
import io
import os
import zipfile

PAYLOAD_NAME = "payload.bin"
PAYLOAD_MAGIC = b"YAZP"
PAYLOAD_VERSION = 1

# كلمة السر + الملح ثابتان ويُستخدمان في البناء والتشغيل معاً.
PASSPHRASE = "YazAdb@2026!Exynos#H7G3X9KQ$MN2P4WVZ"
SALT = hashlib.sha256(b"yaz-adb-locked-bundle").digest()[:16]


def _derive_key() -> bytes:
    return hashlib.pbkdf2_hmac("sha256", PASSPHRASE.encode("utf-8"),
                               SALT, 200_000, 32)


def build_payload(engine_root: str, out_path: str) -> str:
    """يجمع engine_root (config.json + ExynosCli.exe + DLLs + presets + data)
    في zip، يشفّره AES-GCM، ويكتب payload.bin."""
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(engine_root):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, engine_root).replace("\\", "/")
                z.write(full, rel)

    data = buf.getvalue()
    key = _derive_key()
    nonce = get_random_bytes(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ct, tag = cipher.encrypt_and_digest(data)

    with open(out_path, "wb") as f:
        f.write(PAYLOAD_MAGIC)
        f.write(bytes([PAYLOAD_VERSION]))
        f.write(nonce)
        f.write(tag)
        f.write(ct)

    return out_path


def unpack_payload(payload_path: str, dest_dir: str) -> bool:
    """يفك تشفير payload.bin ويستخرج محتوياته في dest_dir.
    يرجع True عند النجاح."""
    from Crypto.Cipher import AES

    try:
        with open(payload_path, "rb") as f:
            blob = f.read()
        if not blob.startswith(PAYLOAD_MAGIC):
            return False
        ver = blob[len(PAYLOAD_MAGIC)]
        if ver != PAYLOAD_VERSION:
            return False
        nonce = blob[len(PAYLOAD_MAGIC) + 1: len(PAYLOAD_MAGIC) + 13]
        tag = blob[len(PAYLOAD_MAGIC) + 13: len(PAYLOAD_MAGIC) + 29]
        ct = blob[len(PAYLOAD_MAGIC) + 29:]

        cipher = AES.new(_derive_key(), AES.MODE_GCM, nonce=nonce)
        try:
            plain = cipher.decrypt_and_verify(ct, tag)
        except ValueError:
            return False

        with zipfile.ZipFile(io.BytesIO(plain)) as z:
            z.extractall(dest_dir)
        return True
    except Exception:
        return False