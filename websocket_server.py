import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect


class ConnectionManager:
    """管理在线客户端，并把消息转发给除发送者外的其他客户端。"""

    def __init__(self):
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

    async def broadcast(self, message: str, sender: WebSocket) -> None:
        disconnected_connections = []
        for connection in tuple(self.active_connections):
            if connection is sender:
                continue
            try:
                await connection.send_text(message)
            except (RuntimeError, WebSocketDisconnect):
                disconnected_connections.append(connection)

        for connection in disconnected_connections:
            self.disconnect(connection)


app = FastAPI(
    title="WebSocket Service",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """接受客户端连接，并将其文本消息广播给其他在线客户端。"""
    await manager.connect(websocket)
    try:
        while True:
            message = await websocket.receive_text()
            print("server recv: ", message)
            await manager.broadcast(message, sender=websocket)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port)
