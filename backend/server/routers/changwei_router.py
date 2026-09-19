"""长委业务 HTTP 适配层。"""

from urllib.parse import quote
import asyncio
import json
from contextlib import suppress
from fastapi import WebSocket, WebSocketDisconnect
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from server.utils.auth_middleware import get_db, get_required_user
from yuxi.services.changwei_service import ChangweiService, TASK_TYPES, view
from yuxi.services.changwei_documents import CATEGORIES, MAX_FILE_BYTES

changwei = APIRouter(prefix='/changwei', tags=['changwei'])


def service(db=Depends(get_db), user=Depends(get_required_user)):
    """复用现有 Yuxi 登录和数据库依赖。"""
    return ChangweiService(db, user.uid)


class ProjectInput(BaseModel):
    """工程基本信息。"""
    name: str = Field(min_length=1, max_length=255, pattern=r'\S')
    lot: str = Field(min_length=1, max_length=100, pattern=r'\S')


class MemberInput(BaseModel):
    """已有账号的成员标识。"""
    uid: str = Field(min_length=1, max_length=64)


class TaskInput(BaseModel):
    """业务任务创建输入。"""
    kind: str
    title: str = Field(min_length=1, max_length=255, pattern=r'\S')
    period: str = Field(min_length=1, max_length=40, pattern=r'\S')


class ModuleInput(BaseModel):
    """单个模块更新的版本前提。"""
    revision: int = Field(ge=1)
    text: str = Field(max_length=50000)
    confirm: bool = False
    assignee: str | None = Field(default=None, max_length=64)


class CategoryInput(BaseModel):
    """人工确认的资料分类。"""
    category: str


class DraftInput(BaseModel):
    """指定中台模型和业务指令。"""
    model_spec: str = Field(min_length=1, max_length=255)
    instruction: str = Field(default='', max_length=2000)


class GenerateInput(BaseModel):
    """生成的预期业务版本。"""
    revision: int = Field(ge=1)
    template_id: str | None = Field(default=None, max_length=64)


@changwei.get('/catalog')
async def catalog(s=Depends(service)):
    """返回业务定义及当前模型目录。"""
    from yuxi.models.providers.cache import model_cache
    return {'types': TASK_TYPES, 'categories': CATEGORIES,
            'models': [{'spec': x.spec} for x in model_cache.get_all_specs('chat')]}


@changwei.get('/projects')
async def projects(s=Depends(service)):
    """读取当前账号可见工程。"""
    return [view(x) for x in await s.repo.projects()]


@changwei.post('/projects')
async def create_project(body: ProjectInput, s=Depends(service)):
    """建立独立工程。"""
    return await s.create_project(body.name, body.lot)


@changwei.post('/projects/{project_id}/members')
async def add_member(project_id: str, body: MemberInput, s=Depends(service)):
    """添加现有用户。"""
    return await s.add_member(project_id, body.uid)


@changwei.get('/projects/{project_id}/tasks')
async def tasks(project_id: str, s=Depends(service)):
    """读取任务列表。"""
    return [view(x) for x in await s.repo.tasks(project_id)]


@changwei.post('/projects/{project_id}/tasks')
async def create_task(project_id: str, body: TaskInput, s=Depends(service)):
    """建立业务任务。"""
    return await s.create_task(project_id, body.kind, body.title, body.period)


@changwei.get('/tasks/{task_id}')
async def task(task_id: str, s=Depends(service)):
    """读取完整任务和成果版本。"""
    return {'task': view(await s.repo.task(task_id)), 'artifacts': [view(x) for x in await s.repo.artifacts(task_id)]}


@changwei.put('/tasks/{task_id}/modules/{module_id}')
async def update_module(task_id: str, module_id: str, body: ModuleInput, s=Depends(service)):
    """保存或确认当前负责模块。"""
    return await s.update_module(task_id, module_id, **body.model_dump())


@changwei.post('/tasks/{task_id}/modules/{module_id}/draft')
async def draft(task_id: str, module_id: str, body: DraftInput, s=Depends(service)):
    """生成待人工核对的 AI 草稿。"""
    return await s.draft(task_id, module_id, **body.model_dump())


@changwei.post('/tasks/{task_id}/generate')
async def generate(task_id: str, body: GenerateInput, s=Depends(service)):
    """固化已确认成果。"""
    return await s.generate(task_id, body.revision, body.template_id)


