"""سياق التعميق — the /deepen execution context (stdlib contextvars).

الموجة ٢: الحصر البنيوي للوكلاء المدفوعين. `BaseAgent` يرفض تشغيل وكيل
`PAID=True` ما لم يكن السياق مفعّلاً — فلا يعتمد المنع على تذكُّر إضافة حارس
في api.py (درس الثغرات الثلاث التاريخية "استدعاء مدفوع تلقائي").

contextvars (لا متغير وحدة عام) حتى يبقى العزل صحيحاً مع تعدد الطلبات
المتزامنة في FastAPI. صفر تبعيات، صفر شبكة.
"""
from __future__ import annotations

import contextlib
import contextvars

_deepen: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "silk_deepen", default=False)


def deepen_active() -> bool:
    """هل نحن داخل تعميق؟ — True only inside a deepen_context() block."""
    return _deepen.get()


@contextlib.contextmanager
def deepen_context():
    """فعّل سياق التعميق — activate the paid-layer context for a with-block.

    يستخدمه مسار `/deepen` في api.py (والمكتبيون المباشرون عند الحاجة الصريحة).
    """
    token = _deepen.set(True)
    try:
        yield
    finally:
        _deepen.reset(token)
