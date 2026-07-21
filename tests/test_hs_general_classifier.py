"""المصنّف العام لرمز HS — الموجة ٣ (systemic fix، طلب المُشرِف).

البذرة الحتمية (CSV) بذرةُ بدايةٍ لا الحاكم النهائي أبداً — أيّ منتجٍ ضعيف
التمثيل فيها يُطابَق بأقرب صفٍّ لفظياً حتى لو كانت فئته خاطئة تماماً («زبدة
الفول السوداني» => الألبان بدل محضرات الفول السوداني). هذا الملف يقفل:
(PART 1) المصنّف العام + بوابة التحقّق الحتمية + الذاكرة، و(PART 3) بطارية
انحدار عبر عائلات منتجات متنوّعة تثبت التعميم لا حالة واحدة.

Run: python3 -m pytest tests/test_hs_general_classifier.py -q
"""
import json
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path):
    """ذاكرة تصنيف HS معزولة لكل اختبار — لا تلوّث data/ الحقيقي ولا يصيب
    اختبارٌ ذاكرة اختبارٍ آخر (تعارضٌ كاذب بين منتجاتٍ متشابهة الاسم)."""
    import silk_store
    db = str(tmp_path / "store.db")
    with patch.object(silk_store, "_db_path", return_value=db):
        yield


def _fake_llm(candidates: list[dict]):
    return json.dumps({"candidates": candidates})


# ══════════════ PART 1 — البوابة الحتمية (سلامة الفصل + تداخل الصفات) ══════

def test_chapter_sanity_rejects_malformed_and_out_of_range_codes():
    """رمزٌ مشوَّه (ليس ٦ أرقام) أو فصلٌ غير موجود في بنية WCO يُرفَض بنيوياً
    قبل أيّ فحص تداخل نصّي — بمعزلٍ عن أيّ ثقةٍ ادّعاها النموذج."""
    import silk_hs_classifier as hsc
    assert hsc._validated_candidate("تمور", "12345") is None      # ٥ أرقام
    assert hsc._validated_candidate("تمور", "999999") is None     # فصل ٩٩ غير موجود
    assert hsc._validated_candidate("تمور", "abcdef") is None     # ليس أرقاماً
    assert hsc._validated_candidate("منتج بترولي", "271000") is None  # فصل ٢٧ مستبعَد نطاقياً


def test_validated_candidate_combines_csv_and_model_description():
    """صفٌّ من القائمة الرسمية بلا ترجمةٍ عربية (إنجليزي فقط، `keywords_ar`
    فارغ) لا يُطأطئ التداخل صفراً حين يقدّم النموذج وصفاً عربياً صحيحاً —
    الأفضل من المصدرين يفوز، لكن `verified` يبقى صحيحاً (الرمز فعلاً في
    المرجع) بمعزلٍ عن أيّ وصفٍ حسم."""
    import silk_hs_classifier as hsc
    from silk_hs_resolver import load_hs_codes
    # 200850 (مشمش محفوظ) بوصفٍ إنجليزيٍّ فقط — لم يُرحَّل له مقابلٌ عربي في
    # الترحيل (لا يوجد رمزٌ مطابقٌ في البذرة القديمة) — راجع data/hscodes_full.csv.
    row = next(r for r in load_hs_codes() if r["hs_code"] == "200850")
    assert not (row.get("keywords_ar") or "").strip(), (
        "الاختبار يفترض صفّاً إنجليزياً فقط — عدِّل الرمز إن أُضيفت له ترجمةٌ لاحقاً")
    v = hsc._validated_candidate(
        "مشمش مجفف محفوظ", "200850", model_desc="مشمش محفوظ")
    assert v is not None
    assert v["verified"] is True
    assert v["overlap"] >= 0.6


