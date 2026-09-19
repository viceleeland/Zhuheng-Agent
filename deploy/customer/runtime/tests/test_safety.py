"""在无 Docker socket 的 Linux 环境验证客户脚本的隔离与失败恢复边界。"""

import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest

RUNTIME = Path(__file__).resolve().parents[1]


def fake_docker() -> int:
    """以持久 JSON 模拟容器状态；测试进程无法访问真实 Docker daemon。"""
    state_path = Path(os.environ["RUNTIME_TEST_STATE"])
    state = json.loads(state_path.read_text())
    containers = state["containers"]
    args = sys.argv[2:]
    if args[:1] == ["--host"]:
        args = args[2:]
    output = []
    result = 0
    state.setdefault("events", []).append(args)

    def labels(container):
        """生成与客户运行时相同的实例标签数据。"""
        values = {
            "io.jiangqing.customer.project": container["project"],
            "io.jiangqing.customer.instance": container["instance"],
        }
        if container.get("service"):
            values["com.docker.compose.project"] = container["project"]
            values["com.docker.compose.service"] = container["service"]
        else:
            values.update({"app": "yuxi-sandbox", "managed-by": "yuxi-sandbox-provisioner"})
        return values

    def start(container):
        """记录实际启动次数，避免漏掉迁移器启动后再次退出的情况。"""
        if container["status"] != "running":
            container["start_count"] = container.get("start_count", 0) + 1
        container["status"] = container.get("after_start", "running")

    if args[0] == "compose":
        action = args[1]
        selected = [c for c in containers if c.get("service") and c["project"] == state["project"]]
        if action == "ps":
            selected = [c for c in selected if c["status"] == "running"]
            output = [c["service"] if "--services" in args else c["id"] for c in selected]
        elif action in {"stop", "start"}:
            services = [arg for arg in args[2:] if not arg.startswith("-") and not arg.isdigit()]
            if action == "start" and services:
                # Compose start also starts dependencies, including exited one-shot services.
                pending = list(services)
                expanded = set(services)
                while pending:
                    for dependency in state.get("dependencies", {}).get(pending.pop(), []):
                        if dependency not in expanded:
                            expanded.add(dependency)
                            pending.append(dependency)
                services = expanded
            selected = [c for c in selected if not services or c["service"] in services]
            for container in selected:
                if action == "start":
                    start(container)
                else:
                    container["status"] = "exited"
                if action == "stop" and state.get("fail_stop") and container["service"] == "api":
                    result = 55
                    break
        elif action == "up":
            if "storage-migrator" in args:
                state["migration_attempted"] = True
                result = 57 if state.get("fail_migration") else 0
            elif "postgres" in args:
                result = 56 if state.get("fail_postgres") else 0
                for container in selected:
                    if container["service"] == "postgres":
                        container["status"] = "exited" if result else "running"
            else:
                raise RuntimeError("Unexpected Compose up in fixture")
        else:
            raise RuntimeError("Unexpected Compose fixture action: " + action)
    elif args[0] == "ps":
        selected = [c for c in containers if c["status"] == "running" or "-a" in args or "-aq" in args]
        filters = [args[index + 1] for index, value in enumerate(args) if value == "--filter"]
        for query in filters:
            if query.startswith("label="):
                key, expected = query[6:].split("=", 1)
                selected = [c for c in selected if labels(c).get(key) == expected]
            elif query.startswith("name="):
                selected = [c for c in selected if re.search(query[5:], "/" + c["name"])]
            else:
                raise RuntimeError("Unexpected filter")
        output = [c["id"] for c in selected]
    elif args[0] == "inspect":
        index = args.index("--format")
        template, ids = args[index + 1], args[index + 2:]
        for identifier in ids:
            container = next((c for c in containers if c["id"] == identifier), None)
            if container is None:
                result = 1
                continue
            if "State.Status" in template:
                sequence = container.get("health_sequence")
                if sequence:
                    container["health"] = sequence.pop(0)
                output.append(f'/{container["name"]} {container["status"]} {container.get("health", "none")}')
            elif "com.docker.compose.service" in template:
                output.append(container.get("service", ""))
            elif "io.jiangqing.customer.project" in template:
                output.append(container["project"] + " " + container["instance"])
            elif "range .Mounts" in template:
                output.extend(container.get("mounts", []))
            elif template == "{{.Name}}":
                output.append("/" + container["name"])
            else:
                raise RuntimeError("Unexpected inspect template: " + template)
    elif args[0] in {"stop", "start"}:
        ids = [arg for arg in args[1:] if not arg.startswith("-") and not arg.isdigit()]
        for container in containers:
            if container["id"] in ids:
                if args[0] == "start":
                    start(container)
                else:
                    container["status"] = "exited"
    elif args[0] != "load":
        raise RuntimeError("Unexpected Docker fixture action: " + args[0])
    state_path.write_text(json.dumps(state))
    if output:
        print("\n".join(output))
    return result


