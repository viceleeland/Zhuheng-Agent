"""和风实况天气只作为当天日志的待确认补充，不写入业务终态。"""

import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException


async def get_task_weather(repo, uid, task_id, location):
    """验证任务和天气模块权限后获取实况，返回可追溯的待确认文本。"""
    task = await repo.task(task_id)
    project = await repo.project(task.project_id)
    weather_module = next((m for m in task.content.get('modules', []) if m['name'] in ('天气信息', '天气与水文')), None)
    if task.kind not in ('supervision_log', 'management_log') or weather_module is None:
        raise HTTPException(422, '仅监理日志或项管日志的天气模块可获取实况')
    if str(project.owner_uid) != str(uid) and str(weather_module.get('assignee')) != str(uid):
        raise HTTPException(403, '仅天气模块负责人或工程负责人可获取天气')
    current = datetime.now(ZoneInfo('Asia/Shanghai'))
    if task.period != current.date().isoformat():
        raise HTTPException(422, '实况仅供当天日志使用；日期须为北京时间当天 YYYY-MM-DD，历史日志请按原始记录填写')
    location = location.strip()
    if not re.fullmatch(r'\d{9}', location):
        if not re.fullmatch(r'-?\d{1,3}(?:\.\d{1,2})?,-?\d{1,2}(?:\.\d{1,2})?', location):
            raise HTTPException(422, '请输入 9 位城市 ID 或经度,纬度（最多两位小数）')
        longitude, latitude = map(float, location.split(','))
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise HTTPException(422, '经纬度超出有效范围')
    host = os.getenv('QWEATHER_API_HOST', '').strip().removeprefix('https://').rstrip('/')
    key = os.getenv('QWEATHER_API_KEY', '').strip()
    if not re.fullmatch(r'(?:[a-zA-Z0-9-]+\.)+qweatherapi\.com', host) or not key:
        raise HTTPException(503, '天气服务尚未配置，请联系管理员')
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.get(f'https://{host}/v7/weather/now', params={'location': location, 'lang': 'zh', 'unit': 'm'}, headers={'X-QW-Api-Key': key})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, '天气服务暂不可用，请稍后重试或手动填写') from None
    if not isinstance(payload, dict) or str(payload.get('code')) != '200':
        raise HTTPException(502, '天气服务未返回有效实况，请核对城市 ID 或服务配额')
    observation = payload.get('now')
    try:
        if not isinstance(observation, dict):
            raise ValueError()
        observed = datetime.fromisoformat(observation['obsTime'])
        if observed.tzinfo is None:
            raise ValueError()
        observed = observed.astimezone(ZoneInfo('Asia/Shanghai'))
        if observed.date() != current.date():
            raise HTTPException(502, '天气服务返回的观测不在北京时间当天，请使用现场记录')
        fields = {k: str(observation[k]) for k in ('text', 'temp', 'windScale', 'windDir')}
        if any(not v or len(v) > 100 for v in fields.values()):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise HTTPException(502, '天气服务返回数据不完整，请手动填写') from None
    warning = '这是指定位置的时点实况，不代表施工现场全天状况或日最高最低气温；请核对位置、观测时间和现场情况后保存确认。'
    if abs((current - observed).total_seconds()) > 7200:
        warning += ' 当前观测距查询时间超过两小时，请特别核实。'
    observed_at = observed.isoformat()
    text = (f"天气：{fields['text']}；气温：{fields['temp']} ℃；风力：{fields['windScale']} 级；风向：{fields['windDir']}。\n"
            f'来源：和风天气；查询位置：{location}；观测时间：{observed_at}（北京时间）。\n{warning}')
    return {'text': text, 'observed_at': observed_at, 'fetched_at': current.isoformat(), 'source': '和风天气',
            'source_url': 'https://www.qweather.com/', 'location': location, 'warning': warning}
