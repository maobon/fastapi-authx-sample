from starlette.testclient import TestClient

import websocket_server


def test_service_only_registers_websocket_route():
    assert [route.path for route in websocket_server.app.routes] == ["/ws"]


def test_two_websocket_clients_exchange_messages():
    with TestClient(websocket_server.app) as client:
        with (
            client.websocket_connect("/ws") as device_a,
            client.websocket_connect("/ws") as device_b,
        ):
            device_a.send_text("message from web")
            assert device_b.receive_text() == "message from web"

            device_b.send_text("message from Flutter")
            assert device_a.receive_text() == "message from Flutter"

    assert websocket_server.manager.active_connections == set()