def test_classify_general_always_asks_the_model_no_local_shortcut_even_for_clean_product():
    """عكس التدفّق (طلب المُشرِف): القائمة المحلية لم تعد تقترح أبداً — حتى
    منتجٌ واضحٌ («تمور») يستلزم استشارة النموذج (مُحاكاة هنا)، لا اقتراحاً
    محلياً مجانياً. أول نداءٍ فعليّ؛ التكرار الثاني لنفس المنتج **مجانيّ**
    (الذاكرة) — لا هدرٌ متكرّر، لكن صفر نداءٍ للمرّة الأولى لم يعد ممكناً."""
    import silk_hs_classifier as hsc
    fake = _fake_llm([{"hs6": "080410", "description_ar": "تمور طازجة أو مجففة",
                       "reason_ar": "تمور تمور تمور — تطابقٌ مباشر",
                       "confidence": 0.95}])
    with patch.dict(os.environ, {"SILK_HS_CLASSIFIER": "1"}), \
         patch("silk_ai_judge.available", return_value=True), \
         patch("silk_ai_judge._call", return_value=fake) as mock_call, \
         patch("silk_usage.try_reserve_paid_calls", return_value=True), \
         patch("silk_usage.try_reserve_usd", return_value=True):
        r1 = hsc.classify_general("تمور", allow_claude=True)
        n1 = mock_call.call_count
        r2 = hsc.classify_general("تمور", allow_claude=True)
        n2 = mock_call.call_count
    assert n1 == 1, "أول تصنيفٍ لمنتجٍ جديد يجب أن يستشير النموذج فعلياً"
    assert n2 == n1, "التكرار الثاني لنفس المنتج مجانيٌّ عبر الذاكرة"
    assert r1["tier"] == "auto" and r1["hs6"] == "080410"
    assert r1["message"] == "✓ صُنّف تلقائياً"
    assert r2["hs6"] == "080410"


def test_classify_general_no_llm_available_never_guesses_locally_even_for_clean_product():
    """بلا كلود إطلاقاً (لا مفتاح/الصمّام مُطفأ) — القائمة المحلية **لا
    تقترح بديلاً أبداً** حتى لمنتجٍ واضح؛ فجوةٌ معلنة صادقة (يدويّ) لا
    تخمينٌ محليّ. هذا الفارق الجوهري عن السلوك القديم (اللاحق الحتمي كان
    يقترح بثقة بلا أيّ نداء) — الآن التحقّق المحلي لا يقترح مطلقاً."""
    import silk_hs_classifier as hsc
    with patch.dict(os.environ, {"SILK_HS_CLASSIFIER": "0"}), \
         patch("silk_ai_judge._call") as mock_call:
        r = hsc.classify_general("تمور", allow_claude=True)
    assert mock_call.called is False
    assert r["tier"] == "manual"
    assert r["hs6"] is None


def test_classify_general_never_auto_passes_flagged_product_without_llm():
    """«زبدة الفول السوداني» — العيّنة الأصلية للحادثة. بلا كلود (اللاحق
    الحتمي وحده) لا تلقائي أبداً؛ 040510 يظهر كمرشّحٍ (صادقٍ) لا كحكمٍ نهائي."""
    import silk_hs_classifier as hsc
    r = hsc.classify_general("زبدة الفول السوداني", hs_code="040510",
                             allow_claude=False)
    assert r["tier"] != "auto"
    assert r["hs6"] is None


def test_classify_general_llm_assisted_surfaces_correct_family_over_wrong_one():
    """بمساعدة كلود (مُحاكاة) — العائلة الصحيحة (٢٠٠٨) تتصدّر على الفئة
    اللفظية الخاطئة (٠٤٠٥١٠) بفارقٍ واضح."""
    import silk_hs_classifier as hsc
    fake = _fake_llm([
        {"hs6": "200811", "description_ar": "فول سوداني محضّر أو محفوظ",
         "reason_ar": "زبدة الفول السوداني تندرج تحت محضرات الفول السوداني",
         "confidence": 0.9},
        {"hs6": "210690", "description_ar": "محضرات غذائية أخرى",
         "reason_ar": "بديلٌ عام", "confidence": 0.4},
    ])
    with patch.dict(os.environ, {"SILK_HS_CLASSIFIER": "1"}), \
         patch("silk_ai_judge.available", return_value=True), \
         patch("silk_ai_judge._call", return_value=fake), \
         patch("silk_usage.try_reserve_paid_calls", return_value=True), \
         patch("silk_usage.try_reserve_usd", return_value=True):
        r = hsc.classify_general("زبدة الفول السوداني", hs_code="040510",
                                 allow_claude=True)
    top = r["candidates"][0]
    assert top["hs6"] == "200811"
    assert all(c["hs6"] != "040510" or c["confidence"] < top["confidence"]
              for c in r["candidates"])


