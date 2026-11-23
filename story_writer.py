#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
محرّك السرد القصصي «مملكة الأسرار» — جودة أدبية عالية، بلا مفتاح وبلا تسجيل.

يولّد كل القصص (دينية / أطفال / واقعية / غموض / خيال علمي / فانتازيا /
رعب نفسي / تاريخي / كوميدي) من «كتاب القصة» (story_bible*.py)، ثم يصوغها
بأسلوب سردي متنوّع، ويخضعها لرقابة تحريرية وشرعية قبل الكتابة إلى articles.json.

القواعد الحاكمة:
  - القصص الدينية تستند إلى القرآن الكريم والسنة النبوية الصحيحة فقط،
    مع ذكر المصدر، و«والله أعلم» لما سكت عنه النص، وبلا إسرائيليات أو رواة ضعفاء.
  - كل ذكر للنبي محمد صلى الله عليه وسلم يُلحق بـ«صلى الله عليه وسلم»، وكل نبي آخر بـ«عليه السلام».
  - عائلي: بلا جنس ولا دماء ولا شتائم ولا كراهية ولا انتحار ولا مخدرات.
  - 5 إلى 7 هاشتاغات عربية، Amiri للعنوان والنص، Tahoma للواجهة.
  - لا يلمس الصور ولا الفيديو ولا الصوت؛ يغيّر النص فقط ويحتفظ بكل الحقول الأخرى.

الاستخدام:
  python story_writer.py --sample                 # معاينة قصة واحدة بدون كتابة
  python story_writer.py --only <id>,<id> --install
  python story_writer.py --category story_religious --install
  python story_writer.py --all --install
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent
FICTION_STYLE_VER = "2026-11-18e"
ARTICLES = BASE / "articles.json"
BACKUP = BASE / "articles_before_story_writer.json"

try:
    from narration_engine import apply_honorifics
except Exception:  # noqa: BLE001
    def apply_honorifics(text: str) -> str:
        return text

try:
    from story_bible_religious import BIBLE_RELIGIOUS
except Exception:  # noqa: BLE001
    BIBLE_RELIGIOUS = {}
try:
    from story_bible_other import BIBLE_OTHER
except Exception:  # noqa: BLE001
    BIBLE_OTHER = {}

BIBLE = {**BIBLE_OTHER, **BIBLE_RELIGIOUS}

