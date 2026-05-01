import json
import pika
import psycopg2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


class JobCreate(BaseModel):
    client_id: str


app = FastAPI()

NOTIFICATION_QUEUE = "notification"

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_connection():
    return psycopg2.connect(
        host="postgres", database="jobsdb", user="user", password="password"
    )


def publish(queue_name, payload):
    connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)

    channel.basic_publish(
        exchange="",
        routing_key=queue_name,
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2),
    )

    connection.close()


def publish_stage1(job_id, client_id):
    publish("stage1_jobs", {"job_id": job_id, "client_id": client_id})


def publish_notification(job_id, client_id, status, result=None):
    payload = {"job_id": job_id, "client_id": client_id, "status": status}
    if result is not None:
        payload["result"] = result
    publish(NOTIFICATION_QUEUE, payload)


@app.on_event("startup")
def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id SERIAL PRIMARY KEY,
            status TEXT,
            stage1_result TEXT,
            final_result TEXT
        );
    """
    )
    conn.commit()
    conn.close()


@app.post("/jobs")
def create_job(job: JobCreate):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO jobs (status) VALUES ('stage1') RETURNING id;")
    job_id = cur.fetchone()[0]
    conn.commit()
    conn.close()

    publish_stage1(job_id, job.client_id)
    publish_notification(job_id, job.client_id, "created")
    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
def get_job(job_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT status, final_result FROM jobs WHERE id=%s;", (job_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return {"error": "Not found"}

    return {"status": row[0], "result": row[1]}