def test_classify_general_manual_when_llm_disabled_no_local_fallback():
    """صمّام `SILK_HS_CLASSIFIER` مُطفأ => لا اختلاق، تدهورٌ صادقٌ لمنتقٍ
    يدوي (لا تلقائي، لا نداء) — القائمة المحلية لا تقترح بديلاً أبداً."""
    import silk_hs_classifier as hsc
    with patch.dict(os.environ, {"SILK_HS_CLASSIFIER": "0"}), \
         patch("silk_ai_judge._call") as mock_call:
        r = hsc.classify_general("مياه ورد", allow_claude=True)
    assert r["tier"] in ("candidates", "manual")
    assert r["hs6"] is None
    assert mock_call.called is False


def test_classify_general_llm_candidate_outside_our_csv_still_validated():
    """مرشّحٌ برمزٍ **خارج المرجع الرسمي الكامل** (لا يوجد في
    data/hscodes_full.csv — نظرياً فقط الآن؛ المرجع كاملٌ رسمياً، لكن
    الحارس البنيوي يبقى ضرورياً لأيّ رمزٍ مشوَّه/مُختلَق من النموذج) لا
    يُرفَض تلقائياً — يُصادَق عليه ضد وصف النموذج نفسه (`verified=False`
    صراحةً، لا اختلاقاً)، ويظهر إن مرّ البوابة."""
    import silk_hs_classifier as hsc
    from silk_hs_confirm import _find_row
    # اختر رمزاً هيكلياً صحيحاً (فصلٌ حقيقي) لكنه غائبٌ عن مرجعنا فعلياً —
    # نبحث عنه ديناميكياً بدل تثبيت رقمٍ صلب (عائلة hardcoded-product-rule).
    from silk_hs_resolver import VALID_HS_CHAPTERS, load_hs_codes
    present = {r["hs_code"] for r in load_hs_codes()}
    missing_code = None
    for ch in sorted(VALID_HS_CHAPTERS):
        for suffix in range(100, 999):
            cand = f"{ch}{suffix:04d}"[:6]
            if len(cand) == 6 and cand not in present:
                missing_code = cand
                break
        if missing_code:
            break
    assert missing_code, "تعذّر إيجاد رمزٍ هيكليٍّ صحيح غائبٍ عن المرجع للاختبار"
    fake = _fake_llm([{"hs6": missing_code,
                       "description_ar": "منتج فريد بلا ترجمة في مرجعنا",
                       "reason_ar": "تطابقٌ دلاليّ من معرفة النموذج",
                       "confidence": 0.7}])
    with patch.dict(os.environ, {"SILK_HS_CLASSIFIER": "1"}), \
         patch("silk_ai_judge.available", return_value=True), \
         patch("silk_ai_judge._call", return_value=fake), \
         patch("silk_usage.try_reserve_paid_calls", return_value=True), \
         patch("silk_usage.try_reserve_usd", return_value=True):
        r = hsc.classify_general("منتج فريد بلا ترجمة في مرجعنا",
                                 allow_claude=True)
    hits = [c for c in r["candidates"] if c["hs6"] == missing_code]
    assert hits and hits[0]["verified"] is False


# ══════════════ الذاكرة — نداءٌ واحدٌ فقط لكل منتجٍ جديد ═══════════════════

def test_repeat_product_hits_cache_zero_extra_llm_calls():
    import silk_hs_classifier as hsc
    fake = _fake_llm([{"hs6": "330741", "description_ar": "بخور وعود",
                       "reason_ar": "مطابقة مباشرة", "confidence": 0.85}])
    mock_call = MagicMock(return_value=fake)
    with patch.dict(os.environ, {"SILK_HS_CLASSIFIER": "1"}), \
         patch("silk_ai_judge.available", return_value=True), \
         patch("silk_ai_judge._call", mock_call), \
         patch("silk_usage.try_reserve_paid_calls", return_value=True), \
         patch("silk_usage.try_reserve_usd", return_value=True):
        r1 = hsc.classify_general("عود معطر فاخر جداً غير معتاد", allow_claude=True)
        n1 = mock_call.call_count
        r2 = hsc.classify_general("عود معطر فاخر جداً غير معتاد", allow_claude=True)
        n2 = mock_call.call_count
    assert n1 >= 1
    assert n2 == n1, "التكرار الثاني لنفس المنتج يجب ألّا يستدعي كلود إطلاقاً"
    assert r1["candidates"] and r2["candidates"]


