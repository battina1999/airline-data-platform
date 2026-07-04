# Pipeline + dashboard image (local runner, Streamlit, dbt).
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git make \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8501

# Default: run the full pipeline once, then keep the dashboard alive.
CMD ["bash", "-lc", "make pipeline && streamlit run dashboards/streamlit_app.py --server.address=0.0.0.0"]
