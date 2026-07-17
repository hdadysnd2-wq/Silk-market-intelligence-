FROM python:3.11-slim

WORKDIR /app

# محرّك تحويل PDF غير القابل للتحرير (§3، اتفاق المالك): LibreOffice headless
# (soffice) + خطّ عربي الشكل (Amiri) — بدونهما يقع GET /analyses/{id}/report.pdf
# في فرع 503 «محرّك التحويل غير متاح» فيصبح زرّ «تصدير التقرير (PDF)» ميتاً حياً.
# راجع docs/DEPLOY_RAILWAY.md §6 (بوابة قبول PDF/RTL) و silk_reports.docx_to_pdf.
# The final client deliverable is a non-editable PDF; LibreOffice + an Arabic
# font must ship on the image or the PDF endpoint 503s live.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libreoffice-writer fonts-hosny-amiri fontconfig \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 8000

# Railway يمرّر PORT وقت التشغيل؛ محليًا يسقط إلى 8000.
# Railway injects PORT at runtime; falls back to 8000 locally.
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
