"""用 Git 跟踪文件白名单准备客户构建上下文，不复制本机数据。"""

from pathlib import Path
import shutil
import subprocess
import sys


def main():
    """只复制明确发布目录中的跟踪文件和指定构建器。"""
    repo = Path(__file__).resolve().parents[2]
    dest = Path(sys.argv[1]).resolve()
    allowed = (repo / "work" / "customer-build").resolve()
    if not dest.is_relative_to(allowed) or dest == allowed or dest.exists():
        raise SystemExit("构建上下文必须是 work/customer-build 下的新目录")
    dest.mkdir(parents=True)
    tracked = subprocess.check_output(["git", "ls-files", "-z", "--", "backend/package", "backend/server", "docker/sandbox_provisioner/app.py", "docker/sandbox_provisioner/sandbox.env", "LICENSE"], cwd=repo).decode().split("\0")
    for name in filter(None, tracked):
        src = repo / name
        if src.is_symlink() or not src.resolve().is_relative_to(repo):
            raise SystemExit(f"构建来源必须是仓库内常规文件：{name}")
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
    for name in ("api.Dockerfile", "compile_core.py", "provisioner.Dockerfile", "patch_provisioner.py"):
        target = dest / "deploy" / "customer" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / "deploy" / "customer" / name, target)
    print(dest)


if __name__ == "__main__":
    main()
