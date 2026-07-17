#!/usr/bin/env python3
"""رُتبة ٢ — خادم حقيقي بشكل الإنتاج (rung 2: the real-server harness).

> **القاعدة الجديدة (تأكيد المالك آخِراً لا أوّلاً).** قبل أن يُوسَم أيّ PR
> يمسّ سلوكاً إنتاجياً «جاهزاً»، نستنفد كل رُتب الاختبار. الرُتبة ٢: أقلِع
> **التطبيق الفعلي** بـuvicorn على ملف SQLite حقيقي مبذور بالمدوّنة القانونية
> الحقيقية الشكل (تمور × هولندا)، واضرب كل نقطة نهاية بـHTTP حقيقي. لا نموذج،
> لا TestClient — عملية خادم فعلية على منفذ فعلي.
>
> **What this is.** Boots the ACTUAL app (uvicorn) against a REAL SQLite file
> seeded with the canonical real-shape Netherlands blob, so rung-2 tests and
> the rung-3 Playwright flow both drive a real server over real HTTP.

المفاتيح المدفوعة (Claude/Comtrade) غائبة عمداً — نقاط القراءة/التصدير التي
تخدمها هذه البيئة (‏`/analyses`, `/analyses/{id}`, `report.md`, `report.docx`,
‏`/research/{id}/status`) تُقرَأ من المخزن ولا تلمس أيّ API خارجي، فلا حاجة
لأيّ محاكاة هنا؛ الطبقة الوحيدة التي كانت ستُحاكى (المزودون المدفوعون) لا
تُستدعى أصلاً على مسار الإسناد. أي تغيير قرب مسار المال يُشغّل رُتبة ٤
(‏tools/acceptance_run.py) بمزودين محاكَين بدلاً منها.

الاستعمال المستقل (standalone):
    python3 tools/live_shape_server.py --port 8099 --hold   # يبقى معلّقاً للتصفّح اليدوي
    python3 tools/live_shape_server.py --port 8099          # يُقلِع، يفحص /health، يطبع، يُغلق

الاستعمال المستورَد (اختبارات رُتبة ٢/٣):
    from live_shape_server import LiveShapeServer
    with LiveShapeServer() as srv:
        print(srv.base_url, srv.completed_id, srv.running_id)

المكتبات: stdlib فقط (subprocess/urllib/tempfile) — لا تبعيات جديدة.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))

from canonical_netherlands import netherlands_research_blob  # noqa: E402


def _free_port() -> int:
    """منفذ حرّ يمنحه النظام — يتجنّب تصادم المنافذ الثابتة في CI المتوازي."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def seed_db(db_path: str) -> tuple[int, int]:
    """ابذر ملف SQLite بالمدوّنة القانونية: صفّ مكتمل (تقرير كامل + تصدير)
    وصفّ جارٍ (شارة تقدّم «جارٍ التشغيل…» + زرّ استئناف في الشريط الجانبي).
    يعيد (completed_id, running_id). Seed a real DB; return the two row ids.

    نبذر عبر واجهات silk_storage الحقيقية نفسها التي يستعملها الإنتاج
    (`save_analysis` / `create_research_run`) — لا كتابة SQL يدوية تلتفّ على
    المخطّط الفعلي."""
    import silk_storage
    silk_storage.init_db(db_path)
    completed_id = silk_storage.save_analysis(
        netherlands_research_blob(), path=db_path)
    # صفّ جارٍ — يُظهر مسار التقدّم الحيّ في الشريط الجانبي (شارة + استئناف)
    # دون تشغيلة فعلية (deterministic، بلا نداء مدفوع).
    running_id = silk_storage.create_research_run(
        product="تمور", market_iso3="ESP", hs_code="080410",
        request_snapshot={"product": "تمور", "market": "ESP",
                          "hs_code": "080410"},
        path=db_path, market_name="إسبانيا")
    return completed_id, running_id


