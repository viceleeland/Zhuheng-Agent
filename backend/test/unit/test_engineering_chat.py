"""聊天工程工具的追问、草稿与权限边界。"""

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from langchain_core.tools import ToolException

from yuxi.agents.toolkits.buildin import engineering
from yuxi.services.changwei_chat import EngineeringChatService
from yuxi.services.changwei_service import TASK_TYPES
from yuxi.storage.postgres.models_business import ChangweiTask


@pytest.fixture
def service():
    """以真实业务对象和隔离仓储执行服务分支。"""
    db = SimpleNamespace(add=Mock(), commit=AsyncMock())
    svc = EngineeringChatService(db, 'member')
    svc.repo = SimpleNamespace(
        project=AsyncMock(return_value=SimpleNamespace(owner_uid='owner')),
        materials=AsyncMock(return_value=[]),
        task=AsyncMock(),
        chat_creation=AsyncMock(return_value=None),
        audit=Mock(),
    )
    return svc


def draft_args(**overrides):
    """提供最小有效日志输入，缺项由调用者覆盖。"""
    return dict(operation_id='thread:call', project_id='project', kind='supervision_log',
                title='施工记录', period='2026-09-20', modules={'施工部位及施工内容': '左岸基础开挖'},
                material_ids=[]) | overrides


def existing_task():
    """构造已确认的真实 ORM 任务对象以观察原地修改。"""
    return ChangweiTask(id='task', project_id='project', kind='supervision_log', title='施工记录',
                        period='2026-09-20', creator_uid='owner', status='confirmed', revision=3,
                        content={'material_ids': [], 'modules': [
                            {'id': str(i), 'name': name, 'text': '原始记录', 'assignee': 'member',
                             'confirmed_by': 'owner', 'confirmed_at': '2026-09-20', 'sources': []}
                            for i, name in enumerate(TASK_TYPES['supervision_log']['modules'])]})


def assert_no_write(service):
    """拒绝分支不新增、审计或提交。"""
    service.db.add.assert_not_called()
    service.db.commit.assert_not_awaited()
    service.repo.audit.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(('field', 'label'), [('project_id', '工程'), ('kind', '业务类型'),
                                              ('title', '任务名称'), ('period', '日期或报告期')])
async def test_missing_basic_field_asks_without_writing(service, field, label):
    """缺少基础定位信息时返回明确追问。"""
    result = await service.save_draft(**draft_args(**{field: '  '}))
    assert result == {'needs_input': [label], 'saved': False}
    assert_no_write(service)


@pytest.mark.asyncio
async def test_empty_facts_asks_without_writing(service):
    """空正文不能变成看似成功的任务。"""
    result = await service.save_draft(**draft_args(modules={'天气信息': ' '}))
    assert result == {'needs_input': ['现场记录或报告资料'], 'saved': False}
    assert_no_write(service)


@pytest.mark.asyncio
async def test_report_requires_confirmed_material(service):
    """月报必须追问实际资料，不能凭空建立报告。"""
    result = await service.save_draft(**draft_args(kind='supervision_report', modules={'工程进度': '完成开挖'}))
    assert result['saved'] is False
    assert result['needs_input'] == ['已上传并确认的审查或报告资料']
    assert_no_write(service)


@pytest.mark.asyncio
@pytest.mark.parametrize('confirmed', [False, None])
async def test_unconfirmed_or_foreign_material_rejected(service, confirmed):
    """不存在或未经人工确认的资料不能作为草稿依据。"""
    service.repo.materials.return_value = [] if confirmed is None else [SimpleNamespace(id='m', confirmed=False)]
    with pytest.raises(HTTPException) as error:
        await service.save_draft(**draft_args(material_ids=['m']))
    assert error.value.status_code == 422
    assert_no_write(service)


