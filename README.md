تحديث نكسوس بريس (2026-11-16d) — إصلاح خطأ build_site.py + مزامنة ملفات البوت + فجوات الفحص والصور
سبب الخطأ الظاهر في لقطة الشاشة (IndentationError في build_site.py)
جميع الخطوات الثلاث في GitHub Actions فشلت عند استيراد build_site:

fetch_news.py:55 -> import build_site
check_site.py:8 -> import build_site
adsense_audit.py:26 -> import build_site
والسبب: النسخة الموجودة حالياً على GitHub من ملف build_site.py فيها خطأ إزاحة (IndentationError) في السطر 350–351 داخل دالة newsletter():

IndentationError: expected an indented block after 'if' statement on line 350
return f'<section class="nl-band">...</section>'
كما أن adsense_audit.py على GitHub مختلف عن نسخة الحزمة (import build_site في السطر 26 بدل السطر 30)، مما يعني أن المستودع على GitHub لم يتلقَّ جميع ملفات التحديث السابقة متزامنةً.

الإصلاحات المضافة في هذه النسخة (2026-11-16d)
build_site.py:

دالة newsletter() نظيفة وبإزاحة صحيحة 100% (لا IndentationError).
توحيد حد حجم الصورة في ensure_images ليصبح 8192 بايت (8 KB) مطابقاً تماماً لبوابة adsense_audit.py (بدل 4096).
إضافة شبكة أمان داخلية عبر Pillow لرسم صورة WebP حادة ومعتمدة تلقائياً إذا غاب illustrations.py عن المستودع.
إنشاء robots.txt وsitemap.xml حتى عند التشغيل المحلي بدون SITE_URL.
check_site.py:

تحديد قسم المقال من articles.json (id_to_cat) بدل الاعتماد على بادئة اسم الملف (page.name.split("-")[0])، لأن curate.py ينقل المقالات بين الأقسام دون تغيير الـ id.
فحص الروابط المغربية داخل قسم المصادر .sources حصراً وتجاهل query string (?v=...) عند عدّ الصور المكررة.
fetch_news.py و adsense_audit.py:

توحيد قياس الحدة SHARP_MIN = 80 على الصورة الكاملة في fetch_news.py ليتطابق 100% مع adsense_audit.py (بدل 30 على نسخة مصغرة).
تخطي تصنيف LLM في curate.run() إذا انتهت ميزانية الوقت قبل بدء المعالجة.
إصلاح فحص تكرار ملف الصورة في adsense_audit.py ليقارن ضد بقية المقالات فقط (a_other != aid).
الملفات المطلوب رفعها إلى GitHub (جميعها في الحزمة)
ارفع كامل ملفات الحزمة إلى جذر المستودع على GitHub (مع إبقاء auto_news.yml داخل .github/workflows/):

build_site.py
fetch_news.py
check_site.py
adsense_audit.py
curate.py
books_library.py
legal.py
style.css
articles.json
.github/workflows/auto_news.yml
هذا التحديث يعالج مباشرة الخطأ الأحمر الذي ظهر في GitHub Actions:

