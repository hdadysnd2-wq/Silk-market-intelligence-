#!/usr/bin/env python3
"""معايرةُ مقياس محاذاة RTL — RTL-alignment measurer calibration (Wave 2, §4).

> **أمر المُشرِف (الخيار ٣ + التعديلات الأربعة).** قبل الوثوق بأيّ رقم: ابنِ
> عيّنتين من **نفس** المحتوى العربي — A بـ`jc=start` (الوصفة الصحيحة، يجب أن
> تنحاز يمينًا)، وB بـ`jc=right` (البناء المقلوب المعروف، ينحاز يسارًا).
>
> **العقد (التعديل ١): صفرُ محاذاةٍ يسارًا للأسطر العربية.** fixture-A أثبت أنّ
> الوصفة تُصيَّر **100%** يمينًا — فأيّ سطرٍ **عربيّ الأغلبية** مُحاذًى يسارًا
> عيبٌ حقيقيّ. الأسطرُ لاتينيّةُ الأغلبية (أسماء مصادر، تواريخ، أرقام، رموز HS)
> **تُستثنى** من النسبة كليًّا. التساهلُ الهندسيّ 10 نقاط فقط.
>
> الاحتياطيّ القديم `pdftotext -bbox` كان يعدّ **كلّ كلمةٍ سطرًا** بلا تجميع y
> (لا يميّز A من B) => حُذِف نهائيًّا. القياسُ الآن `pymupdf/fitz` بتجميعٍ صحيحٍ
> للأسطر على y — تبعيةٌ صلبةٌ لوظيفة e2e.

يُشغَّل في وظيفة e2e-live-shape (soffice + fitz حاضران هناك):
    python3 tools/rtl_calibration.py
يطبع نسخة LibreOffice + خُلاصة تصنيفٍ لكلّ عيّنة + حكم A/B، وينهي بـ0 دائمًا
(تشخيصيّ). الحارسُ الدائم لنفس العقد يعيش في اختبار (test_report_output_overhaul).
"""
from __future__ import annotations

import collections
import os
import shutil
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# أسطرٌ عربيةٌ قصيرةٌ متعرّجة (غير مشكّلة كي يكون تجريدُ الحركات لا-أثر) — كلُّ
# فقرةٍ سطرٌ قصيرٌ مفردٌ فتكثر الأسطرُ الراجعةُ القصيرةُ القابلةُ للقياس.
_LINES = [
    "هذا سطر اختبار قصير", "السوق ينمو سنويا", "الاسعار مستقرة",
    "المنافسة معتدلة", "الطلب مرتفع", "التصدير ممكن", "الجودة عالية",
    "المستوردون كثر", "الشحن بحري", "التقرير جاهز", "الخلاصة واضحة",
    "التوصية بالدخول", "المخاطر محدودة", "الفرصة قائمة", "النتيجة ايجابية",
]

# نطاقاتُ الحروف العربية (بلا حركات — الحركاتُ فئةُ Mn تُتجاهَل في عدّ الأغلبية).
_AR_RANGES = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF),
              (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))


def _is_arabic_letter(ch: str) -> bool:
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in _AR_RANGES)


def is_arabic_majority(text: str) -> bool:
    """سطرٌ عربيُّ الأغلبية إن كان عددُ حروفه العربية > اللاتينية و> صفر.
    الأرقامُ والترقيمُ لا تُحسَب — فسطرُ `080410` أو `UN Comtrade` ليس عربيًّا."""
    ar = sum(1 for c in text if _is_arabic_letter(c))
    la = sum(1 for c in text if c.isascii() and c.isalpha())
    return ar > 0 and ar > la


def build_fixture(jc: str) -> str:
    """ابنِ docx بكلّ فقرةٍ bidi + قيمة jc معطاة، من نفس المحتوى."""
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    doc = Document()
    for ln in _LINES:
        p = doc.add_paragraph()
        r = p.add_run(ln)
        r.font.name = "Amiri"
        ppr = p._p.get_or_add_pPr()
        if ppr.find(qn("w:bidi")) is None:
            ppr.append(OxmlElement("w:bidi"))
        el = ppr.find(qn("w:jc"))
        if el is None:
            el = OxmlElement("w:jc")
            ppr.append(el)
        el.set(qn("w:val"), jc)
        rpr = r._r.get_or_add_rPr()
        if rpr.find(qn("w:rtl")) is None:
            rpr.append(OxmlElement("w:rtl"))
    path = os.path.join(tempfile.mkdtemp(prefix=f"rtlcal_{jc}_"), "f.docx")
    doc.save(path)
    return path


def to_pdf(docx_path: str) -> str:
    import silk_reports
    return silk_reports.docx_to_pdf(
        docx_path, os.path.join(os.path.dirname(docx_path), "f.pdf"))