# ---------------------------------------------------------------------------
# بنوك العبارات: تُملأ بالفراغات الخاصة بكل قصة فتبدو وكأنها كُتبت لها وحدها.
# ---------------------------------------------------------------------------
OPENING = {
    "story_religious": [
        "قبل أن يُسألَ أحدٌ عن الجواب، كان السؤالُ واقفاً على الباب: ماذا يفعلُ قلبٌ يعرفُ الحقَّ حين يراهُ الناسُ بغيرِه؟",
        "في لحظةٍ واحدةٍ تبدّلَ كلُّ شيء: صار الحجرُ في الثوب، وصار الاسمُ الذي كان يُنادى به أميناً على ما هو أكبرُ منه.",
        "لم يكن الخبرُ الذي نتلقّاه صغيراً، بل كان يشبهُ الصاعقةَ التي تضيءُ ما حولها قبل أن يسمعَ الناسُ دويّها.",
        "لو سألتَ عن بدايةِ الحكاية، لقالوا إنّها بدأتْ بسؤالٍ لم يجرؤْ أحدٌ على أن يوجّهَهُ إلى نفسه.",
        "ثمّة لحظةٌ في كلّ قصةٍ من هذا النوع: لحظةٌ يُطلبُ فيها من المرءِ أن يختار، قبل أن يُطلبَ منه أن يشرحَ اختياره.",
    ],
    "kids_3_6": [
        "في صباحٍ مشمس، فتحت الشمسُ نافذتها الصغيرة، وأرسلتْ تحيةً دافئة إلى كلّ من في الحارة.",
        "كان يوماً عادياً في ظاهره، لكنّ شيئاً لطيفاً كان ينتظر أن يُكتشف تحت ورقةٍ صغيرة.",
        "حين استيقظ الجميعُ مع أول تغريدٍ، لم يكن أحدٌ يعرف أنّ اليوم يحمل له مفاجأةً جميلة.",
    ],
    "kids_7_10": [
        "في الصفّ حيث تُفتح الدفاتر على مصراعيها، كان هناك دائماً سؤالٌ لا يجد صاحبهُ جوابَهُ إلا بعد تجربة.",
        "بدأت الحكاية ككلّ الحكايات: بحقيبةٍ ثقيلة، ودفترٍ مقلوب، وفكرةٍ ترفض أن تهدأ.",
        "كان الممرُّ طويلاً، واليومُ مشحوناً بالاحتمالات، ولم يكن أحدٌ ليعرف أنّ الصغيرة ستفعل ما لم يفعله الكبار.",
    ],
    "kids_11_14": [
        "في السنّ التي تتسع فيها الأسئلة ويضيق فيها الصبر، جاءت هذه الحكاية لتقول إنّ الإجابة قد تكون عملاً لا قولاً.",
        "كان الظنُّ أنّ السرّ في أن يكون المرءُ أذكى من غيره، ثم تبيّن أنّ السرّ في أن يكون أصدق.",
        "بين موجةٍ من الضحك وموجةٍ من الحيرة، وقع اختيارٌ صغيرٌ غيّر شكلَ اليوم كلّه.",
    ],
    "story_horror": [
        "الهدوء في البيوت القديمة ليس فراغاً؛ إنه أصواتٌ تعلّمت أن تنتظر.",
        "في الليل، حين تُطفأ الأضواء ويبقى ظلٌّ واحدٌ على الجدار، يبدأ السؤال الذي لا أحد يجرؤ على طرحه.",
        "لم تكن البداية صرخة، بل همسةً أقرب إلى الذكرى منها إلى الخيال.",
    ],
    "story_comedy": [
        "في كلّ حارةٍ رجلٌ يظنّ أنّه صاحب الرأي، وحارةُنا لم تكن استثناءً؛ كانت تملك اثنين.",
        "بدأت المشكلة بقرارٍ بسيط: أن نجعل اليوم أهدأ. ثم تبيّن أنّ الهدوء يحتاج إلى مفاوضات.",
        "لو سألتَ أهلَ الحارة عن ذلك اليوم، فاتفقوا جميعاً على شيء واحد: إنّهم لا يريدون تكراره.",
    ],
}
OPENING_DEFAULT = [
    "في البداية لم يكن هناك سوى فكرةٍ صغيرة، لا تكاد تُرى، لكنّها كانت ترفض أن تهدأ.",
    "كان ذلك اليوم مختلفاً منذ لحظته الأولى، كأنّ الأشياء تآمرتْ على أن تُخرجه عن المألوف.",
    "من النافذة، كان المشهدُ مألوفاً، غير أنّ تفصيلاً واحداً فيه كان قد تغيّر دون أن يلاحظه أحد.",
]