def test_cache_key_normalizes_diacritics_and_case():
    import silk_hs_classifier as hsc
    fake = _fake_llm([{"hs6": "330741", "description_ar": "بخور",
                       "reason_ar": "x", "confidence": 0.6}])
    mock_call = MagicMock(return_value=fake)
    with patch.dict(os.environ, {"SILK_HS_CLASSIFIER": "1"}), \
         patch("silk_ai_judge.available", return_value=True), \
         patch("silk_ai_judge._call", mock_call), \
         patch("silk_usage.try_reserve_paid_calls", return_value=True), \
         patch("silk_usage.try_reserve_usd", return_value=True):
        hsc.classify_general("عُوداً معطّراً نادراً تماماً", allow_claude=True)
        hsc.classify_general("عودا معطرا نادرا تماما", allow_claude=True)
    assert mock_call.call_count == 1


# ══════════════ الحجز — لا حجزَ استكشافيّ، فقط عند الحاجة الفعلية ══════════

def test_no_reservation_when_classifier_flag_off():
    """الصمّام `SILK_HS_CLASSIFIER` هو البوّابة — مُطفأً (الافتراضي هنا، لا
    ضبط بيئةٍ صريح) لا حجز إطلاقاً مهما كان `allow_claude`؛ لا اقتراحاً
    محلياً بديلاً يُغني عن الحجز (ذلك المسار حُذف — عكس التدفّق)."""
    import silk_hs_classifier as hsc
    with patch("silk_usage.try_reserve_paid_calls") as mock_reserve:
        hsc.classify_general("تمور", allow_claude=True)
    mock_reserve.assert_not_called()


def test_reservation_denied_degrades_to_declared_gap_not_local_guess():
    """رفض الحجز (سقف مستنفَد) => تدهورٌ صادق (فجوةٌ معلنة)، لا استثناء ولا
    اختلاقٌ محلّي بديل — القائمة المحلية لا تقترح شيئاً عوضاً عن كلود."""
    import silk_hs_classifier as hsc
    with patch.dict(os.environ, {"SILK_HS_CLASSIFIER": "1"}), \
         patch("silk_ai_judge.available", return_value=True), \
         patch("silk_usage.try_reserve_paid_calls", return_value=False), \
         patch("silk_ai_judge._call") as mock_call:
        r = hsc.classify_general("مياه ورد", allow_claude=True)
    assert mock_call.called is False
    assert r["tier"] in ("candidates", "manual")


# ══════════════ preflight_block — نقطة الاختناق تحمل مرشّحين لا رفضاً عارياً ═

def test_preflight_block_attaches_candidates_on_flagged_code():
    from silk_hs_confirm import preflight_block
    with patch.dict(os.environ, {"SILK_HS_CONFIRM_GATE": "1"}):
        blocked = preflight_block("زبدة الفول السوداني", "040510",
                                  allow_claude=False)
    assert blocked is not None
    assert blocked["error"] == "hs_confirmation_needed"
    assert "candidates" in blocked and isinstance(blocked["candidates"], list)
    assert blocked["candidates"]  # غير فارغة — على الأقل 040510 نفسه كمرشّح صادق


def test_preflight_block_never_renders_auto_badge_message():
    """رسالةُ الحجب لا تحمل «✓ صُنّف تلقائياً» أبداً — تناقضٌ (البند: لا
    اعرض تأكيداً تلقائياً على رفضٍ)."""
    from silk_hs_confirm import preflight_block
    with patch.dict(os.environ, {"SILK_HS_CONFIRM_GATE": "1"}):
        blocked = preflight_block("زبدة الفول السوداني", "040510",
                                  allow_claude=False)
    assert "✓" not in blocked["message"]
    assert "صُنّف تلقائياً" not in blocked["message"]


def test_preflight_block_confirmed_code_still_passes_with_zero_candidates_call():
    """رمزٌ مؤكَّدٌ (تمور/080410) لا يستدعي `classify_general` إطلاقاً —
    لا هدرَ حسابيّاً على المسار السعيد الشائع."""
    from silk_hs_confirm import preflight_block
    with patch.dict(os.environ, {"SILK_HS_CONFIRM_GATE": "1"}), \
         patch("silk_hs_classifier.classify_general") as mock_gen:
        blocked = preflight_block("تمور", "080410", allow_claude=True)
    assert blocked is None
    mock_gen.assert_not_called()