SITE CHECK FAILED
articles/ar_economy-....html -> missing ../images/....svg
category-ar_tech.html -> missing images/....svg
ما الذي تغيّر؟
كل الأقسام الثمانية تظهر دائماً في قائمة الموقع وفي التذييل: أخبار المغرب، أخبار المدن، الأخبار الدولية، اقتصاد، تكنولوجيا، رياضة، فن وثقافة، المكتبة الرقمية المجانية. لا يُخفى أي قسم بعد الآن.
إصلاح ذاتي للصور المفقودة: قبل بناء أي صفحة، يتحقق build_site.py من كل صورة. إذا كانت الصورة مفقودة أو بصيغة SVG قديمة، يرسم لها نسخة WebP أصلية حادة ويعيد كتابة المسار في articles.json. لذلك خطأ «missing .svg» لا يمكن أن يوقف البناء مرة أخرى.
بوابة مراجعة أدسنس جديدة adsense_audit.py تفحص: التكرار، الصور المتشابهة أو الضبابية، الصور بلا حقوق، المقالات بلا مصادر، الأخبار الأجنبية داخل قسم المغرب، المقالات اللاتينية، الكلمات المحظورة، الصفحات القانونية الناقصة. تعمل تلقائياً بعد check_site.py.
قسم المكتبة الرقمية لم يبق فارغاً: أُضيفت ثلاث مقالات حقيقية (ذكاء اصطناعي، بايثون، تطوير الويب) مبنية على كتب مجانية قانونية من مستودع Free Programming Books، مع الروابط والرخص.
صفحتان قانونيتان جديدتان: editorial-policy.html (سياسة التحرير والذكاء الاصطناعي والتصحيحات) وterms.html (شروط الاستخدام)، وروابطهما في التذييل. هذه من أهم ما ينقص مواقع أدسنس.
تنظيف المحتوى: حُذفت مقالات لا تصلح للمراجعة (خبر طقس أمريكي داخل قسم المغرب، مقالات مشاهير وترفيه رخيص، مقال بمصدر مغربي داخل قسم دولي، مقال بلا مصدر). أصبح عدد المقالات 68، وكل مقال له صورة أصلية ومصدر مذكور.
ميزانية زمنية صلبة للدورة (RUN_BUDGET_MIN) — هذا هو إصلاح الإلغاء الأخير: بعد 150 دقيقة يتوقف fetch_news.py عن بدء مقالات جديدة، ويكمل البناء والرفع بما جُهّز. كما يراقب كل طلب HTTP ومزود صور الوقت المتبقي، فلا يستهلك مزود بطيء بقية الدورة. سابقاً كان GitHub يقتل الوظيفة عند 60 دقيقة قبل خطوة الرفع، فتضيع الدورة كاملة (ظهر في السجل: cancelled ... in 1h 0m 16s / Error: The operation was canceled).
مهلة الوظيفة أصبحت 350 دقيقة في auto_news.yml بدل السطر الشرطي القديم (... && 340 || 60)، والتشغيل التلقائي كل ساعتين بدل كل ساعة، والتشغيل التلقائي يعمل بـ regen_images = none (الباني يرسم أي صورة ناقصة تلقائياً)، فلا يستهلك الوقت في إعادة الصور.
رفع رقم الإصدار إلى 2026-11-16c لتتأكد من أن الكود الجديد هو الذي يعمل، وتحديث إجراءات GitHub إلى checkout@v7 وsetup-python@v7 وsetup-node@v7 مع Node.js 24 لإزالة تحذير إهمال Node.js 20.
الملفات التي ترفعها (كاملة، دون تعديل يدوي)
الملف	المسار في المستودع
fetch_news.py	fetch_news.py
build_site.py	build_site.py
curate.py	curate.py
legal.py	legal.py
check_site.py	check_site.py
adsense_audit.py	adsense_audit.py
articles.json	articles.json
books_library.py	books_library.py (يستورده fetch_news.py، لا تشغيل بدونه)
style.css	style.css
auto_news.yml	.github/workflows/auto_news.yml
لا ترفع أي صورة. البناء سيرسم تلقائياً أي صورة ناقصة ويحفظها في images/.

خطوات الرفع
افتح مستودعك على GitHub.
اضغط Add file ثم Upload files.
اسحب الملفات العشرة أعلاه مع الحفاظ على المسار (خصوصاً ملف سير العمل داخل .github/workflows/).
اكتب في خانة الوصف: إصلاح الأقسام والصور + بوابة أدسنس.
اضغط Commit changes.
انتظر دقيقة، ثم افتح تبويب Actions → Nexus Press Auto Publisher → Run workflow:
count: 8
regen_images: none
تأكد من ظهور الأسطر التالية في أول السجل:
pipeline: 2026-11-16c | regen images: none
run budget: 150 min (the run always builds and pushes before this limit)
وإذا كان الملف قديماً سيظهر 2026-11-16b أو أقدم، ومعناه أن الرفع لم ينجح.
لماذا count = 8 وregen_images = none؟ لأن كل مقال يمر بثلاث محاولات كتابة ثم يولّد صورة قد تنتظر ثلاث دقائق عند المزوّد المجاني. مع count = 36 وregen_images = fill استهلكت ثلاث مقالات ساعة كاملة. ابدأ بـ 8، وكرّر الدورة ثلاث مرات (8 + 8 + 8) لملء الأقسام، ثم ارجع إلى count = 6.

