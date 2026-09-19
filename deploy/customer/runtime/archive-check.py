"""验证冷备归档的路径和文件类型，供备份与恢复共同使用。"""

from __future__ import annotations

import pathlib
from collections import deque
import sys
import tarfile


def resolve_symlink(name: str, links: dict[str, str]) -> None:
    """逐段展开归档链接后再处理父目录，沿用 Linux 的 40 次展开上限。"""
    pending = deque(pathlib.PurePosixPath(name).parts)
    resolved: list[str] = []
    expansions = 0
    while pending:
        part = pending.popleft()
        if part in {"", "."}:
            continue
        if part == "..":
            if not resolved:
                raise SystemExit("Archive symlink leaves the data directory")
            resolved.pop()
            continue
        target = links.get("/".join([*resolved, part]))
        if target is None:
            resolved.append(part)
            continue
        if target.startswith("/"):
            raise SystemExit("Archive symlink has an absolute target")
        expansions += 1
        if expansions > 40:
            raise SystemExit("Archive symlink chain is cyclic or too deep")
        pending.extendleft(reversed(target.split("/")))


def validate_archive(filename: str) -> None:
    """拒绝越界路径、写穿软链和不支持的特殊文件。"""
    allowed = {
        "postgres", "redis", "minio", "minio-config", "etcd", "milvus", "neo4j", "neo4j-logs",
        "user-data", "skill-sources", "skill-projections", "legacy-saves", ".jiangqing-instance",
    }
    with tarfile.open(filename, "r:gz") as archive:
        by_name = {}
        links = {}
        for member in archive.getmembers():
            path = pathlib.PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise SystemExit("Unsafe archive member path")
            name = str(path)
            if name in by_name:
                raise SystemExit("Duplicate archive member")
            if path.parts and path.parts[0] not in allowed:
                raise SystemExit("Unexpected data directory in archive")
            if not (member.isdir() or member.isfile() or member.issym() or member.islnk()):
                raise SystemExit("Archive contains unsupported special files")
            by_name[name] = member
            if member.issym():
                links[name] = member.linkname
        for name in links:
            resolve_symlink(name, links)
        for name, member in by_name.items():
            if any(str(parent) in links for parent in pathlib.PurePosixPath(name).parents):
                raise SystemExit("Archive writes through a symlink")
            if member.islnk():
                target = str(pathlib.PurePosixPath(member.linkname))
                if target not in by_name or not by_name[target].isfile():
                    raise SystemExit("Invalid archive hard link")
        marker = by_name.get(".jiangqing-instance")
        if marker is None or not marker.isfile():
            raise SystemExit("Missing customer data marker")


if __name__ == "__main__":
    validate_archive(sys.argv[1])