# ══════════════ PART 3 — بطارية الانحدار عبر عائلات منتجات متنوّعة ═════════
#
# كل صفٍّ: (المنتج، فصولُ HS2 المقبولة). العقد: **مهما كانت الدرجة (تلقائي/
# مرشّحون/يدوي)**، لا تلقائيٌّ أبداً برمزٍ خارج الفصول المقبولة — هذا يثبت
# التعميم (لا حالة "زبدة الفول السوداني" وحدها) بمعزلٍ عن توفّر كلود.

_BATTERY = [
    ("زبدة الفول السوداني", {"20", "21"}),   # peanut butter — ليس ٠٤ (ألبان)
    ("مياه ورد", {"33"}),                     # rose water — عطور/زيوت
    ("شيبس بنكهة الجبن", {"19", "20", "21"}),  # cheese-flavored chips
    ("تمر سكري", {"08"}),                      # sukkari dates
    ("عسل سدر", {"04"}),                       # sidr honey
    ("عود معطر", {"33", "44"}),                # oud incense
    ("مكسرات محمصة مملحة", {"20", "08"}),      # roasted salted nuts
    ("صلصة شطة", {"20", "21"}),                # chili sauce
    ("قهوة مختصة محمصة", {"09"}),              # specialty roasted coffee
    ("مياه زمزم معبأة", {"22"}),               # zamzam-style bottled water
]


@pytest.mark.parametrize("product,ok_chapters", _BATTERY)
def test_battery_never_auto_passes_wrong_chapter_without_llm(product, ok_chapters):
    """صفر مساعدةٍ من كلود (اللاحق الحتمي وحده، أسوأ حال) — أيّ نتيجة
    تلقائية يجب أن تقع في فصلٍ مقبول؛ غير ذلك يُسجَّل الحكم tier != auto
    (يسأل، لا يخمّن) — العقد الجوهري لكل هذا الإصلاح."""
    import silk_hs_classifier as hsc
    r = hsc.classify_general(product, allow_claude=False)
    if r["tier"] == "auto":
        chapter = r["hs6"][:2]
        assert chapter in ok_chapters, (
            f"{product!r}: تلقائيٌّ بفصلٍ خاطئ {chapter} (رمز {r['hs6']}) — "
            "خرقٌ للعقد الجوهري (لا تخمين صامت)")
    # tier != auto مقبولٌ دائماً (يسأل بدل يخمّن) — لا فشل هنا.


_BATTERY_LLM_HINTS = {
    "مياه ورد": [{"hs6": "330129", "description_ar": "مياه مقطّرة عطرية",
                 "reason_ar": "مياه ورد منتجٌ من المياه العطرية المقطّرة",
                 "confidence": 0.85}],
    "شيبس بنكهة الجبن": [{"hs6": "200520", "description_ar": "بطاطس محضّرة أو محفوظة",
                          "reason_ar": "شيبس البطاطس محضّرات خضروات",
                          "confidence": 0.8}],
    "مكسرات محمصة مملحة": [{"hs6": "200819", "description_ar": "مكسرات أخرى محضّرة أو محفوظة",
                            "reason_ar": "تحميص وتمليح لا يغيّر الفصل الأساسي",
                            "confidence": 0.85}],
    "صلصة شطة": [{"hs6": "210390", "description_ar": "صلصات وتوابل مركّبة أخرى",
                  "reason_ar": "صلصة شطة صلصةٌ مركّبة",
                  "confidence": 0.8}],
    "مياه زمزم معبأة": [{"hs6": "220110", "description_ar": "مياه معدنية وغازية معبّأة",
                          "reason_ar": "مياه معبّأة للشرب",
                          "confidence": 0.8}],
}