ماذا تتوقع في السجل؟
pipeline: 2026-11-16c | regen images: none
run budget: 150 min (the run always builds and pushes before this limit)
...
published (8/8): ...
repaired N missing/placeholder image reference(s)
site built: ...
site check OK: ... pages, all internal links and images exist
AdSense audit OK: no duplicates, no broken/misclassified/dangerous content.
pushed
إذا وصلت ميزانية الوقت قبل إتمام العدد ستجد بدل آخر سطر:

run budget reached (150 min): stopping generation and building what is ready (5/8 new articles this run)
ومع ذلك يستمر البناء والرفع، فلا تُفقد أي مقالة كُتبت. أما تحذيرات single-source article وno canonical URL فليست فشلاً: الأولى تنبيه لجودة التحرير، والثانية تختفي تلقائياً في Actions لأن GITHUB_REPOSITORY يضبط العنوان القانوني.

تحذير قوي قبل إرسال الموقع إلى أدسنس
الموقع الآن أنظف بكثير، لكن هذا لا يعني أنه جاهز للقبول اليوم. أسباب الرفض الحقيقية المتبقية هي:

قسم «أخبار المدن» ما زال فارغاً (0 مقال)، وقسم «أخبار المغرب» فيه مقالان فقط. صفحة قسم فارغة أو شبه فارغة = «محتوى ضعيف» في نظر جوجل.
معظم المقالات تعتمد على مصدر واحد (BBC أو Guardian) وهي إعادة صياغة لخبر منشور. جوجل يرفض هذا تحت بند Scraped content / Low value content حتى لو كانت الصياغة سليمة.
الموقع ينشر كل ساعة عدداً كبيراً من المقالات الآلية. هذا النمط يُقرأ كموقع مولد آلياً، وهو من أسرع أسباب الرفض.
لا ترسل طلب أدسنس قبل تحقق كل ما يلي:

تشغيل خط النشر عدة مرات حتى يصبح في كل قسم رئيسي 15 مقالاً حقيقياً على الأقل (المغرب، المدن، العالم، اقتصاد، تكنولوجيا، رياضة، فن).
أن يكون في قسم المدن 10 أخبار مغربية موثقة على الأقل، بلا أسماء أشخاص ولا اتهامات.
أن يضيف كل مقال تحليلاً أصلياً وسياقاً لا يوجد حرفياً في المصدر، وأفضل أن يعتمد على مصدرين على الأقل.
مراجعة يدوية لعشر مقالات عشوائية: هل توجد جملة واحدة منقولة من المصدر؟ هل الأسماء والأرقام صحيحة؟ هل الصورة مناسبة للخبر؟
إيقاف النشر المؤقت أو تقليله إلى مقالين أو ثلاثة يومياً قبل المراجعة، ثم العودة بعد القبول.
التأكد من أن about.html وeditorial-policy.html وterms.html وprivacy-policy.html تعمل، وأن بريد التواصل يستقبل الرسائل فعلاً.
إذا أرسلت الموقع اليوم بقسم مدن فارغ ومقالات مصدرها واحد، فالرفض شبه مؤكد. الإصلاحات أعلاه تمنع الأعطال التقنية والصور المكسورة، لكنها لا تستبدل المحتوى الأصلي المطلوب للقبول.

بصمات MD5 للملفات
56ac6bfe04ee07164ed69ebb2d893141  fetch_news.py
bad2f610d0fa136a971f6a1722033533  build_site.py
54488b16cf43504212503da0cdc2741a  curate.py
454b5661a5013aeffd2beaa15ab99bfa  legal.py
0acb264cfef77cc550ecc8ac7f6f95d8  check_site.py
30714f7695ea783de6f0ec6f94634e0c  adsense_audit.py
0a1a104f3808c5245d38112829af164e  articles.json
a9718af13e54a27a876e1d5daf6d7480  .github/workflows/auto_news.yml
fa30138a0be054573d6386a82523016a  books_library.py
361506f245de9a4caa3fecd6a6e3a706  style.css
a8222d7f946ec28674faf6e6c007c625  QUICK_FIX_AR.md
