"""长委业务持久化与工程成员隔离。"""

from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, or_, text
from sqlalchemy.orm import defer
from yuxi.storage.postgres.models_business import (
    ChangweiProject, ChangweiTask, ChangweiMaterial, ChangweiArtifact, ChangweiAudit, User,
)


class ChangweiRepository:
    """在所有资源查询之前核对工程成员。"""

    def __init__(self, db, uid):
        self.db, self.uid = db, str(uid)

    async def projects(self):
        """只列当前成员所属工程。"""
        result = await self.db.scalars(select(ChangweiProject).where(or_(
            ChangweiProject.owner_uid == self.uid,
            ChangweiProject.members[self.uid].as_string().is_not(None),
        )).order_by(ChangweiProject.created_at.desc()))
        return list(result)

    async def project(self, project_id, manage=False, lock=False):
        """以同一权限边界保护工程中的全部业务对象。"""
        stmt = select(ChangweiProject).where(ChangweiProject.id == project_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        project = await self.db.scalar(stmt)
        if not project or (project.owner_uid != self.uid and self.uid not in project.members):
            raise HTTPException(404, '工程不存在或无权访问')
        if manage and project.owner_uid != self.uid:
            raise HTTPException(403, '仅工程负责人可操作')
        return project

    async def task(self, task_id, lock=False):
        """锁定任务后执行版本检查和状态写入。"""
        stmt = select(ChangweiTask).where(ChangweiTask.id == task_id)
        if lock:
            stmt = stmt.with_for_update()
        task = await self.db.scalar(stmt)
        if not task:
            raise HTTPException(404, '任务不存在')
        await self.project(task.project_id)
        return task

    async def tasks(self, project_id):
        """列出授权工程任务。"""
        await self.project(project_id)
        return list(await self.db.scalars(select(ChangweiTask).where(
            ChangweiTask.project_id == project_id).order_by(ChangweiTask.updated_at.desc())))

    async def chat_creation(self, task_id, lock_key):
        """串行化同次聊天工具的新建重试，并校验已有任务可见性。"""
        await self.db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_key})
        row = await self.db.get(ChangweiTask, task_id)
        if row:
            await self.project(row.project_id)
        return row

    async def materials(self, project_id):
        """列表不读取原件字节。"""
        await self.project(project_id)
        return list(await self.db.scalars(select(ChangweiMaterial).options(defer(ChangweiMaterial.data)).where(
            ChangweiMaterial.project_id == project_id).order_by(ChangweiMaterial.created_at.desc())))

    async def material(self, material_id, lock=False):
        """核验资料所属工程；回写时加锁并刷新缓存中的旧内容。"""
        stmt = select(ChangweiMaterial).where(ChangweiMaterial.id == material_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        item = await self.db.scalar(stmt)
        if not item:
            raise HTTPException(404, '资料不存在')
        await self.project(item.project_id)
        return item

    async def artifacts(self, task_id):
        """按任务读取成果元数据。"""
        await self.task(task_id)
        return list(await self.db.scalars(select(ChangweiArtifact).options(defer(ChangweiArtifact.data)).where(
            ChangweiArtifact.task_id == task_id).order_by(ChangweiArtifact.created_at.desc())))

    async def artifact(self, artifact_id):
        """下载前复核任务所属工程。"""
        item = await self.db.get(ChangweiArtifact, artifact_id)
        if not item:
            raise HTTPException(404, '成果不存在')
        await self.task(item.task_id)
        return item

    async def member_exists(self, uid):
        """成员必须对应已有 Yuxi 用户。"""
        return await self.db.scalar(select(User.uid).where(User.uid == uid)) is not None

    def audit(self, project_id, action, target_id, detail=None):
        """审计与业务修改由同一事务提交。"""
        self.db.add(ChangweiAudit(id=str(uuid4()), project_id=project_id, uid=self.uid,
                                 action=action, target_id=target_id, detail=detail or {}))

    async def audits(self, project_id):
        """返回最近的工程操作记录。"""
        await self.project(project_id)
        return list(await self.db.scalars(select(ChangweiAudit).where(
            ChangweiAudit.project_id == project_id).order_by(ChangweiAudit.created_at.desc()).limit(100)))