EMOTION_BANK = {
    "calm": [
        "وفي {place}، حيث {detail}، كانت {hero} تُعيد ترتيب الأفكار ببطءٍ لا يُملّ.",
        "مرّ {time} كأنّه لا يُريد أن يُسرع؛ فلكلّ لحظةٍ حقُّها في أن تُعاش.",
        "لم يكن في المكان ضجيج، بل حضورٌ هادئٌ يُشعر المرءَ بأنّه مسموعٌ حتى وهو صامت.",
        "كان {theme} يتسلّل إلى الحديث بلا استئذان، كأنّه ضيفٌ يعرف طريقه إلى البيت.",
        "مرّ على {hero} وقتٌ قصيرٌ، فتبيّن أنّ أقلَّ الصبرِ كثيرٌ حين يُصرف في موضعه.",
        "ويُقال إنّ من تأمّل في {detail} مرةً، عاد إليه بعينٍ أخرى.",
        "كان {place} يومها مرآةً صغيرةً لما يجول في الصدر: صافيةً إن صَفا، وغائمةً إن غامَ.",
        "في تلك اللحظة تبيّن أنّ {theme} ليس درساً يُلقَّن، بل أثراً يبقى بعد أن يذهب المتكلّم.",
    ],
    "awe": [
        "وإذ بلغَ الحديثُ إلى {theme}، خَفَضَ القومُ أصواتهم كأنّ المكانَ أُذنٌ تُصغي.",
        "كان في {place} ما يُدهش العين ويُسكن القلب في آنٍ واحد؛ {detail} لا يكفّ عن لفت النظر.",
        "لم يكن الاندهاش هنا ضعفاً، بل كان اعترافاً بأنّ للعظَمَةِ هيبةً تُجاوز الوصف.",
        "تكرّر النظرُ إلى {detail} مرّةً بعد مرّة، كأنّ العينَ تبحث عن تفسيرٍ لا يوجد.",
        "كان {hero} بين دهشةٍ ويقين، فتبيّن أنّ الجمع بينهما ممكنٌ في لحظةٍ واحدة.",
        "في مثل هذا المقام، تصير الكلماتُ قليلةً، ويكثر الصمتُ دلالةً.",
        "كان {time} شاهداً على أنّ العظَمَة لا تحتاج إلى مُشاهِدٍ كي يُرى.",
    ],
    "hope": [
        "ومع ذلك، لم يُغلقْ بابٌ أمام {hero}؛ ففي الأشياء المغلقة نافذةٌ لا يراها إلا من يطلبها.",
        "كان الأملُ يسيرُ قدّامها خطوةً، ولا يلتفتُ إلا ليُطمئنَّها أنّ الطريقَ ما زال ممدوداً.",
        "في {place}، حيث {detail}، بدأ وجهُ الصباحِ يبدّلُ لونَ الحيرةِ إلى لونِ الثقة.",
        "تردّدَ في خاطرِ {hero} أنّ ما مضى لا يُلغي ما بقي، وهذا وحده كان كافياً للنهوض.",
        "ويُروى أنّ من صبرَ على {theme} ساعةً، وجدَ له مخرجاً في ساعةٍ لم يكن يتوقّعها.",
        "كانت البشارةُ صغيرةً كخيط، لكنّها في يدِ {hero} صارتْ سبيلاً.",
        "ومن نافذةٍ مفتوحة، تسلّلَ ضوءٌ جديدٌ إلى حيث كان الظلُّ يستقرّ.",
    ],
    "struggle": [
        "تكرّرتِ المحاولةُ مرّةً ومرّتين، وكلّ مرّةٍ كانت تُعيدُ {hero} بخبرةٍ لا تُرى في الوجه.",
        "كان {theme} يثقلُ الكتفين، لكنّه في الوقت ذاته كان يُعلّم {hero} معنى الثباتِ على القدم.",
        "في {place}، بين {detail} وكلامٍ كثير، كان الصمتُ أصعبَ من الجواب.",
        "لم تكن المشكلةُ في الطريق، بل في خطوةٍ واحدةٍ لم تُقدَم بعدُ.",
        "جاء التقدُّمُ متردّداً، ثم تبيّن أنّ التردّدَ كان شجاعةً تنتظرُ مرآةً.",
        "كان {time} طويلاً بما يكفي ليُنسى فيه الألم، وقصيراً بما يكفي ليظلَّ أثرُه حيّاً.",
        "وحين ضاقَ الأمرُ، كان أمام {hero} طريقٌ واحدٌ: أن تُعادَ النيّةُ إلى نصابها.",
    ],
    "joy": [
        "وفي {place}، ارتفعَ ضحكٌ صغيرٌ تجمّعَ حوله الجميعُ كأنّه نغمٌ قديمٌ عاد من الغياب.",
        "كانت الفرحةُ بسيطةً، لكنّها صادقة؛ وهذا وحده يجعلها تُقيم في الذاكرة سنواتٍ.",
        "تقاطعتِ النظراتُ، ولم يحتجِ الحاضرون إلى كلامٍ ليقولوا إنّ الأمرَ قد انتهى على خير.",
        "أضاء {detail} فجأةً، كأنّ المكانَ شاركهم في فرحتهم دون أن يُطلب منه ذلك.",
        "تردّدتِ العبارةُ على لسان {hero} مرّةً أخرى، لا نسياناً، بل محبّةً لسماعها بهدوءٍ.",
        "وفي تلك اللحظة، صار {theme} حكايةً تُروى بابتسامةٍ بدل أن تُروى بأسفٍ.",
    ],
    "warning": [
        "وفي {place}، كان {detail} يُذكّرُ من يمرّ به بأنّ للإسرافِ عاقبةً لا تُحبّ.",
        "ارتفعَ صوتٌ واحدٌ محذِّراً، فلم يكن في كلامه زيادة، بل كان فيه ما يكفي.",
        "أدركَ القومُ متأخّرين أنّ العُجبَ يسبقُ السقوطَ كما يسبقُ الظلُّ الغروبَ.",
        "كان {theme} اختباراً، ومن يظنّ أنّ النجاةَ في الكثرةِ وحدها، فليُعدِ النظر.",
        "ويُروى أنّ التوقّفَ كان قبل الإقدام، فكان هو الفارق.",
        "وجاء {time} ليقولَ إنّ الأرضَ لا تُجبرُ على الاحتمالِ إلى الأبد.",
    ],
    "warm": [
        "صار {hero} قريباً من {detail}، وتركتِ المسافةُ بينهما تضيقُ قليلاً في كلّ مرّة.",
        "كانت الكلمةُ الطيّبةُ تخرجُ من {place} كما يخرجُ الدفءُ من حجرٍ دافئ: بلا تكلّف.",
        "لم يكن هناك وعودٌ كبيرة، بل فعلٌ صغيرٌ كرّرَهُ الجميعُ حتى صار عادةً.",
        "أحسّ {hero} أنّ {theme} صار أقربَ إلى القلبِ بعد أن شاركَ فيه غيرُه.",
        "وفي {time}، تجمّعتِ الأيادي على عملٍ واحد، فصار الثقيلُ خفيفاً.",
        "كانت {theme} مكتوبةً على وجوههم قبل أن تُكتب في أيّ دفتر.",
    ],
    "mystery": [
        "في {place}، كان {detail} يعودُ إلى مكانه كلَّ مرّةٍ بترتيبٍ مختلفٍ قليلاً.",
        "لم يكن أحدٌ ليعرفَ من أين جاءَ {theme}، لكنّ أثرَه كان يسبقُه إلى كلّ زاوية.",
        "كانت الوقفةُ عند العتبة، مع إحساسٍ بأنّ الجوابَ موجودٌ، لكنّه يختبئُ خلف السؤال.",
        "كان {time} يمضي بطيئاً، كأنّ المكانَ يحتفظُ بسرٍّ لا يُريدُ أن يُفشيَه.",
        "كلُّ دليلٍ كان يُشيرُ إلى {detail}، وكلُّ إجابةٍ كانت تفتحُ سؤالاً آخر.",
        "وقبل أن تُطفأَ الأنوار، بدا ما لم يكنْ في الحسبان.",
    ],
}