@changwei.get('/projects/{project_id}/materials')
async def materials(project_id: str, s=Depends(service)):
    """读取解析结果和分类。"""
    return [view(x) for x in await s.repo.materials(project_id)]


@changwei.post('/projects/{project_id}/materials')
async def upload(project_id: str, file: UploadFile = File(...), s=Depends(service)):
    """限制上传大小并提交资料处理。"""
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, '单文件最大 30 MB')
    return await s.upload(project_id, file.filename or '资料', data)


@changwei.put('/materials/{material_id}')
async def confirm_material(material_id: str, body: CategoryInput, s=Depends(service)):
    """人工确认资料类型。"""
    return await s.confirm_material(material_id, body.category)


@changwei.get('/artifacts/{artifact_id}/download')
async def download(artifact_id: str, s=Depends(service)):
    """按工程权限下载不可变成果版本。"""
    row = await s.repo.artifact(artifact_id)
    task = await s.repo.task(row.task_id)
    s.repo.audit(task.project_id, '下载成果', row.id)
    await s.db.commit()
    return Response(row.data, media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(row.filename)}"})


@changwei.get('/projects/{project_id}/audit')
async def audit(project_id: str, s=Depends(service)):
    """读取工程操作记录。"""
    return [view(x) for x in await s.repo.audits(project_id)]


class TaskMaterialsInput(BaseModel):
    """报告期对应的资料范围。"""
    revision: int = Field(ge=1)
    material_ids: list[str] = Field(max_length=100)


@changwei.put('/tasks/{task_id}/materials')
async def select_task_materials(task_id: str, body: TaskMaterialsInput, s=Depends(service)):
    """选择本次任务的资料，防止混用其他报告期内容。"""
    return await s.select_materials(task_id, **body.model_dump())


@changwei.post('/materials/{material_id}/ocr')
async def ocr_material(material_id: str, s=Depends(service)):
    """按五页分批调用已有 OCR 组件。"""
    return await s.ocr_material(material_id)


class WeatherInput(BaseModel):
    """明确查询位置，不猜测工程所在地。"""
    location: str = Field(min_length=1, max_length=64)


@changwei.post('/tasks/{task_id}/weather')
async def task_weather(task_id: str, body: WeatherInput, s=Depends(service)):
    """获取当天实况供人工核对，不保存或确认日志。"""
    from yuxi.services.changwei_weather import get_task_weather
    return await get_task_weather(s.repo, s.uid, task_id, body.location)


@changwei.websocket('/tasks/{task_id}/modules/{module_id}/transcribe')
async def transcribe(websocket: WebSocket, task_id: str, module_id: str):
    """首帧复用登录认证，密钥不出现在 WebSocket URL 或前端。"""
    from server.utils.auth_middleware import get_current_user
    from yuxi.repositories.changwei_repository import ChangweiRepository
    from yuxi.services.changwei_speech import authorize_speech, relay_speech
    from yuxi.storage.postgres.manager import pg_manager

    await websocket.accept()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=5)
        if len(raw) > 8192:
            raise ValueError('oversized start')
        start = json.loads(raw)
        if not isinstance(start, dict) or start.get('type') != 'start':
            raise ValueError('invalid start')
        token = start.get('token')
        if not isinstance(token, str) or not token or len(token) > 4096:
            raise HTTPException(401, '请重新登录')
        if start.get('audio') != {'encoding': 'pcm_s16le', 'sample_rate': 16000, 'channels': 1}:
            raise ValueError('unsupported audio')
        async with pg_manager.get_async_session_context() as db:
            user = await get_required_user(await get_current_user(authorization=f'Bearer {token}', db=db))
            await authorize_speech(ChangweiRepository(db, user.uid), user.uid, task_id, module_id)
        await relay_speech(websocket)
    except HTTPException as exc:
        with suppress(WebSocketDisconnect, RuntimeError):
            await websocket.send_json({'type': 'error', 'message': '请重新登录或确认当前模块的填写权限', 'status': exc.status_code})
    except (ValueError, TypeError, KeyError, TimeoutError):
        with suppress(WebSocketDisconnect, RuntimeError):
            await websocket.send_json({'type': 'error', 'message': '实时转录初始化失败，请刷新后重试'})
    except WebSocketDisconnect:
        pass
    finally:
        with suppress(WebSocketDisconnect, RuntimeError):
            await websocket.close()