class ArchiveSafetyTests(unittest.TestCase):
    """以真实 tar 元数据复现软链链路越界与环。"""

    def setUp(self):
        """加载实际交付的校验器。"""
        self.temp = tempfile.TemporaryDirectory()
        spec = importlib.util.spec_from_file_location("archive_check", RUNTIME / "archive-check.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def tearDown(self):
        """清理本测试创建的临时目录。"""
        self.temp.cleanup()

    def archive(self, links):
        """创建含实例标记和指定软链的归档。"""
        target = Path(self.temp.name) / "fixture.tar.gz"
        with tarfile.open(target, "w:gz") as archive:
            marker = tarfile.TarInfo(".jiangqing-instance")
            marker.size = 1
            archive.addfile(marker, io.BytesIO(b"x"))
            for name, destination in links.items():
                link = tarfile.TarInfo(name)
                link.type = tarfile.SYMTYPE
                link.linkname = destination
                archive.addfile(link)
        return target

    def test_indirect_parent_escape_rejected(self):
        """先展开 a 再处理父目录时，b 会离开归档根。"""
        target = self.archive({"user-data/a": "..", "user-data/b": "a/../.."})
        with self.assertRaisesRegex(SystemExit, "leaves the data directory"):
            self.module.validate_archive(str(target))

    def test_cycle_rejected(self):
        """归档软链环不能使校验无限等待。"""
        target = self.archive({"user-data/a": "b", "user-data/b": "a"})
        with self.assertRaisesRegex(SystemExit, "cyclic or too deep"):
            self.module.validate_archive(str(target))

    def test_safe_link_chain_preserved(self):
        """普通目录内的相对链接链仍然可备份和恢复。"""
        target = self.archive({"user-data/a": "folder", "user-data/b": "a/file.txt"})
        self.module.validate_archive(str(target))


@unittest.skipUnless(sys.platform.startswith("linux"), "Bash permissions and flock require Linux")
class ScriptSafetyTests(unittest.TestCase):
    """用可回读的容器状态验证实际 Bash 控制流程。"""

    def setUp(self):
        """为每个测试创建完全独立的命令替身和数据目录。"""
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "private" / "data"
        self.data.mkdir(parents=True)
        (self.data / "legacy-saves").mkdir()
        self.state_file = self.root / "state.json"
        self.instance = "fixture-instance-12345678"
        self.state = {
            "project": "foo",
            "dependencies": {
                "api": ["storage-migrator"],
                "worker": ["storage-migrator"],
                "storage-migrator": ["postgres"],
            },
            "containers": [
                {"id": name, "name": "foo-" + name + "-1", "project": "foo", "instance": self.instance,
                 "service": name, "status": "running", "health": "healthy", "mounts": [str(self.data / name)]}
                for name in ("api", "worker", "postgres")
            ] + [
                {"id": "migrator", "name": "foo-storage-migrator-1", "project": "foo", "instance": self.instance,
                 "service": "storage-migrator", "status": "exited", "health": "none", "mounts": []},
                {"id": "own", "name": "foo-sandbox-run", "project": "foo", "instance": self.instance,
                 "status": "running", "health": "none", "mounts": []},
                {"id": "other-project", "name": "foo-sandbox-sandbox-run", "project": "foo-sandbox", "instance": self.instance,
                 "status": "running", "health": "none", "mounts": []},
                {"id": "other-instance", "name": "foo-sandbox-old", "project": "foo", "instance": "other-instance-12345678",
                 "status": "running", "health": "none", "mounts": []},
            ],
        }
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fake_engine = self.root / "fake_docker.py"
        shutil.copyfile(Path(__file__), fake_engine)
        docker = self.bin / "docker"
        docker.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake_engine}" fake-docker "$@"\n')
        docker.chmod(0o700)
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"], RUNTIME_TEST_STATE=str(self.state_file))

    def tearDown(self):
        """删除测试私有目录，不接触任何部署数据。"""
        self.temp.cleanup()

    def save(self):
        """发布测试的输入状态。"""
        self.state_file.write_text(json.dumps(self.state))

    def run_bash(self, body, timeout=30):
        """执行实际 common 函数，以替身 Docker 作为外部协议边界。"""
        self.save()
        script = self.root / "case.sh"
        script.write_text(f'''set -Eeuo pipefail
umask 077
source "{RUNTIME / 'common.sh'}"
PROJECT=foo
INSTANCE_ID={self.instance}
DATA_DIR="{self.data}"
dc() {{ docker compose "$@"; }}
{body}
''')
        return subprocess.run(["bash", str(script)], env=self.env, capture_output=True, text=True, timeout=timeout)

    def read_states(self, path=None):
        """读取最终容器事实，避免以 start 调用成功作为结果。"""
        state = json.loads((path or self.state_file).read_text())
        return {container["id"]: container for container in state["containers"]}

    def assert_original_statuses(self):
        """恢复后保留每个容器先前状态，包括已退出的一次性迁移器。"""
        self.assertEqual(
            {name: container["status"] for name, container in self.read_states().items()},
            {container["id"]: container["status"] for container in self.state["containers"]},
        )

    def test_overlapping_project_names_and_reused_instance_are_isolated(self):
        """foo 不能停止 foo-sandbox，也不能接管其他实例遗留沙箱。"""
        snapshot = self.root / "quiesced.json"
        result = self.run_bash(f'quiesce_instance\ncp "$RUNTIME_TEST_STATE" "{snapshot}"\nresume_instance')
        self.assertEqual(result.returncode, 0, result.stderr)
        stopped = self.read_states(snapshot)
        self.assertEqual(stopped["own"]["status"], "exited")
        self.assertEqual(stopped["other-project"]["status"], "running")
        self.assertEqual(stopped["other-instance"]["status"], "running")
        self.assert_original_statuses()

    def test_resume_never_restarts_completed_migrator(self):
        """复现 Compose 的隐式依赖启动，再验证真实恢复函数仅启动原 ID。"""
        previous = self.run_bash('quiesce_instance\ndc start "${ORIGINAL_SERVICES[@]}"')
        self.assertEqual(previous.returncode, 0, previous.stderr)
        self.assertEqual(self.read_states()["migrator"].get("start_count", 0), 1)
        self.assertEqual(self.read_states()["migrator"]["status"], "running")

        result = self.run_bash('quiesce_instance\nresume_instance')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_original_statuses()
        self.assertEqual(self.read_states()["migrator"].get("start_count", 0), 0)

    def test_start_success_but_container_exits_is_failure(self):
        """Docker start 返回零但进程立即退出时，恢复不能报成功。"""
        self.state["containers"][0]["after_start"] = "exited"
        result = self.run_bash('quiesce_instance\nresume_instance')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("failed after restart", result.stderr)
        self.assertEqual(self.read_states()["api"]["status"], "exited")

    def test_health_wait_reads_until_healthy(self):
        """容器保持运行但未 ready 时，应持续读取到健康。"""
        self.state["containers"][0]["health_sequence"] = ["starting", "healthy"]
        result = self.run_bash('wait_for_container_health 5 api')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_states()["api"]["health"], "healthy")

    def test_unhealthy_container_has_bounded_failure(self):
        """持续不健康必须按期限失败，不能只看 Running。"""
        self.state["containers"][0]["health"] = "unhealthy"
        began = time.monotonic()
        result = self.run_bash('wait_for_container_health 1 api')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Timed out", result.stderr)
        self.assertLess(time.monotonic() - began, 4)

    def test_lock_preserves_existing_parent_mode_and_contents(self):
        """获取锁不能放宽目录权限或截断已有锁文件。"""
        self.data.parent.chmod(0o700)
        lock = Path(str(self.data) + ".lock")
        lock.write_text("existing owner record\n")
        result = self.run_bash('lock_instance')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stat.S_IMODE(self.data.parent.stat().st_mode), 0o700)
        self.assertEqual(lock.read_text(), "existing owner record\n")

    def test_competing_lock_refuses_without_truncation(self):
        """被另一进程持有的锁必须失败，并保留原文件。"""
        import fcntl
        lock = Path(str(self.data) + ".lock")
        lock.write_text("held\n")
        with lock.open("a") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_bash('lock_instance')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("holds this instance lock", result.stderr)
        self.assertEqual(lock.read_text(), "held\n")

    def run_install_failure(self, failure):
        """运行未修改的 install.sh，把镜像与预备份步骤替换为测试边界。"""
        self.state[failure] = True
        self.save()
        runtime = self.root / "package" / "runtime"
        runtime.mkdir(parents=True)
        (runtime.parent / "images").mkdir()
        (runtime.parent / "images" / "fixture.tar").touch()
        shutil.copyfile(RUNTIME / "install.sh", runtime / "install.sh")
        overrides = f'''
require_host() {{ :; }}
load_context() {{ ENV_FILE=$1; PROJECT=foo; INSTANCE_ID={self.instance}; DATA_DIR="{self.data}"; }}
verify_bundle() {{ PACKAGE_DIR="{runtime.parent}"; }}
verify_images() {{ :; }}
require_marker() {{ :; }}
dc() {{ docker compose "$@"; }}
'''
        (runtime / "common.sh").write_text((RUNTIME / "common.sh").read_text() + overrides)
        (runtime / "backup.sh").write_text(f'source "{runtime / "common.sh"}"\ncreate_backup() {{ LAST_BACKUP=fixture-backup; }}\n')
        return subprocess.run(["bash", str(runtime / "install.sh"), "upgrade", str(self.root / "customer.env")], env=self.env, capture_output=True, text=True, timeout=30)

    def test_partial_quiesce_failure_resumes_original_services(self):
        """停写只完成一部分就失败时，安装退出仍恢复所有原容器。"""
        result = self.run_install_failure("fail_stop")
        self.assertEqual(result.returncode, 55, result.stderr)
        self.assert_original_statuses()

    def test_pre_migration_postgres_start_failure_resumes_original_services(self):
        """迁移命令尚未开始时的数据库启动错误仍必须恢复。"""
        result = self.run_install_failure("fail_postgres")
        self.assertEqual(result.returncode, 56, result.stderr)
        self.assert_original_statuses()
        self.assertFalse(json.loads(self.state_file.read_text()).get("migration_attempted", False))

    def test_migration_failure_keeps_writers_stopped(self):
        """Schema 修改可能已开始后，禁止自动重启旧写服务。"""
        result = self.run_install_failure("fail_migration")
        self.assertEqual(result.returncode, 57, result.stderr)
        states = self.read_states()
        self.assertTrue(all(states[name]["status"] == "exited" for name in ("api", "worker", "own")))
        self.assertEqual(states["other-project"]["status"], "running")
        self.assertTrue(json.loads(self.state_file.read_text())["migration_attempted"])


if __name__ == "__main__":
    if sys.argv[1:2] == ["fake-docker"]:
        raise SystemExit(fake_docker())
    unittest.main(verbosity=2)
