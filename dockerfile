FROM python:3.12-slim

# ---- Environment defaults ----
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    LANG=C.UTF-8 \
    HOME=/app \
    XDG_CACHE_HOME=/app/.cache \
    HF_HOME=/app/.cache/huggingface \
    HUGGINGFACE_HUB_CACHE=/app/.cache/huggingface \
    SURYA_CACHE_DIR=/app/.cache/surya

# ---- System packages (OCR/PDF stack) ----
RUN apt-get update && apt-get install -y --no-install-recommends \
      git build-essential libgl1 libglib2.0-0 \
      ffmpeg tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng \
      poppler-utils qpdf ghostscript \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- Python deps (as root) ----
RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install \
      "markitdown[all]" && \
    python -m pip install --extra-index-url https://download.pytorch.org/whl/cpu \
      torch torchvision torchaudio && \
    python -m pip install \
      "marker-pdf[full]" \
      docling \
      streamlit \
      pptx2md \
      watchdog \
      easyocr \
      rapidocr-onnxruntime onnxruntime \
      ocrmypdf
RUN python -m pip install pypdf

# ---- App & cache dirs (as root) ----
RUN mkdir -p /app/data/in /app/data/out /app/.cache /app/.cache/huggingface /app/.cache/surya

# Pre-create static dir for Marker fonts and download at build time
RUN mkdir -p /usr/local/lib/python3.12/site-packages/static && \
    python - <<'PY'
from marker.util import download_font
download_font()
PY

# ---- Create non-root user and give ownership ----
RUN addgroup --system app && adduser --system --ingroup app --home /app app && \
    chown -R app:app /app && \
    chown -R app:app /usr/local/lib/python3.12/site-packages/static

# ---- Switch to non-root ----
USER app

# ---- App code ----
COPY --chown=app:app app.py /app/app.py

EXPOSE 8501