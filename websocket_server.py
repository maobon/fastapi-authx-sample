import contextlib
import json
import mimetypes
import os
import uuid
import warnings
from datetime import datetime

# 忽略 urllib3 的 OpenSSL 警告（在所有导入之前处理，以确保生效）
try:
    from urllib3.exceptions import NotOpenSSLWarning

    warnings.filterwarnings("ignore", category=NotOpenSSLWarning)
except ImportError:
    pass

import traceback
from typing import Any, Dict, Optional

import httpx
from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from minio import Minio
from urllib.parse import quote

from constant import (
    DEFAULT_MINIO_ACCESS_KEY,
    DEFAULT_MINIO_BUCKET,
    DEFAULT_MINIO_ENDPOINT,
    DEFAULT_MINIO_SECRET_KEY,
)


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


# 全局 HTTP 客户端，在 lifespan 中管理其生命周期
http_client: Optional[httpx.AsyncClient] = None


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient()
    yield
    await http_client.aclose()


app = FastAPI(
    title="WebSocket Service",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

# 添加 CORS 中间件以支持跨域请求（解决 OPTIONS 405 错误）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """自定义验证错误处理器，方便排查 422 错误详情。"""
    print(f"Validation Error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"success": False, "error": "Validation Error", "detail": exc.errors()},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """统一 HTTPException 的返回格式。"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail},
    )


manager = ConnectionManager()

# MinIO 配置
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", DEFAULT_MINIO_ENDPOINT)
# 自动去掉可能存在的 http:// 或 https:// 前缀
if MINIO_ENDPOINT.startswith("http://"):
    MINIO_ENDPOINT = MINIO_ENDPOINT[7:]
elif MINIO_ENDPOINT.startswith("https://"):
    MINIO_ENDPOINT = MINIO_ENDPOINT[8:]

MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", DEFAULT_MINIO_ACCESS_KEY)
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", DEFAULT_MINIO_SECRET_KEY)
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", DEFAULT_MINIO_BUCKET)
MINIO_SECURE = os.environ.get("MINIO_SECURE", "False").lower() == "true"

print(f"Connecting to MinIO at {MINIO_ENDPOINT} (secure={MINIO_SECURE}), Bucket: {MINIO_BUCKET}")

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)

# 确保 Bucket 存在并设置为公开只读
try:
    if not minio_client.bucket_exists(MINIO_BUCKET):
        print(f"Bucket {MINIO_BUCKET} does not exist, creating...")
        minio_client.make_bucket(MINIO_BUCKET)

    # 设置公开只读策略 (参考 minio.py)
    policy = f"""{{
      "Version": "2012-10-17",
      "Statement": [
        {{
          "Effect": "Allow",
          "Principal": {{"AWS": ["*"]}},
          "Action": ["s3:GetObject"],
          "Resource": ["arn:aws:s3:::{MINIO_BUCKET}/*"]
        }}
      ]
    }}"""
    minio_client.set_bucket_policy(MINIO_BUCKET, policy)
    print(f"Bucket {MINIO_BUCKET} is now public (ReadOnly).")
except Exception as e:
    print(f"Error: Could not connect to MinIO or set bucket policy: {e}")


async def process_image_url(url: str) -> Dict[str, Any]:
    """获取图片 URL 的基本信息以验证其有效性。"""
    try:
        # 使用全局 http_client 提升性能，避免频繁创建/关闭连接
        response = await http_client.head(url, follow_redirects=True, timeout=5.0)
        if response.status_code != 200:
            # 如果 HEAD 不支持，尝试 GET
            response = await http_client.get(url, follow_redirects=True, timeout=5.0)

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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, user_id: Optional[str] = None):
    """接受客户端连接，处理用户加入、退出及各类消息。"""
    # 允许通过 Query 参数 user_id 指定身份，否则生成随机 ID
    user_id = user_id or f"user_{str(uuid.uuid4())[:8]}"
    
    await manager.connect(websocket, user_id)
    
    # 广播加入消息
    await manager.broadcast({
        "type": "system",
        "content": f"{user_id} 加入了聊天室"
    })

    try:
        while True:
            # 接收原始文本
            message = await websocket.receive_text()
            print(f"server recv from {user_id}: {message}")

            # 尝试解析为 JSON
            data: Dict[str, Any]
            try:
                parsed = json.loads(message)
                if isinstance(parsed, dict):
                    data = parsed
                else:
                    data = {"type": "text", "content": message}
            except json.JSONDecodeError:
                data = {"type": "text", "content": message}

            msg_type = data.get("type")
            if msg_type == "text":
                await manager.broadcast(data, sender=websocket)
            elif msg_type == "image":
                url = data.get("url")
                if not isinstance(url, str):
                    await websocket.send_json(
                        {"type": "error", "message": "Missing or invalid 'url' for image"})
                    continue

                # 处理图片 URL
                info = await process_image_url(url)
                if info["success"]:
                    data["metadata"] = {
                        "size": info["size"],
                        "mime_type": info["mime_type"]
                    }
                    await manager.broadcast(data, sender=websocket)
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Invalid image URL: {info['error']}"
                    })
            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Unsupported type: {msg_type}"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"Error for {user_id}: {e}")
    finally:
        manager.disconnect(websocket)
        # 广播退出消息
        await manager.broadcast({
            "type": "system",
            "content": f"{user_id} 离开了聊天室"
        })


@app.post("/upload/pic")
async def upload_pic(file: UploadFile = File(...)):
    """接收图片文件并流式保存到 MinIO。"""
    try:
        # 1. 校验文件类型 (MIME Type)
        content_type = file.content_type

        # 如果是通用的字节流类型，尝试从文件名猜测
        if not content_type or content_type == "application/octet-stream":
            guessed_type, _ = mimetypes.guess_type(file.filename or "")
            if guessed_type:
                content_type = guessed_type

        if not content_type or not content_type.startswith("image/"):
            print(
                f"Upload Denied: Content-Type is '{file.content_type}', guessed as '{content_type}'")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {content_type}. Only images are allowed."
            )

        # 2. 获取文件大小
        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()
        file.file.seek(0)

        # 3. 生成唯一文件名
        ext = os.path.splitext(file.filename or "")[1].lower()
        if not ext and content_type:
            ext = "." + content_type.split("/")[-1]

        # 直接存储在存储桶根目录下 (存储桶为 images)
        object_name = f"{uuid.uuid4()}{ext}"

        # 4. 上传到 MinIO
        result = minio_client.put_object(
            MINIO_BUCKET,
            object_name,
            file.file,
            length=file_size,
            content_type=content_type,  # 使用识别后的类型
        )

        # 验证：立即检查文件是否存在
        try:
            stat = minio_client.stat_object(MINIO_BUCKET, object_name)
            print(f"Verification Success: Found {object_name} in {MINIO_BUCKET}, size={stat.size}")
        except Exception as ve:
            print(f"Verification Failed: {object_name} not found after upload! Error: {ve}")
            raise HTTPException(status_code=500,
                                detail="File upload confirmed by SDK but verification failed.")

        # 5. 构造访问链接 (参考 minio.py 使用 quote 编码)
        encoded_name = "/".join(quote(part, safe="") for part in object_name.split("/"))
        image_url = f"http://{MINIO_ENDPOINT}/{MINIO_BUCKET}/{encoded_name}"

        resp_data = {
            "success": True,
            "image_id": object_name,
            "url": image_url,
            "size": file_size,
            "mime_type": content_type,
            "etag": result.etag
        }
        print(f"Upload Success: {resp_data}")
        return resp_data

    except HTTPException as e:
        raise e
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port)
