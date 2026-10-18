FROM python:3.11-slim

# INSTALL_ML=false (default): lightweight VADER + TF-IDF fallbacks, small image, fast build.
# INSTALL_ML=true          : adds torch (CPU), transformers and sentence-transformers (large image;
#                            models download from Hugging Face on first analysis).
ARG INSTALL_ML=false
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt requirements-lite.txt ./
RUN if [ "$INSTALL_ML" = "true" ]; then \
      pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
      pip install --no-cache-dir -r requirements.txt; \
    else \
      pip install --no-cache-dir -r requirements-lite.txt; \
    fi
RUN python -m spacy download en_core_web_sm

COPY app ./app
EXPOSE 8000
# One worker on purpose: analysis jobs run in-process and are serialised by a lock.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
