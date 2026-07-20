"""أقفال ترقية محرّك جودة التقرير — Report Quality Engine Upgrade lock-tests.

> **العقد الحاكم (أمر العمل الرئيس).** كل عائلة عيبٍ رصدها تدقيق المالك التحريري
> على تقرير زبدة الفول السوداني/اليمن تصير **قاعدة عقد كاتب + قفل اختبار دائم**
> — لا تصحيحاً يدوياً لتقرير واحد. مدوّنة الإعادة الإنتاجية: `tools/canonical_yemen.py`
> (نفس شكل الإنتاج المخزَّن، تحمل كل العيوب: رمز HS خاطئ، أرقام قديمة، طلب Trends
> ضعيف، صفوف أسعار بلا وزن، HHI فوق رمز مُعلَّم).
>
> الموجات: 1 اتساق منطقي · 2 جودة البيانات · 3 المنافسة/التسعير · 4 العرض/البنية
> · 5 اللغة/النبرة · 6 عقد الحكم/خارطة الطريق.
"""
from __future__ import annotations

import importlib
import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.canonical_yemen import yemen_research_blob  # noqa: E402


# ════════════════════ الموجة ١ — الاتساق المنطقي ════════════════════

def test_w1_1_verdict_badge_matches_body_verdict():
    """1.1 — شارة الحكم (verdict_label) تطابق جملة الحكم في المتن/المختصر.

    مصدر أسبقية واحد (AI-أولاً) يستهلكه الشارة والمختصر والنبرة — لا تناقض
    «التوصية بالدخول» في الشارة مع «مراقبة» في المتن."""
    import silk_render as R
    from silk_narrative import verdict_ar
    dr = R.build_view(yemen_research_blob())["deep_research"]
    badge = dr["verdict_label"]
    # المتن/المختصر يشتقّ من نفس v_raw عبر verdict_ar.
    v_raw = ((dr["verdict"].get("ai") or {}).get("verdict")
             or dr["verdict"].get("verdict"))
    body = verdict_ar(v_raw)
    # كلاهما WATCH => «مراقبة السوق» / «مراقبة …» — لا go/دخول في أحدهما دون الآخر.
    assert "مراقبة" in badge and "مراقبة" in body
    assert "الدخول" not in badge  # الشارة لا تقول «التوصية بالدخول» بينما المتن مراقبة


def test_w1_2_hs_confirm_flags_peanut_butter_but_not_valid_matches():
    """1.2 — عقد التأكيد يُعلِّم «زبدة الفول السوداني»/040510 (الصفة المميّزة
    «فول سوداني» غائبة) ولا يُعلِّم التطابقات الصحيحة."""
    from silk_hs_confirm import confirm_hs, is_flagged
    bad = confirm_hs("زبدة الفول السوداني", "040510")
    assert bad["confirmed"] is False and is_flagged(bad)
    assert "فول" in bad["missing_terms"] and "سوداني" in bad["missing_terms"]
    # الصفة المميّزة لا يمكن أن تخسر أمام تطابق «زبدة» العاري.
    for name, code in [("تمور", "080410"), ("زبدة", "040510"),
                       ("olive oil", "150910")]:
        c = confirm_hs(name, code)
        assert c["confirmed"] is not False, (name, code, c)


def test_w1_2_hs_confirm_no_fabrication_on_unknown_code():
    """1.2 — رمزٌ خارج البذرة لا يُعلَّم False كاذبة؛ confirmed=None (غير مؤكَّد)."""
    from silk_hs_confirm import confirm_hs, is_flagged
    c = confirm_hs("زبدة الفول السوداني", "000000")  # خارج البذرة تماماً
    assert c["confirmed"] is None and not is_flagged(c)


def test_w1_3_flagged_hs_reframe_single_methodology_note_and_conf_cap():
    """1.3/4.1 — رمز مُعلَّم => (أ) ملاحظة منهجية **واحدة** «مؤشر سياقي»،
    (ب) سقف ثقة الحكم، (ج) الرمز مُتاح للمُصدِّرات عبر hs_flagged."""
    import silk_render as R
    from silk_hs_confirm import CONTEXTUAL_TAG
    dr = R.build_view(yemen_research_blob())["deep_research"]
    assert dr["hs_flagged"] is True
    # ثقة الحكم مسقوفة عند 0.5 (كانت 0.55 في المدوّنة).
    assert dr["verdict"]["confidence"] <= 0.5
    # ملاحظة «مؤشر سياقي» تظهر مرة واحدة بالضبط في الحدود (لا تكرار في كل قسم).
    hits = [l for l in dr["limits"] if CONTEXTUAL_TAG in l]
    assert len(hits) == 1, dr["limits"]


