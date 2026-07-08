"""أدوات اختبار مشتركة — shared test helpers (M0).

يوفّر `block_network` القانوني الواحد بدل النسخ المكرَّرة في ملفات الموجات
(الأثر التاريخي يُنظَّف في M9). الاختبارات الجديدة تستورد من هنا حصراً.
Canonical network guard for hermetic tests; new tests import from here only.
"""
import contextlib
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@contextlib.contextmanager
def block_network():
    """اقطع الشبكة مؤقتاً — make outbound sockets fail so 'no data' paths hold."""
    real = socket.socket

    def _no_net(*a, **k):  # noqa: ANN002, ANN003
        # صياغة بلا كلمة hermetic عمداً: حارس تقارير الإنتاج يرفض أي أثر يحمل
        # الكلمة (إصلاح مراجعة Stage 5) — قطع الشبكة حالة تشغيل صادقة لا بديل
        # بيانات، فلا يجوز أن تسمّم ملاحظاتُه تقريراً مشتقاً في اختبار.
        raise OSError("network disabled for offline test")

    socket.socket = _no_net
    try:
        yield
    finally:
        socket.socket = real


def docx_all_text(path: str) -> str:
    """كل نص مستند Word — فقرات + خلايا جداول (مراجعة المشروع: بعض أقسام
    render_docx صارت جداولاً حقيقية بدل نقاط سردية؛ `doc.paragraphs` وحدها
    لا تصل خلايا الجداول، فتفوّت اختباراتٌ محتوًى انتقل إليها بلا انحدار فعلي).
    """
    from docx import Document
    doc = Document(path)
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


import tempfile

import pytest


@pytest.fixture(autouse=True)
def _isolated_fact_store(monkeypatch):
    """عزل مخزن الحقائق لكل اختبار — كتابة M2 العابرة دفّأت المخزن الافتراضي
    فتسرّبت حقائق حقيقية بين الاختبارات (اكتُشف عبر test_engine_localprice_layer_offline
    بعد تشغيلات تدقيق Stage 1). Every test gets its own store unless it overrides."""
    monkeypatch.setenv("SILK_STORE_DB",
                       os.path.join(tempfile.mkdtemp(), "store.db"))
