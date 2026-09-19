"""实时音频中转与上游事件映射，不保存录音或自动确认日志。"""

import asyncio
import base64
import json
import os
from contextlib import suppress
from uuid import uuid4

import aiohttp
from fastapi import HTTPException, WebSocketDisconnect


async def authorize_speech(repo, uid, task_id, module_id):
    """按任务可见性和模块负责人限制语音调用。"""
    task = await repo.task(task_id)
    project = await repo.project(task.project_id)
    module = next((m for m in task.content["modules"] if m["id"] == module_id), None)
    if module is None:
        raise HTTPException(404, "模块不存在")
    if str(project.owner_uid) != str(uid) and str(module["assignee"]) != str(uid):
        raise HTTPException(403, "只能为本人负责的模块进行实时转录")


def map_speech_event(event):
    """预览替换当前句，最终结果按上游句子标识归并。"""
    if not isinstance(event, dict):
        raise ValueError("invalid upstream event")
    kind = event.get("type")
    if kind == "session.updated":
        return {"type": "ready"}
    if kind == "conversation.item.input_audio_transcription.text":
        return {
            "type": "partial",
            "segment_id": event["item_id"],
            "text": event.get("text", "") + event.get("stash", ""),
        }
    if kind == "conversation.item.input_audio_transcription.completed":
        return {"type": "final", "segment_id": event["item_id"], "text": event["transcript"]}
    if kind == "session.finished":
        return {"type": "done"}
    if kind in ("error", "conversation.item.input_audio_transcription.failed"):
        # 不透传上游错误：其中可能包含请求头、账号或音频片段。
        return {"type": "error", "message": "语音服务识别失败，请检查服务额度或稍后重试"}
    return None


async def relay_speech(client):
    """把有限时长的 PCM 实时流转发到百炼，并可靠结束尾句。"""
    key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not key:
        await client.send_json({"type": "error", "message": "实时转录尚未配置百炼 API Key，请联系管理员"})
        return
    url = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model=qwen3-asr-flash-realtime"
    workers = []
    ready = asyncio.Event()
    stopped = asyncio.Event()

    async def send_event(upstream, kind, **fields):
        """为每个上游客户端事件附加独立标识。"""
        await upstream.send_json({"event_id": uuid4().hex, "type": kind, **fields})

    async def receive_audio(upstream):
        """限制帧尺寸和累计音频，停止后继续等待识别尾句。"""
        count = 0
        while True:
            packet = await asyncio.wait_for(client.receive(), timeout=30)
            if packet["type"] == "websocket.disconnect":
                return
            audio = packet.get("bytes")
            if audio is not None:
                if stopped.is_set() or not ready.is_set() or not 0 < len(audio) <= 32000 or len(audio) % 2:
                    raise ValueError("invalid audio frame")
                count += len(audio)
                if count > 16000 * 2 * 300:
                    raise ValueError("audio duration limit")
                await send_event(upstream, "input_audio_buffer.append", audio=base64.b64encode(audio).decode("ascii"))
                continue
            raw = packet.get("text", "")
            if len(raw) > 1024:
                raise ValueError("oversized command")
            command = json.loads(raw)
            if not isinstance(command, dict):
                raise ValueError("invalid command")
            if command.get("type") == "cancel":
                return
            if command.get("type") != "stop":
                raise ValueError("unknown command")
            if stopped.is_set():
                continue
            await send_event(upstream, "session.finish")
            stopped.set()
            # 保持接收，以便停止后的取消/断线能及时回收上游连接。

    async def receive_text(upstream):
        """只投影协议允许的文本事件，实时结果不进入数据库。"""
        async for message in upstream:
            if message.type != aiohttp.WSMsgType.TEXT:
                raise ValueError("upstream closed")
            event = map_speech_event(json.loads(message.data))
            if event is None:
                continue
            if event["type"] == "ready":
                ready.set()
            await client.send_json(event)
            if event["type"] in ("done", "error"):
                return
        raise ValueError("upstream ended without completion")

    async def watch_deadlines():
        """上游初始化及用户停止后的尾句等待均有明确期限。"""
        await asyncio.wait_for(ready.wait(), 10)
        await stopped.wait()
        await asyncio.sleep(10)
        raise TimeoutError("final transcript timeout")

    try:
        timeout = aiohttp.ClientTimeout(total=None, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(
                url, headers={"Authorization": f"Bearer {key}"}, heartbeat=20, max_msg_size=1024 * 1024
            ) as upstream:
                await send_event(
                    upstream,
                    "session.update",
                    session={
                        "input_audio_format": "pcm",
                        "sample_rate": 16000,
                        "input_audio_transcription": {"language": "zh"},
                        "turn_detection": {"type": "server_vad", "threshold": 0.0, "silence_duration_ms": 600},
                    },
                )
                workers = [
                    asyncio.create_task(receive_audio(upstream)),
                    asyncio.create_task(receive_text(upstream)),
                    asyncio.create_task(watch_deadlines()),
                ]
                done, _ = await asyncio.wait(workers, timeout=310, return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    raise TimeoutError("session duration limit")
                for worker in done:
                    worker.result()
    except WebSocketDisconnect:
        pass
    except (aiohttp.ClientError, TimeoutError, ValueError, KeyError, TypeError):
        with suppress(WebSocketDisconnect, RuntimeError):
            await client.send_json(
                {"type": "error", "message": "实时转录连接中断或音频无效；已完成的文字可保留，请重试"}
            )
    finally:
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
