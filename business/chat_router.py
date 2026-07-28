from fastapi import APIRouter, File, UploadFile, WebSocket, status
from authx.exceptions import AuthXException

from utils.chat_utils import get_http_client
from utils.minio_manager import minio_client, MINIO_BUCKET, MINIO_ENDPOINT
from business.chat_business import handle_chat_session, handle_image_upload
from business.deps import auth, manager

router = APIRouter(tags=["chat"])

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """接受客户端连接，处理用户加入、退出及各类消息。"""
    try:
        # 使用 AuthX 的 WebSocket 校验方法
        payload = await auth._ws_auth_required(websocket)
        user_id = payload.sub
        print(f"WebSocket Token Verified: {user_id}")
    except AuthXException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed")
        return

    await handle_chat_session(websocket, user_id, manager, get_http_client())

@router.post("/upload/pic")
async def upload_pic(file: UploadFile = File(...)):
    """接收图片文件并流式保存到 MinIO。"""
    return await handle_image_upload(file, minio_client, MINIO_BUCKET, MINIO_ENDPOINT)
