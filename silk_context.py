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


# توجيهات الوكلاء (P3): درج «إعدادات الوكلاء» بالواجهة يرسل agent_prefs
# — {agent_key: {on: bool, cmd: str}}. الأمر النصي يوجّه **تركيز** برومبتات
# كلود حصراً (يُلحق داخل عزل _isolate القائم)؛ لا يصل أي وكيل بيانات رقمي
# ولا يستطيع توليد رقم — الثابت التأسيسي محفوظ بنيوياً.
_agent_prefs: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "silk_agent_prefs", default=None)


def agent_pref(agent_key: str) -> dict:
    """تفضيل وكيل واحد — {} حين لا سياق/لا تفضيل (السلوك الافتراضي)."""
    prefs = _agent_prefs.get() or {}
    p = prefs.get(agent_key)
    return p if isinstance(p, dict) else {}


def agent_command(agent_key: str) -> str:
    """أمر المستخدم النصي لوكيل — "" افتراضياً؛ مقصوص لطول آمن."""
    return str(agent_pref(agent_key).get("cmd") or "")[:500].strip()


def agent_enabled(agent_key: str) -> bool:
    """هل الوكيل مفعّل؟ — True افتراضياً (غياب التفضيل لا يعطّل شيئاً)."""
    p = agent_pref(agent_key)
    return bool(p.get("on", True))


@contextlib.contextmanager
def agent_prefs_context(prefs: dict | None):
    """فعّل تفضيلات الوكلاء للكتلة — contextvar بنمط deepen_context نفسه."""
    token = _agent_prefs.set(prefs if isinstance(prefs, dict) else None)
    try:
        yield
    finally:
        _agent_prefs.reset(token)


# اقتصاد البيانات (persist-5): عدّاد لكل تحليل — كم قراءة خُدمت من المخزن/
# ذاكرة الطلبات مقابل كم جلبة حية. contextvar فيعزل الطلبات المتزامنة؛
# غياب العدّاد (نداء مكتبي خارج analyze) = لا عدّ، صفر أثر على أي مسار.
# Per-analysis data-economics counter: store/cache hits vs live fetches.
_data_counter: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "silk_data_counter", default=None)


def begin_data_counter() -> dict:
    """ابدأ عدّاداً جديداً — fresh counter for this analysis run (contextvar).

    `llm_calls`/`tool_calls` (V5 wave 1): كل نداء كلود ونداء أداة داخل حلقة
    الوكيل اللغوي (`silk_llm_runtime.run_llm_agent`) يُعدّ هنا — نفس القناة
    الجانبية الصامتة لعدّادات المخزن/الجلب الحي، صفر أثر خارج تحليل نشط.
    """
    c = {"store_hits": 0, "cache_hits": 0, "live_fetches": 0,
         "llm_calls": 0, "tool_calls": 0}
    _data_counter.set(c)
    return c


def count_data(kind: str, n: int = 1) -> None:
    """سجّل حدث بيانات — increment a counter kind; silent no-op without one."""
    c = _data_counter.get()
    if c is not None and kind in c:
        c[kind] += n


def data_counter() -> dict | None:
    """العدّاد الحالي — the active counter dict, or None outside an analysis."""
    return _data_counter.get()
