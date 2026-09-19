"""工程工作台使用随应用发布的固定技能，避免个人同名技能改变业务规则。"""

import hashlib

import yaml

from yuxi.agents.skills.buildin import ENGINEERING_SKILLS


def load_engineering_skill(kind: str) -> tuple[str, dict[str, str]]:
    """读取同一份技能快照，返回模型正文和可追溯的版本摘要。"""
    spec = ENGINEERING_SKILLS[kind]
    raw = (spec.source_dir / "SKILL.md").read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise ValueError("工程技能缺少元数据")
    header, separator, body = text[4:].partition("\n---\n")
    try:
        metadata = yaml.safe_load(header)
    except yaml.YAMLError as exc:
        raise ValueError("工程技能元数据解析失败") from exc
    if (
        not separator
        or not isinstance(metadata, dict)
        or metadata.get("name") != spec.slug
        or not metadata.get("description")
        or not body.strip()
    ):
        raise ValueError("工程技能元数据或正文无效")
    return body.strip(), {
        "slug": spec.slug,
        "version": spec.version,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