def test_w1_3_confidence_cap_never_raises_confidence():
    """1.3 — السقف لا يرفع ثقةً أدنى منه أبداً (عقد عدم الاختلاق)."""
    import silk_render as R
    blob = yemen_research_blob()
    blob["deep_research"]["verdict"]["confidence"] = 0.3
    blob["deep_research"]["verdict"]["ai"]["confidence"] = 0.3
    dr = R.build_view(blob)["deep_research"]
    assert dr["verdict"]["confidence"] == 0.3


def test_w1_3_unflagged_code_is_not_reframed():
    """1.3 — رمز مؤكَّد لا يُطأطئ ثقةً ولا يضيف ملاحظة سياقية (لا إيجابية كاذبة)."""
    import silk_render as R
    from silk_hs_confirm import CONTEXTUAL_TAG
    blob = yemen_research_blob()
    blob["product"] = "تمور"
    blob["hs_code"] = "080410"
    blob.pop("hs_confirmation", None)  # يُحسَب حياً => مؤكَّد
    dr = R.build_view(blob)["deep_research"]
    assert dr["hs_flagged"] is False
    assert not any(CONTEXTUAL_TAG in l for l in dr["limits"])


def test_w1_2_writer_prompt_reframes_flagged_hs_once():
    """1.3/4.1 — موجّه الكاتب يحمل تعليمة تأطير «مؤشر سياقي» + «مرة واحدة»
    حين يُمرَّر عقد تأكيد غير مؤكَّد."""
    import silk_ai_judge as J
    captured = {}

    def _fake_call(system, user, **kw):
        captured["user"] = user
        return "## 1. الخلاصة التنفيذية\nنص."

    with mock.patch.object(J, "available", return_value=True), \
         mock.patch.object(J, "_call", side_effect=_fake_call):
        J.deep_report({}, "ملخّص", {"verdict": "WATCH"},
                      "زبدة الفول السوداني", "اليمن", hs_code="040510",
                      hs_confirmation={"confirmed": False,
                                       "code_desc": "زبدة (Butter)",
                                       "missing_terms": ["فول", "سوداني"]})
    u = captured["user"]
    assert "مؤشر" in u and "سياقي" in u
    assert "مرة واحدة" in u  # تعليمة عدم التكرار


# ════════════════════ بوّابة /research (1.2 — قبل الإنفاق) ════════════════════

def _client(**env):
    import api as api_mod
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    importlib.reload(api_mod)
    return api_mod


def test_w1_2_research_gate_422_on_unconfirmed_hs_before_spend():
    """1.2 — مع تفعيل الصمّام، رمزٌ غير مؤكَّد => 422 hs_confirmation_needed
    **قبل** أيّ حجز، وتأكيد المستخدم (hs_confirmed) يتجاوزها."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    api_mod = _client(SILK_HS_CONFIRM_GATE="1", SILK_API_KEY=None,
                      SILK_REQUIRE_HS6=None, SILK_WORLD_MARKETS=None)
    client = TestClient(api_mod.create_app())
    with mock.patch("requests.get",
                    side_effect=OSError("net blocked for offline test")):
        r = client.post("/research",
                        json={"product": "زبدة الفول السوداني",
                              "market": "Yemen", "hs_code": "040510",
                              "async_run": False, "persist": False})
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "hs_confirmation_needed"
    # تأكيد المستخدم يتجاوز البوّابة (لا يعود نفس الخطأ).
    with mock.patch("requests.get",
                    side_effect=OSError("net blocked for offline test")):
        r2 = client.post("/research",
                         json={"product": "زبدة الفول السوداني",
                               "market": "Yemen", "hs_code": "040510",
                               "hs_confirmed": True,
                               "async_run": False, "persist": False})
    assert not (r2.status_code == 422
                and r2.json().get("detail", {}).get("error")
                == "hs_confirmation_needed")


def test_w1_2_research_gate_off_by_default_no_block():
    """1.2 — الصمّام مُطفأ افتراضياً => لا حجب (السلوك كاليوم)."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    api_mod = _client(SILK_HS_CONFIRM_GATE=None, SILK_API_KEY=None,
                      SILK_REQUIRE_HS6=None, SILK_WORLD_MARKETS=None)
    client = TestClient(api_mod.create_app())
    with mock.patch("requests.get",
                    side_effect=OSError("net blocked for offline test")):
        r = client.post("/research",
                        json={"product": "زبدة الفول السوداني",
                              "market": "Yemen", "hs_code": "040510",
                              "async_run": False, "persist": False})
    assert not (r.status_code == 422
                and r.json().get("detail", {}).get("error")
                == "hs_confirmation_needed")
