from fastapi import APIRouter, File, UploadFile, WebSocket, status, Request
from authx.exceptions import AuthXException

from utils.chat_utils import get_http_client
from utils.minio_manager import minio_client, MINIO_BUCKET, MINIO_PUBLIC_HOST, MINIO_SECURE
from business.chat_business import handle_chat_session, handle_image_upload
from business.deps import auth, manager, verify_access_token

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
async def upload_pic(request: Request, file: UploadFile = File(...)):
    """接收图片文件并流式保存到 MinIO """
    username = await verify_access_token(request)

    # 检查请求头中的 head_pic 字段
    head_pic_header = request.headers.get("head_pic", "false").lower()
    is_head_pic = head_pic_header == "true"

    msg = f"--- [API Upload] User: {username}, Is Avatar: {is_head_pic} (Hdr: {head_pic_header})"
    print(msg)

    return await handle_image_upload(
        file,
        minio_client,
        MINIO_BUCKET,
        MINIO_PUBLIC_HOST,
        use_ssl=MINIO_SECURE,
        username=username,
        is_head_pic=is_head_pic
    )
