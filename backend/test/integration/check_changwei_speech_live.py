"""Explicit local-instance probe. No upstream audio call and no business writes."""
import asyncio
import json
import os

import websockets
from sqlalchemy import select, func
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import ChangweiTask, ChangweiProject, ChangweiAudit, User
from yuxi.utils.auth_utils import AuthUtils


async def main():
    assert not os.getenv('DASHSCOPE_API_KEY'), 'This negative probe requires an unconfigured ASR instance'
    async with pg_manager.get_async_session_context() as db:
        owner = await db.scalar(select(User).where(User.uid == 'changwei_admin'))
        outsider = await db.scalar(select(User).where(User.uid.like('cwtest_%')))
        task = await db.scalar(select(ChangweiTask).where(ChangweiTask.creator_uid == owner.uid))
        project = await db.get(ChangweiProject, task.project_id)
        assert outsider and outsider.uid not in project.members
        module_id = task.content['modules'][0]['id']
        before = json.dumps([task.revision, task.status, task.content], sort_keys=True)
        audit_before = await db.scalar(select(func.count()).select_from(ChangweiAudit).where(ChangweiAudit.project_id == task.project_id))
        tokens = {name: AuthUtils.create_access_token({'sub': str(user.id)}) for name, user in [('owner', owner), ('outsider', outsider)]}
        task_id, project_id = task.id, project.id
    url = f'ws://127.0.0.1:5050/api/changwei/tasks/{task_id}/modules/{module_id}/transcribe'
    results = {}
    for name, token in [('anonymous', ''), ('cross_project', tokens['outsider']), ('unconfigured', tokens['owner'])]:
        async with websockets.connect(url, open_timeout=10) as ws:
            await ws.send(json.dumps({'type': 'start', 'token': token, 'audio': {
                'encoding': 'pcm_s16le', 'sample_rate': 16000, 'channels': 1}}))
            event = json.loads(await asyncio.wait_for(ws.recv(), 10))
            assert event['type'] == 'error'
            if name == 'anonymous':
                assert event['status'] == 401
            elif name == 'cross_project':
                assert event['status'] == 404
            else:
                assert '尚未配置' in event['message']
            results[name] = event
    async with pg_manager.get_async_session_context() as db:
        task = await db.get(ChangweiTask, task_id)
        assert json.dumps([task.revision, task.status, task.content], sort_keys=True) == before
        audit_after = await db.scalar(select(func.count()).select_from(ChangweiAudit).where(ChangweiAudit.project_id == project_id))
        assert audit_after == audit_before
    print(json.dumps({'result': 'passed', 'business_state_unchanged': True, 'checks': results,
                      'upstream_audio_verified': False}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