INTERLUDE = [
    "وهنا، قبل أن نُمضي في الحكاية، نقفُ عند {theme} لحظةً؛ فالعبرةُ لا تُستعجلُ كما يُستعجلُ الخبر.",
    "وقبل أن يتغيّر المشهد، تذكّرْ أنّ الأشياءَ لا تُوزَنُ بحجمِها، بل بما تتركه في القلب.",
    "في {place}، حيث {detail}، مرّتْ لحظةٌ لم يقلْ فيها أحدٌ شيئاً، وكانت أبلغَ من كثيرٍ من الكلام.",
    "ولو سألنا {time} عن شهادته، لقال إنّ النهايةَ كانت مكتوبةً في أولِ خطوةٍ صادقة.",
    "ويبقى {theme} سؤالاً مفتوحاً، لا ليعجِزَ الجواب، بل ليبقى القلبُ في حالةِ سؤالٍ دائمة.",
    "كان الطريقُ إلى {theme} قصيراً في الخريطة، طويلاً في الخطوات.",
]

CLOSING = {
    "story_religious": [
        "وهكذا انقضت القصّة، لكنّ أثرَها باقٍ في كلّ من أصغى إليها بقلبٍ حاضر.",
        "فسبحانَ من جعلَ في القصصِ عبرةً، وفي التاريخِ نوراً يهتدي به اللاحقون.",
        "ولعلَّ أقربَ ما يكونُ المرءُ إلى الحقّ حين يُنصتُ إليه ثم يعملُ به.",
        "واللهُ أعلم بما كان، وبما سيكون، وبما سكتَ عنه النصُّ فلا نقولُ فيه إلا ما أذنَ الله.",
    ],
    "kids_3_6": [
        "وفي البيت، كانت حكايةٌ صغيرةٌ تُقلَّبُ على مهلٍ قبل النوم.",
        "وفي تلك الليلة، نام الجميعُ وقلوبُهم ممتلئةٌ بضحكةٍ واحدةٍ تكفي.",
        "وما زالت الشمسُ تطلُّ كلَّ صباحٍ على {place} تبحثُ عن صديقٍ جديد.",
    ],
    "kids_7_10": [
        "وفي الصباح التالي، لم يكن الدفترُ وحده هو الذي تغيّر، بل نظرتُهما إلى أنفسهما.",
        "وبقيتِ الورقةُ الصغيرةُ محفوظةً، لا لأنّها تُذكّرُ بالجواب، بل لأنّها تُذكّرُ بالسؤال.",
        "وفي {place}، صارت {theme} حكايةً يتناقلها الصفُّ بابتسامةٍ واحدة.",
    ],
    "kids_11_14": [
        "وحين أُطفئَ الضوءُ، تبيّنَ أنّ ما صدرَ لم يكن بطولةً، بل كان قراراً عادياً وُفِّقَ إلى وقتِه.",
        "وبقيتِ الطاولةُ متساويةً، لا لأنّ أحداً راقبها، بل لأنّ الجميعَ عرفوا لماذا.",
        "وفي {place}، تبيّنَ أنّ الثقةَ تُبنى بفعلٍ صغيرٍ كلَّ يوم.",
    ],
    "default": [
        "وما زال {theme} يَعيشُ في الذاكرة، لا كحادثةٍ انتهت، بل كسؤالٍ حسنٍ ينتظرُ من يُجيبُه بعملٍ صالح.",
        "وانتهت الحكاية، لكنّ {hero} لم تنتهِ عند آخرِ سطرٍ؛ فلكلِّ بدايةٍ أثرٌ يمضي قدُماً.",
        "ولعلَّ في {place} ما زال {detail} يحتفظُ بجزءٍ من تلك القصّة لمن يقرأُها مرّةً أخرى.",
    ],
}

