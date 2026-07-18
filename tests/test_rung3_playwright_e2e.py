"""رُتبة ٣ — متصفّح حقيقي (rung 3 — the real-browser lane).

> **القاعدة الجديدة (تأكيد المالك آخِراً لا أوّلاً).** الرُتبة ٢ تُثبِت أن
> الخادم يخدم الـHTTP الصحيح؛ هذه الرُتبة تُثبِت أن **الواجهة الفعلية تعمل**:
> chromium (headless) ينقر الأزرار الحقيقية ضدّ خادم رُتبة ٢. التدفّق: افتح
> اللوحة ← انقر عنصر الشريط الجانبي ← يُعرَض التقرير ← تصدير Word (‏.docx غير
> فارغ) ← تصدير Markdown (محتوى حقيقي لا القالب الفارغ) ← صندوق التقدّم. هذا
> بالضبط كان سيلتقط **خطأَي التصدير** و**الشريط الجانبي الميت** قبل المالك.

يُقلِع الخادم الحقيقي (`tools/live_shape_server.LiveShapeServer`) ثم يشغّل
تدفّق Playwright (`tests/e2e/live_shape_flow.mjs`) عبر Node مع NODE_PATH يحلّ
حزمة playwright العمومية والمتصفّح من `/opt/pw-browsers`.

بيئة بلا Node/playwright: يُخطَّى بسبب صريح (أفضل جهد — نفس تساهل اختبارات
الواجهة عبر Node)، لكن في وظيفة `e2e-live-shape` كلاهما مثبّت فيعمل فعلياً.
يُتخطّى في `pytest tests/ -q` الافتراضية (SILK_RUN_E2E غير مضبوط).

Run locally:
    SILK_RUN_E2E=1 python3 -m pytest tests/test_rung3_playwright_e2e.py -q -s
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "tools"))

pytestmark = pytest.mark.e2e

_FLOW = os.path.join(_ROOT, "tests", "e2e", "live_shape_flow.cjs")
_PRERUN_FLOW = os.path.join(_ROOT, "tests", "e2e", "prerun_flow.cjs")
_READINESS_FLOW = os.path.join(_ROOT, "tests", "e2e", "readiness_flow.cjs")


def _node() -> str | None:
    return shutil.which("node")


def _node_path() -> str | None:
    """جذر حزم npm العمومية — حيث تُثبَّت playwright في هذه البيئة/CI."""
    node = _node()
    if not node:
        return None
    try:
        out = subprocess.run(["npm", "root", "-g"], capture_output=True,
                             timeout=30)
        root = out.stdout.decode().strip()
        return root or None
    except Exception:  # noqa: BLE001
        return None


def _playwright_available(node_path: str | None) -> bool:
    node = _node()
    if not node or not node_path:
        return False
    env = dict(os.environ, NODE_PATH=node_path)
    r = subprocess.run(
        [node, "-e", "require('playwright');console.log('ok')"],
        capture_output=True, env=env, timeout=30)
    return r.returncode == 0


def test_rung3_full_browser_flow_word_and_md_export_and_sidebar():
    """التدفّق الكامل عبر متصفّح حقيقي — يجب أن يخرج سكربت Playwright بـ0 ويطبع
    RUNG3 PASS بعد اجتياز كل خطوة (لوحة/تقدّم/نقر جانبي/Word/Markdown)."""
    node = _node()
    if not node:
        pytest.skip("node غير متاح في هذه البيئة (أفضل جهد؛ وظيفة CI تثبّته)")
    node_path = _node_path()
    if not _playwright_available(node_path):
        pytest.skip("حزمة playwright غير محلولة عبر NODE_PATH "
                    "(أفضل جهد؛ وظيفة e2e-live-shape تثبّتها)")

    from live_shape_server import LiveShapeServer
    with LiveShapeServer() as srv:
        env = dict(
            os.environ,
            NODE_PATH=node_path or "",
            BASE_URL=srv.base_url,
            COMPLETED_ID=str(srv.completed_id),
            RUNNING_ID=str(srv.running_id),
        )
        # المتصفّح يُورَّث من البيئة كما هي: هذه البيئة تصدّر
        # PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers مسبقاً؛ وعلى CI يضعه
        # `playwright install chromium` في مخبأه الافتراضي. لا نفرض مساراً
        # هنا كي لا نُخطئ الموضع في أيّ من البيئتين.
        r = subprocess.run([node, _FLOW], capture_output=True, env=env,
                           timeout=180)
        out = r.stdout.decode("utf-8", "replace")
        err = r.stderr.decode("utf-8", "replace")
        assert r.returncode == 0, (
            f"Playwright flow failed (rc={r.returncode}).\n"
            f"STDOUT:\n{out}\nSTDERR:\n{err}")
        assert "RUNG3 PASS" in out, f"missing PASS marker.\nSTDOUT:\n{out}"


def test_rung3_prerun_modals_flow_classify_confirm_advisory_consent():
    """الشرط المُلزِم (Wave 1): متصفّح حقيقي ينقر نوافذ ما قبل التشغيل الجديدة —
    اختيار منتج/سوق ← «بحث عميق» ← نافذة تصنيف HS ← تأكيد ← نافذة استشارة بلد
    المنشأ ← موافقة صريحة ← إعادة إرسال بالموافقة. الأعلام مُفعَّلة في الخادم
    فقط (prerun_flags)، والاستشارة تُطلق من مخبأ تصدير مبذور (بلا شبكة/مفتاح/
    soffice). يخرج السكربت بـ0 ويطبع PRERUN PASS بعد كل خطوة."""
    node = _node()
    if not node:
        pytest.skip("node غير متاح في هذه البيئة (أفضل جهد؛ وظيفة CI تثبّته)")
    node_path = _node_path()
    if not _playwright_available(node_path):
        pytest.skip("حزمة playwright غير محلولة عبر NODE_PATH "
                    "(أفضل جهد؛ وظيفة e2e-live-shape تثبّتها)")

    from live_shape_server import LiveShapeServer
    with LiveShapeServer(prerun_flags=True) as srv:
        env = dict(
            os.environ,
            NODE_PATH=node_path or "",
            BASE_URL=srv.base_url,
            PRERUN_PRODUCT=srv.PRERUN_PRODUCT,
            PRERUN_HS=srv.PRERUN_HS,
            PRERUN_MARKET_ISO3=srv.PRERUN_MARKET_ISO3,
        )
        r = subprocess.run([node, _PRERUN_FLOW], capture_output=True, env=env,
                           timeout=180)
        out = r.stdout.decode("utf-8", "replace")
        err = r.stderr.decode("utf-8", "replace")
        assert r.returncode == 0, (
            f"Prerun Playwright flow failed (rc={r.returncode}).\n"
            f"STDOUT:\n{out}\nSTDERR:\n{err}")
        assert "PRERUN PASS" in out, f"missing PASS marker.\nSTDOUT:\n{out}"


def test_rung3_readiness_panel_flow_checklist_before_confirm():
    """عائلة D (Wave 1.5): متصفّح حقيقي يرى لوحة «جاهزية الدراسة» — كلُّ تدهورٍ
    كسطر ✓/⚠/✗ قبل زرّ التأكيد — ثم «أكمل الدراسة» يرسل الموافقات الموحّدة.
    الخادم في وضع readiness_panel (SILK_PRERUN_ADVISORIES + مخبأ مبذور)."""
    node = _node()
    if not node:
        pytest.skip("node غير متاح (أفضل جهد؛ وظيفة CI تثبّته)")
    node_path = _node_path()
    if not _playwright_available(node_path):
        pytest.skip("حزمة playwright غير محلولة عبر NODE_PATH (أفضل جهد)")

    from live_shape_server import LiveShapeServer
    with LiveShapeServer(readiness_panel=True) as srv:
        env = dict(
            os.environ,
            NODE_PATH=node_path or "",
            BASE_URL=srv.base_url,
            PRERUN_PRODUCT=srv.PRERUN_PRODUCT,
            PRERUN_HS=srv.PRERUN_HS,
            PRERUN_MARKET_ISO3=srv.PRERUN_MARKET_ISO3,
        )
        r = subprocess.run([node, _READINESS_FLOW], capture_output=True,
                           env=env, timeout=180)
        out = r.stdout.decode("utf-8", "replace")
        err = r.stderr.decode("utf-8", "replace")
        assert r.returncode == 0, (
            f"Readiness Playwright flow failed (rc={r.returncode}).\n"
            f"STDOUT:\n{out}\nSTDERR:\n{err}")
        assert "READINESS PASS" in out, f"missing PASS marker.\nSTDOUT:\n{out}"