@pytest.mark.asyncio
async def test_new_draft_remains_unconfirmed_and_reports_missing_modules(service):
    """保存只形成草稿，缺项和确认状态保持可见。"""
    result = await service.save_draft(**draft_args())
    task = result['task']
    assert result['saved'] is True
    assert task['status'] == 'draft'
    assert task['revision'] == 1
    modules = task['content']['modules']
    assert all(m['confirmed_by'] is None and m['confirmed_at'] is None for m in modules)
    assert next(m['text'] for m in modules if m['name'] == '施工部位及施工内容') == '左岸基础开挖'
    assert '天气信息' in result['needs_input']
    service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['revision', 'assignee', 'materials', 'project'])
async def test_update_rejection_preserves_original_task(service, reason):
    """并发和权限拒绝不能损坏既有正文或确认状态。"""
    task = existing_task()
    args = draft_args(task_id='task', revision=3)
    expected = 403
    if reason == 'revision':
        args['revision'] = 2
        expected = 409
    elif reason == 'assignee':
        for module in task.content['modules']:
            module['assignee'] = 'other'
    elif reason == 'materials':
        service.repo.materials.return_value = [SimpleNamespace(id='m', confirmed=True, filename='记录.docx')]
        args['material_ids'] = ['m']
    else:
        task.project_id = 'other-project'
        expected = 422
    before = copy.deepcopy(task.content)
    service.repo.task.return_value = task
    with pytest.raises(HTTPException) as error:
        await service.save_draft(**args)
    assert error.value.status_code == expected
    assert task.content == before
    assert task.revision == 3
    assert task.status == 'confirmed'
    assert_no_write(service)


@pytest.mark.asyncio
async def test_edit_invalidates_only_edited_confirmation(service):
    """修改正文后须重新确认，其余模块原确认保留。"""
    task = existing_task()
    service.repo.task.return_value = task
    await service.save_draft(**draft_args(task_id='task', revision=3))
    edited = next(m for m in task.content['modules'] if m['name'] == '施工部位及施工内容')
    assert edited['text'] == '左岸基础开挖'
    assert edited['confirmed_by'] is None and edited['confirmed_at'] is None
    assert task.content['modules'][0]['confirmed_by'] == 'owner'
    assert task.status == 'draft' and task.revision == 4


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['permission', 'revision', 'blank'])
async def test_finalize_rejection_does_not_confirm_or_generate(service, reason):
    """负责人权限、审批版本和缺项都在成果副作用之前拒绝。"""
    task = existing_task()
    revision = 3
    if reason == 'permission':
        service.repo.project.side_effect = HTTPException(403, '仅负责人可操作')
        expected = 403
    elif reason == 'revision':
        revision = 2
        expected = 409
    else:
        task.content['modules'][0]['text'] = ' '
        expected = 422
    service.repo.task.return_value = task
    service.generate = AsyncMock()
    before = copy.deepcopy(task.content)
    with pytest.raises(HTTPException) as error:
        await service.finalize('task', revision)
    assert error.value.status_code == expected
    assert task.content == before and task.revision == 3
    service.repo.project.assert_awaited_once_with('project', manage=True)
    service.generate.assert_not_awaited()
    assert_no_write(service)


@pytest.mark.asyncio
@pytest.mark.parametrize('context', [SimpleNamespace(uid=None), SimpleNamespace(uid='member', is_subagent_runtime=True)])
@pytest.mark.parametrize('tool_name', ['engineering_read', 'engineering_save_draft', 'engineering_finalize'])
async def test_tools_reject_missing_identity_and_subagents(context, tool_name):
    """身份拒绝发生在任何数据库会话创建前。"""
    target = getattr(engineering, tool_name)
    kwargs = {'engineering_read': {'action': 'projects'}, 'engineering_save_draft': {'tool_call_id': 'call'},
              'engineering_finalize': {'task_id': 'task', 'revision': 3, 'tool_call_id': 'call'}}[tool_name]
    with pytest.raises(ToolException, match='已登录的主助手'):
        await target.coroutine(runtime=SimpleNamespace(context=context), **kwargs)


@pytest.mark.parametrize('target', [engineering.engineering_read, engineering.engineering_save_draft,
                                     engineering.engineering_finalize])
def test_model_schema_hides_identity_and_runtime(target):
    """模型不能填写认证身份、运行上下文或可信工具调用标识。"""
    schema = target.tool_call_schema.model_json_schema()
    assert not {'uid', 'runtime', 'tool_call_id', 'thread_id'} & set(schema['properties'])


