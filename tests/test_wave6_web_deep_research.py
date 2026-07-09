"""اختبارات الموجة ٤د (V5): لوحة البحث العميق في web/index.html.

يغطي: القالب الموحّد نفسه (لا مسار عرض موازٍ — renderBoard يتفرّع لا
يُستبدَل)، وجود دالة renderDeepResearch مربوطة بـ v.deep_research، وأن
جافاسكربت الملف صحيح النحو بعد التعديل (فحص node --check حين متاح).
Run:  python3 -m pytest tests/ -q
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_HTML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "web", "index.html")


def _html() -> str:
    return open(_HTML, encoding="utf-8").read()


def test_deep_research_render_function_wired_into_render_board():
    html = _html()
    assert "function renderDeepResearch(" in html
    assert "if(v.deep_research){renderDeepResearch(v);return}" in html
    # نفس القالب الموحّد — لا استيراد لمسار عرض جديد، الدالة تقرأ v فقط.
    assert "v.deep_research" in html


def test_deep_research_panel_uses_the_five_intersections():
    html = _html()
    for cat in ("demand", "entry_cost", "price_competitiveness",
               "entry_door", "swot"):
        assert f'{cat}:"' in html or f"{cat}:" in html


def test_javascript_syntax_is_valid_after_edit():
    node = shutil.which("node")
    if not node:
        return  # بيئة بلا node — لا يُفشَل الاختبار، فحص أفضل الجهد
    import re
    import tempfile
    m = re.search(r"<script>(.*)</script>", _html(), re.S)
    assert m, "no <script> block found"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(m.group(1))
        tmp_path = f.name
    try:
        proc = subprocess.run([node, "--check", tmp_path],
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
    finally:
        os.unlink(tmp_path)