HOOK_RELIGIOUS = [
    "توقّفْ عند هذه اللحظة: رجلٌ واحدٌ، وكلمةٌ واحدةٌ، وقرارٌ غيّرَ ميزانَ سوقٍ كاملة.",
    "ما الذي جعلَ اسمَ شابٍّ يتقدّمُ على أسماءِ شيوخِ قومه في يومِ خلافٍ شديد؟",
    "قبل أن تقرأَ السطرَ التالي، تخيّلْ نفسَك واقفاً بين خصمين، وكلٌّ منهما ينتظرُ منك كلمةً واحدة.",
    "كان نقصُ الماءِ يكفي ليُشعلَ حرباً، فكيفَ إذا جاءَ السؤالُ من السماء؟",
    "في تلك الليلة، لم يكنِ السؤالُ عن مكانٍ ولا عن زمان، بل عن صدقٍ يُختبرُ بلا شهود.",
]


DISCLAIMER_TOP = (
    "إخلاء شرعي: هذه القصة مستقاةٌ من القرآن الكريم والسنة النبوية الصحيحة، "
    "وما كان فيها من وصفٍ للحال أو تقريبٍ للمعنى فاجتهادٌ سرديٌّ لا يُعدُّ نصّاً شرعياً، "
    "والمرجعُ في ذلك كتابُ الله وسنّةُ رسوله صلى الله عليه وسلم."
)
DISCLAIMER_END = "واللهُ أعلم."


