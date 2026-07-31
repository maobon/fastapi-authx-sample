import pytest
from starlette.testclient import TestClient
import basic_server

@pytest.fixture
def client():
    with TestClient(basic_server.app) as test_client:
        yield test_client

def test_webrtc_signaling_exchange(client):
    """测试 WebRTC 信令报文 (Offer/Answer/Candidate) 的交换逻辑。"""
    # 模拟两个用户连接
    token_a = basic_server.auth.create_access_token(uid="UserA")
    token_b = basic_server.auth.create_access_token(uid="UserB")

    with (
        client.websocket_connect(f"/ws?token={token_a}") as ws_a,
        client.websocket_connect(f"/ws?token={token_b}") as ws_b,
    ):
        # 消耗加入消息
        ws_a.receive_json() # UserA joins
        ws_a.receive_json() # UserB joins
        ws_b.receive_json() # UserB joins

        # 1. 模拟 UserA 发送 Offer
        rtc_offer = {
            "type": "rtc",
            "offer": "v=0\r\no=- 4722123456789 2 IN IP4 127.0.0.1..."
        }
        ws_a.send_json(rtc_offer)
        
        # UserB 应该收到该 Offer
        resp_b = ws_b.receive_json()
        assert resp_b["type"] == "rtc"
        assert resp_b["offer"] == rtc_offer["offer"]
        assert resp_b["sender"] == "UserA"
        assert "timestamp" in resp_b

        # 2. 模拟 UserB 发送 Answer
        rtc_answer = {
            "type": "rtc",
            "answer": "v=0\r\no=- 4722123456789 2 IN IP4 127.0.0.1..."
        }
        ws_b.send_json(rtc_answer)
        
        # UserA 应该收到该 Answer
        resp_a = ws_a.receive_json()
        assert resp_a["type"] == "rtc"
        assert resp_a["answer"] == rtc_answer["answer"]
        assert resp_a["sender"] == "UserB"

        # 3. 模拟 Candidate 交换
        rtc_candidate = {
            "type": "rtc",
            "candidate": "candidate:842163049 1 udp 1677729535 192.168.1.1 50000 typ host"
        }
        ws_a.send_json(rtc_candidate)
        
        resp_b_cand = ws_b.receive_json()
        assert resp_b_cand["type"] == "rtc"
        assert resp_b_cand["candidate"] == rtc_candidate["candidate"]
        assert resp_b_cand["sender"] == "UserA"