class LiveShapeServer:
    """مدير سياق يُقلِع uvicorn على DB مبذور ويُغلقه — real uvicorn subprocess.

    `base_url` جاهز بعد `__enter__` (بعد أن يرد /health بـ200). المفاتيح
    المدفوعة غائبة، والتخزين كلّه في مجلّد مؤقّت يُنظَّف عند الخروج."""

    def __init__(self, port: int | None = None, boot_timeout: float = 45.0):
        self.port = port or _free_port()
        self.boot_timeout = boot_timeout
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._tmp = tempfile.mkdtemp(prefix="silk_rung2_")
        self.db_path = os.path.join(self._tmp, "silk.db")
        self.completed_id = 0
        self.running_id = 0
        self._proc: subprocess.Popen | None = None

    def _env(self) -> dict:
        env = dict(os.environ)
        # كل المخازن على المجلّد المؤقّت — لا تلوّث قرص المطوّر ولا الإنتاج.
        env["SILK_DB"] = self.db_path
        env["SILK_STORE_DB"] = os.path.join(self._tmp, "store.db")
        env["SILK_USAGE_DB"] = os.path.join(self._tmp, "usage.db")
        env["SILK_CACHE_DIR"] = os.path.join(self._tmp, "cache")
        env["SILK_TRACE_DIR"] = os.path.join(self._tmp, "traces")
        # وضع تطوير مفتوح مشروع (لا مفاتيح مدفوعة) — الشريط الجانبي يُقرَأ
        # بلا X-API-Key فلا يحتاج المتصفّح لحقن مفتاح. المفاتيح المدفوعة
        # تُنزَع صراحةً كي لا يفلت نداء خارجي في e2e.
        for k in ("SILK_API_KEY", "ANTHROPIC_API_KEY", "SERPER_API_KEY",
                  "COMTRADE_API_KEY", "GOOGLE_MAPS_API_KEY", "EXPLEE_API_KEY",
                  "VOLZA_API_KEY", "SILK_REFRESH_HOURS",
                  "SILK_REQUIRE_PERSISTENT_DATA_DIR"):
            env.pop(k, None)
        env.setdefault("SILK_HTTP_MIN_GAP_MS", "0")
        return env

    def __enter__(self) -> "LiveShapeServer":
        self.completed_id, self.running_id = seed_db(self.db_path)
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api:app",
             "--host", "127.0.0.1", "--port", str(self.port), "--log-level",
             "warning"],
            cwd=_ROOT, env=self._env(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if not self._wait_healthy():
            out = b""
            with contextlib.suppress(Exception):
                if self._proc and self._proc.stdout:
                    out = self._proc.stdout.read(4000)
            self.__exit__(None, None, None)
            raise RuntimeError(
                "rung-2 server did not become healthy in "
                f"{self.boot_timeout}s — server output:\n"
                f"{out.decode('utf-8', 'replace')}")
        return self

    def _wait_healthy(self) -> bool:
        deadline = time.time() + self.boot_timeout
        while time.time() < deadline:
            if self._proc and self._proc.poll() is not None:
                return False  # مات مبكّراً
            try:
                with urllib.request.urlopen(
                        self.base_url + "/health", timeout=3) as r:
                    if r.status == 200:
                        return True
            except (urllib.error.URLError, OSError):
                time.sleep(0.3)
        return False

    def __exit__(self, *exc) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            with contextlib.suppress(Exception):
                self._proc.wait(timeout=10)
            if self._proc.poll() is None:
                self._proc.kill()
        shutil.rmtree(self._tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="رُتبة ٢ — خادم حقيقي مبذور")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--hold", action="store_true",
                    help="أبقِ الخادم معلّقاً للتصفّح اليدوي (Ctrl-C للإيقاف)")
    a = ap.parse_args()
    with LiveShapeServer(port=a.port) as srv:
        print(json.dumps({
            "base_url": srv.base_url,
            "completed_id": srv.completed_id,
            "running_id": srv.running_id,
            "db_path": srv.db_path,
        }, ensure_ascii=False))
        sys.stdout.flush()
        if a.hold:
            print(f"→ افتح {srv.base_url} في المتصفّح — Ctrl-C للإيقاف",
                  file=sys.stderr)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
