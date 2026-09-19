"""把工程核心模块编译为扩展，并只保留可运行发布文件。"""

import json
import os
from pathlib import Path
import subprocess
import sys

from Cython.Build import cythonize
from setuptools import Extension, setup


CORE_MODULES = (
    "yuxi.services.changwei_documents",
    "yuxi.services.changwei_service",
    "yuxi.services.changwei_speech",
    "yuxi.services.changwei_templates",
    "yuxi.services.changwei_weather",
    "yuxi.repositories.changwei_repository",
)


def main():
    """在隔离构建目录编译，缺少任何二进制时拒绝生成发布目录。"""
    root = Path("/release/package")
    os.chdir(root)
    extensions = [Extension(name, [name.replace(".", "/") + ".py"], extra_compile_args=["-O2", "-g0"])
                  for name in CORE_MODULES]
    setup(
        name="jiangqing-core",
        ext_modules=cythonize(
            extensions,
            compiler_directives={"language_level": 3, "binding": True, "annotation_typing": False},
            build_dir="/tmp/cython-generated",
            nthreads=2,
        ),
        script_args=["build_ext", "--inplace", "--build-temp", "/tmp/cython-objects", "-j", "2"],
    )
    records = []
    for name in CORE_MODULES:
        source = root / (name.replace(".", "/") + ".py")
        binaries = list(source.parent.glob(source.stem + ".*.so"))
        if len(binaries) != 1:
            raise RuntimeError(f"原生扩展产物不唯一：{name}")
        subprocess.run(["strip", "--strip-unneeded", str(binaries[0])], check=True)
        source.unlink()
        records.append({"module": name, "binary": str(binaries[0].relative_to(root))})
    for path in Path("/release").rglob("*"):
        if path.is_file() and (path.suffix in {".pyc", ".pyo", ".c"} or "__pycache__" in path.parts):
            path.unlink()
    # 编译临时目录只属于构建阶段，不复制到最终镜像。
    import shutil
    shutil.rmtree(root / "build", ignore_errors=True)
    Path("/release/core-protection.json").write_text(
        json.dumps({"method": "Cython native extensions", "python": sys.version.split()[0],
                    "architecture": "linux/amd64", "modules": records,
                    "boundary": "Upstream framework, API schemas and third-party Python remain readable; reverse engineering is not prevented."},
                   indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
