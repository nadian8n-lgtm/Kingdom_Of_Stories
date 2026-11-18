# دليل التسليم — مملكة الأسرار Kingdom Of Secrets

## 1. ما الموجود في هذا الأرشيف

| المجلد/الملف | ماذا يعمل به |
| --- | --- |
| `Nexus_Press-UPDATE/` | **هذا هو ما ترفعه إلى GitHub.** انسخ محتواه (لا المجلد نفسه) إلى جذر المستودع. |
| `Nexus_Press-CODES/` | متصفح أكواد للقراءة فقط: كل كود في صفحة مستقلة كاملة من الأول للآخر، مع نسخة خام قابلة للتنزيل. **لا ترفعه إلى GitHub.** |
| `DELETE_OLD_AR.md` | القائمة الدقيقة لكل ما كان خاصاً بالجريدة القديمة ويجب حذفه. |
| `DELETE_OLD_AR-articles.txt` / `DELETE_OLD_AR-images.txt` | الأسماء الكاملة للمقالات والصور القديمة. |
| `DELIVERY_AR.md` | هذا الدليل. |
| `MD5SUMS.txt` | بصمات التحقق من أن كل ملف وصل كاملاً. |

## 2. قبل الرفع

1. اقرأ `DELETE_OLD_AR.md` واحذف من المستودع كل الملفات المذكورة فيه (أهمها صفحات `category-ar_world/economy/sports/local/cities` و`city-*.html` والـ56 مقالاً القديمة وصور الجريدة و`cities.py` و`reclassify_archive.py`).
2. احتفظ بـ`Nexus_Press-NEWS-BACKUP/` على جهازك كنسخة احتياطية، لكن **لا ترفعه** إلى المستودع.
3. لا تحذف `news-state.json` ولا `curate.py` ولا `googlecce3f858fe11b667.html` (تحقق Search Console).

## 3. الرفع من متصفح GitHub (سحب وإفلات فقط)

1. افتح المستودع على github.com ثم افتح مجلد `Nexus_Press-UPDATE` المُستخرج.
2. حدّد **كل ما بداخله** (الملفات + المجلدات `.github` و`admin` و`articles` و`deals` و`images`)، واسحبها إلى صفحة المستودع حتى يظهر مربع **Drop files to upload**. لا تعدّل أي ملف يدوياً على GitHub.
3. انتظر اكتمال الرفع (تظهر قائمة الملفات في أعلى الصفحة).
4. في رسالة الالتزام اكتب: `تحديث مملكة الأسرار: قصص وأفلام ووسوم` ثم **Commit directly to the `main` branch**.
5. تحقّق أن `index.html` و`articles.json` و`video_factory.py` و`logo.webp` و`.github/workflows/auto_news.yml` موجودة في جذر المستودع.

> إن احتفظ GitHub ببعض الملفات القديمة بعد الرفع، احذفها يدوياً من نفس الصفحة (زر الحذف بجانب الملف) ثم انسخ القائمة من `DELETE_OLD_AR.md`.

## 4. الإعدادات (Settings)

- **Pages → Build and deployment:** Source = `Deploy from a branch`، Branch = `main`، Folder = `/ (root)`. ملف `.nojekyll` موجود أصلاً.
- **Variables** ( Settings → Secrets and variables → Actions → Variables ):

  `CONTACT_EMAIL = nadia.bouizgarne1@gmail.com` · `ADSENSE_CLIENT` · `ADSENSE_SLOT` · `NEWSLETTER_BUTTONDOWN` · `NP_API` · `ADSENSE_MIN_PER_CATEGORY = 0` · `MIN_PER_CATEGORY = 15` · `KEEP_PER_CATEGORY = 30` · `HEAL_IMAGES = 24` · `RESTYLE_ARCHIVE = 10` · `RUN_BUDGET_MIN = 150` · `VIDEO_PER_RUN = 1` (حتى 8) · `VIDEO_MAX_MINUTES = 20` · `VIDEO_MAX_SCENES = 40` · `VIDEO_FPS = 24` · `EDGE_TTS_VOICE = ar-SA-ZariyahNeural` · `IA_COLLECTION` · `IA_IDENTIFIER_PREFIX` · `CF_IMAGE_MODEL` · `GEMINI_TEXT_MODEL` · `GEMINI_IMAGE_MODEL`.