@pytest.mark.asyncio
async def test_save_requires_trusted_thread_identity():
    """没有持久会话标识时不能建立不稳定幂等键。"""
    with pytest.raises(ToolException, match='可信会话标识'):
        await engineering.engineering_save_draft.coroutine(
            runtime=SimpleNamespace(context=SimpleNamespace(uid='member')), tool_call_id='call')


@pytest.mark.parametrize(('target', 'expected_fields'), [
    (engineering.engineering_read, {'action', 'project_id', 'task_id', 'location', 'material_id', 'start'}),
    (engineering.engineering_save_draft,
     {'project_id', 'kind', 'title', 'period', 'modules', 'material_ids', 'task_id', 'revision'}),
    (engineering.engineering_finalize, {'task_id', 'revision', 'template_id'}),
])
def test_manifest_metadata_and_raw_schema_are_json_serializable(target, expected_fields):
    """真实元数据路径不能因隐藏的 ToolRuntime Callable 导致 worker 启动失败。"""
    import json

    from yuxi.agents.toolkits import service as toolkit_service
    from yuxi.agents.toolkits.utils import get_tool_info

    schema = json.loads(json.dumps(target.args_schema.schema()))
    assert set(schema['properties']) == expected_fields
    metadata = json.loads(json.dumps(toolkit_service._extract_tool_info(target)))
    assert metadata['slug'] == target.name
    assert {arg['name'] for arg in metadata['args']} == expected_fields
    manifest = json.loads(json.dumps(get_tool_info([target])))
    assert len(manifest) == 1
    assert manifest[0]['id'] == target.name
    assert {arg['name'] for arg in manifest[0]['args']} == expected_fields


@pytest.mark.asyncio
async def test_omitted_materials_preserve_sources_and_other_confirmations(service):
    """仅改本人正文时不省略原资料，也不失效其他模块确认。"""
    task = existing_task()
    task.content['material_ids'] = ['m']
    for module in task.content['modules']:
        module['sources'] = ['现场记录.docx']
    before = copy.deepcopy(task.content)
    service.repo.task.return_value = task
    service.repo.materials.return_value = [SimpleNamespace(id='m', confirmed=True, filename='现场记录.docx')]
    result = await service.save_draft(**draft_args(task_id='task', revision=3, material_ids=None))
    assert result['saved'] is True
    assert task.content['material_ids'] == ['m']
    for original, updated in zip(before['modules'], task.content['modules'], strict=True):
        assert updated['sources'] == ['现场记录.docx']
        if updated['name'] != '施工部位及施工内容':
            assert updated == original
        else:
            assert updated['confirmed_by'] is None and updated['confirmed_at'] is None
    assert task.revision == 4


@pytest.mark.asyncio
@pytest.mark.parametrize('is_owner', [True, False])
async def test_explicit_material_clear_requires_owner(service, is_owner):
    """显式清空资料只允许负责人执行，并失效整份任务确认。"""
    task = existing_task()
    task.content['material_ids'] = ['m']
    before = copy.deepcopy(task.content)
    service.repo.task.return_value = task
    service.repo.materials.return_value = [SimpleNamespace(id='m', confirmed=True, filename='现场记录.docx')]
    if is_owner:
        service.repo.project.return_value.owner_uid = service.uid
        result = await service.save_draft(**draft_args(task_id='task', revision=3, material_ids=[]))
        assert result['saved'] is True and task.content['material_ids'] == []
        assert all(m['confirmed_by'] is None and m['confirmed_at'] is None for m in task.content['modules'])
        assert task.revision == 4
    else:
        with pytest.raises(HTTPException) as error:
            await service.save_draft(**draft_args(task_id='task', revision=3, material_ids=[]))
        assert error.value.status_code == 403
        assert task.content == before and task.revision == 3
        assert_no_write(service)


