import json
import threading
import pika
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

clients: dict[str, WebSocket] = {}

origins = ["*"]


def rabbit_listener(loop):

    def callback(ch, method, properties, body):
        data = json.loads(body)
        client_id = data["client_id"]
        job_id = data["job_id"]
        status = data["status"]
        print(f"Received status '{status}' for job {job_id} from client {client_id}")

        client = clients.get(client_id)

        if client:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    client.send_text(json.dumps(data)),
                    loop,
                )
                future.result(timeout=5)
            except Exception:
                pass

        ch.basic_ack(delivery_tag=method.delivery_tag)

    connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
    channel = connection.channel()
    channel.queue_declare(queue="notification", durable=True)
    channel.basic_consume(queue="notification", on_message_callback=callback)
    channel.start_consuming()


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    app.state.loop = loop
    listener_thread = getattr(app.state, "listener_thread", None)

    if listener_thread is None or not listener_thread.is_alive():
        listener_thread = threading.Thread(target=rabbit_listener, args=(loop,), daemon=True)
        app.state.listener_thread = listener_thread
        listener_thread.start()

    yield


app = FastAPI(lifespan=lifespan)

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