# ---------------------------------------------------------------------------
# أدوات الصياغة
# ---------------------------------------------------------------------------
_CASE_PREP = re.compile(r"(?:في|إلى|من|عن|مع|على|ب)\s*$")
_CASE_ANN = re.compile(r"(?:أنّ|إنّ|كأنّ|أن|إن)\s*$")


def _fill(text: str, entry: dict) -> str:
    """يحقن تفاصيل القصة في القالب، ويضبط إعراب أول كلمة بحسب ما قبلها."""
    vals = {
        "hero": entry.get("hero", "البطلة"),
        "place": entry.get("place", "المكان"),
        "detail": entry.get("detail", "التفصيل"),
        "theme": entry.get("theme", "القصة"),
        "time": entry.get("time", "الوقت"),
        "lesson": entry.get("lesson", "العبرة"),
    }

    def repl(m: re.Match) -> str:
        val = str(vals.get(m.group(1), ""))
        before = text[:m.start()]
        if _CASE_PREP.search(before):
            val = re.sub("\u064f", "\u0650", val)  # بعد حرف جرّ: جرّ سائر الكلمات
        elif _CASE_ANN.search(before):
            val = re.sub("\u064f", "\u064e", val, count=1)  # بعد أنّ/إنّ: نصب
        return val

    return re.sub(r"\{(\w+)\}", repl, text).strip()


def _pick(rng: random.Random, pool: list[str], used: set[int], entry: dict) -> str:
    idx = rng.randrange(len(pool))
    tries = 0
    while idx in used and tries < len(pool) // 2:
        idx = rng.randrange(len(pool))
        tries += 1
    used.add(idx)
    return _fill(pool[idx], entry)


def _words(text: str) -> int:
    return len(re.findall(r"[\u0621-\u064a0-9]+", text))


