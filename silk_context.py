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


# حجب إضافات كلود (مراجعة المشروع، H2): استخلاص ثقافة المستهلك وفلترة
# الكيانات نداءاتُ كلود تجري على مسار /analyze المجاني — خارج وكلاء PAID
# الثلاثة فلا يمسكها حارس BaseAgent. هذا السياق يحجبها بنيوياً حين يقرّر
# api.py ذلك (مفتاح Anthropic بلا SILK_API_KEY، أو السقف اليومي مستنفد)،
# فتتدهور الطبقات إلى مسارها الكيليسي المعهود (لا اختلاق، الغياب مُعلَن).
_ai_extras_blocked: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "silk_ai_extras_blocked", default=False)


def ai_extras_blocked() -> bool:
    """هل إضافات كلود محجوبة؟ — True only inside a block_ai_extras() block."""
    return _ai_extras_blocked.get()


@contextlib.contextmanager
def block_ai_extras():
    """احجب إضافات كلود للكتلة — silk_ai_judge.available() يعيد False داخلها."""
    token = _ai_extras_blocked.set(True)
    try:
        yield
    finally:
        _ai_extras_blocked.reset(token)
