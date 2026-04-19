FROM python:3.12-slim-buster

WORKDIR /app

# Copy shared library in editable mode
# This assumes kimvieware-shared is at the same level as kimvieware-monitor
COPY ../kimvieware-shared /app/kimvieware-shared
WORKDIR /app/kimvieware-shared
RUN pip install -e .

# Copy monitor service code
WORKDIR /app/kimvieware-monitor
COPY ./requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "monitor_service.py"]
