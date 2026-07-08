"""جامعا البيانات المُجدولان لسِلك — Silk budgeted data collectors (M2, §4).

يملآن مخزن الحقائق بدل الجلب اللحظي المتكرر:
  • collect_worldbank — جلب جماعي (country=all) لكل مؤشر في نداء واحد: الاقتصاد
    (سكان/دخل) + ركيزة وكيل المخاطر (حوكمة WGI، لوجستيات LPI، صرف FX). عند فشل
    الشبكة يسقط لمؤشرَي السكان/الدخل إلى اللقطة الحقيقية المضمّنة (silk_seed_data)
    بوسمها الصريح — قيم حقيقية بمصدر معلن، لا اختلاق.
  • collect_comtrade — جلب تدفقات بميزانية يومية صلبة (سجلّ collection_runs)،
    تسلسلي بإيقاع مضبوط + backoff يحترم Retry-After — عكس التوزيع المتزامن الذي
    يخنق طبقة المعاينة (ANALYSIS.md §3).
كل تشغيل يسجَّل صفاً في collection_runs (طلب/جلب/فشل/المتبقي من الميزانية).
"""
from __future__ import annotations

import datetime
import logging
import os
import time

import silk_store
from silk_data_layer import (ENDPOINTS, ISO3_TO_M49, M49_TO_ISO3,
                             COMTRADE_KEY, _comtrade_url)

log = logging.getLogger(__name__)

# مؤشرات الجلب الجماعي: الاقتصاد + ركيزة وكيل المخاطر (كلها البنك الدولي، مجانية).
WB_INDICATORS = [
    "SP.POP.TOTL",        # السكان
    "NY.GDP.PCAP.PP.CD",  # دخل الفرد PPP
    "NY.GDP.PCAP.CD",     # دخل الفرد الاسمي (بديل)
    "PV.EST",             # الاستقرار السياسي (WGI) — وكيل المخاطر
    "RQ.EST",             # جودة التنظيم (WGI) — وكيل المخاطر
    "LP.LPI.OVRL.XQ",     # مؤشر الأداء اللوجستي — وكيل المخاطر
    "PA.NUS.FCRF",        # سعر الصرف الرسمي — تقلب العملة (وكيل المخاطر)
]
_WB_CONF = 0.95


def _today_year() -> int:
    return datetime.date.today().year


def _run_start(source: str, requested: int) -> int:
    with silk_store.connect() as conn:
        cur = conn.cursor()
        cur.execute(silk_store._q(
            "INSERT INTO collection_runs (source, started_at, requested) "
            "VALUES (?,?,?)"), (source, silk_store._now(), requested))
        conn.commit()
        return cur.lastrowid


def _run_finish(run_id: int, fetched: int, failed: int,
                budget_left: int | None, note: str = "") -> None:
    with silk_store.connect() as conn:
        conn.execute(silk_store._q(
            "UPDATE collection_runs SET finished_at=?, fetched=?, failed=?, "
            "budget_left=?, note=? WHERE id=?"),
            (silk_store._now(), fetched, failed, budget_left, note, run_id))
        conn.commit()


def comtrade_budget_left() -> int:
    """المتبقي من ميزانية اليوم — daily Comtrade request budget remaining.

    السقف: COMTRADE_DAILY_BUDGET (افتراضي 450 بمفتاح، 4 بلا مفتاح — طبقة المعاينة
    عرض محدود لا مصدر إنتاج). يُحتسب المصروف من collection_runs لليوم UTC الجاري.
    """
    default = 450 if COMTRADE_KEY else 4
    cap = int(os.environ.get("COMTRADE_DAILY_BUDGET", default) or default)
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    with silk_store.connect() as conn:
        row = conn.execute(silk_store._q(
            "SELECT COALESCE(SUM(fetched + failed), 0) FROM collection_runs "
            "WHERE source='comtrade' AND started_at >= ?"), (today,)).fetchone()
    spent = int(row[0] or 0)
    return max(0, cap - spent)


def collect_worldbank(indicators: list[str] | None = None,
                      year_from: int | None = None) -> dict:
    """اجلب مؤشرات البنك الدولي جماعياً — one bulk call per indicator (country=all).

    يكتب كل قيمة غير فارغة في مخزن الحقائق بمصدرها وسنتها. فشل مؤشر لا يوقف
    البقية؛ وفشل السكان/الدخل يسقط للّقطة المضمّنة الحقيقية بوسم صريح.
    Returns {fetched, failed, seeded}.
    """
    indicators = indicators or WB_INDICATORS
    year_from = year_from or (_today_year() - 6)
    run = _run_start("worldbank", len(indicators))
    fetched = failed = seeded = 0
    for ind in indicators:
        url = f"{ENDPOINTS['world_bank']}/country/all/indicator/{ind}"
        params = {"format": "json", "per_page": "20000",
                  "date": f"{year_from}:{_today_year()}"}
        try:
            import requests  # lazy — hermetic tests patch this
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            payload = r.json()
            recs = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
            n = 0
            for rec in recs or []:
                iso3 = (rec.get("countryiso3code") or "").strip()
                val, yr = rec.get("value"), rec.get("date")
                if len(iso3) == 3 and val is not None and yr:
                    silk_store.upsert_indicator(
                        iso3, ind, int(yr), float(val), "World Bank", _WB_CONF,
                        f"{ind} bulk collect")
                    n += 1
            fetched += 1
            log.info("worldbank %s: %d rows", ind, n)
        except Exception as e:  # noqa: BLE001 — مؤشر يفشل، البقية تكمل
            failed += 1
            log.warning("worldbank %s failed: %s", ind, e)
            seeded += _seed_fallback(ind)
    _run_finish(run, fetched, failed, None,
                f"seeded={seeded}" if seeded else "")
    return {"fetched": fetched, "failed": failed, "seeded": seeded}


