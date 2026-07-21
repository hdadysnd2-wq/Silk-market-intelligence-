"""محلل رموز النظام المنسق (HS) لمنتجات سِلك — HS code resolver for Silk.

Maps an Arabic OR English product name to an international HS6 code using a
curated CSV seed plus stdlib matching (difflib + keyword lookup). No network,
no fuzzy-match dependency, fully offline.

seed scope / نطاق البيانات:
    data/hscodes_full.csv is the complete official HS2022 six-digit reference
    (5,613 codes, UN Comtrade) — chapter/heading hierarchy + English official
    description on every row, Arabic keywords (`keywords_ar`, semicolon-
    separated) on the subset migrated from the prior curated seed
    (`tools/migrate_hs_keywords.py`) plus a small hand-curated disambiguation
    set for known lexical collisions (butter: dairy/shea/cocoa/peanut; بن vs
    بنكهة). All codes are real international HS6 values; nothing is invented.
    The former partial seed (`data/hs_codes.csv`, ~5,627 rows) is retired —
    this file is now the sole reference for both resolution and validation.

Every result is a provenance-tagged DataPoint: weak/no match -> value=None,
confidence=0.0. The resolver never fabricates a code.
"""
from __future__ import annotations

import csv
import datetime
import difflib
import functools
import logging
import os

log = logging.getLogger(__name__)

# DataPoint عقد مشترك — shared contract from the data layer, with a local
# fallback so this module imports and runs standalone (no hard dependency).
try:
    from silk_data_layer import DataPoint  # type: ignore
except Exception:  # pragma: no cover - fallback when data layer absent
    from dataclasses import dataclass

    @dataclass
    class DataPoint:  # mirrors the shared contract
        value: object
        source: str
        confidence: float
        note: str = ""
        retrieved_at: str = ""


_HERE = os.path.dirname(os.path.abspath(__file__))
_SOURCE = "Silk curated HS6 seed (HS Nomenclature / UN Comtrade)"

# نطاق سِلك: تصدير غير نفطي — الفصل 27 (وقود معدنية: نفط خام 2709، مكرر
# 2710، غازات 2711، قار ومشتقات 2712–2715، زيوت قطران 2707، فحم وكوك
# 2701–2706، كهرباء 2716) خارج النطاق بتعريف «الصادرات غير النفطية»
# الرسمي. ثابت واحد مسمّى ليضبطه المالك — فلترة نطاق لا حذف صفوف: المرجع
# الكامل يبقى في CSV، والمُحلَّل الواقع في فصل مستبعد يُعلن خارج النطاق.
EXCLUDED_HS_CHAPTERS: frozenset[str] = frozenset({"27"})

_EXCLUSION_MSG = ("منتج بترولي/وقود معدني — خارج نطاق سِلك للتصدير "
                  "غير النفطي (فصل HS {chapter})")

# فصولُ النظام المنسّق الحقيقية (بنية WCO الرسمية، ثابتٌ هيكليّ لا اسمُ منتجٍ
# أو دولة) — ٩٧ فصلاً مُرقَّماً ٠١–٩٧، والفصل ٧٧ محجوزٌ للاستعمال المستقبلي
# (غير مخصَّص لأي بضاعة اليوم). تُستعمَل لفحص «سلامة الفصل» على مرشّحي
# التصنيف العام (silk_hs_classifier.classify_general) — رمزٌ من نموذجٍ في
# فصلٍ غير موجود أصلاً (مثل «00» أو «98» تجاريًا أو رقمٍ مختلَق) يُرفَض فورًا
# قبل أيّ فحص تداخل نصّي، بمعزلٍ تامٍّ عن بذرة CSV الجزئية.
VALID_HS_CHAPTERS: frozenset[str] = frozenset(
    f"{n:02d}" for n in range(1, 98) if n != 77)


def chapter_of(hs_code: object) -> str:
    """فصل الرمز (أول رقمين) — نصٌّ فارغ إن كان الرمز أقصر من رقمين."""
    return str(hs_code or "").strip()[:2]


def chapter_valid(hs_code: object) -> bool:
    """هل فصل هذا الرمز فصلٌ حقيقيٌّ في بنية WCO؟ — فحصٌ هيكليٌّ بحت، لا
    علاقة له بمرجعنا الجزئي (CSV): رمزٌ من نموذجٍ قد يكون صحيحاً دولياً حتى
    لو غاب عن بذرتنا الـ٥٦٠٠ صفّ (المرجع الكامل ~٦٩٤٠ رمزاً)."""
    return chapter_of(hs_code) in VALID_HS_CHAPTERS


def exclusion_note(hs_code: object) -> str | None:
    """سبب الاستبعاد النطاقي لرمز HS، أو None إن كان داخل النطاق.

    نقطة الحقيقة الواحدة لفلترة النطاق — يستعملها المصنّف (أدناه)،
    والمحرّك لمسار hs_code الصريح، والاكتشاف العكسي لفلترة الفرص.
    """
    chapter = str(hs_code or "").strip()[:2]
    if chapter in EXCLUDED_HS_CHAPTERS:
        return _EXCLUSION_MSG.format(chapter=chapter)
    return None


def _abspath(path: str) -> str:
    """حوّل المسار النسبي إلى مطلق نسبةً لهذا الملف — resolve path relative to this file."""
    return path if os.path.isabs(path) else os.path.join(_HERE, path)


