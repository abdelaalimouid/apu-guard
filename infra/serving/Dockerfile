# Scoring API image (built from the repo root: docker build -f infra/serving/Dockerfile .)
FROM python:3.12-slim
RUN pip install --no-cache-dir "mlflow-skinny==3.18.0" "numpy==2.2.6" "pandas==2.3.3" fastapi uvicorn
WORKDIR /app
COPY src/apu_guard /app/apu_guard
ENV PYTHONPATH=/app
EXPOSE 8000
USER 1000
CMD ["uvicorn", "apu_guard.serving.app:app", "--host", "0.0.0.0", "--port", "8000"]
