# قائمة الحذف الدقيقة — ملفات الجريدة القديمة

هذه القائمة هي ما يجب حذفه **من المستودع على GitHub** قبل رفع ملفات «مملكة الأسرار». كل ملف مذكور هنا كان خاصاً بـ«نكسوس بريس»/الجريدة الإخبارية أو زاوية المنتخب المغربي، ولا علاقة له بالمدونة القصصية الجديدة.

## أ — أكواد وملفات الجريدة القديمة (احذفها إن كانت موجودة عندك)

| الملف | السبب |
| --- | --- |
| `cities.py` | كان يبني صفحات المدن والزوايا المحلية. |
| `reclassify_archive.py` | كان يعيد تصنيف أخبار الجريدة القديمة. |
| `category-ar_world.html` | صفحة أخبار العالم القديمة. |
| `category-ar_economy.html` | صفحة الاقتصاد القديمة. |
| `category-ar_sports.html` | صفحة الرياضة القديمة. |
| `category-ar_local.html` | صفحة الأخبار المحلية القديمة. |
| `category-ar_cities.html` | صفحة المدن القديمة. |
| `city-*.html` | كل صفحات المدن المولّدة قديماً (إن وُجدت). |
| `CHANGES.diff` | أرشيف تعديلات الجريدة القديمة، لا يُستخدم. |
| `image_MUwSAA.png` | صورة قديمة من عهد الجريدة، استُبدلت بـ`logo.webp`/`logo.png`. |
| `__pycache__/` | ملفات `.pyc` مترجمة محلياً؛ لا ترفعها أصلاً. |


> لا تحذف `ar_tech` أو `ar_arts`؛ هما الآن قراءتا رأي شخصية، ومع ذلك صفحتاهما القديمتان تُستبدلان بالنسختين الجديدتين في مجلد الرفع. لا تحذف `news-state.json` ولا `curate.py` (يُستخدمان الآن لتذكّر العناوين ومنع التكرار فقط).

## ب — مقالات الجريدة الستون القديمة (يُحذف 56 منها وتبقى 4)

احذف كل ملفات `articles/` القديمة ما عدا الأربعة المحفوظة:
`ar_books-202611160830-0ec2f4.html`، `ar_books-202611161015-ea9eb6.html`، `ar_books-202611161240-5baf99.html`، `ar_books-202611170356-4ed581.html`.

الـ56 ملفاً المراد حذفها مذكورة بالاسم الكامل في `DELETE_OLD_AR-articles.txt` (داخل مجلد الرفع). أسماؤها تبدأ بـ`ar_world-` أو `ar_economy-` أو `ar_sports-` أو `ar_tech-` أو `ar_arts-` أو `post-`.

## ج — صور الجريدة القديمة

`images/` في المستودع الحالي فيه 281 ملفاً؛ مدونة الأسرار تحتاج 16 غلافاً + 16 مصغّرة فقط (موجودة في مجلد الرفع). احذف كل الباقي. القائمة الكاملة بالاسم موجودة في `DELETE_OLD_AR-images.txt`. القاعدة السريعة: احذف كل ملف يبدأ بـ`ar_world-` أو `ar_economy-` أو `ar_sports-` أو `ar_local-` أو `ar_cities-` أو `post-`، وكل النسخ المكرّرة من أغلفة القصص الحالية (مثل `story_comedy-phone-basket.webp` و`story_history-fez-notebook.webp` و`story_horror-lullaby-wall.webp` و`*-ill.webp`).

## د — أكواد كانت للجريدة لكنها خُفّضت وأُعيد استخدامها (لا تحذفها)

هذه الملفات وُلدت في عهد الجريدة، لكنها **أُعيدت كتابتها** لتخدم المدونة القصصية؛ حذفها يكسر النشر التلقائي:

- `build_site.py`: كان يبني صفحات الأخبار، الآن يبني 13 قسماً قصصياً وصفحة فيلم لكل قصة.
- `fetch_news.py`: كان يجلب RSS إخباري، الآن يكتب قصصاً وومضات وقراءات رأي؛ يحتفظ بمفتاح `nexus/` في Cloudinary و`FICTION_STYLE_VER`.
- `check_site.py` / `adsense_audit.py`: كانا يفحصان الأخبار، الآن يفحصان القصص والهاشتاغات والفيديو.
- `curate.py`: يُستخدم الآن لتذكّر العناوين ومنع التكرار فقط؛ لا تحذفه رغم بقاء مفاتيح الأقسام القديمة بداخله كألوان/خرائط داخلية.
- `illustrations.py` / `image_jobs.py` / `gen_image.mjs`: أدوات توليد الصور؛ تعمل مع القصص أيضاً.
- `style.css` / `site.js` / `admin/*` / `*.yml`: تم تعديلها لتخدم المدونة؛ لا تحذفها.
- `legal.py` / `style_guide.py` / `ai_hub.py` / `books_library.py` / `amazon_products.js` / `chat.js` / `tools.js` / `sw.js`: خدمات مستقلة بقيت كما هي وظيفياً.