@functools.lru_cache(maxsize=1)
def load_hs_codes(path: str = "data/hscodes_full.csv") -> list[dict]:
    """حمّل مرجع رموز HS الكامل من CSV — load the full HS reference as dict rows.

    Cached: the 5,613-row CSV is parsed once and reused across resolve() calls.
    Every field is read as-is (csv.DictReader never coerces types — leading
    zeros in hs_code survive intact, no dtype handling needed).
    """
    fp = _abspath(path)
    try:
        with open(fp, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception as exc:  # missing/unreadable file degrades to empty
        log.warning("failed to load HS reference %s: %s", fp, exc)
        return []


def _norm(s: str) -> str:
    """طبّع النص للمطابقة — lowercase/strip for matching."""
    return (s or "").strip().lower()


def _keywords(row: dict) -> list[str]:
    """استخرج الكلمات المفتاحية لصف — keyword + description tokens for a row.

    `keywords_ar` مفصولةٌ بفاصلةٍ منقوطة `;` (لا فاصلة عادية — تفادياً لخلط
    فاصل القائمة بفاصل حقول CSV نفسه)."""
    kw = [_norm(k) for k in (row.get("keywords_ar") or "").split(";") if k.strip()]
    return kw + [_norm(row.get("description_en", ""))]


def _score(query: str, row: dict) -> float:
    """احسب قوة المطابقة 0..1 — match strength: exact keyword high, fuzzy medium."""
    q = _norm(query)
    if not q:
        return 0.0
    kws = [k for k in _keywords(row) if k]
    if q in kws:                                   # exact keyword hit
        return 1.0
    if any(q in k or k in q for k in kws):         # substring containment
        return 0.85
    best = max((difflib.SequenceMatcher(None, q, k).ratio() for k in kws), default=0.0)
    return best                                    # fuzzy ratio (medium/low)


def resolve(product_name: str, path: str = "data/hscodes_full.csv") -> DataPoint:
    """طابق أفضل رمز HS لاسم منتج عربي أو إنجليزي — best HS6 match for one name."""
    results = resolve_all(product_name, top_n=1, path=path)
    if results:
        return results[0]
    return DataPoint(None, _SOURCE, 0.0,
                     note=f"no HS match for {product_name!r}",
                     retrieved_at=datetime.date.today().isoformat())


def resolve_all(product_name: str, top_n: int = 3,
                path: str = "data/hscodes_full.csv") -> list[DataPoint]:
    """رتّب أفضل المرشحين — ranked HS6 candidates as DataPoints (weak -> None)."""
    today = datetime.date.today().isoformat()
    rows = load_hs_codes(path)
    if not rows:
        return [DataPoint(None, _SOURCE, 0.0, note="HS seed empty/unavailable",
                          retrieved_at=today)]

    scored = sorted(((_score(product_name, r), r) for r in rows),
                    key=lambda t: t[0], reverse=True)[:max(1, top_n)]

    out: list[DataPoint] = []
    for sc, r in scored:
        # قص الثقة: ضعيف جداً => لا قيمة — clamp weak matches to value=None.
        if sc < 0.7:
            out.append(DataPoint(None, _SOURCE, 0.0,
                                 note=f"weak match for {product_name!r} "
                                      f"(best='{r.get('description_en')}', "
                                      f"score={sc:.2f})",
                                 retrieved_at=today))
            continue
        # بوابة النطاق غير النفطي (8d): تطابق قوي في فصل مستبعد يُعلن خارج
        # النطاق برسالة واضحة — لا يُحلَّل ولا يُخفى سبب الرفض.
        excl = exclusion_note(r["hs_code"])
        if excl:
            out.append(DataPoint(None, _SOURCE, 0.0,
                                 note=f"{excl} — أقرب تطابق: "
                                      f"{r.get('description_en')} ({r['hs_code']})",
                                 retrieved_at=today))
            continue
        out.append(DataPoint(
            r["hs_code"], _SOURCE, round(sc, 2),
            note=r.get("description_en", ""),
            retrieved_at=today))
    return out


def extend_from_comtrade_rows(rows: list[dict],
                              path: str = "data/hs_codes.csv") -> int:
    """[متروكة/deprecated] وسّع بذرةً قديمة الشكل (hs_code,name_en,name_ar,
    keywords) من جدول مرجع Comtrade. القائمة الحالية (`data/hscodes_full.csv`)
    كاملةٌ رسمياً أصلاً (٥٦١٣ رمزاً) فلا حاجة عملية للتوسيع، وشكل أعمدتها
    مختلفٌ عن هذه الدالة (`chapter/description_en/keywords_ar` لا
    `name_en/name_ar/keywords`) — استدعاؤها على المسار الجديد سيُفسِد الملف.
    أُبقيت للتوافق التاريخي فقط؛ راجع `tools/migrate_hs_keywords.py` للترحيل
    الفعلي المستعمَل في هذه الهجرة.

    Each input row needs at least hs_code + name_en (name_ar/keywords optional).
    Skips codes already present. Returns the number of rows added.
    """
    fp = _abspath(path)
    existing = {r["hs_code"] for r in load_hs_codes(path)}
    new = [r for r in rows if r.get("hs_code") and r["hs_code"] not in existing]
    if not new:
        return 0
    try:
        with open(fp, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["hs_code", "name_en", "name_ar", "keywords"])
            for r in new:
                w.writerow({k: r.get(k, "") for k in
                            ("hs_code", "name_en", "name_ar", "keywords")})
        load_hs_codes.cache_clear()  # file changed -> drop stale cached rows
        return len(new)
    except Exception as exc:
        log.warning("failed to extend HS seed %s: %s", fp, exc)
        return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    samples = ["تمور", "زعفران", "عسل سدر", "olive oil", "بخور عود",
               "silk scarf", "مجوهرات ذهب", "قهوة", "spaceship"]
    for name in samples:
        dp = resolve(name)
        print(f"{name:>14}  ->  hs={dp.value}  conf={dp.confidence}  | {dp.note}")
