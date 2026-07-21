#!/usr/bin/env python3
"""ترحيل الكلمات المفتاحية العربية من البذرة القديمة إلى القائمة الرسمية
الكاملة — migrate Arabic keywords from the old curated seed into the new
complete official HS2022 reference (data/hscodes_full.csv).

المصدر (data/hs_codes.csv، ٤ أعمدة: hs_code,name_en,name_ar,keywords) —
الهدف (data/hscodes_full.csv، ٧ أعمدة: hs_code,chapter,chapter_desc_en,
heading,heading_desc_en,description_en,keywords_ar). المطابقة **برمز HS
فقط** (لا مطابقة اسمية/دلالية) — صفٌّ قديم برمزٍ لم يعد موجوداً في القائمة
الرسمية الحالية (نُسِخ HS2022 أعاد ترقيم/تقسيم بعض الرموز — راجع
docs/DECISIONS.md) يُسجَّل صراحةً في السجلّ المطبوع، لا يُسقَط صامتاً.

**دمجٌ لا استبدال:** الملف المرفوع يحمل ٥ صفوفٍ مُنسَّقة يدوياً سلفاً
(بالضبط عائلة حوادث «زبدة» — ألبان/شيا/كاكاو/فول سوداني — وبنّ/بنكهة) —
دليلٌ صريح على قصدٍ لتوضيح نفس الالتباسات التي أُصلِحت خوارزمياً هذه
الجلسة. الترحيل **يُلحِق** لا يستبدل، بفاصلةٍ منقوطة `;` (نفس فاصل الملف
المرفوع أصلاً — لا خلطُ فاصلٍ داخل عمودٍ واحد)، مع إزالة التكرار.

كل الأعمدة تُقرأ/تُكتَب كنصٍّ صرف (`csv.DictReader`/`DictWriter` — لا تحويل
رقمي أبداً) فلا فقدان أصفار بادئة (٠٨٠٤١٠ لا يصير ٨٠٤١٠). stdlib فقط — لا
حاجة لـpandas لعملية دمجٍ بسيطة كهذه (المكتبة القياسية تحفظ كل الحقول
نصوصاً أصلاً، فلا مشكلة dtype للحلّ من الأساس).

Usage:
    python3 tools/migrate_hs_keywords.py
    python3 tools/migrate_hs_keywords.py --old data/hs_codes.csv --new data/hscodes_full.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(path: str, encoding: str) -> tuple[list[dict], list[str]]:
    with open(path, newline="", encoding=encoding) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


_SEP = ";"  # نفس فاصل الملف المرفوع — لا خلط فاصلٍ داخل عمودٍ واحد.


def build_keywords_ar(existing: str, name_ar: str, keywords: str) -> str:
    """ألحِق اسماً عربياً + كلماتٍ مفتاحية بأيّ محتوًى موجودٍ سلفاً (لا
    استبدال) — الموجود يبقى أولاً (قد يحمل تمييزاً يدوياً متعمَّداً، مثل
    تفريق «زبدة» ألبان/شيا/كاكاو/فول سوداني)، بلا تكرار (تطابقٌ حالة-حروفٍ
    غير حسّاس)."""
    parts: list[str] = []
    seen = set()
    for raw in [*(existing or "").split(_SEP), name_ar,
                *(keywords or "").split(",")]:
        t = (raw or "").strip()
        if t and t.lower() not in seen:
            parts.append(t)
            seen.add(t.lower())
    return _SEP.join(parts)


def migrate(old_path: str, new_path: str) -> dict:
    old_rows, _ = _load(old_path, "utf-8")
    new_rows, new_fields = _load(new_path, "utf-8-sig")
    old_by_code = {r["hs_code"]: r for r in old_rows if r.get("hs_code")}

    migrated = 0
    for r in new_rows:
        old = old_by_code.get(r["hs_code"])
        if old is None:
            continue
        kw = build_keywords_ar(r.get("keywords_ar", ""),
                               old.get("name_ar", ""), old.get("keywords", ""))
        if kw and kw != (r.get("keywords_ar") or ""):
            r["keywords_ar"] = kw
            migrated += 1
    new_codes = {r["hs_code"] for r in new_rows}
    unmatched = sorted(c for c, r in old_by_code.items()
                       if (r.get("name_ar") or "").strip() and c not in new_codes)

    with open(new_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=new_fields)
        w.writeheader()
        w.writerows(new_rows)

    return {"total_new_rows": len(new_rows), "migrated": migrated,
           "unmatched_old_codes_with_arabic": unmatched}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--old", default=os.path.join(_ROOT, "data", "hs_codes.csv"))
    ap.add_argument("--new", default=os.path.join(_ROOT, "data", "hscodes_full.csv"))
    args = ap.parse_args()
    if not os.path.exists(args.old):
        print(f"old sheet not found: {args.old}", file=sys.stderr)
        return 1
    if not os.path.exists(args.new):
        print(f"new sheet not found: {args.new}", file=sys.stderr)
        return 1
    result = migrate(args.old, args.new)
    print(f"migrated keywords_ar for {result['migrated']}/{result['total_new_rows']} rows")
    if result["unmatched_old_codes_with_arabic"]:
        print("old codes with Arabic terms NOT present in the new official list "
              "(HS2022 renumbering — terms did not carry over, see DECISIONS.md):")
        for c in result["unmatched_old_codes_with_arabic"]:
            print(f"  {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
