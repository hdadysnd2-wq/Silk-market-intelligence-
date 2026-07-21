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
    """صفٌّ من بذرتنا بلا ترجمةٍ عربية (إنجليزي فقط) لا يُطأطئ التداخل صفراً
    حين يقدّم النموذج وصفاً عربياً صحيحاً — الأفضل من المصدرين يفوز، لكن
    `verified` يبقى صحيحاً (الرمز فعلاً في مرجعنا) بمعزلٍ عن أيّ وصفٍ حسم."""
    import silk_hs_classifier as hsc
    # 200811 في بذرتنا بوصفٍ إنجليزي فقط (name_ar فارغ) — راجع data/hs_codes.csv.
    v = hsc._validated_candidate(
        "زبدة الفول السوداني", "200811",
        model_desc="فول سوداني محضّر أو محفوظ")
    assert v is not None
    assert v["verified"] is True
    assert v["overlap"] >= 0.6


def test_classify_general_deterministic_only_never_needs_llm_for_clean_match():
    """منتجٌ محسومٌ جيداً في بذرتنا («تمور») => تلقائي بلا أيّ نداء كلود،
    حتى مع `allow_claude=True` — لا هدر."""
    import silk_hs_classifier as hsc
    with patch("silk_ai_judge._call") as mock_call:
        r = hsc.classify_general("تمور", allow_claude=True)
    assert r["tier"] == "auto" and r["hs6"] == "080410"
    assert mock_call.called is False
    assert r["message"] == "✓ صُنّف تلقائياً"


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


def test_classify_general_manual_when_llm_disabled_and_deterministic_insufficient():
    """صمّام `SILK_HS_CLASSIFIER` مُطفأ + منتجٌ غير مغطّى جيداً => لا اختلاق،
    تدهورٌ صادقٌ لمنتقٍ يدوي (لا تلقائي، لا نداء)."""
    import silk_hs_classifier as hsc
    with patch.dict(os.environ, {"SILK_HS_CLASSIFIER": "0"}), \
         patch("silk_ai_judge._call") as mock_call:
        r = hsc.classify_general("مياه ورد", allow_claude=True)
    assert r["tier"] in ("candidates", "manual")
    assert r["hs6"] is None
    assert mock_call.called is False


def test_classify_general_llm_candidate_outside_our_csv_still_validated():
    """مرشّحٌ برمزٍ **خارج بذرتنا الجزئية** (لا يوجد في data/hs_codes.csv)
    لا يُرفَض تلقائياً — يُصادَق عليه ضد وصف النموذج نفسه (`verified=False`
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

def test_no_reservation_when_deterministic_already_sufficient():
    import silk_hs_classifier as hsc
    with patch("silk_usage.try_reserve_paid_calls") as mock_reserve:
        hsc.classify_general("تمور", allow_claude=True)
    mock_reserve.assert_not_called()


def test_reservation_denied_degrades_to_deterministic_candidates_only():
    """رفض الحجز (سقف مستنفَد) => تدهورٌ صادق، لا استثناء ولا اختلاق."""
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
