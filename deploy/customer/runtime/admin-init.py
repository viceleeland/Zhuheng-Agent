"""通过既有身份服务创建初始管理员，不承担数据库迁移。"""

import asyncio
import re
import sys

from yuxi.repositories.user_repository import UserRepository
from yuxi.services.identity_admin_service import initialize_system_admin
from yuxi.storage.postgres.manager import pg_manager
from yuxi.utils.auth_utils import AuthUtils


async def main() -> None:
    """读取标准输入中的凭据，提交后回读管理员记录。"""
    pg_manager.initialize()
    try:
        await pg_manager.require_current_schema(include_knowledge=True)
        if sys.argv[1:] == ["--check-initialized"]:
            async with pg_manager.get_async_session_context() as session:
                if await UserRepository(session).is_first_run():
                    raise SystemExit(3)
            return
        if sys.argv[1:]:
            raise SystemExit("Unsupported administrator helper argument.")
        uid = sys.stdin.readline().rstrip("\n")
        password = sys.stdin.readline().rstrip("\n")
        if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", uid):
            raise SystemExit("Admin ID must contain 3-20 letters, digits or underscores.")
        if len(password) < 12:
            raise SystemExit("Use an administrator password of at least 12 characters.")
        async with pg_manager.get_async_session_context() as session:
            await initialize_system_admin(session, uid=uid, password=password, phone_number=None)
        async with pg_manager.get_async_session_context() as session:
            admin = await UserRepository(session).get_by_uid(uid)
            if admin is None or admin.role != "superadmin" or not AuthUtils.verify_password(admin.password_hash, password):
                raise RuntimeError("Administrator read-back verification failed.")
        print(f"Administrator initialized and verified: {uid}")
    finally:
        await pg_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
