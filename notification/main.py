import json
import threading
import pika
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

clients: dict[str, WebSocket] = {}

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()

    clients[client_id] = websocket
    print(f"Client connected: {client_id}")

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        clients.pop(client_id, None)
        print(f"Client disconnected: {client_id}")


def rabbit_listener():

    def callback(ch, method, properties, body):
        data = json.loads(body)

        client_id = data["client_id"]
        job_id = data["job_id"]
        print(f"Received completion for job {job_id} from client {client_id}")
        message = json.dumps({"job_id": job_id, "status": "completed"})

        client = clients.get(client_id)

        if client:
            try:
                asyncio.run(client.send_text(message))
            except Exception:
                pass

        ch.basic_ack(delivery_tag=method.delivery_tag)

    connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
    channel = connection.channel()
    channel.queue_declare(queue="notification", durable=True)
    channel.basic_consume(queue="notification", on_message_callback=callback)
    channel.start_consuming()


threading.Thread(target=rabbit_listener, daemon=True).start()
