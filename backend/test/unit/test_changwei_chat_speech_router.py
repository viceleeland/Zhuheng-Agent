"""聊天转录真实 ASGI WebSocket 路由边界；云端连接使用明确替身。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from server.routers import changwei_router as router
from server.utils import auth_middleware
from yuxi.services import changwei_speech as speech
from yuxi.storage.postgres.manager import pg_manager

START = {
    "type": "start",
    "token": "test-login-token",
    "audio": {"encoding": "pcm_s16le", "sample_rate": 16000, "channels": 1},
}


@pytest.fixture
def client(monkeypatch):
    """保留真实路由和 required-user 校验，替换数据库认证边界。"""

    @asynccontextmanager
    async def session():
        yield object()

    monkeypatch.setattr(pg_manager, "get_async_session_context", session)
    monkeypatch.setattr(
        auth_middleware,
        "get_current_user",
        AsyncMock(return_value=SimpleNamespace(uid="u", department_id="d")),
    )
    app = FastAPI()
    app.include_router(router.changwei, prefix="/api")
    with TestClient(app) as value:
        yield value


def test_chat_does_not_require_or_access_a_task(client, monkeypatch):
    """新聊天只转录输入，不借用任何任务权限。"""
    authorize = AsyncMock(side_effect=AssertionError("chat must not access task"))
    monkeypatch.setattr(speech, "authorize_speech", authorize)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with client.websocket_connect("/api/changwei/transcribe/chat") as ws:
        ws.send_json(START)
        event = ws.receive_json()
    assert event["type"] == "error"
    assert "尚未配置" in event["message"]
    authorize.assert_not_called()
    assert auth_middleware.get_current_user.await_args.kwargs["authorization"] == "Bearer test-login-token"


@pytest.mark.parametrize("token", ["", None, 12])
def test_missing_token_never_reaches_auth_or_cloud(client, monkeypatch, token):
    """URL 参数不能替代首帧登录凭据。"""
    relay = AsyncMock()
    monkeypatch.setattr(speech, "relay_speech", relay)
    with client.websocket_connect("/api/changwei/transcribe/chat?token=url-token") as ws:
        ws.send_json({**START, "token": token})
        assert ws.receive_json()["status"] == 401
    auth_middleware.get_current_user.assert_not_called()
    relay.assert_not_called()


@pytest.mark.parametrize("user, status", [(None, 401), (SimpleNamespace(uid="u", department_id=None), 400)])
def test_chat_required_user_guard(client, monkeypatch, user, status):
    """匿名或未绑定部门用户不能消费语音服务。"""
    auth_middleware.get_current_user.return_value = user
    relay = AsyncMock()
    monkeypatch.setattr(speech, "relay_speech", relay)
    with client.websocket_connect("/api/changwei/transcribe/chat") as ws:
        ws.send_json(START)
        assert ws.receive_json()["status"] == status
    relay.assert_not_called()


@pytest.mark.parametrize("status", [401, 423])
def test_invalid_or_locked_login_never_reaches_cloud(client, monkeypatch, status):
    """真实认证器拒绝的无效或锁定账号保持拒绝。"""
    auth_middleware.get_current_user.side_effect = HTTPException(status, "private diagnostic")
    relay = AsyncMock()
    monkeypatch.setattr(speech, "relay_speech", relay)
    with client.websocket_connect("/api/changwei/transcribe/chat") as ws:
        ws.send_json(START)
        event = ws.receive_json()
    assert event["status"] == status
    assert "private diagnostic" not in event["message"]
    relay.assert_not_called()


def test_task_route_still_enforces_ownership(client, monkeypatch):
    """聊天入口的增加不能让旧任务入口跳过模块授权。"""
    authorize = AsyncMock(side_effect=HTTPException(403, "forbidden"))
    relay = AsyncMock()
    monkeypatch.setattr(speech, "authorize_speech", authorize)
    monkeypatch.setattr(speech, "relay_speech", relay)
    with client.websocket_connect("/api/changwei/tasks/foreign/modules/m/transcribe") as ws:
        ws.send_json(START)
        assert ws.receive_json()["status"] == 403
    assert authorize.await_args.args[1:] == ("u", "foreign", "m")
    relay.assert_not_called()


@pytest.mark.parametrize("packet", [{"type": "stop"}, {**START, "audio": {}}, [], {**START, "token": "x" * 4097}])
def test_invalid_start_never_reaches_cloud(client, monkeypatch, packet):
    """错误协议初始化在音频计费前拒绝。"""
    relay = AsyncMock()
    monkeypatch.setattr(speech, "relay_speech", relay)
    with client.websocket_connect("/api/changwei/transcribe/chat") as ws:
        ws.send_json(packet)
        assert ws.receive_json()["type"] == "error"
    relay.assert_not_called()


def test_authenticated_chat_relays_protocol_without_business_write(client, monkeypatch):
    """登录后可接收转录结果，路由不创建任务或自动发送聊天。"""

    async def relay(ws):
        await ws.send_json({"type": "ready"})
        packet = await ws.receive()
        assert packet["bytes"] == b"\0\0" * 160
        assert await ws.receive_json() == {"type": "stop"}
        await ws.send_json({"type": "final", "segment_id": "1", "text": "今天现场无异常"})
        await ws.send_json({"type": "done"})

    monkeypatch.setattr(speech, "relay_speech", relay)
    monkeypatch.setattr(speech, "authorize_speech", AsyncMock(side_effect=AssertionError("no task access")))
    with client.websocket_connect("/api/changwei/transcribe/chat") as ws:
        ws.send_json(START)
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(b"\0\0" * 160)
        ws.send_json({"type": "stop"})
        assert ws.receive_json() == {"type": "final", "segment_id": "1", "text": "今天现场无异常"}
        assert ws.receive_json() == {"type": "done"}