@pytest.mark.parametrize("product,hints", sorted(_BATTERY_LLM_HINTS.items()))
def test_battery_llm_assisted_surfaces_correct_chapter_when_deterministic_weak(
        product, hints):
    """للمنتجات ضعيفة التمثيل في بذرتنا — بمساعدة كلود (مُحاكاة، وصفٌ رسميٌّ
    واقعي) — الفصل الصحيح **يظهر ضمن المرشّحين المعروضين** (لا يُفقَد)،
    ومهما كانت النتيجة (تلقائي أو مرشّحون) لا فصل خاطئ يمرّ تلقائياً."""
    import silk_hs_classifier as hsc
    ok_chapters = dict(_BATTERY)[product]
    fake = _fake_llm(hints)
    with patch.dict(os.environ, {"SILK_HS_CLASSIFIER": "1"}), \
         patch("silk_ai_judge.available", return_value=True), \
         patch("silk_ai_judge._call", return_value=fake), \
         patch("silk_usage.try_reserve_paid_calls", return_value=True), \
         patch("silk_usage.try_reserve_usd", return_value=True):
        r = hsc.classify_general(product, allow_claude=True)
    surfaced_chapters = {c["hs6"][:2] for c in r["candidates"]}
    assert surfaced_chapters & ok_chapters, (
        f"{product!r}: لا مرشّح بفصلٍ صحيح ({ok_chapters}) ضمن "
        f"{[c['hs6'] for c in r['candidates']]}")
    if r["tier"] == "auto":
        assert r["hs6"][:2] in ok_chapters


# ══════════════ ONE FIX — الأساسي المصادَق يتصدّر، لا المرفوض ولا الفراغ ═══
#
# البلاغ الحيّ (طلب المُشرِف): التاجر لا يعرف رموز HS ولا يجوز أن يُطلَب منه
# كتابة واحد أبداً. حين يرفض اللاحق الحتمي مرشّحه الوحيد (تداخل صفاتٍ مميّزة
# دون العتبة)، يجب أن **يتصدّر** مرشّحٌ صحيحٌ مصادَقٌ عليه فعلياً (نداء كلود
# مُحاكًى هنا) — لا الرمز المرفوض نفسه (حتى لو بقي «مُتحقَّقاً» لمجرّد وجوده
# في بذرتنا الجزئية)، ولا منتقٍ يدويٌّ فارغ. ثماني عائلاتٍ متنوّعة (طلب
# المُشرِف الصريح) تثبت التعميم — لا حالة «زبدة الفول السوداني» وحدها من
# جديد. القفل يفحص **موضع** المرشّح الأول تحديداً (`candidates[0]`) — عكس
# الاختبار أعلاه الذي يكتفي بظهور الفصل الصحيح في أيّ مكان ضمن القائمة.

_BREADTH_8 = [
    # (المنتج، فصولُ HS2 المقبولة للمرشّح **الأساسي**، تلميحُ كلود المُحاكى)
    ("زبدة الفول السوداني", {"20", "21"},
     [{"hs6": "200811", "description_ar": "فول سوداني محضّر أو محفوظ",
       "reason_ar": "زبدة الفول السوداني تندرج تحت محضرات الفول السوداني لا الألبان",
       "confidence": 0.9}]),
    ("مياه ورد", {"33"},
     [{"hs6": "330129", "description_ar": "مياه مقطّرة عطرية",
       "reason_ar": "مياه ورد منتجٌ من المياه العطرية المقطّرة",
       "confidence": 0.85}]),
    ("عود معطر", {"33", "44"},
     [{"hs6": "330741", "description_ar": "بخور وعود",
       "reason_ar": "عود معطر بخورٌ عطري", "confidence": 0.8}]),
    ("شيبس بنكهة الجبن", {"19", "20", "21"},
     [{"hs6": "200520", "description_ar": "بطاطس محضّرة أو محفوظة",
       "reason_ar": "شيبس البطاطس محضّرات خضروات لا أجبان",
       "confidence": 0.8}]),
    ("قهوة عربية محمصة", {"09"},
     [{"hs6": "090121", "description_ar": "بن محمص غير منزوع الكافيين",
       "reason_ar": "قهوة عربية محمصة بنٌّ محمّص", "confidence": 0.85}]),
    ("صلصة شطة", {"20", "21"},
     [{"hs6": "210390", "description_ar": "صلصات وتوابل مركّبة أخرى",
       "reason_ar": "صلصة شطة صلصةٌ مركّبة", "confidence": 0.8}]),
    ("مكسرات محمصة مملحة", {"20", "08"},
     [{"hs6": "200819", "description_ar": "مكسرات أخرى محضّرة أو محفوظة",
       "reason_ar": "تحميص وتمليح لا يغيّر الفصل الأساسي",
       "confidence": 0.85}]),
    ("لبان مستكة", {"13"},
     [{"hs6": "130190", "description_ar": "صموغ وراتنجات طبيعية أخرى",
       "reason_ar": "لبان المستكة راتنجٌ طبيعي", "confidence": 0.8}]),
]


