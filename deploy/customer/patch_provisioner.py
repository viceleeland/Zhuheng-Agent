"""让客户沙盒仅使用已导入的镜像，缺失时明确失败。"""

from pathlib import Path
import sys


def main():
    """替换唯一的自动拉取调用，保持现有容器就绪与清理流程。"""
    path = Path(sys.argv[1])
    content = path.read_text(encoding="utf-8")
    old = """                container = self._client.containers.run(
                    self._sandbox_image, **run_kwargs
                )
                container.reload()"""
    new = """                # Customer delivery uses only the verified, preloaded sandbox image.
                # create() does not implicitly pull a missing image, unlike run().
                run_kwargs.pop("detach", None)
                container = self._client.containers.create(
                    self._sandbox_image, **run_kwargs
                )
                container.start()
                container.reload()"""
    if content.count(old) != 1:
        raise SystemExit("沙盒创建实现已变化，请重新审阅客户离线补丁")
    content = content.replace(old, new)
    patches = [
        (
            '        self._container_prefix = os.getenv("DOCKER_SANDBOX_PREFIX", "yuxi-sandbox")',
            '''        self._container_prefix = os.getenv("DOCKER_SANDBOX_PREFIX", "yuxi-sandbox")
        self._customer_labels = {
            "io.jiangqing.customer.project": os.environ["SANDBOX_CUSTOMER_PROJECT"],
            "io.jiangqing.customer.instance": os.environ["SANDBOX_CUSTOMER_INSTANCE"],
        }
        if not all(self._customer_labels.values()):
            raise ValueError("Customer sandbox ownership must not be empty")''',
        ),
        (
            '                "labels": {\n                    "app": "yuxi-sandbox",',
            '                "labels": {\n                    **self._customer_labels,\n                    "app": "yuxi-sandbox",',
        ),
        (
            '                "label": ["app=yuxi-sandbox", "managed-by=yuxi-sandbox-provisioner"]',
            '''                "label": ["app=yuxi-sandbox", "managed-by=yuxi-sandbox-provisioner"]
                + [f"{key}={value}" for key, value in self._customer_labels.items()]''',
        ),
    ]
    for expected, replacement in patches:
        if content.count(expected) != 1:
            raise SystemExit("沙盒身份实现已变化，请重新审阅客户隔离补丁")
        content = content.replace(expected, replacement)
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
