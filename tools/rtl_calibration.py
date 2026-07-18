#!/usr/bin/env python3
"""معايرةُ مقياس محاذاة RTL — RTL-alignment measurer calibration (Wave 2, §4).

> **أمر المُشرِف (الخيار ٣).** قبل الوثوق بأيّ رقم: ابنِ عيّنتين من **نفس**
> المحتوى العربي — A بـ`jc=start` (الوصفة الصحيحة، يجب أن تنحاز يمينًا)، وB بـ
> `jc=right` (البناء المقلوب المعروف، ينحاز يسارًا). مقياسٌ **صالح** يسجّل ≥90%
> محاذاة يمين على A و≤10% على B. نقيس بطريقتين — `pdftotext -bbox` (الاحتياطي
> الحالي) و`pymupdf/fitz` (نظير verify_rtl) — ونطبع مصفوفة 2×2 + نسخة LibreOffice.
>
> إن فشل `pdftotext -bbox` في تمييز A من B => الـ18% مصنوعٌ قياسًا (الاحتياطي
> يعدّ **كلّ كلمة سطرًا** بلا تجميع y — سطر ٣٤٦–٣٤٨ في `_measure_pdf_lines`).

يُشغَّل في وظيفة e2e-live-shape (soffice + fitz حاضران هناك):
    python3 tools/rtl_calibration.py
يطبع المصفوفة وينهي بـ0 دائمًا (تشخيصيّ، لا بوّابة) — القراءةُ من سجلّ CI.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# أسطرٌ عربيةٌ قصيرةٌ متعرّجة (غير مشكّلة كي يكون تجريدُ الحركات لا-أثر) — كلُّ
# فقرةٍ سطرٌ قصيرٌ مفردٌ فتكثر الأسطرُ الراجعةُ القصيرةُ القابلةُ للقياس.
_LINES = [
    "هذا سطر اختبار قصير", "السوق ينمو سنويا", "الاسعار مستقرة",
    "المنافسة معتدلة", "الطلب مرتفع", "التصدير ممكن", "الجودة عالية",
    "المستوردون كثر", "الشحن بحري", "التقرير جاهز", "الخلاصة واضحة",
    "التوصية بالدخول", "المخاطر محدودة", "الفرصة قائمة", "النتيجة ايجابية",
]


def _build(jc: str) -> str:
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


def _to_pdf(docx_path: str) -> str:
    import silk_reports
    return silk_reports.docx_to_pdf(
        docx_path, os.path.join(os.path.dirname(docx_path), "f.pdf"))


def _pct_right(segs, pw: float) -> float:
    """% الأسطر القصيرة المتعرّجة غير الموسَّطة المنحازة يمينًا (نفس منطق §4)."""
    ragged = [(x0, x1) for x0, x1 in segs
              if (x1 - x0) < 0.40 * pw and abs(((x0 + x1) / 2) - pw / 2) > 0.05 * pw]
    if len(ragged) < 3:
        return -1.0
    block_right = sorted(x1 for _, x1 in segs)[int(len(segs) * 0.90)]
    return sum(1 for _, x1 in ragged if block_right - x1 <= 10) / len(ragged)


def _measure_bbox(pdf_path: str):
    """القياسُ الحالي: `pdftotext -bbox` (يعدّ كلّ كلمة سطرًا — بلا تجميع y)."""
    if not shutil.which("pdftotext"):
        return None
    xhtml = subprocess.run(["pdftotext", "-bbox", pdf_path, "-"],
                           capture_output=True, text=True, timeout=60).stdout
    m = re.search(r'<page width="([\d.]+)"', xhtml)
    if not m:
        return None
    pw = float(m.group(1))
    segs = [(float(a), float(b)) for a, b in re.findall(
        r'<word xMin="([\d.]+)" yMin="[\d.]+" xMax="([\d.]+)"', xhtml)]
    return _pct_right(segs, pw)


def _measure_fitz(pdf_path: str):
    """القياسُ المرجعيّ: pymupdf/fitz بتجميعٍ صحيحٍ للأسطر (نظير verify_rtl)."""
    try:
        import collections
        import fitz  # pymupdf
    except Exception:  # noqa: BLE001
        return None
    doc = fitz.open(pdf_path)
    pw = doc[0].rect.width
    segs = []
    for page in doc:
        rows = collections.defaultdict(list)
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                for s in line["spans"]:
                    if s["text"].strip():
                        rows[round(s["bbox"][3] / 2)].append(s)
        for sp in rows.values():
            segs.append((min(s["bbox"][0] for s in sp),
                         max(s["bbox"][2] for s in sp)))
    return _pct_right(segs, pw)


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
    results = {}
    for label, jc in (("A(jc=start,correct)", "start"),
                      ("B(jc=right,inverted)", "right")):
        try:
            pdf = _to_pdf(_build(jc))
            results[label] = {"bbox": _measure_bbox(pdf), "fitz": _measure_fitz(pdf)}
        except Exception as e:  # noqa: BLE001
            results[label] = {"error": str(e)}
    print("\n===== RTL measurer calibration 2x2 (% right-anchored) =====")
    print(f"{'fixture':<26}{'pdftotext-bbox':<18}{'pymupdf-fitz':<14}")
    for label, r in results.items():
        b = r.get("bbox"); f = r.get("fitz")
        fmt = lambda v: ("n/a" if v is None else
                         "too-few-lines" if v == -1.0 else f"{v*100:.0f}%")
        print(f"{label:<26}{fmt(b):<18}{fmt(f):<14}")
    # حكمُ الصلاحية: مقياسٌ صالحٌ يميّز A(≥90%) من B(≤10%).
    def _valid(m):
        a = results.get("A(jc=start,correct)", {}).get(m)
        bb = results.get("B(jc=right,inverted)", {}).get(m)
        return (a is not None and bb is not None and a >= 0.90 and bb <= 0.10)
    print("\nDISCRIMINATES A from B?  bbox:", _valid("bbox"),
          "| fitz:", _valid("fitz"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