@pytest.mark.parametrize("product,ok_chapters,hints", _BREADTH_8,
                         ids=[c[0] for c in _BREADTH_8])
def test_breadth_active_resolution_surfaces_correct_primary_not_rejected_or_blank(
        product, ok_chapters, hints):
    """ONE FIX — طلب المُشرِف الصريح، حرفياً: عبر ثماني عائلاتٍ متنوّعة،
    حين يرفض اللاحق الحتمي مرشّحه الوحيد، مسار كلود (مُحاكًى — بيئة CI بلا
    مفتاح حيّ) يُستدعى فعلياً ويتصدّر **المرشّح الأول** (`candidates[0]`)
    بنقرة واحدة — لا الرمز المرفوض (حتى لو تعادل لفظياً أو تصدّر بمجرّد
    وجوده في بذرتنا الجزئية)، ولا تدهورٌ لمنتقٍ يدويٍّ رغم توفّر مرشّحٍ صحيح.

    الحسم الحيّ (بمفتاح كلود فعلي) يتطلّب بيئة المالك — هذا القفل يثبت
    **الآلية** (استدعاءٌ + تحقّقٌ + صدارةٌ) حتمياً بمحاكاة استجابة النموذج."""
    import silk_hs_classifier as hsc
    fake = _fake_llm(hints)
    with patch.dict(os.environ, {"SILK_HS_CLASSIFIER": "1"}), \
         patch("silk_ai_judge.available", return_value=True), \
         patch("silk_ai_judge._call", return_value=fake), \
         patch("silk_usage.try_reserve_paid_calls", return_value=True), \
         patch("silk_usage.try_reserve_usd", return_value=True):
        r = hsc.classify_general(product, allow_claude=True)
    assert r["tier"] != "manual", (
        f"{product!r}: تدهورٌ لمنتقٍ يدويٍّ فارغ رغم مرشّحٍ صحيحٍ متاحٍ من كلود")
    assert r["candidates"], f"{product!r}: لا مرشّحين إطلاقاً"
    primary = r["candidates"][0]
    assert primary["hs6"][:2] in ok_chapters, (
        f"{product!r}: المرشّح الأساسي {primary['hs6']} (فصل "
        f"{primary['hs6'][:2]}) خارج الفصول المقبولة {ok_chapters} — لم "
        f"يتصدّر المرشّح الصحيح رغم توفّره ضمن {[c['hs6'] for c in r['candidates']]}")


# ══════════════ القائمة الرسمية الكاملة — التباسٌ عبر-فصولٍ + تغطية الأقسام ═
#
# طلب المُشرِف الصريح (الترحيل للقائمة الرسمية الكاملة HS2022): (أ) عباراتٌ
# مركّبة حيث كلمةٌ واحدةٌ بمفردها تقع في فصلٍ مختلفٍ عن العبارة كاملةً —
# «زيت» وحدها قد تصادف الفصل ٢٧ المستبعَد (وقود معدني) بينما «زيت السمسم»
# فصلٌ غذائيٌّ ١٥ بلا علاقة؛ «أنابيب» وحدها قد تصادف الفصل ٧٣ (صلب) بينما
# «أنابيب بلاستيكية» فصلٌ ٣٩ مختلفٌ تماماً. (ب) قسمٌ واحدٌ على الأقل من كل
# قسمٍ رئيسي (غذاء/نسيج/آلات/كيماويات) — إثباتُ عمومية الآلية عبر تصنيف
# النظام المنسّق كاملاً، لا الأغذية وحدها التي هيمنت على البطاريات السابقة.