def _seed_fallback(indicator: str) -> int:
    """اللقطة الحقيقية بديلاً — real bundled snapshot rows for pop/income on failure.

    قيم حقيقية (البنك الدولي) بمصدر موسوم «لقطة مضمّنة» وسنتها الفعلية — الشبكة
    الحية تظل تفوز عند توفرها (upsert بالمصدر المنفصل). Returns rows written."""
    try:
        import silk_seed_data as seed
    except Exception:  # noqa: BLE001
        return 0
    n = 0
    getter = None
    if indicator == "SP.POP.TOTL":
        getter = seed.population
    elif indicator.startswith("NY.GDP.PCAP"):
        getter = seed.gdp_per_capita
    if getter is None:
        return 0
    for iso3 in ISO3_TO_M49:  # الأسواق المعروفة للمنصّة تكفي كتغطية بذور
        got = getter(iso3)
        if got:
            silk_store.upsert_indicator(iso3, indicator, int(got[1]), float(got[0]),
                                        seed._SOURCE, 0.85, "seed fallback")
            n += 1
    return n


def collect_comtrade(hs6: str, targets: list[dict], year: int,
                     pace_seconds: float | None = None) -> dict:
    """اجلب تدفقات أسواقٍ بميزانية — budgeted, PACED serial Comtrade collection.

    targets: [{"iso3","m49"}...] بالأولوية. لكل هدف نداء واحد (شركاء partner=all).
    قبل كل نداء: فحص الميزانية (نفادها = توقف مُعلن لا صامت). فشل عابر يعاد
    بمحاولتين مع backoff أُسّي يحترم Retry-After. النتائج تُكتب لمخزن الحقائق.
    Returns {requested, fetched, failed, skipped_budget, budget_left}.
    """
    pace = float(os.environ.get("COMTRADE_PACE_S", "1.0")
                 if pace_seconds is None else pace_seconds)
    run = _run_start("comtrade", len(targets))
    fetched = failed = skipped = 0
    from silk_data_layer import comtrade_trade, primary_value
    # الميزانية تُقرأ مرة وتُخصم محلياً داخل التشغيلة (صف collection_runs يُحدَّث
    # عند النهاية فقط) — read once, decrement locally within the run.
    budget = comtrade_budget_left()
    # مراجعة المشروع: الميزانية تُحاسِب **النداءات الفعلية** لا الأهداف —
    # حلقة الإعادة كانت تطلق حتى ٣ نداءات وتُحتسب هدفاً واحداً، فيتجاوز
    # الصرف الحقيقي السقف اليومي. `calls` = كل استدعاء comtrade_trade؛
    # ودفتر collection_runs يبقى صادقاً لأن failed صار "محاولات فاشلة"
    # (calls - نجاحات) فيساوي SUM(fetched+failed) مجموعَ النداءات الفعلية.
    # حدّ معروف: [] لا يميّز "فشل جلب" عن "سوق لا يستورد فعلاً" (عقد
    # comtrade_trade) — فالإعادة قد تكرّر سؤالاً جوابه الصادق فارغ.
    calls = 0
    failed_targets = 0
    for t in targets:
        if calls >= budget:
            skipped = len(targets) - fetched - failed_targets
            log.warning("comtrade budget exhausted — %d target(s) deferred", skipped)
            break
        ok = False
        for attempt in range(3):  # محاولة + إعادتان بتراجع أُسّي
            recs = comtrade_trade(hs6, t["m49"], year, flow="M", partner="all")
            calls += 1
            if recs:
                rows = []
                for rec in recs:
                    code = str(rec.get("partnerCode"))
                    val = primary_value(rec)
                    if val is None:
                        continue
                    piso = "WLD" if code == "0" else M49_TO_ISO3.get(code, code)
                    rows.append({"hs6": hs6, "reporter_iso3": t["iso3"],
                                 "partner_iso3": piso, "year": int(year),
                                 "flow": "M", "value_usd": val})
                if rows:
                    silk_store.upsert_trade_flows(rows)
                ok = True
                break
            if calls >= budget:  # لا محاولة إضافية فوق الميزانية
                break
            time.sleep(pace * (2 ** attempt))  # backoff — طبقة المعاينة حسّاسة للاندفاع
        if ok:
            fetched += 1
        else:
            failed_targets += 1
        time.sleep(pace)  # إيقاع بين الأهداف — pacing between targets
    failed = calls - fetched   # محاولات فاشلة — keeps the daily ledger honest
    left = comtrade_budget_left()
    _run_finish(run, fetched, failed, left,
                f"skipped_budget={skipped}" if skipped else "")
    return {"requested": len(targets), "fetched": fetched, "failed": failed,
            "skipped_budget": skipped, "budget_left": left}


def refresh() -> dict:
    """التحديث المُجدول — the worker entrypoint: top up World Bank facts.

    (تدفقات Comtrade تُجلب حسب الطلب عبر write-through + collect_comtrade الموجَّه؛
    الجلب الشامل الدوري يُقرَّر مع الميزانية في الإنتاج.)"""
    silk_store.migrate()
    wb = collect_worldbank()
    return {"worldbank": wb, "comtrade_budget_left": comtrade_budget_left()}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("silk_collectors —", refresh())
