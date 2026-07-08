"""طبقة البيانات الأساسية لسِلك — Silk core data layer.

Real public data only (UN Comtrade preview, World Bank). Never fabricates:
on any failure returns a provenance-tagged None / [] and logs a warning.
"""
from __future__ import annotations

import datetime
import logging
import os
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)


def _load_dotenv(path: str = ".env") -> None:
    """حمّل مفاتيح من .env إن وُجد — minimal stdlib .env loader (no dependency).

    Fills only env vars that are not already set. Missing file is fine (offline).
    """
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"\''))
    except FileNotFoundError:
        pass


_load_dotenv()

# نقاط النهاية — base URLs of the real sources. Comtrade has TWO surfaces:
#   • preview (/public/v1/preview/...) — بلا مفتاح، محدود الصفوف ومخنوق الطلبات.
#   • data    (/data/v1/get/...)       — مع مفتاح، البيانات الكاملة و~500 طلب/يوم.
# نختار الإنتاج تلقائيًّا متى توفّر المفتاح؛ كلاهما بنفس المسار C/A/HS والمعاملات.
ENDPOINTS = {
    "comtrade": "https://comtradeapi.un.org/public/v1/preview/C/A/HS",
    "comtrade_data": "https://comtradeapi.un.org/data/v1/get/C/A/HS",
    "world_bank": "https://api.worldbank.org/v2",
}

_TIMEOUT = 30

# مفتاح Comtrade الاختياري — optional free key; switches to the full /data/v1/get
# endpoint and raises the cap to ~500 requests/day. Set COMTRADE_API_KEY in env/.env.
COMTRADE_KEY = os.environ.get("COMTRADE_API_KEY", "").strip()


def _comtrade_url() -> str:
    """اختر سطح كومتريد — full data endpoint when a key is set, else preview."""
    return ENDPOINTS["comtrade_data"] if COMTRADE_KEY else ENDPOINTS["comtrade"]


# جلسة مشتركة بـkeep-alive (P2) — one pooled Session so the ~150 fan-out calls
# per analysis reuse TCP/TLS connections instead of a fresh handshake each.
# stdlib requests فقط (لا httpx، لا تبعية جديدة). الاختبارات الهيرمتية تقطع
# requests.sessions.Session.request فتقطع هذه الجلسة و requests.get معاً (كلاهما
# يمرّ عبر Session.request)، فيبقى قطع الشبكة شاملاً.
_session = requests.Session()
_session.mount("https://", requests.adapters.HTTPAdapter(
    pool_connections=16, pool_maxsize=16, max_retries=0))


# 1b: مباعدة النداءات لكل مضيف (تحليل واحد يطلق ~150 نداء دفعة واحدة فيضرب
# حدود المعدل) + إعادة محاولة بتراجع أسّي على 429/5xx مع احترام Retry-After.
# الإعادة على أكواد HTTP فقط (الردّ الحقيقي الموثَّق) — أخطاء الاتصال تمرّ
# كما كانت (الاختبارات الهيرمتية تقطع الشبكة فلا حلقات نوم فيها).
import threading as _threading
import time as _time

_host_lock = _threading.Lock()
_last_hit: dict[str, float] = {}
_RETRYABLE = (429, 500, 502, 503, 504)


def _throttle(host: str) -> None:
    gap = float(os.environ.get("SILK_HTTP_MIN_GAP_MS", "250")) / 1000.0
    if gap <= 0:
        return
    with _host_lock:
        wait = _last_hit.get(host, 0.0) + gap - _time.monotonic()
        _last_hit[host] = max(_time.monotonic(), _last_hit.get(host, 0.0) + gap)
    if wait > 0:
        _time.sleep(min(wait, 5.0))


