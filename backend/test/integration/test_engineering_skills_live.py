"""可选真实模型探针：HTTP 生成后回读 PostgreSQL，清理专属验收工程。"""

import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from yuxi.services.changwei_service import TASK_TYPES
from yuxi.services.changwei_skills import load_engineering_skill
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    ChangweiAudit, ChangweiMaterial, ChangweiProject, ChangweiTask, Skill, User,
)
from yuxi.utils.auth_utils import AuthUtils


async def test_five_skills_live_http_and_persisted_provenance():
    """五类草稿、来源审计、未确认生成拒绝和内置注册均经真实服务核对。"""
    uid = os.getenv("TEST_ENGINEERING_UID")
    model = os.getenv("TEST_ENGINEERING_MODEL")
    if not uid or not model:
        pytest.skip("需显式配置验收用户与真实模型，运行会产生模型调用费用")
    async with pg_manager.get_async_session_context() as db:
        user = await db.scalar(select(User).where(User.uid == uid))
        assert user is not None
        token = AuthUtils.create_access_token({"sub": str(user.id)})
    pid = None
    base = os.getenv("TEST_BASE_URL", "http://127.0.0.1:5050")
    async with httpx.AsyncClient(base_url=base, headers={"Authorization": "Bearer " + token}, timeout=150) as client:
        async def request(method, path, **kwargs):
            """经真实 HTTP 调用业务入口并检查返回。"""
            response = await client.request(method, "/api/changwei" + path, **kwargs)
            response.raise_for_status()
            return response.json()

        try:
            project = await request("POST", "/projects", json={"name": "pytest-skills-" + uuid4().hex, "lot": "测试"})
            pid = project["id"]
            facts = "2026-09-20，右岸引水渠K1+250至K1+300，施工人员12人，开展混凝土浇筑。未提供验收结果及规范原文。"
            materials = await request("POST", f"/projects/{pid}/materials", files={"file": ("记录.txt", facts.encode(), "text/plain")})
            material = materials[0]
            await request("PUT", f"/materials/{material['id']}", json={"category": "其他资料"})
            for kind in TASK_TYPES:
                task = await request("POST", f"/projects/{pid}/tasks", json={"kind": kind, "title": "技能验收", "period": "2026-09-20"})
                tid = task["id"]
                task = await request("PUT", f"/tasks/{tid}/materials", json={"revision": task["revision"], "material_ids": [material["id"]]})
                mid = task["content"]["modules"][1]["id"]
                task = await request("PUT", f"/tasks/{tid}/modules/{mid}", json={"revision": task["revision"], "text": facts, "confirm": False})
                result = await request("POST", f"/tasks/{tid}/modules/{mid}/draft", json={"model_spec": model, "instruction": "按本模块规则简短整理，保留与模块相关的原始事实，缺少依据标待核验。"})
                _, provenance = load_engineering_skill(kind)
                assert result["skill"] == provenance
                assert isinstance(result["text"], str) and result["text"].strip()
                async with pg_manager.get_async_session_context() as db:
                    stored = await db.get(ChangweiTask, tid)
                    module = next(m for m in stored.content["modules"] if m["id"] == mid)
                    assert module["text"] == result["text"]
                    assert module["generation_skill"] == provenance
                    assert module["confirmed_by"] is None and stored.status == "draft"
                    assert stored.revision == task["revision"] + 1
                    audit = await db.scalar(select(ChangweiAudit).where(ChangweiAudit.target_id == tid, ChangweiAudit.action == "AI 生成草稿"))
                    assert audit.detail["skill"] == provenance
                    registered = await db.scalar(select(Skill).where(Skill.slug == provenance["slug"]))
                    assert registered and registered.enabled and registered.source_type == "builtin"
                blocked = await client.post(f"/api/changwei/tasks/{tid}/generate", json={"revision": result["task"]["revision"]})
                assert blocked.status_code == 422
        finally:
            if pid:
                async with pg_manager.get_async_session_context() as db:
                    for cls in (ChangweiAudit, ChangweiTask, ChangweiMaterial):
                        await db.execute(delete(cls).where(cls.project_id == pid))
                    await db.execute(delete(ChangweiProject).where(ChangweiProject.id == pid))
                    await db.commit()
