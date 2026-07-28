import json
import mimetypes
import os
import uuid
import traceback
from typing import Any, Dict, Optional
from urllib.parse import quote

from fastapi import HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from minio import Minio
import httpx

from utils.chat_utils import ConnectionManager, process_image_url

async def handle_chat_session(
    websocket: WebSocket,
    user_id: str,
    manager: ConnectionManager,
    http_client: Optional[httpx.AsyncClient]
):
    """处理 WebSocket 聊天会话逻辑。"""
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
                info = await process_image_url(http_client, url)
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

async def handle_image_upload(
    file: UploadFile,
    minio_client: Minio,
    bucket_name: str,
    minio_endpoint: str
) -> Dict[str, Any]:
    """处理图片上传逻辑。"""
    try:
        # 1. 校验文件类型 (MIME Type)
        content_type = file.content_type
        if not content_type or content_type == "application/octet-stream":
            guessed_type, _ = mimetypes.guess_type(file.filename or "")
            if guessed_type:
                content_type = guessed_type

        if not content_type or not content_type.startswith("image/"):
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

        object_name = f"{uuid.uuid4()}{ext}"

        # 4. 上传到 MinIO
        minio_client.put_object(
            bucket_name,
            object_name,
            file.file,
            length=file_size,
            content_type=content_type,
        )

        # 5. 构造访问链接
        encoded_name = "/".join(quote(part, safe="") for part in object_name.split("/"))
        image_url = f"http://{minio_endpoint}/{bucket_name}/{encoded_name}"

        return {
            "success": True,
            "image_id": object_name,
            "url": image_url,
            "size": file_size,
            "mime_type": content_type
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
