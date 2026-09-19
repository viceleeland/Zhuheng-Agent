"""显式启用的真实 PostgreSQL 聊天草稿与成果事务回归。"""

import asyncio
import copy
import hashlib
import json
import os
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import pytest
from docx import Document
from fastapi import HTTPException
from sqlalchemy import delete, select

from yuxi.agents.toolkits.buildin.engineering import engineering_finalize
from yuxi.services.changwei_chat import EngineeringChatService
from yuxi.services.changwei_service import TASK_TYPES
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    ChangweiArtifact, ChangweiAudit, ChangweiMaterial, ChangweiProject, ChangweiTask, User,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_chat_concurrent_draft_and_finalization_transaction(monkeypatch, tmp_path):
    """真实行锁、回滚和成果字节证明聊天写入边界。"""
    uid = os.getenv('TEST_ENGINEERING_UID')
    if not uid:
        pytest.skip('配置 TEST_ENGINEERING_UID 才运行真实工程数据回归')
    project_id, material_id = str(uuid4()), str(uuid4())
    operation_id = f'pytest-engineering-{uuid4()}'
    captured = []

    async def capture_output(self, project_name, lot, period, artifact_id, filename, data):
        """只截取实际生成字节，避免向用户个人目录发布副本。"""
        captured.append((artifact_id, bytes(data)))
        output = tmp_path / uid / 'outputs'
        output.mkdir(parents=True, exist_ok=True)
        (output / filename).write_bytes(data)
        return f'/outputs/{filename}'

    monkeypatch.setattr(EngineeringChatService, '_publish_output_copy', capture_output)
    monkeypatch.setattr('yuxi.workspace.filesystem.user_workspace_dir', lambda user: tmp_path / user)
    (tmp_path / uid / 'projects' / 'chat-project').mkdir(parents=True)
    pg_manager.initialize()
    assert pg_manager.async_engine.dialect.name == 'postgresql'
    try:
        async with pg_manager.get_async_session_context() as db:
            assert await db.scalar(select(User.uid).where(User.uid == uid)) == uid
            db.add(ChangweiProject(id=project_id, name='pytest聊天事务验证', lot='隔离测试标段',
                                   owner_uid=uid, members={}))

        modules = {name: f'测试事实：{name}已现场核对' for name in TASK_TYPES['supervision_log']['modules']}
        args = dict(operation_id=operation_id, project_id=project_id, kind='supervision_log',
                    title='pytest监理日志', period='2026-09-20', modules=modules, material_ids=[])
        start = asyncio.Event()

        async def save_once():
            """各并发调用使用独立 PostgreSQL 会话。"""
            await start.wait()
            async with pg_manager.get_async_session_context() as db:
                return await EngineeringChatService(db, uid).save_draft(**args)

        jobs = [asyncio.create_task(save_once()) for _ in range(4)]
        start.set()
        results = await asyncio.gather(*jobs, return_exceptions=True)
        assert all(isinstance(result, dict) for result in results), results
        task_id = results[0]['task']['id']
        assert {result['task']['id'] for result in results} == {task_id}
        assert sum(bool(result.get('replayed')) for result in results) == 3
        async with pg_manager.get_async_session_context() as db:
            tasks = list(await db.scalars(select(ChangweiTask).where(ChangweiTask.project_id == project_id)))
            assert len(tasks) == 1
            task = tasks[0]
            assert task.status == 'draft' and task.revision == 1
            assert all(m['confirmed_by'] is None and m['confirmed_at'] is None for m in task.content['modules'])
            before = copy.deepcopy(task.content)
            audits = list(await db.scalars(select(ChangweiAudit).where(ChangweiAudit.project_id == project_id)))
            assert [a.action for a in audits] == ['问答保存草稿']

        with pytest.raises(HTTPException) as stale:
            async with pg_manager.get_async_session_context() as db:
                await EngineeringChatService(db, uid).save_draft(**args, task_id=task_id, revision=99)
        assert stale.value.status_code == 409

        invalid_template = BytesIO()
        document = Document()
        document.add_paragraph('这是普通文档，不是监理日志表格模板')
        document.save(invalid_template)
        async with pg_manager.get_async_session_context() as db:
            db.add(ChangweiMaterial(id=material_id, project_id=project_id, filename='错误模板.docx',
                                    category='template', parse_status='parsed', confirmed=True,
                                    content={'segments': []}, data=invalid_template.getvalue()))
        with pytest.raises(HTTPException) as bad_template:
            async with pg_manager.get_async_session_context() as db:
                await EngineeringChatService(db, uid).finalize(task_id, 1, material_id)
        assert bad_template.value.status_code == 422
        assert captured == []
        async with pg_manager.get_async_session_context() as db:
            task = await db.get(ChangweiTask, task_id)
            assert task.content == before and task.revision == 1 and task.status == 'draft'
            assert list(await db.scalars(select(ChangweiArtifact).where(ChangweiArtifact.task_id == task_id))) == []
            audits = list(await db.scalars(select(ChangweiAudit).where(ChangweiAudit.project_id == project_id)))
            assert [a.action for a in audits] == ['问答保存草稿']

        command = await engineering_finalize.coroutine(
            runtime=SimpleNamespace(context=SimpleNamespace(uid=uid, workdir_relative_path='projects/chat-project')),
            task_id=task_id, revision=1, tool_call_id='pg-test-finalize')
        result = json.loads(command.update['messages'][0].content)
        assert command.update['messages'][0].tool_call_id == 'pg-test-finalize'
        from yuxi.services.chat_service import extract_agent_state
        projected = extract_agent_state(command.update, workdir_path='/home/gem/user-data/projects/chat-project')
        assert projected['artifacts'] == [f"/home/gem/user-data/projects/chat-project{result['output_path']}"]
        async with pg_manager.get_async_session_context() as db:
            artifact = await db.get(ChangweiArtifact, result['id'])
            task = await db.get(ChangweiTask, task_id)
            assert artifact.task_id == task_id and artifact.revision == 2
            assert task.status == 'generated' and task.revision == 2
            assert all(m['confirmed_by'] == uid and m['confirmed_at'] for m in task.content['modules'])
            assert len(captured) == 1 and captured[0][0] == artifact.id
            assert hashlib.sha256(artifact.data).digest() == hashlib.sha256(captured[0][1]).digest()
            published = tmp_path / uid / 'projects' / 'chat-project' / result['output_path'].lstrip('/')
            assert published.read_bytes() == artifact.data
            with ZipFile(BytesIO(artifact.data)) as archive:
                assert archive.testzip() is None
                xml = archive.read('word/document.xml').decode('utf-8')
                assert 'pytest监理日志' in xml
                assert all(text in xml for text in modules.values())
            audits = list(await db.scalars(select(ChangweiAudit).where(ChangweiAudit.project_id == project_id)))
            assert sum(a.action == '问答审批确认整份任务' for a in audits) == 1
            assert sum(a.action == '生成成果' for a in audits) == 1
    finally:
        async with pg_manager.get_async_session_context() as db:
            task_ids = select(ChangweiTask.id).where(ChangweiTask.project_id == project_id)
            await db.execute(delete(ChangweiArtifact).where(ChangweiArtifact.task_id.in_(task_ids)))
            for model in (ChangweiAudit, ChangweiMaterial, ChangweiTask):
                await db.execute(delete(model).where(model.project_id == project_id))
            await db.execute(delete(ChangweiProject).where(ChangweiProject.id == project_id))
        async with pg_manager.get_async_session_context() as db:
            assert await db.get(ChangweiProject, project_id) is None
        await pg_manager.close()
