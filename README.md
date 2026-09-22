# YAZ adb — أداة تفعيل ADB لأجهزة Samsung Exynos

واجهة رسومية (GUI) بنيت خلفية بيضاء/نص أسود، تغلّف أداة `ExynosCli.exe` لتفعيل ADB
على أجهزة سامسونج المعالجات إكسينوس عبر وضع **Download/Odin**.

---

## 1) التركيب على جهاز المستخدم

ضع ملفات الأديا في مجلد واحد:

```
Enable adb SAMSUNG Exenos/
├── YAZ adb.exe        ← النسخة المبنية (من dist/)
├── config.json         ← بجانبها
├── ExynosCli.exe
├── exynos.dll / drvman.dll / libusb-1.0.dll / Qt5Core.dll / ...
├── data/
└── presets/
```

> الأداة تبحث عن `ExynosCli.exe` و `data/` و `presets/` في مجلدها أو المجلد الأب،
> فلن تعمل إن وضعت `YAZ adb.exe` في مجلد منفصل.

---

## 2) بناء نسخة الويندوز

على جهاز ويندوز مثبت عليه Python 3:

1. ضع هذا المشروع في مجلد على ويندوز.
2. شغّل `build_windows.bat` (أو يدوياً):
   ```
   py -m pip install pyinstaller arabic-reshaper python-bidi
   py -m PyInstaller --noconfirm --onefile --windowed --name "YAZ adb" --add-data "config.json;." yaz_adb.py
   ```
   > المكتبتان `arabic-reshaper` و`python-bidi` ضروريتان لعرض النص العربي بشكل صحيح داخل الواجهة.
3. الناتج: `dist\YAZ adb.exe` — انسخه لمجلد الأداة الأصلي.

بديل سريع للتجربة بدون بناء: `python yaz_adb.py --dryrun` (وضع تجريبي دون تشغيل الاستغلال).

---

## 3) رفع ملفات السيرفر إلى GitHub (التحقق من السيريال + التحديث الإجباري)

1. أنشئ مستودعاً عاماً على GitHub، مثلاً `YAZ-edb-updates`.
2. ارفع ملفي المجلد `server/` كما هما:
   - `server/serials.json` — قائمة السيريالات المسجلة:
     ```json
     { "serials": ["SN-1111", "SN-2222"] }
     ```
   - `server/version.json` — نسخة الأداة (للتحديث الإجباري):
     ```json
     {
       "version": "1.0.0",
       "mandatory": true,
       "url": "https://github.com/USER/REPO/releases/download/v1.0.0/YAZ_adb.exe"
     }
     ```
3. افتح `config.json` داخل الأداة وضع الروابط المباشرة (Raw):
   ```json
   "server": {
     "serials_url": "https://raw.githubusercontent.com/USER/REPO/main/server/serials.json",
     "version_url": "https://raw.githubusercontent.com/USER/REPO/main/server/version.json"
   }
   ```
4. عند وجود نسخة جديدة: غيّر `version` في `server/version.json`
   وارفع `YAZ adb.exe` الجديدة في Releases — **الأداة ستتوقف فوراً مع إشعار تحديث إجباري**.

> ملاحظة: Map التحديث الإجباري يعمل حتى لو كانت `version_url` غير متاحة — تعمل الأداة محلياً
> وتظهر تحذيراً، أما التحقق من السيريال فيتطلب اتصالاً فعلياً بالسيرفر.

---

## 4) طريقة الاستخدام (الخطوات رقم 1-2-3 داخل الأداة)

1. أطفئ الجهاز مع بقاء الكابل غير موصول.
2. اضغط مطولاً **Volume Down + Volume Up** أثناء توصيل كابل USB → تظهر شاشة تحذير الـ Download → اضغط **Volume Up** للتأكيد.
3. داخل الأداة:
   - أدخل السيريال → **تحقق** (يتم التحقق من السيرفر).
   - **قراءة معلومات الجهاز** → تكتشف الجهاز ومنفذ COM.
   - اختر نوع المعالج (اختصار فقط مثل `exynos7884`) أو **Auto** → **تفعيل ADB**.
4. عند النجاح يدخل الجهاز **COMPELSON RECOVERY** مع **ADB جذر** مفعّل.

> الـ Terminal بالشاشة اليمنى **إنجليزي بالكامل** بخط كود (SF Mono/Menlo على ماك،
> Consolas/Cascadia على ويندوز) ويُظهر كل سطر العملية والنتيجة.
> أثناء أي عملية يظهر: `Working: ...` ثم `Ready • DONE ✓` أو `Error • FAILED ✗`.

---

## 5) الأزرار والوظائف

| الزر | الوظيفة |
|---|---|
| قراءة معلومات الجهاز | فحص الجهاز المتصل في وضع Download ومنفذ COM |
| تفعيل ADB | تشغيل الاستغلال عبر `ExynosCli.exe` مع المعالج المختار |
| قائمة نوع المعالج | اختصارات فقط: `exynos7884`, `exynos990`, `exynos2400`... أو `Auto` |
| إصلاح التعريفات | نافذة اختيار: تحميل تعريفة سامسونج / فحص وإصلاح عبر `pnputil` |
| تحقق / تسجيل | التحقق من السيريال في السيرفر / فتح صفحة التسجيل |
| Telegram ✈ | https://t.me/Yazunlo |
| Instagram | https://instagram.com/yaz.salaqq |
| Facebook | https://facebook.com/yazsalaq |

---

## 6) ملفات المشروع

```
YAZ_adb/
├── yaz_adb.py          ← التطبيق الرئيسي
├── config.json         ← الإعدادات (روابط السيرفر، السوشيال، التوكن)
├── build_windows.bat   ← بناء exe للويندوز
├── server/
│   ├── serials.json    ← السيريالات المسجلة (ترفع لـ GitHub)
│   └── version.json    ← نسخة الأداة (تحديثات إجبارية)
├── README.md
└── dist/YAZ adb.exe    ← الناتج بعد البناء
```

---

## ملاحظات أمان

- `ExynosCli.exe` هي أداة تابعة لجهة ثالثة (متحدة مع أصل ثغرة CPDN/DWC3)؛ التوزيع على مسؤوليتك.
- الأداة لا ترسل أي معلومات سوى طلب قائمة السيريالات والنسخة من الروابط المحددة في `config.json`.