_SECTION_AND_COMPOUND_PHRASE = [
    # (المنتج، فصولُ HS2 المقبولة للمرشّح الأساسي، تلميحُ كلود المُحاكى)
    ("معجون طماطم", {"20"},  # غذاء — «معجون» وحدها قد تصادف معاجين تجميلية
     [{"hs6": "200290", "description_ar": "طماطم محضّرة أو محفوظة",
       "reason_ar": "معجون طماطم محضّرات طماطم غذائية لا معجوناً تجميلياً",
       "confidence": 0.85}]),
    ("زيت السمسم", {"15"},  # غذاء/دهون — «زيت» وحدها قد تصادف الفصل ٢٧ المستبعَد
     [{"hs6": "151550", "description_ar": "زيت السمسم وكسوره",
       "reason_ar": "زيت السمسم زيتٌ نباتيٌّ غذائي لا وقوداً معدنياً",
       "confidence": 0.85}]),
    ("أنابيب بلاستيكية للري", {"39"},  # بلاستيك — «أنابيب» وحدها قد تصادف صلب الفصل ٧٣
     [{"hs6": "391722", "description_ar": "أنابيب بلاستيكية من البولي بروبلين",
       "reason_ar": "أنابيب بلاستيكية للري من مادة البلاستيك لا الصلب",
       "confidence": 0.85}]),
    ("خيوط قطن للحياكة", {"52"},  # نسيج — «خيوط» وحدها قد تصادف حرير/صناعي
     [{"hs6": "520512", "description_ar": "خيوط قطنية غير مخصّصة للبيع بالتجزئة",
       "reason_ar": "خيوط قطن للحياكة من القطن الطبيعي لا الحرير أو الصناعي",
       "confidence": 0.85}]),
    ("سبيكة ذهب خام", {"71"},  # معادن ثمينة/مجوهرات — «سبيكة» وحدها قد تصادف معادن أساسية
     [{"hs6": "710812", "description_ar": "ذهب خام غير مصكوك",
       "reason_ar": "سبيكة ذهب خام من المعدن الثمين لا المعادن الأساسية",
       "confidence": 0.85}]),
    ("مضخة مياه طرد مركزي", {"84"},  # آلات
     [{"hs6": "841370", "description_ar": "مضخات طرد مركزي للسوائل",
       "reason_ar": "مضخة مياه طرد مركزي آلةٌ ميكانيكية",
       "confidence": 0.85}]),
    ("حمض الستريك", {"29"},  # كيماويات عضوية
     [{"hs6": "291814", "description_ar": "حمض الستريك",
       "reason_ar": "حمض الستريك حمضٌ عضويٌّ كربوكسيلي",
       "confidence": 0.85}]),
    ("صودا كاوية", {"28"},  # كيماويات غير عضوية
     [{"hs6": "281511", "description_ar": "هيدروكسيد الصوديوم — صودا كاوية صلبة",
       "reason_ar": "صودا كاوية مادّةٌ كيماويةٌ غير عضوية",
       "confidence": 0.85}]),
]


@pytest.mark.parametrize("product,ok_chapters,hints", _SECTION_AND_COMPOUND_PHRASE,
                         ids=[c[0] for c in _SECTION_AND_COMPOUND_PHRASE])
def test_section_and_compound_phrase_breadth_surfaces_correct_primary(
        product, ok_chapters, hints):
    """ترحيل القائمة الكاملة (طلب المُشرِف): عباراتٍ مركّبة (كلمةٌ منفردة
    تقع في فصلٍ مختلفٍ عن العبارة كاملةً) + قسمٌ واحدٌ على الأقل من كل قسمٍ
    رئيسي (غذاء/بلاستيك/نسيج/معادن ثمينة/آلات/كيماويات×٢) — المرشّح الأساسي
    دوماً بالفصل الصحيح، لا فصل الكلمة المفردة المُضلِّل."""
    import silk_hs_classifier as hsc
    fake = _fake_llm(hints)
    with patch.dict(os.environ, {"SILK_HS_CLASSIFIER": "1"}), \
         patch("silk_ai_judge.available", return_value=True), \
         patch("silk_ai_judge._call", return_value=fake), \
         patch("silk_usage.try_reserve_paid_calls", return_value=True), \
         patch("silk_usage.try_reserve_usd", return_value=True):
        r = hsc.classify_general(product, allow_claude=True)
    assert r["tier"] != "manual", (
        f"{product!r}: تدهورٌ لمنتقٍ يدويٍّ فارغ رغم مرشّحٍ صحيحٍ متاحٍ من كلود")
    assert r["candidates"], f"{product!r}: لا مرشّحين إطلاقاً"
    primary = r["candidates"][0]
    assert primary["hs6"][:2] in ok_chapters, (
        f"{product!r}: المرشّح الأساسي {primary['hs6']} (فصل "
        f"{primary['hs6'][:2]}) خارج الفصول المقبولة {ok_chapters} — لم "
        f"يتصدّر المرشّح الصحيح رغم توفّره ضمن {[c['hs6'] for c in r['candidates']]}")
