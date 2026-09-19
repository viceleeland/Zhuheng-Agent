"""One opt-in real-model acceptance run, in a newly created verification task."""
import asyncio
import json
from pathlib import Path
import httpx
from sqlalchemy import select
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import User, ChangweiProject, ChangweiTask
from yuxi.utils.auth_utils import AuthUtils


async def main():
    async with pg_manager.get_async_session_context() as db:
        admin = await db.scalar(select(User).where(User.uid == 'changwei_admin'))
        project = await db.scalar(select(ChangweiProject).where(ChangweiProject.name.like('CW验证-%'), ChangweiProject.owner_uid == admin.uid))
        assert project, 'No verification project found'
        pid = project.id
        token = AuthUtils.create_access_token({'sub': str(admin.id)})
    facts = '施工部位为右岸引水渠，桩号K1+250至K1+300，现场施工人员12人，开展混凝土浇筑。'
    result = {'project_id': pid, 'input_facts': facts, 'model_spec': 'deepseek:deepseek-v4-flash'}
    async with httpx.AsyncClient(base_url='http://127.0.0.1:5050/api/changwei', headers={'Authorization': 'Bearer '+token}, timeout=150) as client:
        response = await client.post(f'/projects/{pid}/tasks', json={'kind': 'supervision_log', 'title': 'AI日志整理验收', 'period': '2026-09-19'})
        response.raise_for_status()
        task = response.json()
        tid, mid = task['id'], task['content']['modules'][0]['id']
        result.update(task_id=tid, module_id=mid, created_revision=task['revision'])
        response = await client.put(f'/tasks/{tid}/modules/{mid}', json={'revision': task['revision'], 'text': facts, 'confirm': False})
        response.raise_for_status()
        saved = response.json()
        result['input_saved_revision'] = saved['revision']
        response = await client.post(f'/tasks/{tid}/modules/{mid}/draft', json={'model_spec': result['model_spec'], 'instruction': '将原始施工记录整理成简洁的监理日志正文，完整保留施工部位、桩号范围、12人和浇筑作业四项事实；不增加未经记录的事实。'})
        result['draft_http_status'] = response.status_code
        response.raise_for_status()
        drafted = response.json()
    async with pg_manager.get_async_session_context() as db:
        stored = await db.get(ChangweiTask, tid)
        module = next(m for m in stored.content['modules'] if m['id'] == mid)
        text = module['text']
        result.update(pg_revision=stored.revision, pg_status=stored.status, pg_module_text=text,
                      confirmed_by=module.get('confirmed_by'), confirmed_at=module.get('confirmed_at'),
                      content_is_string=isinstance(text,str))
        checks = {'location':'右岸引水渠' in text, 'station_start':'K1+250' in text,
                  'station_end':'K1+300' in text, 'workers':'12' in text and '人' in text,
                  'activity':'混凝土' in text and '浇筑' in text}
        result['facts_preserved'] = checks
        assert isinstance(text, str) and all(checks.values()), result
        assert stored.revision == saved['revision'] + 1 == drafted['task']['revision']
        assert stored.status == 'draft' and module.get('confirmed_by') is None and module.get('confirmed_at') is None
    result['result'] = 'passed'
    Path('/tmp/ai-business-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
