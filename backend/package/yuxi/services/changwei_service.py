"""长委业务流程：数据归集、分工确认、模型草稿和成果快照。"""

import asyncio
import copy
import re
import zlib
from datetime import UTC, datetime
from uuid import uuid4
from zipfile import BadZipFile

from fastapi import HTTPException
from lxml.etree import XMLSyntaxError
from yuxi.repositories.changwei_repository import ChangweiRepository
from yuxi.services.changwei_documents import (
    CATEGORIES,
    classify,
    export_docx,
    normalize_station,
    ocr_pdf_pages,
    parse_document,
    unpack,
)
from yuxi.services.changwei_skills import load_engineering_skill
from yuxi.storage.postgres.models_business import ChangweiArtifact, ChangweiMaterial, ChangweiProject, ChangweiTask
from yuxi.workspace.filesystem import Workspace
from yuxi.workspace.paths import ensure_user_workspace

TASK_TYPES = {
    "supervision_log": {
        "name": "监理日志",
        "modules": [
            "天气信息",
            "施工部位及施工内容",
            "施工形象及资源投入",
            "承包人质量检验和安全作业",
            "监理检查巡视检验",
            "问题及处理落实",
            "监理签发意见",
            "其他事项",
        ],
    },
    "management_log": {
        "name": "项管日志",
        "modules": ["天气与水文", "工程进度", "工程质量", "安全环保", "征地组卷报批", "合同管理", "信息管理"],
    },
    "supervision_report": {
        "name": "监理月报",
        "modules": [
            "工程施工概况",
            "工程进度",
            "质量验收与评定",
            "检测与测量",
            "安全管理",
            "合同与支付",
            "监理工作",
            "下月工作计划",
        ],
    },
    "management_report": {
        "name": "项管月报",
        "modules": [
            "工程概况与组织",
            "人员设备配置",
            "安全管理",
            "技术质量管理",
            "形象进度",
            "合同支付与资金",
            "分包合同与变更",
            "档案与信息管理",
            "参建单位工作",
            "管理总结与下月计划",
        ],
    },
    "scheme_review": {
        "name": "施工方案审核",
        "modules": [
            "工程概况核对",
            "编制依据及有效性",
            "主要规范完整性",
            "施工进度匹配",
            "施工工艺与设计要求",
            "质量保证措施",
            "安全措施与应急预案",
            "审查意见汇总",
        ],
    },
}


def view(row):
    """投影业务对象，原件与成果字节不进入 JSON。"""
    result = {}
    for column in row.__table__.columns:
        if column.name == "data":
            continue
        value = getattr(row, column.name)
        result[column.name] = value.isoformat() if isinstance(value, datetime) else value
    return result