def _http_get(url: str, params: dict | None = None):
    """جلب مرن عبر الجلسة المجمّعة — throttled GET with 429/5xx backoff (1b)."""
    host = url.split("/")[2] if "://" in url else url
    retries = int(os.environ.get("SILK_HTTP_RETRIES", "3"))
    resp = None
    for attempt in range(retries + 1):
        _throttle(host)
        resp = _session.get(url, params=params, timeout=_TIMEOUT)
        if resp.status_code not in _RETRYABLE or attempt >= retries:
            return resp
        ra = str(resp.headers.get("Retry-After") or "").strip()
        delay = float(ra) if ra.replace(".", "", 1).isdigit() else 1.0 * (2 ** attempt)
        log.warning("HTTP %s from %s — retry %d/%d in %.1fs",
                    resp.status_code, host, attempt + 1, retries, min(delay, 30))
        _time.sleep(min(delay, 30.0))
    return resp


@dataclass
class DataPoint:
    """نقطة بيانات موثّقة — a value plus its provenance."""

    value: object            # actual value, or None when unavailable
    source: str              # e.g. "UN Comtrade", "World Bank"
    confidence: float        # 0.0–1.0
    note: str = ""           # units / year / caveat / failure reason
    retrieved_at: str = ""   # ISO date string
    # 1b (بلاغ مالك: تقرير سنغافورة فارغ بسبب 429 عُرض «لا بيانات»):
    # تمييز بنيوي — "fetch_failed" (تعذّر الجلب: حد معدل/شبكة، أعد المحاولة)
    # مقابل "no_record" (ردّ ناجح بلا سجل فعلاً). "" = غير محدد (سلوك قديم).
    status: str = ""


def _today() -> str:
    """تاريخ اليوم — today's ISO date."""
    return datetime.date.today().isoformat()


def _cached_get(url: str, params: dict, ttl_seconds: int = 86400) -> object:
    """جلب مع تخزين مؤقت اختياري — try the on-disk cache, else None (caller falls back).

    Transparent: returns parsed JSON when cache/fetch succeeds, None otherwise so
    the caller keeps its existing direct-GET + graceful-failure behavior. Never
    raises; offline this just returns None (same end result as before).
    """
    try:
        from silk_cache import cached_get
        return cached_get(url, params, ttl_seconds=ttl_seconds,
                          fetcher=_http_get)  # pooled fetch (P2)
    except Exception as e:  # noqa: BLE001 — cache is best-effort, never break the layer
        log.warning("cache layer unavailable (%s); using direct fetch", e)
        return None


# M49 numeric (str) -> ISO3, for World Bank lookups of trade partners.
M49_TO_ISO3 = {
    "682": "SAU", "784": "ARE", "634": "QAT", "414": "KWT", "512": "OMN",
    "048": "BHR", "400": "JOR", "422": "LBN", "818": "EGY", "504": "MAR",
    "788": "TUN", "012": "DZA", "434": "LBY", "729": "SDN", "887": "YEM",
    "368": "IRQ", "364": "IRN", "792": "TUR", "586": "PAK", "356": "IND",
    "050": "BGD", "144": "LKA", "360": "IDN", "458": "MYS", "702": "SGP",
    "764": "THA", "704": "VNM", "608": "PHL", "156": "CHN", "392": "JPN",
    "410": "KOR", "344": "HKG", "158": "TWN", "036": "AUS", "554": "NZL",
    "840": "USA", "124": "CAN", "484": "MEX", "076": "BRA", "032": "ARG",
    "152": "CHL", "170": "COL", "604": "PER", "826": "GBR", "276": "DEU",
    "250": "FRA", "380": "ITA", "724": "ESP", "528": "NLD", "056": "BEL",
    "756": "CHE", "040": "AUT", "752": "SWE", "578": "NOR", "208": "DNK",
    "246": "FIN", "616": "POL", "203": "CZE", "620": "PRT", "300": "GRC",
    "372": "IRL", "643": "RUS", "804": "UKR", "710": "ZAF", "566": "NGA",
    "404": "KEN", "231": "ETH", "288": "GHA", "834": "TZA", "800": "UGA",
}
ISO3_TO_M49 = {v: k for k, v in M49_TO_ISO3.items()}