@pytest.mark.asyncio
async def test_task_rename_is_rejected_without_writes(service):
    """正文工具不能静默忽略用户请求的新标题。"""
    task = existing_task()
    before = copy.deepcopy(task.content)
    service.repo.task.return_value = task
    with pytest.raises(HTTPException) as error:
        await service.save_draft(**draft_args(task_id='task', revision=3, title='新标题'))
    assert error.value.status_code == 422
    assert '不支持修改任务名称' in error.value.detail
    assert task.title == '施工记录' and task.revision == 3 and task.content == before
    assert_no_write(service)


@pytest.mark.asyncio
@pytest.mark.parametrize('file_state', ['file', 'missing', 'directory', 'symlink', 'outside', 'unpublished', 'no_workdir', 'write_failed'])
async def test_finalize_exposes_only_verified_current_user_artifacts(monkeypatch, tmp_path, file_state):
    """复用artifact状态协议，提交后缺失副本不虚构下载卡片。"""
    import json
    from contextlib import asynccontextmanager

    from langgraph.types import Command

    result = {'id': 'artifact', 'task_id': 'task', 'revision': 4, 'filename': '监理日志.docx',
              'output_path': '/outputs/江擎/项目/日志.docx', 'output_warning': None}
    if file_state == 'outside':
        result['output_path'] = '/../other-user/secret.docx'
    if file_state == 'unpublished':
        result['output_path'] = None
        result['output_warning'] = '成果版本已生成，但个人空间副本暂未写入'
    finalize = AsyncMock(return_value=result)
    monkeypatch.setattr(EngineeringChatService, 'finalize', finalize)

    @asynccontextmanager
    async def session():
        """这里只替代会话，保留真实工具消息和路径映射。"""
        yield object()

    monkeypatch.setattr(engineering.pg_manager, 'get_async_session_context', session)
    root = tmp_path / 'member'
    (root / 'projects' / 'chat-project').mkdir(parents=True)
    archive = root / 'outputs' / '江擎' / '项目' / '日志.docx'
    archive.parent.mkdir(parents=True)
    if file_state in {'file', 'no_workdir', 'write_failed'}:
        archive.write_bytes(b'original-archived-docx')
    if file_state == 'directory':
        archive.mkdir()
    if file_state == 'symlink':
        secret = tmp_path / 'secret.docx'
        secret.write_bytes(b'private')
        archive.symlink_to(secret)
    monkeypatch.setattr('yuxi.workspace.filesystem.user_workspace_dir', lambda uid: tmp_path / uid)
    if file_state == 'write_failed':
        monkeypatch.setattr(engineering.Workspace, 'replace_authorized_file', Mock(side_effect=OSError('disk full')))
    command = await engineering.engineering_finalize.coroutine(
        runtime=SimpleNamespace(context=SimpleNamespace(uid='member', workdir_relative_path=(
            None if file_state == 'no_workdir' else 'projects/chat-project'))),
        task_id='task', revision=3, tool_call_id='trusted-call')

    assert isinstance(command, Command)
    message = command.update['messages'][0]
    assert message.tool_call_id == 'trusted-call'
    payload = json.loads(message.content)
    assert payload['artifact_paths'] == command.update['artifacts']
    assert payload['id'] == 'artifact' and payload['revision'] == 4
    finalize.assert_awaited_once_with('task', 3, None)
    if file_state == 'file':
        from yuxi.services.chat_service import extract_agent_state
        from yuxi.agents.backends.paths import workspace_scope_from_runtime_path
        projected = extract_agent_state(command.update, workdir_path='/home/gem/user-data/projects/chat-project')
        expected = '/home/gem/user-data/projects/chat-project/outputs/日志.docx'
        assert projected['artifacts'] == [expected]
        assert (root / workspace_scope_from_runtime_path(expected).lstrip('/')).read_bytes() == archive.read_bytes()
        assert payload['output_path'] == '/outputs/江擎/项目/日志.docx'
        assert payload['output_warning'] is None
    else:
        assert command.update['artifacts'] == []
        assert payload['output_warning']
    if file_state in {'no_workdir', 'write_failed'}:
        assert archive.read_bytes() == b'original-archived-docx'