def measure_lines(pdf_path: str):
    """أرجِع (عرض_الصفحة، [(x0,x1,text) لكلّ **سطرٍ مُجمَّع** على y]) عبر fitz،
    أو None إن غاب pymupdf. النقاطُ بوحدة النقطة."""
    try:
        import fitz  # pymupdf
    except Exception:  # noqa: BLE001
        return None
    try:
        doc = fitz.open(pdf_path)
    except Exception:  # noqa: BLE001
        return None
    pw = doc[0].rect.width if doc.page_count else None
    if not pw:
        return None
    lines = []
    for page in doc:
        rows = collections.defaultdict(list)
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                for s in line["spans"]:
                    if s["text"].strip():
                        rows[round(s["bbox"][3] / 2)].append(s)
        for sp in rows.values():
            sp.sort(key=lambda s: s["bbox"][0])
            lines.append((min(s["bbox"][0] for s in sp),
                          max(s["bbox"][2] for s in sp),
                          " ".join(s["text"] for s in sp)))
    return pw, lines


def classify(pw: float, lines, tol: float = 10.0) -> dict:
    """صنِّف الأسطرَ القصيرةَ المتعرّجةَ غير الموسَّطة وفق عقد «صفرُ يسارٍ عربيّ».

    - `block_right`: المئينُ الـ90 لحافة اليمين (x1) عبر كلّ الأسطر — مرجعُ حدّ
      الكتلة اليمين، متينٌ ضدّ الشواذّ.
    - سطرٌ عربيُّ الأغلبية «منحازٌ يمينًا» إن كان `block_right - x1 <= tol`.
    - العربيُّ المنحازُ يسارًا = عيب. اللاتينيُّ يُستثنى من النسبة."""
    ragged = [(x0, x1, t) for x0, x1, t in lines
              if (x1 - x0) < 0.40 * pw
              and abs(((x0 + x1) / 2) - pw / 2) > 0.05 * pw]
    if not lines:
        return {"block_right": 0.0, "arabic_right": 0, "arabic_left": 0,
                "latin_excluded": 0, "arabic_left_texts": [],
                "latin_texts": [], "ragged": 0}
    xs = sorted(x1 for _, x1, _ in lines)
    block_right = xs[min(int(len(xs) * 0.90), len(xs) - 1)]
    ar_right = ar_left = 0
    ar_left_texts, latin_texts = [], []
    for x0, x1, t in ragged:
        if is_arabic_majority(t):
            if block_right - x1 <= tol:
                ar_right += 1
            else:
                ar_left += 1
                ar_left_texts.append((round(x0), round(x1), t))
        else:
            latin_texts.append((round(x0), round(x1), t))
    return {"block_right": round(block_right, 1), "arabic_right": ar_right,
            "arabic_left": ar_left, "latin_excluded": len(latin_texts),
            "arabic_left_texts": ar_left_texts, "latin_texts": latin_texts,
            "ragged": len(ragged)}


def format_digest(title: str, d: dict) -> str:
    """خُلاصةٌ قابلةٌ للفحص تُطبَع **دائمًا** (لا فقط عند الفشل) — التعديل ٢."""
    out = [f"----- {title} -----",
           f"block_right(90pct x1)={d['block_right']}  ragged={d['ragged']}  "
           f"arabic_right={d['arabic_right']}  arabic_left={d['arabic_left']}  "
           f"latin_excluded={d['latin_excluded']}"]
    if d["latin_texts"]:
        out.append("  latin (excluded from ratio):")
        for x0, x1, t in d["latin_texts"]:
            out.append(f"    [x0={x0} x1={x1}] {t!r}")
    if d["arabic_left_texts"]:
        out.append("  ARABIC-LEFT offenders (real defects):")
        for x0, x1, t in d["arabic_left_texts"]:
            out.append(f"    [x0={x0} x1={x1}] {t!r}")
    return "\n".join(out)


def _lo_version() -> str:
    for b in ("soffice", "libreoffice"):
        exe = shutil.which(b)
        if exe:
            try:
                return subprocess.run([exe, "--version"], capture_output=True,
                                      text=True, timeout=30).stdout.strip()
            except Exception:  # noqa: BLE001
                pass
    return "unknown"


def main() -> int:
    print("LibreOffice:", _lo_version())
    digests = {}
    for label, jc in (("A(jc=start,correct)", "start"),
                      ("B(jc=right,inverted)", "right")):
        try:
            measured = measure_lines(to_pdf(build_fixture(jc)))
            if measured is None:
                print(f"{label}: no fitz measurer available")
                continue
            pw, lines = measured
            d = classify(pw, lines)
            digests[label] = d
            print(format_digest(label, d))
        except Exception as e:  # noqa: BLE001
            print(f"{label}: ERROR {e}")
    # عقدُ الصلاحية الدائم: A بلا يسارٍ عربيّ (تمرّ)؛ B بيسارٍ عربيّ (تفشل).
    a = digests.get("A(jc=start,correct)")
    b = digests.get("B(jc=right,inverted)")
    a_ok = bool(a) and a["arabic_left"] == 0 and a["arabic_right"] >= 3
    b_catches = bool(b) and b["arabic_left"] > 0
    print(f"\nCALIBRATION (zero-left Arabic contract): "
          f"A passes={a_ok} | B is caught={b_catches} | "
          f"VALID MEASURER={a_ok and b_catches}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
