#!/usr/bin/env python3
"""فحص دخان بعد النشر — post-deploy live smoke check (PART A5، أمر العمل الرئيس).

الاختبارات الهرمتية تثبت العقود لكنها **لا تلتقط فروق بيئة النشر** (تبعية
حاضرة محلياً غائبة على Railway، متغيّر تخزين غير مضبوط، مسار تصدير يرفع 501
حياً وحده). هذا السكربت يضرب النشر الحيّ فعلياً — نفس عائلة أخطاء 501 التي
تكرّرت ثلاث مرّات لا يمكن أن تُشحَن بصمت بعده:

  1. GET /health  → 200، ويطبع data_dir/persist_guard/research_ready.
  2. GET /analyses → أحدث تحليل مكتمل (إن وُجد).
  3. GET /analyses/{id}/report.md   → 200 + جسم غير فارغ.
  4. GET /analyses/{id}/report.docx → 200 + توقيع ZIP (‏docx = zip) + يُفتَح
     عبر python-docx إن كانت مثبّتة.

الاستعمال:
    python3 tools/post_deploy_smoke.py https://<railway-host>  [--key SILK_API_KEY]

يخرج برمز 0 عند نجاح كل ما هو قابل للفحص، و1 عند أوّل فشل صريح (مع سبب).
لا يختلق نجاحاً: تحليل غير موجود = فحص تصدير «متخطّى» معلَن لا «ناجح».
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
import urllib.error


def _get(base: str, path: str, key: str | None, raw: bool = False):
    req = urllib.request.Request(base.rstrip("/") + path)
    if key:
        req.add_header("X-API-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa: BLE001 — فشل شبكة = فحص فاشل صريح
        return None, str(e).encode()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base", help="live base URL, e.g. https://x.up.railway.app")
    ap.add_argument("--key", default=None, help="X-API-Key if auth is enabled")
    args = ap.parse_args()
    base, key = args.base, args.key
    fails: list[str] = []

    # 1) /health
    st, body = _get(base, "/health", key)
    if st != 200:
        print(f"✗ /health: HTTP {st}")
        return 1
    health = json.loads(body)
    storage = health.get("storage") or {}
    print(f"✓ /health 200 — data_dir={storage.get('data_dir')} "
          f"persist_guard={storage.get('persist_guard')} "
          f"research_ready={health.get('research_ready')}")
    if not storage.get("data_dir"):
        fails.append("storage.data_dir فارغ — التخزين فانٍ (لا وحدة تخزين)")
    if health.get("warnings"):
        print("  ⚠ warnings:", "; ".join(health["warnings"]))

    # 2) أحدث تحليل مكتمل
    st, body = _get(base, "/analyses", key)
    if st != 200:
        print(f"✗ /analyses: HTTP {st} — {body[:200]!r}")
        return 1
    rows = json.loads(body)
    completed = [r for r in rows if r.get("status") in (None, "completed")]
    if not completed:
        print("⊘ لا تحليل مكتمل بعد — فحص التصدير متخطّى (ليس نجاحاً ولا فشلاً)")
        return 1 if fails else 0
    aid = completed[0]["id"]
    print(f"✓ /analyses 200 — أحدث تحليل مكتمل id={aid}")

    # 3) report.md
    st, body = _get(base, f"/analyses/{aid}/report.md", key)
    if st != 200 or not (body or b"").strip():
        fails.append(f"report.md id={aid}: HTTP {st}, حجم={len(body or b'')}")
    else:
        print(f"✓ report.md 200 — {len(body)} بايت")

    # 4) report.docx — عائلة 501: هنا يُلتقَط الفشل الحيّ
    st, body = _get(base, f"/analyses/{aid}/report.docx", key)
    if st != 200:
        fails.append(f"report.docx id={aid}: HTTP {st} — {(body or b'')[:200]!r}")
    elif not (body[:2] == b"PK"):     # docx = حاوية ZIP
        fails.append(f"report.docx id={aid}: 200 لكن ليس ملف ZIP/docx صالحاً")
    else:
        opened = "غير مفحوص (python-docx غير مثبّتة محلياً)"
        try:
            import docx  # noqa: F401
            from docx import Document
            Document(io.BytesIO(body))
            opened = "يُفتَح عبر python-docx"
        except ImportError:
            pass
        except Exception as e:  # noqa: BLE001
            fails.append(f"report.docx id={aid}: 200 لكن python-docx فشل فتحه: {e}")
            opened = "فشل الفتح"
        print(f"✓ report.docx 200 — {len(body)} بايت، {opened}")

    if fails:
        print("\n✗ فشل فحص الدخان:")
        for f in fails:
            print("  -", f)
        return 1
    print("\n✓ كل الفحوص القابلة للتنفيذ نجحت.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