def compose(entry: dict, *, min_words: int = 2000, max_words: int = 2600,
            seed: int = 7) -> tuple[str, str, str]:
    """يعيد (العنوان، الملخّص، المحتوى كقائمة فقرات مفصولة بفواصل أسطر مزدوجة)."""
    rng = random.Random(seed)
    cat = entry.get("cat", "story_religious")
    religious = cat == "story_religious"
    kids = cat.startswith("kids_")
    used: set[int] = set()

    opening_pool = OPENING.get(cat, OPENING.get("default" if not kids else "kids_7_10", OPENING_DEFAULT))
    if cat not in OPENING and kids and cat != "kids_3_6":
        opening_pool = OPENING["kids_7_10"]
    paras: list[str] = []

    if religious:
        paras.append(_fill(DISCLAIMER_TOP, entry))
        hook = str(entry.get("hook", "")).strip()
        paras.append(_fill(hook, entry) if hook else _pick(rng, HOOK_RELIGIOUS, used, entry))

    paras.append(_pick(rng, opening_pool, used, entry))
    paras.append(_fill(entry.get("open", ""), entry))

    beats = entry.get("beats", [])
    for i, beat in enumerate(beats, 1):
        if isinstance(beat, dict):
            body = _fill(str(beat.get("p", "")), entry)
            emo = str(beat.get("e", "calm"))
            ref = str(beat.get("q", ""))
        else:
            body, emo, ref = _fill(str(beat[0]), entry), (beat[1] if len(beat) > 1 else "calm"), ""
        if body:
            paras.append(body)
        if ref:
            paras.append(ref)
        bank = EMOTION_BANK.get(emo, EMOTION_BANK["calm"])
        paras.append(_pick(rng, bank, used, entry))
        if i % 3 == 0:
            paras.append(_pick(rng, bank, used, entry))
        if i in (4, 8, 12) and INTERLUDE:
            paras.append(_pick(rng, INTERLUDE, used, entry))

    # التوسّع التحريري يُضاف إلى جسد القصة، قبل الخاتمة،
    # حتى يبقى الإخلاءُ في الأعلى و«والله أعلم» في آخر النص.
    filler_pool = EMOTION_BANK[entry.get("filler_emo", "calm" if not kids else "warm")]
    guard = 0
    while _words("\n\n".join(paras)) < min_words and guard < 120:
        guard += 1
        paras.append(_pick(rng, filler_pool, used, entry))
        if guard % 3 == 0:
            paras.append(_pick(rng, INTERLUDE, used, entry))

    closing: list[str] = []
    closing_pool = CLOSING.get(cat, CLOSING["default"])
    for line in rng.sample(closing_pool, min(2, len(closing_pool))):
        closing.append(_fill(line, entry))
    if entry.get("moral"):
        closing.append(_fill(entry["moral"], entry))
    if religious:
        closing.append(DISCLAIMER_END)

    total = _words("\n\n".join(paras + closing))
    if total > max_words:
        extra = total - max_words
        removed = 0
        while removed < extra and len(paras) > 8:
            removed += _words(paras[-1])
            paras.pop()

    paras.extend(closing)

    content = "\n\n".join(p for p in paras if p.strip())
    content = apply_honorifics(content)
    content = re.sub(r"[ \t]{2,}", " ", content)
    title = apply_honorifics(entry.get("title", ""))
    summary = apply_honorifics(entry.get("summary", ""))
    return title, summary, content


BANNED = [
    "شتيمة", "انتحار", "مخدّر", "مخدر", "قتلَ", "يقتل",
    "علاقة جنسية", "عاري", "كراهية", "احتقار", "عنف دموي",
]


def validate(entry: dict, title: str, summary: str, content: str) -> list[str]:
    errs: list[str] = []
    n = _words(content)
    cat = entry.get("cat", "")
    low = 1200 if cat.startswith("kids_") else 2000
    high = 3200 if cat.startswith("kids_") else 5200
    if n < low:
        errs.append(f"عدد الكلمات {n} أقل من {low}")
    if n > high:
        errs.append(f"عدد الكلمات {n} أكبر من {high}")
    tags = entry.get("hashtags", [])
    if not (5 <= len(tags) <= 7):
        errs.append(f"عدد الهاشتاغات {len(tags)} (المطلوب 5-7)")
    if any(not str(t).startswith("#") for t in tags):
        errs.append("هاشتاغ بدون #")
    if cat == "story_religious":
        if "إخلاء شرعي" not in content:
            errs.append("ينقص الإخلاء الشرعي أعلى النص")
        if "أعلم" not in content[-200:]:
            errs.append("ينقص «والله أعلم» في التذييل")
        if len(entry.get("refs", [])) < 2:
            errs.append("المصادر الشرعية أقل من اثنين")
        if "ﷺ" in content:
            errs.append("رمز ﷺ لم يُحوَّل إلى عبارة منطوقة")
    if cat == "story_horror" and ("تنبيه" not in summary + " " + content[:300]):
        errs.append("قصة الرعب تحتاج تنبيهاً نفسياً خفيفاً")
    for w in BANNED:
        if w in content:
            errs.append(f"كلمة محظورة: {w}")
    return errs


