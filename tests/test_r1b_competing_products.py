"""اختبارات PR-B (R1 القطعة المركزية): قسم «المنتجات المنافسة وأسعارها»
كمخرَج أول في «المنافسة والتسعير والهامش» — القرار يُتَّخذ من داخل الدراسة.

يغطّي: (أ) ترقية بعثة pricing_scout (أداة locale + التقاط كامل + تطبيع/دليل)،
(ب) عقد برومبت الكاتب (جدول المنتجات المنافسة بأعمدته)، (ج) العيّنة المحفوظة
تُظهر الجدول وتبقى خالية من التِلِمِتري (حارس المصطلحات المحظورة).
Run:  python3 -m pytest tests/test_r1b_competing_products.py -q
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conftest import docx_all_text  # noqa: E402


# ── (أ) ترقية بعثة pricing_scout ──────────────────────────────────────────

def test_pricing_scout_can_reach_locale_reference():
    """الأداة locale مضافة لـallowed_tools — بدونها لا يعرف كلود لغة/متاجر
    السوق (اسم أداة غير مُدرَج = لا نداء صامت)."""
    import silk_missions as M
    assert "lookup_reference" in M.MISSIONS["pricing_scout"]["allowed_tools"]


def test_pricing_scout_instructions_capture_full_product_fields():
    import silk_missions as M
    ins = M.MISSIONS["pricing_scout"]["instructions"]
    assert "locale" in ins                       # يبدأ بمعرفة لغة/متاجر السوق
    assert "بلد المنشأ" in ins                    # التقاط المنشأ
    assert "حجم العبوة" in ins                    # التقاط العبوة
    assert "لكل كجم" in ins                       # تطبيع لكل كجم/وحدة
    assert "بالدولار" in ins                      # + بالدولار
    assert "◐" in ins and "✓" in ins             # شارة الدليل
    assert "جدول المنتجات المنافسة" in ins        # الجدول هو المخرَج الأساسي


def test_pricing_scout_keeps_baseline_ladder_and_comtrade():
    """قاعدة المالك: السلّم الحالي (≥٣ متاجر) وسطر كومتريد المرجعي يبقيان —
    هذه الترقية تضيف فوقهما لا تستبدلهما."""
    import silk_missions as M
    ins = M.MISSIONS["pricing_scout"]["instructions"]
    assert "٣ متاجر" in ins or "3 متاجر" in ins
    assert "comtrade_imports" in ins
    assert "سعر جملة مرجعي" in ins


# ── (ب) عقد برومبت الكاتب ─────────────────────────────────────────────────

def test_writer_prompt_requires_competing_products_table():
    import silk_ai_judge as J
    src = inspect.getsource(J.deep_report)
    # العنوان الفرعي المسمّى (قد ينقسم النص عبر سطرين في المصدر — نتحقق من
    # الجزأين المتّصلين لا من العبارة كاملة عبر فاصل السطر).
    assert "### المنتجات" in src and "المنافسة وأسعارها" in src
    assert "المنشأ" in src and "العبوة" in src           # أعمدة الالتقاط
    assert "السعر/كجم بالدولار" in src                   # عمود التطبيع
    assert "✓ مرصود برابط" in src and "◐ مُقدَّر" in src  # عمود الدليل
    assert "صفّ بفجوة معلنة لا حذف" in src               # لا حذف للمفقود


def test_writer_prompt_keeps_hhi_and_no_product_card_contract():
    """الترقية تحافظ على محتوى HHI وجملة 'أسعار السوق مرصودة' القائمة."""
    import silk_ai_judge as J
    src = inspect.getsource(J.deep_report)
    assert "HHI" in src
    assert "أسعار السوق مرصودة" in src


# ── (ج) العيّنة المحفوظة تُظهر الجدول وتبقى نظيفة ──────────────────────────

def test_committed_client_sample_shows_competing_products_table():
    import silk_reports as R
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "samples", "client_report_latest.docx")
    assert os.path.exists(path), "شغّل tools/gen_client_report_sample.py"
    text = docx_all_text(path)
    # العنوان المسمّى + صف منافِس + شارة دليل + عمود التطبيع
    assert "المنتجات المنافسة وأسعارها" in text
    assert "دقلة نور" in text                       # منتج منافِس مرصود بالاسم
    assert "السعر/كجم بالدولار" in text             # عمود التطبيع
    assert "✓" in text and "◐" in text              # شارتا الدليل
    # يهبط داخل قسم العميل الصحيح
    assert "المنافسة والتسعير والهامش" in text
    # يبقى خالياً من التِلِمِتري رغم الإضافة
    assert R._client_forbidden_hits(text) == []
