"""Realtime relay tests use a fake upstream; these do not prove cloud ASR availability."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest
from fastapi import HTTPException

from yuxi.services import changwei_speech as speech


class Client:
    def __init__(self):
        self.inbox = asyncio.Queue()
        self.events = []
        self.ready = asyncio.Event()

    async def receive(self):
        return await self.inbox.get()

    async def send_json(self, event):
        self.events.append(event)
        if event['type'] == 'ready':
            self.ready.set()

    def command(self, kind):
        self.inbox.put_nowait({'type': 'websocket.receive', 'text': json.dumps({'type': kind})})


class Upstream:
    def __init__(self, initialize=True, finish=True):
        self.queue = asyncio.Queue()
        self.sent = []
        self.initialize = initialize
        self.finish = finish
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    def emit(self, kind, **kwargs):
        self.queue.put_nowait(SimpleNamespace(type=aiohttp.WSMsgType.TEXT,
                                             data=json.dumps({'type': kind, **kwargs})))

    async def send_json(self, event):
        self.sent.append(event)
        if event['type'] == 'session.update' and self.initialize:
            self.emit('session.updated')
        if event['type'] == 'session.finish' and self.finish:
            self.emit('conversation.item.input_audio_transcription.completed', item_id='last', transcript='尾句')
            self.emit('session.finished')

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.queue.get()


class Session:
    def __init__(self, upstream):
        self.upstream = upstream

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def ws_connect(self, *args, **kwargs):
        return self.upstream


def setup(monkeypatch, **kwargs):
    client, upstream = Client(), Upstream(**kwargs)
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'test-secret-never-forwarded')
    monkeypatch.setattr(speech.aiohttp, 'ClientSession', lambda **kw: Session(upstream))
    return client, upstream


def test_maps_partial_final_done_and_redacts_errors():
    assert speech.map_speech_event({'type': 'conversation.item.input_audio_transcription.text',
        'item_id': 'a', 'text': '已确定', 'stash': '待定'}) == {
        'type': 'partial', 'segment_id': 'a', 'text': '已确定待定'}
    assert speech.map_speech_event({'type': 'conversation.item.input_audio_transcription.completed',
        'item_id': 'a', 'transcript': '最终'})['text'] == '最终'
    assert speech.map_speech_event({'type': 'session.finished'}) == {'type': 'done'}
    assert 'secret' not in str(speech.map_speech_event({'type': 'error', 'error': 'secret'}))
    with pytest.raises(ValueError):
        speech.map_speech_event([])


@pytest.mark.asyncio
async def test_missing_key_never_connects(monkeypatch):
    monkeypatch.delenv('DASHSCOPE_API_KEY', raising=False)
    monkeypatch.setattr(speech.aiohttp, 'ClientSession', lambda **kw: pytest.fail('must not connect'))
    client = Client()
    await speech.relay_speech(client)
    assert client.events[0]['type'] == 'error'
    assert '尚未配置' in client.events[0]['message']


@pytest.mark.asyncio
async def test_stop_keeps_last_sentence_until_done(monkeypatch):
    client, upstream = setup(monkeypatch)
    task = asyncio.create_task(speech.relay_speech(client))
    await asyncio.wait_for(client.ready.wait(), 1)
    client.inbox.put_nowait({'type': 'websocket.receive', 'bytes': b'\0\0' * 160})
    client.command('stop')
    await asyncio.wait_for(task, 1)
    assert [e['type'] for e in client.events] == ['ready', 'final', 'done']
    assert client.events[1]['text'] == '尾句'
    assert [e['type'] for e in upstream.sent] == ['session.update', 'input_audio_buffer.append', 'session.finish']
    assert len({e['event_id'] for e in upstream.sent}) == 3
    assert upstream.closed


@pytest.mark.asyncio
@pytest.mark.parametrize('packet', [{'type': 'websocket.disconnect'},
                                   {'type': 'websocket.receive', 'text': '{"type":"cancel"}'}])
async def test_disconnect_or_cancel_after_stop_releases_immediately(monkeypatch, packet):
    client, upstream = setup(monkeypatch, finish=False)
    task = asyncio.create_task(speech.relay_speech(client))
    await asyncio.wait_for(client.ready.wait(), 1)
    client.command('stop')
    client.inbox.put_nowait(packet)
    await asyncio.wait_for(task, 1)
    assert upstream.closed
    assert not any(e['type'] == 'done' for e in client.events)


@pytest.mark.asyncio
@pytest.mark.parametrize('packet', [
    {'bytes': b'x'}, {'bytes': b''}, {'bytes': b'x' * 32002},
    {'text': '[]'}, {'text': '{'}, {'text': 'x' * 1025}, {'text': '{"type":"bogus"}'},
])
async def test_invalid_input_fails_closed(monkeypatch, packet):
    client, upstream = setup(monkeypatch)
    task = asyncio.create_task(speech.relay_speech(client))
    await asyncio.wait_for(client.ready.wait(), 1)
    client.inbox.put_nowait({'type': 'websocket.receive', **packet})
    await asyncio.wait_for(task, 1)
    assert client.events[-1]['type'] == 'error'
    assert upstream.closed
    assert all(e['type'] != 'input_audio_buffer.append' for e in upstream.sent)


@pytest.mark.asyncio
async def test_tail_timeout_is_explicit(monkeypatch):
    client, upstream = setup(monkeypatch, finish=False)
    real_sleep = asyncio.sleep
    monkeypatch.setattr(speech.asyncio, 'sleep', lambda delay: real_sleep(0))
    task = asyncio.create_task(speech.relay_speech(client))
    await asyncio.wait_for(client.ready.wait(), 1)
    client.command('stop')
    await asyncio.wait_for(task, 1)
    assert client.events[-1]['type'] == 'error'
    assert upstream.closed


@pytest.mark.asyncio
async def test_upstream_initialization_timeout(monkeypatch):
    client, upstream = setup(monkeypatch, initialize=False)
    real_wait_for = asyncio.wait_for
    monkeypatch.setattr(speech.asyncio, 'wait_for', lambda future, timeout: real_wait_for(future, .01 if timeout == 10 else timeout))
    await real_wait_for(speech.relay_speech(client), 1)
    assert client.events[-1]['type'] == 'error'
    assert upstream.closed


@pytest.mark.asyncio
async def test_upstream_disconnect_fails_without_fake_done(monkeypatch):
    client, upstream = setup(monkeypatch)
    task = asyncio.create_task(speech.relay_speech(client))
    await asyncio.wait_for(client.ready.wait(), 1)
    upstream.queue.put_nowait(SimpleNamespace(type=aiohttp.WSMsgType.CLOSED))
    await asyncio.wait_for(task, 1)
    assert client.events[-1]['type'] == 'error'
    assert not any(e['type'] == 'done' for e in client.events)
    assert upstream.closed


@pytest.mark.asyncio
async def test_audio_before_ready_is_rejected(monkeypatch):
    client, upstream = setup(monkeypatch, initialize=False)
    client.inbox.put_nowait({'type': 'websocket.receive', 'bytes': b'\0\0'})
    await asyncio.wait_for(speech.relay_speech(client), 1)
    assert client.events[-1]['type'] == 'error'
    assert [e['type'] for e in upstream.sent] == ['session.update']


@pytest.mark.asyncio
async def test_repeated_stop_sends_only_one_finish(monkeypatch):
    client, upstream = setup(monkeypatch, finish=False)
    task = asyncio.create_task(speech.relay_speech(client))
    await asyncio.wait_for(client.ready.wait(), 1)
    client.command('stop')
    client.command('stop')
    client.command('cancel')
    await asyncio.wait_for(task, 1)
    assert sum(e['type'] == 'session.finish' for e in upstream.sent) == 1


@pytest.mark.asyncio
async def test_authorization_uses_repository_project_boundary():
    repo = SimpleNamespace(task=AsyncMock(side_effect=HTTPException(404)), project=AsyncMock())
    with pytest.raises(HTTPException) as exc:
        await speech.authorize_speech(repo, 'u', 'foreign', 'm')
    assert exc.value.status_code == 404
    repo.project.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('uid,module,code', [('u', 'm', 403), ('owner', 'missing', 404)])
async def test_module_owner_or_assignee_required(uid, module, code):
    repo = SimpleNamespace(task=AsyncMock(return_value=SimpleNamespace(project_id='p', content={
        'modules': [{'id': 'm', 'assignee': 'other'}]})),
        project=AsyncMock(return_value=SimpleNamespace(owner_uid='owner')))
    with pytest.raises(HTTPException) as exc:
        await speech.authorize_speech(repo, uid, 't', module)
    assert exc.value.status_code == code
