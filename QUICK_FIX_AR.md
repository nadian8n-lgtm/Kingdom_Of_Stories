إصلاح سريع لإلغاء GitHub Actions وخطأ IndentationError في build_site.py
التشخيص المؤكد لخطأ السجل الأخير
من لقطة الشاشة:

فشل fetch_news.py و check_site.py و adsense_audit.py كلها بنفس الخطأ:
File "/home/runner/work/Nexus_Press/Nexus_Press/build_site.py", line 351
  return f'<section class="nl-band">...</section>'
IndentationError: expected an indented block after 'if' statement on line 350
السبب: نسخة build_site.py المرفوعة حالياً على GitHub معطوبة في دالة newsletter() (السطر 350–351 بدون 4 مسافات بعد if kind == "band":)، كما أن نسخة adsense_audit.py على GitHub قديمة (import build_site بالسطر 26 بدل 30).

الحل المباشر خطوة بخطوة
ارفع كل ملفات الحزمة المصححة إلى مستودعك على GitHub (ولا ترفع فقط ملفاً واحداً):

build_site.py (مصحح ونظيف تماماً)
fetch_news.py (تحديث 2026-11-16d + توحيد فحص الحدة والصور)
check_site.py (فحص القسم الفعلي من articles.json بدل الاعتماد على بادئة الـ ID)
adsense_audit.py (إصلاح مقارنة تكرار الصور)
curate.py و books_library.py و legal.py و style.css و articles.json
.github/workflows/auto_news.yml (في مساره .github/workflows/)
ثم شغّل Actions → Nexus Press Auto Publisher → Run workflow بـ count = 8 و regen_images = none.

التشخيص المؤكد
من لقطة الشاشة، السبب واضح:

Duration shown: cancelled ... in 1h 0m 16s
Error: The operation was canceled.
إلغاء دورة كاملة بعد نحو 60 دقيقة يعني أن سير العمل القديم كان يوقف الوظيفة عند حد 60 دقيقة، قبل وصوله إلى خطوة البناء والدفع. لذلك ضاعت المواد التي أنشأها البوت في تلك الدورة.

التحذير الأصفر:

Node.js 20 is deprecated ... forced to run on Node.js 24

ليس هو سبب الإلغاء، لكنه تم تحديثه أيضاً حتى يختفي التحذير.

ما تم إصلاحه
.github/workflows/auto_news.yml

timeout-minutes: 350 بدل الحد القديم 60 دقيقة.
actions/checkout@v7 وactions/setup-python@v7 وactions/setup-node@v7.
Node.js 24 بدل 20.
إصلاح مسار حزمة @google/genai عبر NODE_PATH.
لا يُرفع الموقع إذا فشل فحص الروابط/الصور أو تدقيق أدسنس.
fetch_news.py

ميزانية زمنية صلبة داخل البرنامج: لا يبدأ مقالاً جديداً بعد RUN_BUDGET_MIN (150 دقيقة افتراضياً).
كل طلب HTTP ومزود صور يراقب الوقت المتبقي؛ إذا اقتربت النهاية يتوقف ويستخدم الرسم المحلي السريع بدل انتظار مزود بطيء.
الحد الأقصى المضمون لميزانية التشغيل 300 دقيقة، حتى لا يتجاوز حد GitHub ولا تُلغى الدورة.
خيار fill في الواجهة صار له معنى صحيح داخل الكود.
إصدار خط النشر: 2026-11-16c.
أسرع طريقة لتطبيق الإصلاح
ارفع فقط الملفين التاليين إلى المستودع، مع الحفاظ على مسار سير العمل:

.github/workflows/auto_news.yml
fetch_news.py
ثم:

افتح Actions → Nexus Press Auto Publisher → Run workflow.
اختر count = 6 وregen_images = none.
تأكد أن أول السجل يحتوي:
pipeline: 2026-11-16c | regen images: none
run budget: 150 min (the run always builds and pushes before this limit)
وفي نهاية الدورة الجيدة ستظهر:

site check OK
AdSense audit OK
pushed
ملاحظة مهمة
الملف المضغوط يحتوي حزمة المشروع التي أرسلها المستخدم مع التعديلات. عند الرفع اليدوي إلى GitHub من الواجهة، لا ترفع الملف المضغوط نفسه؛ ارفع الملفين المذكورين أعلاه إلى مسارهما الصحيح. كما يجب رفع fetch_news.py إلى الجذر، وauto_news.yml إلى .github/workflows/.

ملف CHANGES.diff يوضح الفروق بالضبط، وQUICK_FIX_AR.md هو هذا الدليل.