class ChangweiService:
    """业务事务和正式成果生成的唯一 Owner。"""

    def __init__(self, db, uid):
        self.db, self.uid = db, str(uid)
        self.repo = ChangweiRepository(db, uid)

    async def _publish_output_copy(self, project_name, project_lot, task_period, artifact_id, artifact_filename, data):
        """把成果副本写入当前负责人的个人空间 outputs，便于集中查找和预览。"""
        return await asyncio.to_thread(
            _publish_output_copy,
            self.uid,
            project_name,
            project_lot,
            task_period,
            artifact_id,
            artifact_filename,
            data,
        )

    async def create_project(self, name, lot):
        """创建工程并以当前用户作为负责人。"""
        row = ChangweiProject(id=str(uuid4()), name=name.strip(), lot=lot.strip(), owner_uid=self.uid, members={})
        self.db.add(row)
        await self.db.flush()
        self.repo.audit(row.id, "创建工程", row.id)
        await self.db.commit()
        return view(row)

    async def add_member(self, project_id, uid):
        """负责人添加已有账号，成员不可自行扩大权限。"""
        row = await self.repo.project(project_id, manage=True, lock=True)
        if not await self.repo.member_exists(uid):
            raise HTTPException(422, "请先在 Yuxi 用户管理中创建该账号")
        row.members = {**row.members, uid: "member"}
        self.repo.audit(project_id, "添加成员", uid)
        await self.db.commit()
        return view(row)

    async def create_task(self, project_id, kind, title, period):
        """按业务类型建立待填报模块。"""
        await self.repo.project(project_id)
        if kind not in TASK_TYPES:
            raise HTTPException(422, "未知业务类型")
        row = ChangweiTask(
            id=str(uuid4()),
            project_id=project_id,
            kind=kind,
            title=title.strip(),
            period=period,
            creator_uid=self.uid,
            status="draft",
            revision=1,
            content={
                "material_ids": [],
                "modules": [
                    {"id": str(i), "name": name, "text": "", "assignee": self.uid, "confirmed_by": None, "sources": []}
                    for i, name in enumerate(TASK_TYPES[kind]["modules"])
                ],
            },
        )
        self.db.add(row)
        self.repo.audit(project_id, "创建任务", row.id)
        await self.db.commit()
        return view(row)

    async def update_module(self, task_id, module_id, revision, text, confirm, assignee=None):
        """拒绝旧版本与越权修改，修改正文即撤销原确认。"""
        task = await self.repo.task(task_id, lock=True)
        project = await self.repo.project(task.project_id)
        if task.revision != revision:
            raise HTTPException(409, "任务已被更新，请刷新后重新编辑")
        content = copy.deepcopy(task.content)
        module = next((m for m in content["modules"] if m["id"] == module_id), None)
        if module is None:
            raise HTTPException(404, "模块不存在")
        manager = project.owner_uid == self.uid
        if not manager and module["assignee"] != self.uid:
            raise HTTPException(403, "只能填写本人负责的模块")
        if assignee is not None and assignee != module["assignee"]:
            if not manager or assignee not in {project.owner_uid, *project.members.keys()}:
                raise HTTPException(403, "仅负责人可分派给工程成员")
            module["assignee"] = assignee
            confirm = False
        if confirm and not text.strip():
            raise HTTPException(422, "请填写内容，无事项请明确填写无")
        module.update(
            text=text.strip(),
            confirmed_by=self.uid if confirm else None,
            confirmed_at=datetime.now(UTC).isoformat() if confirm else None,
        )
        task.content = content
        task.revision += 1
        task.status = "confirmed" if all(m.get("confirmed_by") for m in content["modules"]) else "draft"
        self.repo.audit(
            task.project_id,
            "确认模块" if confirm else "保存模块",
            task.id,
            {"module": module["name"], "revision": task.revision},
        )
        await self.db.commit()
        return view(task)

    async def upload(self, project_id, filename, data):
        """资料包全量校验后统一提交；解析错误不留下部分成功。"""
        await self.repo.project(project_id)
        try:
            files = await asyncio.to_thread(unpack, filename, data)
            result = []
            for name, raw in files:
                parsed = await asyncio.to_thread(parse_document, name, raw)
                row = ChangweiMaterial(
                    id=str(uuid4()),
                    project_id=project_id,
                    filename=name[:255],
                    category=classify(name),
                    parse_status=parsed["status"],
                    confirmed=False,
                    content=parsed,
                    data=raw,
                )
                self.db.add(row)
                result.append(row)
            await self.db.flush()
        except (ValueError, UnicodeError, BadZipFile, KeyError, RuntimeError, zlib.error, XMLSyntaxError) as exc:
            await self.db.rollback()
            raise HTTPException(422, "文件无法读取，请检查格式、压缩包密码或文件完整性") from exc
        self.repo.audit(project_id, "上传资料", project_id, {"count": len(result)})
        await self.db.commit()
        return [view(r) for r in result]

    async def ocr_material(self, material_id):
        """每次识别最多五个待处理页，允许分批恢复和人工检查。"""
        material = await self.repo.material(material_id)
        if not material.filename.lower().endswith(".pdf"):
            raise HTTPException(422, "OCR 只适用于 PDF")
        import re

        pages = []
        for warning in material.content["warnings"]:
            match = re.match(r"第 (\d+) 页需要 OCR", warning)
            if match:
                pages.append(int(match[1]))
        pages = pages[:5]
        if not pages:
            raise HTTPException(422, "没有待 OCR 页面")
        data = material.data
        await self.db.rollback()
        try:
            results = await asyncio.to_thread(ocr_pdf_pages, data, pages)
        except Exception as exc:
            raise HTTPException(503, "OCR 未完成，请检查 RapidOCR 模型和运行环境，原资料保留") from exc
        # Merge into the latest committed content while holding the row lock.
        material = await self.repo.material(material_id, lock=True)
        content = copy.deepcopy(material.content)
        locations = {item["location"] for item in results}
        content["segments"] = [s for s in content["segments"] if s["location"] not in locations]
        content["segments"].extend(s for s in results if s["text"].strip())
        content["warnings"] = [
            w for w in content["warnings"] if not any(w.startswith(f"第 {n} 页需要 OCR") for n in pages)
        ]
        for item in results:
            if not item["text"].strip():
                content["warnings"].append(f"{item['location']} 未识别到文字，请人工检查原件")
        material.content = content
        material.parse_status = "needs_attention" if content["warnings"] else "ready"
        material.confirmed = False
        self.repo.audit(material.project_id, "OCR 分批识别", material.id, {"pages": pages})
        await self.db.commit()
        return view(material)

    async def confirm_material(self, material_id, category):
        """用户确认分类，解析状态仍保留独立事实。"""
        row = await self.repo.material(material_id)
        if category not in CATEGORIES:
            raise HTTPException(422, "未知资料分类")
        row.category, row.confirmed = category, True
        self.repo.audit(row.project_id, "确认资料分类", row.id)
        await self.db.commit()
        return view(row)

    async def select_materials(self, task_id, revision, material_ids):
        """绑定本报告期资料；来源变化后撤销所有模块确认。"""
        task = await self.repo.task(task_id, lock=True)
        project = await self.repo.project(task.project_id)
        if self.uid not in {task.creator_uid, project.owner_uid}:
            raise HTTPException(403, "只有任务创建人或工程负责人可选择资料")
        if task.revision != revision:
            raise HTTPException(409, "任务已更新")
        available = {m.id for m in await self.repo.materials(task.project_id)}
        if not set(material_ids).issubset(available):
            raise HTTPException(422, "资料不属于当前工程")
        content = copy.deepcopy(task.content)
        content["material_ids"] = list(dict.fromkeys(material_ids))
        for module in content["modules"]:
            module["confirmed_by"] = None
            module["confirmed_at"] = None
        task.content, task.status = content, "draft"
        task.revision += 1
        self.repo.audit(task.project_id, "调整任务资料", task.id, {"count": len(material_ids)})
        await self.db.commit()
        return view(task)

    async def draft(self, task_id, module_id, model_spec, instruction):
        """按业务类型加载工程技能生成待确认草稿，不持锁等待模型。"""
        task = await self.repo.task(task_id)
        project = await self.repo.project(task.project_id)
        module = next((m for m in task.content["modules"] if m["id"] == module_id), None)
        if not module:
            raise HTTPException(404, "模块不存在")
        if self.uid not in {project.owner_uid, module["assignee"]}:
            raise HTTPException(403, "只能处理本人负责模块")
        materials = await self.repo.materials(task.project_id)
        sources = []
        for material in materials:
            if (
                material.id in task.content.get("material_ids", [])
                and material.confirmed
                and material.content["segments"]
            ):
                for segment in material.content["segments"]:
                    sources.append(
                        {
                            "source": f"{material.filename} / {segment['location']}"
                            + ("（解析有待核验项）" if material.parse_status != "ready" else ""),
                            "text": segment["text"],
                        }
                    )
        # 以关键词排序确定窗口；不是全库完整审查，也不宣称是向量检索。
        terms = re_terms(module["name"] + " " + instruction)
        sources.sort(key=lambda s: sum(t in s["text"] for t in terms), reverse=True)
        selected, size = [], 0
        for item in sources:
            if size + len(item["text"]) > 24000:
                continue
            selected.append(item)
            size += len(item["text"])
            if len(selected) >= 30:
                break
        if task.kind in {"scheme_review", "supervision_report", "management_report"} and not selected:
            raise HTTPException(422, "请先上传并确认可读取资料；扫描件需先完成 OCR")
        from yuxi.models import select_model

        try:
            prompt, skill = load_engineering_skill(task.kind)
        except (OSError, UnicodeError, ValueError, KeyError) as exc:
            raise HTTPException(503, "工程技能不可用，请检查服务部署，原内容未改动") from exc
        evidence = "\n\n".join(f"[{i + 1}] {s['source']}\n{s['text']}" for i, s in enumerate(selected))
        request = (
            f"业务：{TASK_TYPES[task.kind]['name']}\n"
            f"模块：{module['name']}\n"
            f"期间：{task.period}\n"
            f"用户记录：{normalize_station(module['text'])}\n"
            f"要求：{instruction}\n"
            f"资料：\n"
            f"{evidence}"
        )
        expected_revision = task.revision
        await self.db.rollback()
        try:
            response = await asyncio.wait_for(
                select_model(model_spec=model_spec).call(
                    [{"role": "system", "content": prompt}, {"role": "user", "content": request}]
                ),
                timeout=120,
            )
        except Exception as exc:
            raise HTTPException(502, "模型调用未完成，请检查模型配置后重试，原内容未改动") from exc
        task = await self.repo.task(task_id, lock=True)
        project = await self.repo.project(task.project_id)
        if task.revision != expected_revision:
            raise HTTPException(409, "AI 处理期间任务已更新，请重试")
        content = copy.deepcopy(task.content)
        target = next(m for m in content["modules"] if m["id"] == module_id)
        if self.uid not in {project.owner_uid, target["assignee"]}:
            raise HTTPException(403, "模块负责人已变化")
        target.update(
            text=response.content,
            sources=[s["source"] for s in selected],
            confirmed_by=None,
            confirmed_at=None,
            model_spec=model_spec,
            generation_skill=skill,
        )
        task.content, task.status = content, "draft"
        task.revision += 1
        self.repo.audit(
            task.project_id,
            "AI 生成草稿",
            task.id,
            {"module": target["name"], "model": model_spec, "source_count": len(selected), "skill": skill},
        )
        await self.db.commit()
        return {
            "task": view(task),
            "text": response.content,
            "sources": [s["source"] for s in selected],
            "skill": skill,
            "notice": "所选资料窗口生成的辅助草稿，需核对后保存确认；并非完整规范审查。",
        }

    async def generate(self, task_id, revision, template_id=None):
        """只允许工程负责人将全部已确认内容固化为成果版本。"""
        task = await self.repo.task(task_id, lock=True)
        project = await self.repo.project(task.project_id, manage=True)
        if task.revision != revision:
            raise HTTPException(409, "任务版本已变化")
        modules = task.content["modules"]
        if not all(m.get("confirmed_by") and m["text"].strip() for m in modules):
            raise HTTPException(422, "所有模块必须填写并人工确认后才能生成")
        if template_id:
            if task.kind != "supervision_log":
                raise HTTPException(422, "原版模板暂仅适用于监理日志")
            template = await self.repo.material(template_id)
            if template.project_id != task.project_id or not template.filename.lower().endswith(".docx"):
                raise HTTPException(422, "请选择当前工程的 Word 模板")
            from yuxi.services.changwei_templates import export_supervision_template

            try:
                data = await asyncio.to_thread(
                    export_supervision_template, template.data, modules, task.period, self.uid
                )
            except ValueError as exc:
                raise HTTPException(422, "模板不匹配，请选择原版监理日志表格") from exc
        else:
            data = await asyncio.to_thread(
                export_docx, task.title, f"{project.name} / {project.lot}", task.period, modules, task.revision
            )
        row = ChangweiArtifact(
            id=str(uuid4()),
            task_id=task.id,
            revision=task.revision,
            filename=f"{TASK_TYPES[task.kind]['name']}-{task.period}-v{task.revision}.docx",
            data=data,
        )
        output_context = {
            "project_name": project.name,
            "project_lot": project.lot,
            "task_period": task.period,
            "artifact_id": row.id,
            "artifact_filename": row.filename,
            "project_id": task.project_id,
            "task_id": task.id,
        }
        self.db.add(row)
        task.status = "generated"
        self.repo.audit(
            task.project_id,
            "生成成果",
            task.id,
            {"artifact_id": row.id, "revision": task.revision, "template_id": template_id},
        )
        await self.db.commit()
        result = view(row)
        output_path = None
        output_warning = None
        try:
            output_path = await self._publish_output_copy(
                output_context["project_name"],
                output_context["project_lot"],
                output_context["task_period"],
                output_context["artifact_id"],
                output_context["artifact_filename"],
                data,
            )
        except (OSError, ValueError):
            await self.db.rollback()
            output_warning = "成果版本已生成，但个人空间副本暂未写入；仍可从下方成果列表下载。"
            self.repo.audit(output_context["project_id"], "同步成果到个人空间失败", output_context["artifact_id"])
            try:
                await self.db.commit()
            except Exception:
                await self.db.rollback()
        else:
            self.repo.audit(
                output_context["project_id"],
                "同步成果到个人空间",
                output_context["artifact_id"],
                {"output_path": output_path},
            )
            try:
                await self.db.commit()
            except Exception:
                await self.db.rollback()
        result["output_path"] = output_path
        result["output_warning"] = output_warning
        return result


