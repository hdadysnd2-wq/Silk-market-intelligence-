"""قفلٌ لحادثة LESSONS ٣١ — نتائج /analyze لم تكن تحليلاتٍ محفوظةً حقيقيةً.

الجذر (مراجعة شيفرة، file:line): `silk_engine.analyze` كان يثبّت
`db_path="data/silk.db"` (مسارٌ نسبيٌّ لمجلد العمل الجاري)، والمعالج `/analyze`
لا يمرّر `db_path` — فيكتب `_persist` عبر `save_analysis(result, "data/silk.db")`
بمسارٍ **صريح** يتجاوز `silk_storage._db_path()`. بينما كل القرّاء
(`get_analysis`/`list_analyses`/كل نقاط `report.*`) ومسار `/research` يحسمون
`path=None → _db_path()` الذي يحترم `SILK_DATA_DIR`. على النشر (`SILK_DATA_DIR=
/data`) كان `/analyze` يكتب `./data/silk.db` الفاني (يُمسح عند إعادة النشر
فيعود العدّاد ١) والقرّاء يقرؤون `/data/silk.db` — فالمعرّف «1» ثم 404. نفس عائلة
LESSONS ٤، لم تُلتقط لأن `/analyze` لم يُدخَّن حيًّا قط (Commands #1-6 غطّت
`/research` حصرًا).

يغطي هذا الملف:
  (أ) توجيه القاعدة: `analyze(persist=True)` يكتب لنفس قاعدة `_db_path()` التي
      يقرأ منها `/analyses/{id}` — مع `SILK_DATA_DIR` مضبوطًا.
  (ب) تدفّق حقيقي عبر TestClient: POST /analyze → analysis_id → GET
      /analyses/{id} ينجح → التصديرات (md/docx/pdf) لا تُرجِع 404 → المعرّف
      يظهر في «بحوثي السابقة».
  (ج) نفس التدفّق لـ«مسح الأسواق» (نداء /analyze بلا سوق محدّد) — جذرٌ مشترك.
  (د) قفل الزجاج: صفر «§» في أي سلسلة تواجه العميل (title=، تسميات الأزرار).

Run: python3 -m pytest tests/test_analyze_persistence_and_glyph.py -q
"""
import contextlib
import os
import re
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@contextlib.contextmanager
def _env(**vals):
    saved = {k: os.environ.get(k) for k in vals}
    try:
        for k, v in vals.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


@contextlib.contextmanager
def _no_network():
    """اقطع الشبكة على مستوى requests (نمط اختبارات TestClient الموثَّق) —
    قطع socket عالميًّا يكسر نقل TestClient نفسه."""
    err = OSError("network blocked in test")
    with patch("requests.get", side_effect=err), \
         patch("requests.post", side_effect=err), \
         patch("requests.Session.request", side_effect=err):
        yield


def _client():
    from fastapi.testclient import TestClient
    import api
    import importlib
    importlib.reload(api)   # يلتقط SILK_DATA_DIR الحالي في create_app
    return TestClient(api.app)


_KEYLESS = dict(SILK_API_KEY=None, ANTHROPIC_API_KEY=None, VOLZA_API_KEY=None,
                EXPLEE_API_KEY=None, LOCALPRICE_API_KEY=None)


# ── (أ) توجيه القاعدة على مستوى المحرّك — الحارس الضيّق للجذر ────────────────

def test_engine_persist_writes_to_canonical_db_path_not_relative_literal():
    """`analyze(persist=True)` بلا `db_path` صريح يكتب لقاعدة `_db_path()`
    (تحترم SILK_DATA_DIR) لا لمسارٍ نسبيٍّ ثابت. القرّاء بمسار افتراضي يجدون
    الصفّ — وهذا بالضبط ما فشل حيًّا (id «1» ثم 404)."""
    import importlib
    tmp = tempfile.mkdtemp()
    with _env(SILK_DATA_DIR=tmp, **_KEYLESS), _no_network():
        import silk_engine
        import silk_storage
        importlib.reload(silk_storage)
        importlib.reload(silk_engine)
        result = silk_engine.analyze("شاي أخضر", persist=True)
        aid = result.get("analysis_id")
        assert aid is not None, "لم يُرفَق analysis_id رغم persist=True"
        # القارئ بالمسار الافتراضي (نفس ما يفعله GET /analyses/{id}) يجده:
        assert silk_storage._db_path() == os.path.join(tmp, "silk.db")
        found = silk_storage.get_analysis(aid)     # path=None → _db_path()
        assert found is not None, (
            "الصفّ غير موجود في القاعدة القانونية — كُتب لقرصٍ آخر (الجذر)")
        assert found.get("product") == "شاي أخضر"
        # كُتب فعلًا في قاعدة SILK_DATA_DIR، وليس في ./data/silk.db النسبي:
        assert os.path.exists(os.path.join(tmp, "silk.db"))
        assert aid in {r["id"] for r in silk_storage.list_analyses()}


