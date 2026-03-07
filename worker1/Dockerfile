FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install pika psycopg2-binary
CMD ["python", "worker.py"]
