import json
import time
import pika
import psycopg2


def get_connection():
    return psycopg2.connect(
        host="postgres", database="jobsdb", user="user", password="password"
    )


def stage2_process(stage1_result):
    print("[Worker2] Processing stage 2")
    time.sleep(3)
    return f"FINAL({stage1_result})"


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


def callback(ch, method, properties, body):
    data = json.loads(body)
    job_id = data["job_id"]
    client_id = data["client_id"]

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT stage1_result FROM jobs WHERE id=%s;", (job_id,))
        stage1_result = cur.fetchone()[0]

        final_result = stage2_process(stage1_result)

        cur.execute(
            "UPDATE jobs SET final_result=%s, status='completed' WHERE id=%s;",
            (final_result, job_id),
        )
        conn.commit()
        conn.close()

        publish(
            "notification",
            {
                "job_id": job_id,
                "client_id": client_id,
                "status": "completed",
                "result": final_result,
            },
        )

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print("Error:", e)


connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
channel = connection.channel()
channel.queue_declare(queue="stage2_jobs", durable=True)
channel.queue_declare(queue="notification", durable=True)
channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue="stage2_jobs", on_message_callback=callback)

print("Worker2 started")
channel.start_consuming()