# ── (ب) تدفّق حقيقي كامل عبر TestClient — نفس ما لمسه المالك ─────────────────

def _run_and_assert_full_flow(body: dict):
    with _env(SILK_DATA_DIR=tempfile.mkdtemp(), **_KEYLESS), _no_network():
        c = _client()
        r = c.post("/analyze", json=body)
        assert r.status_code == 200, r.text
        res = r.json()
        aid = res.get("analysis_id")
        assert aid is not None, "POST /analyze لم يُعِد analysis_id"

        # 1) إعادة الفتح بالمعرّف تنجح (كانت 404):
        g = c.get(f"/analyses/{aid}")
        assert g.status_code == 200, (
            f"GET /analyses/{aid} = {g.status_code} (الجذر: 404 'not found')")

        # 2) التصديرات الثلاثة تجد التحليل — لا 404 لأيٍّ منها:
        md = c.get(f"/analyses/{aid}/report.md")
        assert md.status_code == 200 and md.text.strip(), md.status_code
        docx = c.get(f"/analyses/{aid}/report.docx")
        assert docx.status_code == 200, f"docx={docx.status_code} {docx.text[:200]}"
        pdf = c.get(f"/analyses/{aid}/report.pdf")
        # PDF: 200 إن توفّر محرّك التحويل، أو 503 نظيف إن غاب — لكن **ليس
        # 404 أبدًا** (404 = التحليل غير موجود = الجذر المُصلَح).
        assert pdf.status_code != 404, "report.pdf رجع 404 — التحليل غير موجود"
        assert pdf.status_code in (200, 503), pdf.status_code

        # 3) المعرّف يظهر في «بحوثي السابقة» (GET /analyses):
        listing = c.get("/analyses").json()
        assert aid in {row["id"] for row in listing}, (
            "التحليل المحفوظ لا يظهر في قائمة بحوثي السابقة")
        return aid


def test_quick_scan_analyze_full_persisted_flow_no_404():
    """مسحٌ سريع لسوقٍ محدّد (peanut butter/UAE-شكل): كل التدفّق يعمل."""
    _run_and_assert_full_flow(
        {"product": "زبدة الفول السوداني", "persist": True,
         "markets": ["ARE"]})


def test_compare_all_markets_analyze_shares_the_same_fixed_flow():
    """«مسح الأسواق» = نداء /analyze بلا سوق محدّد. جذرٌ مشترك مع المسح
    السريع (كلاهما عبر نفس المعالج) — فيُصلَح بنفس الإصلاح."""
    _run_and_assert_full_flow({"product": "زبدة الفول السوداني", "persist": True})


def test_analyze_backend_honors_persist_false_contract():
    """المعالج يحترم persist=false (المتعاقَد عليه): لا صفّ يُحفَظ، لا
    analysis_id. الواجهة تُرسل persist:true دائمًا (buildBody) — العقد مُتّسِق."""
    with _env(SILK_DATA_DIR=tempfile.mkdtemp(), **_KEYLESS), _no_network():
        c = _client()
        res = c.post("/analyze",
                     json={"product": "زبدة الفول السوداني",
                           "persist": False, "markets": ["ARE"]}).json()
        assert res.get("analysis_id") is None
        assert c.get("/analyses").json() == []


# ── (د) قفل الزجاج: صفر «§» في السلاسل التي تواجه العميل ─────────────────────

def test_no_section_glyph_in_client_facing_strings():
    """انضباط السلاسل اليتيمة (LESSONS ٩): «§» يُبدَّل بصريًّا في RTL — ممنوع
    في أي سلسلة يراها العميل (title=، نصّ الأزرار/التسميات). الاستبدال القياسي
    «القسم N». تعليقات JS/docstrings (غير مرئية للعميل) خارج النطاق."""
    html = open(os.path.join(_ROOT, "web", "index.html"), encoding="utf-8").read()
    # انزع أجسام <script>/<style> — تعليقاتها/سلاسلها منطقٌ داخليّ لا يراه
    # العميل (الرمز يُبدَّل بصريًّا فقط حين يُعرَض كنصّ RTL في الصفحة).
    markup = re.sub(r"<(script|style)\b.*?</\1>", "", html,
                    flags=re.S | re.I)

    # (١) أي قيمة سمة title="..." تحوي § :
    title_hits = [m.group(0)[:80]
                  for m in re.finditer(r'title="[^"]*§[^"]*"', markup)]
    assert not title_hits, f"«§» في تلميحات title=: {title_hits}"

    # (٢) أي نصّ ظاهر بين وسمَين — تسميات الأزرار/العناوين المرئية.
    visible_hits = [m.group(1).strip()[:80]
                    for m in re.finditer(r">([^<>]*§[^<>]*)<", markup)]
    assert not visible_hits, f"«§» في نصّ ظاهر للعميل: {visible_hits}"