- **Secrets:** `GEMINI_API_KEY` (أساسي للكتابة)، واختيارياً `GROQ_API_KEY`، `OPENROUTER_API_KEY`، `OPENAI_API_KEY`، `CLOUDINARY_URL`، `CLOUDINARY_CLOUD_NAME`، `CLOUDINARY_API_KEY`، `CLOUDINARY_API_SECRET`، `CF_ACCOUNT_ID`، `CF_API_TOKEN`، `TOGETHER_API_KEY`، `HF_TOKEN`، `AMAZON_*`.
- **للأفلام فقط:** أضف `IA_ACCESS_KEY` و`IA_SECRET_KEY` من Internet Archive. إن لم تضفهما أو لم تتوفر حزم `edge-tts`/`imageio-ffmpeg`، يصدر الموقع القصص **بدون فيلم** ولا يفشل النشر أبداً.
- `SITE_URL` اختياري: يُشتق تلقائياً من اسم المستودع داخل Actions؛ ضعه يدوياً فقط إن كان لديك نطاق مخصص.

## 5. التشغيل بعد الرفع

- اذهب إلى **Actions → مملكة الأسرار — إعادة بناء القصص → Run workflow** لبناء كل الصفحات فوراً. المتوقع: `site built: 16 articles` ثم `site check OK` ثم `AdSense audit OK`.
- النشر التلقائي يعمل كل ساعتين (`0 */2 * * *`) بالقيم الافتراضية: `count=8`، `regen_images=fill` (يُترجم إلى `svg`)، `timeout-minutes=350`.
- لوحة التحكم `/admin/index.html` خاصة بك وحدك: لا تربطها من أي صفحة، وهي `noindex,nofollow,noarchive,nosnippet,noimageindex`، و`robots.txt` يمنع `/admin/` و`/admin.html`.

## 6. ملاحظات محتوى

- كل قصة جديدة تحتاج حقل `hashtags` فيه 5–7 هاشتاغات عربية قوية؛ يظهر تحت العنوان وعلى البطاقة ويُضاف إلى `search.json`. أضفه من حقل «هاشتاغات قوية للنشر والبحث» في اللوحة، أو يضيفه `fetch_news.py` تلقائياً من `CATEGORY_HASHTAGS`.
- وسوم الشكل الأربعة تبقى: `short` = `#قصة_قصيرة`، `flash` = `#ومضة_قصصية`، `serial` = `#سلسلة_حلقات`، `interactive` = `#قصة_تفاعلية`.
- الإخلاء الأدبي إلزامي في أعلى كل قصة: «هذه القصة عمل إبداعي من تأليف نكسوس، وأي تشابه مع الواقع محض صدفة.»
- `ar_books` لم يتغير نصه التحريري؛ المقالات الأربعة المحفوظة معفاة من الهاشتاغات.
- الشعار الرسمي `logo.webp`/`logo.png` بمقاس 330×180 ويظهر في الهيدر بـ165×90 مع الحفاظ على الشفافية. أيقونة اللغات 🌐 وآلية التبديل لم تتغير.

## 7. فحص محلي اختياري

```bat
python build_site.py
python check_site.py
python adsense_audit.py
```

النتيجة المتوقعة: `site built: 16 articles`، `site check OK: 42 pages, all internal links and images exist`، `AdSense audit OK`. تحذيرات «no canonical URL» تظهر فقط محلياً لأن `GITHUB_REPOSITORY` غير معيّن؛ داخل Actions تختفي.
