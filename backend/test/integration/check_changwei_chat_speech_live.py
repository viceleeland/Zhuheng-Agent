"""显式本地探针：仅测公开聊天转录认证，不发送音频或消费上游。"""

import asyncio
import json

import websockets


async def main():
    """真实运行服务必须拒绝匿名和无效凭据。"""
    checks = {}
    for label, token in [("anonymous", ""), ("invalid", "invalid-test-token")]:
        async with websockets.connect("ws://127.0.0.1:5050/api/changwei/transcribe/chat") as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "start",
                        "token": token,
                        "audio": {"encoding": "pcm_s16le", "sample_rate": 16000, "channels": 1},
                    }
                )
            )
            response = json.loads(await asyncio.wait_for(ws.recv(), 10))
            assert response["type"] == "error" and response["status"] == 401, response
            checks[label] = response["status"]
    print(json.dumps({"checks": checks, "audio_sent": False}))


if __name__ == "__main__":
    asyncio.run(main())
