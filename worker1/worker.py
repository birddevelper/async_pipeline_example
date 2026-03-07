from http import client
import json
import time
import pika
import psycopg2


def get_connection():
    return psycopg2.connect(
        host="postgres", database="jobsdb", user="user", password="password"
    )


def stage1_process(job_id):
    print(f"[Worker1] Processing stage 1 for {job_id}")
    time.sleep(3)
    return f"stage1_result_for_{job_id}"


def callback(ch, method, properties, body):
    data = json.loads(body)
    job_id = data["job_id"]
    client_id = data["client_id"]

    try:
        result = stage1_process(job_id)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE jobs SET stage1_result=%s, status='stage2' WHERE id=%s;",
            (result, job_id),
        )
        conn.commit()
        conn.close()

        ch.basic_publish(
            exchange="",
            routing_key="stage2_jobs",
            body=json.dumps({"job_id": job_id, "client_id": client_id}),
            properties=pika.BasicProperties(delivery_mode=2),
        )

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print("Error:", e)


connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
channel = connection.channel()
channel.queue_declare(queue="stage1_jobs", durable=True)
channel.queue_declare(queue="stage2_jobs", durable=True)
channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue="stage1_jobs", on_message_callback=callback)

print("Worker1 started")
channel.start_consuming()