def _safe_output_component(value, fallback):
    """生成兼容 Windows 下载与 Workspace 路径的单层名称。"""
    clean = re.sub(r'[\x00-\x1f/\\:*?"<>|]+', "-", str(value or "")).strip(" .")
    return (clean or fallback)[:80]


def _publish_output_copy(uid, project_name, project_lot, task_period, artifact_id, artifact_filename, data):
    """以 no-follow Workspace API 原子写入唯一命名的成果副本。"""
    ensure_user_workspace(uid)
    workspace = Workspace(uid)
    folders = [
        "outputs",
        "江擎",
        _safe_output_component(f"{project_name}-{project_lot}", "未命名工程"),
        _safe_output_component(task_period, "未注明日期"),
    ]
    parent = "/"
    for folder in folders:
        target = f"{parent.rstrip('/')}/{folder}"
        try:
            metadata = workspace.stat_authorized_path(target, root="/")
            if not metadata["is_dir"]:
                raise ValueError("output path is not a directory")
        except FileNotFoundError:
            try:
                workspace.create_authorized_directory(parent, folder, root="/")
            except FileExistsError:
                metadata = workspace.stat_authorized_path(target, root="/")
                if not metadata["is_dir"]:
                    raise ValueError("output path is not a directory")
        parent = target
    stem = artifact_filename[:-5] if artifact_filename.lower().endswith(".docx") else artifact_filename
    filename = _safe_output_component(f"{stem}-{artifact_id[:8]}", "成果") + ".docx"
    output_path = f"{parent}/{filename}"
    workspace.replace_authorized_file(output_path, data)
    return output_path


def re_terms(text):
    """从模块名称获取小粒度查询词。"""
    import re

    return re.findall(r"[\u4e00-\u9fff]{2,4}|[A-Za-z0-9]+", text)