## هـ — أكواد جديدة تماماً (تُرفع)

`video_factory.py` (مصنع الأفلام)، `SPEC.md` (المواصفة)، وحقل `hashtags` في `articles.json` والوحة الإدارية، وقسم «فيلم القصة» في `build_site.py` و`style.css`.

## و — ملاحظة مهمة عن أسماء داخلية لا تُغيّر

`nexus-blog` في `POLL_NS`، ومجلد `nexus/` في Cloudinary، وأسماء الـsecrets القديمة إن كانت موجودة، ومفاتيح الأقسام القديمة داخل `curate.py`/`illustrations.py`/`image_jobs.py`: كلها معرّفات تقنية داخلية تُبقى كما هي كي لا ينكسر الإعداد. القوائم السوداء في `check_site.py`/`adsense_audit.py` تحتوي عمداً على عبارات الجريدة القديمة (`نكسوس بريس`، `Nexus Press`، `زاوية المنتخب المغربي`) كي تكتشف أي بقايا؛ **لا تحذفها**.

## ز — ملفات محلية خارج المستودع (احذفها من جهازك فقط)

`Nexus_Press-UPDATE/` القديم و`Nexus_Press-UPDATE.zip` القديمان؛ سيُستبدلان بالنسخة الجديدة في هذا الأرشيف. `Nexus_Press-NEWS-BACKUP/` احتفظ به كنسخة احتياطية شخصية ولا ترفعه.


## ح — الأسماء الكاملة للمقالات الـ56 المراد حذفها

- `articles/ar_arts-202611080745-d00a79.html`
- `articles/ar_arts-202611082012-c9fc0b.html`
- `articles/ar_arts-202611100922-84e82f.html`
- `articles/ar_arts-202611101648-47931c.html`
- `articles/ar_arts-202611101711-9ba09c.html`
- `articles/ar_arts-202611102348-d455c0.html`
- `articles/ar_arts-202611110114-f39a89.html`
- `articles/ar_arts-202611170458-880955.html`
- `articles/ar_economy-202611080716-d70263.html`
- `articles/ar_economy-202611080725-d5b3f7.html`
- `articles/ar_economy-202611080739-be6b19.html`
- `articles/ar_economy-202611080753-24cdde.html`
- `articles/ar_economy-202611081552-401623.html`
- `articles/ar_economy-202611100157-82cde8.html`
- `articles/ar_economy-202611110029-393689.html`
- `articles/ar_economy-202611110414-4d30f1.html`
- `articles/ar_sports-202611080710-d09fee.html`
- `articles/ar_sports-202611080719-703e0e.html`
- `articles/ar_sports-202611080727-227b18.html`
- `articles/ar_sports-202611080744-c1ee58.html`
- `articles/ar_sports-202611080757-739277.html`
- `articles/ar_sports-202611082008-253acf.html`
- `articles/ar_sports-202611091705-cd0281.html`
- `articles/ar_sports-202611101008-6eafdf.html`
- `articles/ar_sports-202611101537-17afbc.html`
- `articles/ar_sports-202611101707-406d05.html`
- `articles/ar_sports-202611102340-17556a.html`
- `articles/ar_sports-202611110104-e3a8d2.html`
- `articles/ar_sports-202611161852-9ac4be.html`
- `articles/ar_sports-202611170200-9ab04e.html`
- `articles/ar_sports-202611170351-6bb125.html`
- `articles/ar_tech-202611080717-3945e2.html`
- `articles/ar_tech-202611080726-d3b791.html`
- `articles/ar_tech-202611080743-e63da3.html`
- `articles/ar_tech-202611080756-6b2618.html`
- `articles/ar_tech-202611081552-63e74f.html`
- `articles/ar_tech-202611090741-223950.html`
- `articles/ar_tech-202611091740-1f36e3.html`
- `articles/ar_tech-202611100200-a8637e.html`
- `articles/ar_tech-202611100949-08bdc8.html`
- `articles/ar_tech-202611101531-866b5d.html`
- `articles/ar_tech-202611101705-5d7661.html`
- `articles/ar_tech-202611110037-e82d5a.html`
- `articles/ar_tech-202611110322-dd7e48.html`
- `articles/ar_tech-202611111833-89b251.html`
- `articles/ar_world-202611080715-9792a9.html`
- `articles/ar_world-202611080723-e42016.html`
- `articles/ar_world-202611091717-bdbfd9.html`
- `articles/ar_world-202611110235-41d127.html`
- `articles/ar_world-202611111827-c3d5e3.html`
- `articles/post-202611090027-a0ecaa.html`
- `articles/post-202611091713-67af0a.html`
- `articles/post-202611091804-67511c.html`
- `articles/post-202611100926-e47aab.html`
- `articles/post-202611101717-3e8448.html`
- `articles/post-202611111021-f8308f.html`