@pytest.mark.asyncio
async def test_material_pagination_preserves_all_text_beyond_preview(service):
    """关键养护内容位于第二窗口仍能完整连续读取。"""
    text = '甲' * 12010 + '连续养护不少于28天' + '乙' * 20
    service.repo.material = AsyncMock(return_value=SimpleNamespace(
        id='m', filename='方案.md', confirmed=True,
        content={'segments': [{'location': '物理31页', 'text': text}]}))
    first = await service.read('material', material_id='m')
    second = await service.read('material', material_id='m', start=first['next_start'])
    assert len(first['text']) == 12000 and first['next_start'] == 12000
    assert '连续养护不少于28天' not in first['text']
    assert '连续养护不少于28天' in second['text']
    assert first['text'] + second['text'] == '[物理31页]\n' + text
    assert second['next_start'] is None
    assert second['total_chars'] == len('[物理31页]\n' + text)
    assert_no_write(service)


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['foreign', 'unconfirmed'])
async def test_material_read_rejects_unauthorized_and_unconfirmed(service, reason):
    """拒绝访问不能通过资料正文分页绕过。"""
    service.repo.material = AsyncMock(return_value=SimpleNamespace(confirmed=False))
    if reason == 'foreign':
        service.repo.material.side_effect = HTTPException(404, '工程不存在或无权访问')
    with pytest.raises(HTTPException) as error:
        await service.read('material', material_id='m')
    assert error.value.status_code == (404 if reason == 'foreign' else 422)
    assert_no_write(service)


def test_material_negative_offset_rejected_by_model_schema():
    """负数游标在工具输入边界拒绝。"""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        engineering.EngineeringReadInput(action='material', material_id='m', start=-1)


@pytest.mark.asyncio
async def test_finalize_toolnode_injects_identity_and_emits_real_file(monkeypatch, tmp_path):
    """真实ToolNode执行工具并把已存在普通文件登记到图状态。"""
    from contextlib import asynccontextmanager
    from dataclasses import dataclass

    from langchain_core.messages import AIMessage
    from langgraph.graph import END, START, StateGraph
    from langgraph.prebuilt import ToolNode

    from yuxi.agents.state import BaseState
    from yuxi.agents.toolkits.registry import get_extra_metadata

    @dataclass
    class Context:
        """最小可信主助手上下文。"""
        uid: str = 'member'
        workdir_relative_path: str = 'projects/chat-project'

    workspace_root = tmp_path / 'member'
    (workspace_root / 'projects' / 'chat-project').mkdir(parents=True)
    output_dir = workspace_root / 'outputs'
    output_dir.mkdir(parents=True)
    (output_dir / 'result.docx').write_bytes(b'verified-output')
    monkeypatch.setattr('yuxi.workspace.filesystem.user_workspace_dir', lambda uid: tmp_path / uid)
    monkeypatch.setattr(EngineeringChatService, 'finalize', AsyncMock(return_value={
        'id': 'artifact', 'revision': 4, 'output_path': '/outputs/result.docx', 'output_warning': None}))

    @asynccontextmanager
    async def session():
        """数据库事务已由独立真实PG用例证明，此处核验图协议。"""
        yield object()

    monkeypatch.setattr(engineering.pg_manager, 'get_async_session_context', session)
    builder = StateGraph(BaseState, context_schema=Context)
    builder.add_node('tools', ToolNode([engineering.engineering_finalize]))
    builder.add_edge(START, 'tools')
    builder.add_edge('tools', END)
    graph = builder.compile()
    result = await graph.ainvoke({'messages': [AIMessage(content='', tool_calls=[{
        'name': 'engineering_finalize', 'args': {'task_id': 'task', 'revision': 3},
        'id': 'call-from-graph', 'type': 'tool_call'}])]}, context=Context())
    assert result['artifacts'] == ['/home/gem/user-data/projects/chat-project/outputs/result.docx']
    assert result['messages'][-1].tool_call_id == 'call-from-graph'
    assert 'artifact' in result['messages'][-1].content
    assert get_extra_metadata('engineering_finalize').requires_workspace_runtime is False
