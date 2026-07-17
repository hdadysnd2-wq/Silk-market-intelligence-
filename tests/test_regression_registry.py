"""سجلّ الانحدار الموحّد — one guard per real incident, one meta-test for coverage.

> **الغرض (أمر المُشرِف).** لكل حادثة إنتاجية حقيقية في هذا المستودع — صفوف
> `docs/LESSONS.md` **وفخاخ** `silk-operations` §2 (THE TRAPS) — حارسٌ واحد
> يُفشِل على عودة نفس العائلة، و**اختبار تغطية شامل** (meta) يثبت أنّ كل حادثة
> مُسجَّلة هنا فعلاً — فلا تسقط حادثة من الشبكة بصمت. يشمل ذلك **الحوادث الثلاث
> لعطل 501 في تصدير docx** (صفوف LESSONS ٣/١١/١٣) بحُرّاس سلوكيين فعليين.
>
> **Why a registry (not just per-file lock-tests).** Lock-tests live scattered
> across `tests/`; this file is the single index that maps EVERY known incident
> to a live guard and then proves — mechanically — that the index is complete
> against both incident ledgers. A new incident that lands in either ledger
> without a registry entry fails `test_meta_registry_covers_every_known_incident`.

هرمتي بالكامل (قراءة مصدر + سلوك محلي، بلا شبكة). الحُرّاس السلوكية (٣/١١/١٣)
تبني/تنقّي فعلياً من المدوّنة القانونية الحقيقية الشكل — لا نماذج مثالية.

Run: python3 -m pytest tests/test_regression_registry.py -q
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))


def _read(rel: str) -> str:
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _exists(rel: str) -> bool:
    return os.path.exists(os.path.join(_ROOT, rel))


def _needles(rel: str, *needles: str):
    """حارس وجود: كل إبرة حاضرة في الملف — يعيد callable للتسجيل."""
    def check():
        assert _exists(rel), f"ملف الإنفاذ مفقود: {rel}"
        src = _read(rel)
        missing = [n for n in needles if n not in src]
        assert not missing, f"{rel}: رموز/علامات إنفاذ مفقودة {missing}"
    return check


def _absent(rel: str, *forbidden: str):
    def check():
        src = _read(rel)
        present = [n for n in forbidden if n in src]
        assert not present, f"{rel}: رموز يجب أن تكون قد أُزيلت لا تزال {present}"
    return check


# ── حُرّاس سلوكية للحوادث الثلاث لعطل docx-501 (LESSONS ٣/١١/١٣) ──────────────

def _guard_docx501_row3():
    """LESSONS ٣ — 501 شُحن لأن الاختبارات نماذج مموّهة. الحارس: تصدير docx
    العميل يُنتِج ملفاً حقيقياً قابلاً للفتح من **المدوّنة القانونية الحقيقية
    الشكل** (لا نموذج)، بلا 501."""
    import silk_render
    from silk_reports import render_client_docx
    from canonical_netherlands import netherlands_research_blob
    view = silk_render.build_view(netherlands_research_blob())
    path = render_client_docx(view, os.path.join(tempfile.mkdtemp(), "c.docx"))
    assert os.path.exists(path)
    from docx import Document
    doc = Document(path)
    assert any(p.text.strip() for p in doc.paragraphs), "docx فارغ"


def _guard_docx501_row11():
    """LESSONS ١١ — 501 تكرّر لأن محفّزات الحارس العربية بلا استبدال مقابل.
    الحارس: مصطلح حكم عربي ممنوع («درجة الثقة») يُحيَّد فعلياً بمُطهِّر/منقِّي
    العميل فلا يبقى في مخرَج التصدير."""
    from silk_reports import _client_redact_text, _client_forbidden_hits
    leaked = "التقييم يعتمد درجة الثقة العالية على مصدر البيانات"
    cleaned = _client_redact_text(leaked)
    assert not _client_forbidden_hits(cleaned), (
        f"محفّز حارس عربي بقي بعد التنقية: {_client_forbidden_hits(cleaned)}")


def _guard_docx501_row13():
    """LESSONS ١٣ — docx يفشل حياً (501) بينما الهرمتي أخضر؛ الحارس كان يرفض
    على تسرّب واحد. القاعدة «نقِّ لا ترفض»: مصطلح إنجليزي عارٍ متسرّب يُستبدَل
    بمحايد ويُسلَّم المستند — لا 501. الحارس: `_client_redact_text` ينقّي
    مصطلحاً إنجليزياً تشغيلياً بدل رفعه."""
    from silk_reports import _client_redact_text, _client_forbidden_hits
    leaked = "mission status: successful run"
    assert _client_forbidden_hits(leaked), "التهيئة خاطئة — النص يجب أن يتسرّب أولاً"
    cleaned = _client_redact_text(leaked)
    assert not _client_forbidden_hits(cleaned), (
        f"مصطلح إنجليزي تشغيلي بقي بعد التنقية: {_client_forbidden_hits(cleaned)}")


# ── حُرّاس سلوكية لفخّي المسار (markets:[] + view بعد التخزين) ────────────────

def _guard_trap_markets_empty():
    """TRAP «markets:[] misroutes exporters» — نتيجة /research دوماً markets:[]؛
    أي مسار عرض يثق بـ`markets[0]` يحصل على {} فيُنتِج صفحة /analyze فارغة.
    الحارس: build_view للمدوّنة القانونية يُنتِج فرع deep_research (لا قالب
    فارغ) رغم markets:[]."""
    import silk_render
    from canonical_netherlands import netherlands_research_blob
    blob = netherlands_research_blob()
    assert blob["markets"] == [], "المدوّنة القانونية يجب أن تحمل markets:[]"
    view = silk_render.build_view(blob)
    assert view.get("deep_research"), "build_view لم يُنتِج فرع deep_research"


def _guard_trap_view_after_persist():
    """TRAP «view attached AFTER persist on one path» — البلوب المخزَّن قد لا
    يحمل view مشتقّاً؛ مسار القراءة يجب أن يعيد بناءه. الحارس: `GET /analyses/{id}`
    يبني view عند غيابه (`found["view"] = _view(found)`)."""
    src = _read("api.py")
    assert 'found["view"] = _view(found)' in src or 'found["view"]=_view(found)' in src, (
        "مسار /analyses/{id} لا يعيد بناء view الغائب")
    assert 'found.setdefault("analysis_id"' in src, (
        "مسار /analyses/{id} لا يضمن analysis_id للبلوبات الأقدم")


# ── حُرّاس تراب باقية (وجود رمز الإصلاح، file:line-anchored) ──────────────────

def _guard_trap_two_sanitizers():
    _needles("silk_reports.py", "_client_assert_clean", "_client_sanitize")()
    _needles("silk_render.py", "_strip_internal_plumbing")()


def _guard_trap_redaction_mangling():
    # الإصلاح الالتفافي: مرحلة التصعيد سُمّيت `..._escalate{attempt}` لتفادي
    # الجزء القصير الذي كان يُشوَّه؛ والمنقِّح `_redact` باقٍ. (بنيوياً مفتوح
    # — لا حارس طول أدنى بعد؛ مُتتبَّع في silk-operations §2.)
    _needles("silk_ai_judge.py", "_escalate{attempt}")()
    _absent("silk_ai_judge.py", "maxtok_retry")()
    _needles("silk_diagnostics.py", "def _redact")()


def _guard_trap_parallel_cache_window():
    # فخّ معروف غير مُصلَح بعد (نافذة الذاكرة المؤقتة عبر ١٢ بعثة متوازية).
    # الحارس يُبقيه مُتتبَّعاً: آلية التوازي (ThreadPoolExecutor) لا تزال في
    # مُشغّل البعثات، والفخّ موسوم صراحةً «Known, not yet fixed» في المهارة.
    _needles("silk_missions.py", "ThreadPoolExecutor")()
    _needles(".claude/skills/silk-operations/SKILL.md", "not yet fixed")()


# كل مدخلة: Incident(key, source, match, check)
#   source: "LESSONS" (key=رقم الصفّ int) أو "trap" (key=slug، match=جزء من
#   اسم الفخّ العريض في §2). check: callable يُفشِل على عودة الانحدار.
_LESSONS = {
    1: _needles("docs/LIVE_PROOF_RUNBOOK.md", "لا يُشغَّل هيرمتياً"),
    2: _needles("silk_render.py", "_deep_research_view"),
    3: _guard_docx501_row3,          # docx-501 (١)
    4: _needles("api.py", "SILK_REQUIRE_PERSISTENT_DATA_DIR",
                "SILK_DATA_DIR غير مضبوط"),
    5: _needles("silk_storage.py", "def create_research_run",
                "def load_mission_checkpoints"),
    6: _needles("silk_llm_runtime.py", "_JSON_PARSE_FAILURE_GAP"),
    7: _needles("silk_data_layer.py", "_WB_INDICATOR_SOURCE"),
    8: _needles("silk_data_layer.py", "class DataPoint"),
    9: _absent("web/index.html", 'id="snapBtn"'),
    10: _needles("docs/AUDIT_STATUS.md", "قراءة فقط", "غير موجود"),
    11: _guard_docx501_row11,         # docx-501 (٣)
    12: _needles("silk_render.py", "_reconcile_mission_limits", "_first_clause"),
    13: _guard_docx501_row13,         # docx-501 (٢، الفشل الحيّ)
    14: _needles("silk_quality_gate.py", "_check_confidentiality_leaks",
                 "_check_style"),
    15: _needles("tools/live_shape_server.py", "class LiveShapeServer",
                 "def seed_db"),
}

_TRAPS = [
    ("mock_passes_real_fails", "Mock-passes / real-fails",
     _needles("silk_render.py", "_deep_research_view")),
    ("markets_empty_misroute", "misroutes exporters",
     _guard_trap_markets_empty),
    ("two_sanitizers", "Two different sanitizers",
     _guard_trap_two_sanitizers),
    ("redaction_mangling", "Redaction mangling",
     _guard_trap_redaction_mangling),
    ("parallel_cache_window", "Parallel missions and the cache window",
     _guard_trap_parallel_cache_window),
    ("cap_counts_not_dollars", "Cap counted operations, not dollars",
     _needles("silk_usage.py", "def try_reserve_usd")),
    ("styled_not_wired", "Styled-but-never-wired UI affordance",
     _needles("web/index.html", 'data-id="',
              '$("#histList").addEventListener("click"')),
    ("silent_noop_family", "silent no-op has three forms",
     _needles("web/index.html", "function openStoredAnalysis")),
    ("view_after_persist", "view attached AFTER persist",
     _guard_trap_view_after_persist),
]


# ── حارس واحد لكل حادثة (تُوسَّع برمجياً لتقارير pytest واضحة) ────────────────

@pytest.mark.parametrize("row", sorted(_LESSONS), ids=[f"lessons-{n}" for n in sorted(_LESSONS)])
def test_lessons_incident_guard_holds(row):
    """كل صفّ في docs/LESSONS.md له حارس حيّ يُفشِل على عودة عائلته."""
    _LESSONS[row]()


@pytest.mark.parametrize("slug,match,check", _TRAPS,
                         ids=[t[0] for t in _TRAPS])
def test_operations_trap_guard_holds(slug, match, check):
    """كل فخّ في silk-operations §2 (THE TRAPS) له حارس حيّ."""
    check()


# ── الاختبار الشامل: التغطية كاملة ضدّ كلا السِّجلّين ─────────────────────────

def _lessons_rows_in_ledger() -> set[int]:
    ledger = _read("docs/LESSONS.md")
    return {int(m.group(1))
            for m in re.finditer(r"^\|\s*(\d+)\s*\|", ledger, re.M)}


def _trap_rows_in_skill() -> list[str]:
    """صفوف بيانات جدول §2 (THE TRAPS) — الخلية الأولى (اسم الفخّ العريض)."""
    skill = _read(".claude/skills/silk-operations/SKILL.md")
    m = re.search(r"## 2\. THE TRAPS(.*?)\n## 3\.", skill, re.S)
    assert m, "قسم §2 THE TRAPS غير موجود في مهارة silk-operations"
    rows = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("| **"):        # صفوف البيانات فقط
            continue
        first_cell = line.split("|")[1].strip()
        rows.append(first_cell)
    return rows


def test_meta_registry_covers_every_known_incident():
    """التغطية الشاملة: كل صفّ LESSONS وكل فخّ §2 مُسجَّل هنا بحارس، ولا مدخلة
    يتيمة بلا صفّ مقابل. حادثة جديدة تسقط في أي سِجلّ بلا حارس تُحمِّر هنا."""
    # (أ) LESSONS: مفاتيح السجلّ = أرقام الصفوف بالضبط، متتابعة ١..N.
    ledger_rows = _lessons_rows_in_ledger()
    assert ledger_rows == set(range(1, max(ledger_rows) + 1)), (
        f"أرقام صفوف LESSONS غير متتابعة: {sorted(ledger_rows)}")
    registry_rows = set(_LESSONS)
    assert registry_rows == ledger_rows, (
        f"صفوف LESSONS بلا حارس في السجلّ: {sorted(ledger_rows - registry_rows)}؛ "
        f"حُرّاس بلا صفّ: {sorted(registry_rows - ledger_rows)}")

    # (ب) TRAPS: كل صفّ فخّ في §2 يطابقه حارس واحد بالضبط عبر إبرة `match`،
    # وكل حارس فخّ يطابق صفّاً واحداً على الأقل (لا يتيم).
    trap_rows = _trap_rows_in_skill()
    assert trap_rows, "لم تُقرَأ صفوف فخاخ من المهارة"
    for row in trap_rows:
        matched = [slug for slug, match, _ in _TRAPS if match in row]
        assert len(matched) == 1, (
            f"صفّ الفخّ «{row[:60]}…» يطابقه {len(matched)} حُرّاس (المتوقّع ١): "
            f"{matched}")
    for slug, match, _ in _TRAPS:
        assert any(match in row for row in trap_rows), (
            f"حارس الفخّ «{slug}» (match={match!r}) لا يطابق أيّ صفّ في §2 — "
            "يتيم؛ حدِّث السجلّ أو المهارة")


def test_meta_docx501_trio_all_have_behavioral_guards():
    """الحوادث الثلاث لعطل docx-501 (LESSONS ٣/١١/١٣) لها حُرّاس **سلوكية**
    (تبني/تنقّي فعلياً)، لا مجرّد وجود رمز — أمر المُشرِف الصريح."""
    behavioral = {3: _guard_docx501_row3, 11: _guard_docx501_row11,
                  13: _guard_docx501_row13}
    for row, guard in behavioral.items():
        assert _LESSONS[row] is guard, (
            f"صفّ docx-501 رقم {row} ليس مربوطاً بحارسه السلوكي")
        guard()  # يجب أن يمرّ فعلياً الآن
