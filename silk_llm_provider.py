"""محوّل مزوّد كلود الرقيق — thin LLM provider seam (تدقيق المعمارية، دين ٣).

مشكلة قبل هذا الملف: `silk_ai_judge._call`/`_call_tools` كانا يعرفان تفاصيل
Anthropic HTTP مباشرة (المسار، رأس الإصدار، شكل الحمولة) — أي مزوّد بديل
مستقبلاً (OpenAI مثلاً) يعني جراحة في كل موضع نداء. هذا الملف يستخرج تلك
التفاصيل خلف واجهة `LLMProvider` بمنهجين فقط: `complete` (نداء نص مفرد) و
`complete_tools` (حلقة استخدام أدوات متعددة الأدوار) — تماماً كما كان
`_call`/`_call_tools` يفعلان، بلا أي تغيير سلوكي (نفس المسار، نفس الحمول،
نفس معالجة الفشل/الرفض).

لا مزوّد ثانٍ اليوم — Anthropic هو التنفيذ الوحيد؛ الاختيار عبر إعداد
(`SILK_LLM_PROVIDER`, افتراضي "anthropic") بدل استيراد مباشر، فإضافة مزوّد
لاحقاً = صفّ جديد + سطر تسجيل في `_PROVIDERS`، لا تغيير في مواضع النداء.
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)


class LLMProvider(ABC):
    """الواجهة الدنيا — نداء إكمال نصّي، ونداء حلقة استخدام أدوات."""

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int,
                model: str, timeout: float) -> str | None:
        """نص الرد أو None عند غياب مفتاح/فشل/رفض — لا استثناء يتسرّب للمستدعي."""

    @abstractmethod
    def complete_tools(self, system: str, messages: list, tools: list | None,
                       max_tokens: int, model: str, timeout: float) -> dict | None:
        """رد الـMessages API الخام (غير مُحلَّل) أو None — يقود `silk_llm_runtime`
        حلقة tool_use/tool_result فوقه."""


class AnthropicProvider(LLMProvider):
    """التنفيذ الوحيد اليوم — يغلّف api.anthropic.com/v1/messages حرفياً
    كما كان `silk_ai_judge._call`/`_call_tools` يفعلان قبل هذا الاستخراج."""

    _ENDPOINT = "https://api.anthropic.com/v1/messages"
    _VERSION = "2023-06-01"

    def __init__(self, api_key_env: str = "ANTHROPIC_API_KEY") -> None:
        self._api_key_env = api_key_env

    def _key(self) -> str:
        return os.environ.get(self._api_key_env, "").strip()

    def _headers(self, key: str) -> dict:
        return {"x-api-key": key, "anthropic-version": self._VERSION,
                "content-type": "application/json"}

    @staticmethod
    def _record_usage(model: str, data: dict) -> None:
        """سجّل رموز الرد في عدّاد اقتصاد البيانات — قناة جانبية صامتة (دين ٤)،
        لا تغيّر عقد complete/complete_tools؛ no-op خارج تحليل نشط أو بلا usage."""
        usage = data.get("usage") if isinstance(data, dict) else None
        if not usage:
            return
        import silk_context  # lazy: keep this module cycle-safe and offline
        silk_context.record_llm_usage(
            model, usage.get("input_tokens", 0), usage.get("output_tokens", 0))

    def complete(self, system, user, max_tokens, model, timeout):
        key = self._key()
        if not key:
            return None
        try:
            import requests  # lazy: keep core import offline-safe
            resp = requests.post(
                self._ENDPOINT, timeout=timeout,
                headers=self._headers(key),
                json={"model": model, "max_tokens": max_tokens, "system": system,
                     "messages": [{"role": "user", "content": user}]})
            resp.raise_for_status()
            data = resp.json()
            self._record_usage(model, data)
            if data.get("stop_reason") == "refusal":  # safety decline -> no fabrication
                log.warning("AI judge: request refused by the model")
                return None
            text = "".join(b.get("text", "") for b in data.get("content", [])
                          if b.get("type") == "text").strip()
            return text or None
        except Exception as e:  # noqa: BLE001 — optional layer must never crash analysis
            log.warning("AI judge call failed: %s", e)
            return None

    def complete_tools(self, system, messages, tools, max_tokens, model, timeout):
        key = self._key()
        if not key:
            return None
        try:
            import requests  # lazy: keep core import offline-safe
            payload = {"model": model, "max_tokens": max_tokens,
                      "system": system, "messages": messages}
            if tools:
                payload["tools"] = tools
            resp = requests.post(
                self._ENDPOINT, timeout=timeout,
                headers=self._headers(key), json=payload)
            resp.raise_for_status()
            data = resp.json()
            self._record_usage(model, data)
            return data
        except Exception as e:  # noqa: BLE001 — optional layer must never crash analysis
            log.warning("AI tool call failed: %s", e)
            return None


_PROVIDERS = {"anthropic": AnthropicProvider}
_provider_instance: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """اختر المزوّد حسب `SILK_LLM_PROVIDER` (افتراضي anthropic) — مفرد
    مُخزَّن مؤقتاً (lazy singleton)؛ اسم غير معروف يتراجع بأمان لـAnthropic."""
    global _provider_instance
    if _provider_instance is None:
        name = os.environ.get("SILK_LLM_PROVIDER", "anthropic").strip().lower()
        cls = _PROVIDERS.get(name, AnthropicProvider)
        _provider_instance = cls()
    return _provider_instance


def reset_provider() -> None:
    """أعد ضبط المفرد المخزَّن — test-only reset (تبديل SILK_LLM_PROVIDER بين
    الاختبارات يتطلبه)."""
    global _provider_instance
    _provider_instance = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    p = get_provider()
    print(f"active provider: {type(p).__name__}")
