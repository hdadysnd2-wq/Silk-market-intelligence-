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
        raise OSError("network disabled for hermetic test")

    socket.socket = _no_net
    try:
        yield
    finally:
        socket.socket = real