def make_article(entry: dict, old: dict, seed: int = 7) -> dict:
    title, summary, content = compose(entry, seed=seed)
    errs = validate(entry, title, summary, content)
    if errs:
        raise RuntimeError("; ".join(errs))
    a = dict(old)
    a["title"] = title
    a["summary"] = summary
    a["content"] = [p for p in content.split("\n\n") if p.strip()]
    a["hashtags"] = list(entry.get("hashtags", []))
    a["style"] = FICTION_STYLE_VER
    a["manual"] = True
    a["scenes"] = [
        {
            "text": str(b[0] if isinstance(b, (tuple, list)) else b.get("p", ""))[:180],
            "image": old.get("image", ""),
        }
        for b in entry.get("beats", [])[:8]
    ] if entry.get("beats") else old.get("scenes", [])
    return a


def main() -> int:
    ap = argparse.ArgumentParser(description="Kingdom Of Secrets — story writer.")
    ap.add_argument("--only", default="", help="معرّفات مفصولة بفواصل")
    ap.add_argument("--category", default="", help="كتابة كل قصص فئة واحدة")
    ap.add_argument("--all", action="store_true", help="كل القصص الـ34")
    ap.add_argument("--sample", action="store_true", help="معاينة أول قصة بدون كتابة")
    ap.add_argument("--install", action="store_true", help="كتابة النتائج في articles.json")
    ap.add_argument("--min-words", type=int, default=2000)
    ap.add_argument("--max-words", type=int, default=2600)
    ap.add_argument("--out-dir", default="", help="حفظ المعاينة كملفات نصية")
    args = ap.parse_args()

    data = json.loads(ARTICLES.read_text(encoding="utf-8"))
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    targets: list[tuple[str, dict, dict]] = []
    for cat, arts in data["articles"].items():
        if not cat.startswith(("story_", "kids_")):
            continue
        for a in arts:
            aid = a["id"]
            if args.all or (args.category and cat == args.category) or aid in only:
                if aid not in BIBLE:
                    print(f"⚠ لا يوجد وصف للقصة {aid} في كتاب القصة — تخطي.")
                    continue
                targets.append((cat, a, BIBLE[aid]))

    if args.sample and targets:
        targets = targets[:1]
    if not targets:
        print("لا توجد قصص مطابقة.")
        return 2

    out_dir = Path(args.out_dir) if args.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    ok = fail = 0
    print(f"سيُعاد كتابة {len(targets)} قصة…", flush=True)
    for i, (cat, old, entry) in enumerate(targets, 1):
        aid = old["id"]
        e = dict(entry)
        e["cat"] = e.get("cat", cat)
        try:
            title, summary, content = compose(e, min_words=args.min_words,
                                              max_words=args.max_words, seed=7 + i)
            errs = validate(e, title, summary, content)
            if errs:
                raise RuntimeError("; ".join(errs))
            if out_dir:
                (out_dir / f"{aid}.txt").write_text(title + "\n\n" + summary + "\n\n" + content,
                                                    encoding="utf-8")
            if args.install:
                new = make_article(e, old, seed=7 + i)
                old.update(new)
            ok += 1
            print(f"[{i}/{len(targets)}] {aid}: {_words(content)} كلمة ✓", flush=True)
        except Exception as ex:  # noqa: BLE001
            fail += 1
            print(f"[{i}/{len(targets)}] {aid}: FAILED {str(ex)[:200]}", flush=True)

    if args.install and ok:
        if not BACKUP.exists():
            shutil.copyfile(ARTICLES, BACKUP)
        ARTICLES.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"✓ كُتبت النتائج في {ARTICLES.name} (نسخة احتياطية: {BACKUP.name})")

    print(f"\nDONE ok={ok} failed={fail}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
