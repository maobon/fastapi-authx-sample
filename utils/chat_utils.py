from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from fastapi import WebSocket, WebSocketDisconnect

# 全局 HTTP 客户端
_http_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> Optional[httpx.AsyncClient]:
    """获取全局 HTTP 客户端。"""
    return _http_client


async def init_http_client():
    """初始化全局 HTTP 客户端。"""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient()


async def close_http_client():
    """关闭全局 HTTP 客户端。"""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


class ConnectionManager:
    """管理在线客户端，记录用户身份，并把消息转发给其他客户端。"""

    def __init__(self):
        # 存储 WebSocket 连接到用户 ID 的映射
        self.active_connections: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        await websocket.accept()
        self.active_connections[websocket] = user_id

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            del self.active_connections[websocket]

    def get_user_id(self, websocket: WebSocket) -> Optional[str]:
        return self.active_connections.get(websocket)

    async def broadcast(self, message: Dict[str, Any], sender: Optional[WebSocket] = None) -> None:
        """广播消息，并自动注入发送者和时间戳。"""
        # 注入服务器时间戳
        if "timestamp" not in message:
            message["timestamp"] = datetime.now().isoformat()

        # 如果有发送者，注入发送者 ID
        if sender and "sender" not in message:
            message["sender"] = self.get_user_id(sender) or "unknown"
        elif "sender" not in message:
            message["sender"] = "system"

        disconnected_connections = []
        for connection in tuple(self.active_connections.keys()):
            if connection is sender:
                continue
            try:
                await connection.send_json(message)
            except (RuntimeError, WebSocketDisconnect):
                disconnected_connections.append(connection)

        for connection in disconnected_connections:
            self.disconnect(connection)


async def process_image_url(http_client: Optional[httpx.AsyncClient], url: str) -> Dict[str, Any]:
    """获取图片 URL 的基本信息以验证其有效性。"""
    client = http_client or get_http_client()
    if client is None:
        return {"success": False, "error": "HTTP client not initialized"}
    try:
        response = await client.head(url, follow_redirects=True, timeout=5.0)
        if response.status_code != 200:
            response = await client.get(url, follow_redirects=True, timeout=5.0)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}"}

        content_type = response.headers.get("content-type", "")
        if not content_type or not content_type.startswith("image/"):
            return {"success": False, "error": f"Not an image: {content_type}"}

        return {
            "success": True,
            "size": response.headers.get("content-length"),
            "mime_type": content_type,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