# M49 numeric (str) -> country name (EN). 0 = World aggregate.
PARTNER_NAMES = {
    "0": "World",
    "682": "Saudi Arabia", "784": "United Arab Emirates", "634": "Qatar",
    "414": "Kuwait", "512": "Oman", "048": "Bahrain", "400": "Jordan",
    "422": "Lebanon", "818": "Egypt", "504": "Morocco", "788": "Tunisia",
    "012": "Algeria", "434": "Libya", "729": "Sudan", "887": "Yemen",
    "368": "Iraq", "364": "Iran", "792": "Turkey", "586": "Pakistan",
    "356": "India", "050": "Bangladesh", "144": "Sri Lanka", "360": "Indonesia",
    "458": "Malaysia", "702": "Singapore", "764": "Thailand", "704": "Viet Nam",
    "608": "Philippines", "156": "China", "392": "Japan", "410": "South Korea",
    "344": "Hong Kong", "158": "Taiwan", "036": "Australia", "554": "New Zealand",
    "840": "United States", "124": "Canada", "484": "Mexico", "076": "Brazil",
    "032": "Argentina", "152": "Chile", "170": "Colombia", "604": "Peru",
    "826": "United Kingdom", "276": "Germany", "250": "France", "380": "Italy",
    "724": "Spain", "528": "Netherlands", "056": "Belgium", "756": "Switzerland",
    "040": "Austria", "752": "Sweden", "578": "Norway", "208": "Denmark",
    "246": "Finland", "616": "Poland", "203": "Czechia", "620": "Portugal",
    "300": "Greece", "372": "Ireland", "643": "Russia", "804": "Ukraine",
    "710": "South Africa", "566": "Nigeria", "404": "Kenya", "231": "Ethiopia",
    "288": "Ghana", "834": "Tanzania", "800": "Uganda",
}


def partner_name(code: object) -> str:
    """اسم الشريك — map an M49 code to a name, else the bare code as string."""
    return PARTNER_NAMES.get(str(code), str(code))


def primary_value(rec: dict) -> float | None:
    """القيمة الرقمية لسجل كومتريد — the record's numeric 'primaryValue', or None.

    سجل ناقص/مشوّه بلا قيمة رقمية حقيقية **ليس صفراً** — عدّه صفراً اختلاقُ
    رقم (المبدأ التأسيسي)؛ يعيد None ليُسقِطه المستهلك ويعلن الفجوة بدل جمعه.
    A partial/malformed record must never masquerade as a genuine 0: callers
    drop None and declare the gap instead of summing a fabricated zero.
    """
    v = rec.get("primaryValue")
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def comtrade_trade(
    hs_code: str,
    reporter_m49: object,
    year: int,
    flow: str = "M",
    partner: object = 0,
) -> list[dict]:
    """تجارة كومتريد — Comtrade preview records, partner codes mapped to names.

    Returns a list of record dicts (each with a 'partnerName' added and
    '_provenance' tag). 1b: fetch failure (429/شبكة) returns **None** —
    ردّ ناجح بلا سجلات يعيد [] — فيميّز المستهلك «تعذّر الجلب» من
    «لا سجل فعلاً» بدل عرض كليهما «لا بيانات».
    """
    params = {
        "period": str(year),
        "cmdCode": str(hs_code),
        "flowCode": flow,
    }
    # نفس عرف الحذف للطرفين: None/"all" => حذف المعامل فيعيد كومتريد كل
    # الدول (الواجهة ترفض قيمة all الصريحة). reporter=all يخدم «أكبر
    # المستوردين عالمياً» (8c) — صف لكل دولة مبلّغة مع partner=0 (العالم).
    if reporter_m49 not in (None, "all", "ALL"):
        params["reporterCode"] = str(reporter_m49)
    # partner=0 => World total (one row). "all"/None => OMIT partnerCode so Comtrade
    # returns every partner (the API rejects partnerCode=all as invalid).
    if partner not in (None, "all", "ALL"):
        params["partnerCode"] = str(partner)
    if COMTRADE_KEY:
        params["subscription-key"] = COMTRADE_KEY  # full /data endpoint + higher cap
    url = _comtrade_url()
    # سياسة TTL لكل مصدر (M2): سنة تجارية مقفلة تتغيّر نادراً — 30 يوماً؛
    # السنة الجارية 24 ساعة. Per-source TTL: closed years 30d, current 24h.
    ttl = 30 * 86400 if int(year) < datetime.date.today().year else 86400
    try:
        payload = _cached_get(url, params, ttl_seconds=ttl)
        if payload is None:  # cache miss + fetch failed -> same graceful [] as before
            r = _http_get(url, params)
            r.raise_for_status()
            payload = r.json()
        data = payload.get("data") or []
    except Exception as e:  # noqa: BLE001 — never raise to caller
        log.warning("Comtrade fetch failed (%s, reporter=%s, %s): %s",
                    hs_code, reporter_m49, year, e)
        return None  # 1b: تعذّر الجلب ≠ لا سجل — المستهلك يميّز
    prov = {"source": "UN Comtrade", "confidence": 0.9, "retrieved_at": _today()}
    for rec in data:
        rec["partnerName"] = partner_name(rec.get("partnerCode"))
        rec["_provenance"] = prov
    return data


