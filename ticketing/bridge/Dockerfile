FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir flask requests pyyaml

COPY app.py /app/app.py
COPY config.yml /app/config.yml
COPY templates /app/templates

EXPOSE 5000

CMD ["python", "/app/app.py"]