def world_bank(iso3: str, indicator: str, year: int | None = None) -> DataPoint:
    """مؤشر البنك الدولي — latest (or given-year) value as a DataPoint."""
    url = f"{ENDPOINTS['world_bank']}/country/{iso3}/indicator/{indicator}"
    params = {"format": "json", "per_page": "100"}
    if year is not None:
        params["date"] = str(year)
    try:
        payload = _cached_get(url, params, ttl_seconds=7 * 86400)  # M2: WB 7d
        if payload is None:  # cache miss + fetch failed -> fall back to direct GET
            r = _http_get(url, params)
            r.raise_for_status()
            payload = r.json()
        records = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        for rec in records:  # WB returns newest-first; take first non-null
            if rec.get("value") is not None:
                return DataPoint(
                    value=rec["value"], source="World Bank", confidence=0.95,
                    note=f"{indicator} year={rec.get('date')}", retrieved_at=_today(),
                )
        note = f"{indicator}: no value returned for {iso3}"
        log.warning(note)
        return DataPoint(None, "World Bank", 0.0, note, _today())
    except Exception as e:  # noqa: BLE001
        note = f"{indicator} fetch failed for {iso3}: {e}"
        log.warning(note)
        return DataPoint(None, "World Bank", 0.0, note, _today())


def gdp_per_capita(iso3: str, year: int | None = None) -> DataPoint:
    """نصيب الفرد من الناتج (US$) — GDP per capita, current US$."""
    return world_bank(iso3, "NY.GDP.PCAP.CD", year)


def population(iso3: str, year: int | None = None) -> DataPoint:
    """عدد السكان — total population."""
    return world_bank(iso3, "SP.POP.TOTL", year)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk data layer — tiny live probe (degrades gracefully offline)")
    dp = gdp_per_capita("SAU")
    if dp.value is None:
        print(f"  GDP/capita SAU: no data / fetch failed — {dp.note}")
    else:
        print(f"  GDP/capita SAU = {dp.value} US$ [{dp.source}, {dp.note}]")
    recs = comtrade_trade("100630", 840, 2022, flow="M", partner=0)
    if not recs:
        print("  Comtrade rice imports (USA, 2022): no data / fetch failed")
    else:
        print(f"  Comtrade returned {len(recs)} record(s); "
              f"first partner = {recs[0].get('partnerName')}")
