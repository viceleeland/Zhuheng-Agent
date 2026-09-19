"""天气实况权限、日期边界与来源信息测试。"""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import HTTPException
from yuxi.services.changwei_weather import get_task_weather


def fixture(period=None, assignee='u', owner='owner'):
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    task = SimpleNamespace(project_id='p', period=period or today, kind='supervision_log', content={'modules': [{'name': '天气信息', 'assignee': assignee}]})
    return SimpleNamespace(task=AsyncMock(return_value=task), project=AsyncMock(return_value=SimpleNamespace(owner_uid=owner)))


def call(repo, location='101010100'):
    return asyncio.run(get_task_weather(repo, 'u', 't', location))


@pytest.mark.parametrize('period', ['2020-01-01', '2026年9月19日', '2026-09'])
def test_history_or_unstructured_period_rejected(period):
    with pytest.raises(HTTPException) as exc:
        call(fixture(period))
    assert exc.value.status_code == 422


def test_unassigned_member_cannot_query():
    with pytest.raises(HTTPException) as exc:
        call(fixture(assignee='other'))
    assert exc.value.status_code == 403


def test_foreign_task_denied_before_weather_request():
    repo = fixture()
    repo.task.side_effect = HTTPException(404)
    with pytest.raises(HTTPException) as exc:
        call(repo)
    assert exc.value.status_code == 404
    repo.project.assert_not_called()


@pytest.mark.parametrize('location', ['https://evil.example/', '181,29', '118,91', '118.123,29', ''])
def test_bad_location_rejected(location):
    with pytest.raises(HTTPException) as exc:
        call(fixture(), location)
    assert exc.value.status_code == 422


def test_weather_keeps_observation_time_and_warning(monkeypatch):
    monkeypatch.setenv('QWEATHER_API_HOST', 'test.qweatherapi.com')
    monkeypatch.setenv('QWEATHER_API_KEY', 'test-key')
    observed = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    response = httpx.Response(200, json={'code': '200', 'now': {'obsTime': observed, 'text': '晴', 'temp': '26', 'windScale': '2', 'windDir': '东风'}}, request=httpx.Request('GET', 'https://test.qweatherapi.com/v7/weather/now'))
    client = AsyncMock()
    client.get.return_value = response
    client.__aenter__.return_value = client
    with patch('yuxi.services.changwei_weather.httpx.AsyncClient', return_value=client):
        result = call(fixture())
    assert result['observed_at'] == observed
    assert '26 ℃' in result['text'] and '不代表' in result['text']
    assert result['source'] == '和风天气'
    assert 'test-key' not in str(result)
    assert client.get.call_args.kwargs['headers'] == {'X-QW-Api-Key': 'test-key'}


def test_place_name_is_resolved_before_weather(monkeypatch):
    monkeypatch.setenv('QWEATHER_API_HOST', 'test.qweatherapi.com')
    monkeypatch.setenv('QWEATHER_API_KEY', 'test-key')
    observed = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    lookup = httpx.Response(200, json={'code': '200', 'location': [{
        'id': '101221006', 'name': '歙县', 'adm2': '黄山市', 'adm1': '安徽省'
    }]}, request=httpx.Request('GET', 'https://test.qweatherapi.com/geo/v2/city/lookup'))
    weather = httpx.Response(200, json={'code': '200', 'now': {
        'obsTime': observed, 'text': '晴', 'temp': '26', 'windScale': '2', 'windDir': '东风'
    }}, request=httpx.Request('GET', 'https://test.qweatherapi.com/v7/weather/now'))
    client = AsyncMock()
    client.get.side_effect = [lookup, weather]
    client.__aenter__.return_value = client
    with patch('yuxi.services.changwei_weather.httpx.AsyncClient', return_value=client):
        result = call(fixture(), '歙县')
    assert result['location'] == '歙县 / 黄山市 / 安徽省'
    assert result['location_id'] == '101221006'
    assert client.get.call_args_list[0].kwargs['params']['location'] == '歙县'
    assert client.get.call_args_list[1].kwargs['params']['location'] == '101221006'


def test_malformed_place_lookup_is_rejected_without_internal_error(monkeypatch):
    monkeypatch.setenv('QWEATHER_API_HOST', 'test.qweatherapi.com')
    monkeypatch.setenv('QWEATHER_API_KEY', 'test-key')
    response = httpx.Response(200, json=[], request=httpx.Request('GET', 'https://test.qweatherapi.com/geo/v2/city/lookup'))
    client = AsyncMock()
    client.get.return_value = response
    client.__aenter__.return_value = client
    with patch('yuxi.services.changwei_weather.httpx.AsyncClient', return_value=client):
        with pytest.raises(HTTPException) as exc:
            call(fixture(), '歙县')
    assert exc.value.status_code == 502
    assert '天气服务暂不可用' in exc.value.detail


def test_yesterday_observation_not_used_for_today(monkeypatch):
    monkeypatch.setenv('QWEATHER_API_HOST', 'test.qweatherapi.com')
    monkeypatch.setenv('QWEATHER_API_KEY', 'test-key')
    observed = (datetime.now(ZoneInfo('Asia/Shanghai')) - timedelta(days=1)).isoformat()
    response = httpx.Response(200, json={'code': '200', 'now': {'obsTime': observed}}, request=httpx.Request('GET', 'https://test.qweatherapi.com/v7/weather/now'))
    client = AsyncMock()
    client.get.return_value = response
    client.__aenter__.return_value = client
    with patch('yuxi.services.changwei_weather.httpx.AsyncClient', return_value=client):
        with pytest.raises(HTTPException) as exc:
            call(fixture())
    assert exc.value.status_code == 502


def test_provider_failure_does_not_expose_request_secrets(monkeypatch):
    monkeypatch.setenv('QWEATHER_API_HOST', 'test.qweatherapi.com')
    monkeypatch.setenv('QWEATHER_API_KEY', 'test-key')
    client = AsyncMock()
    client.get.side_effect = httpx.ConnectError('sensitive transport message')
    client.__aenter__.return_value = client
    with patch('yuxi.services.changwei_weather.httpx.AsyncClient', return_value=client):
        with pytest.raises(HTTPException) as exc:
            call(fixture())
    assert exc.value.status_code == 502
    assert 'sensitive' not in exc.value.detail


def test_missing_configuration_is_explicit(monkeypatch):
    monkeypatch.delenv('QWEATHER_API_KEY', raising=False)
    with pytest.raises(HTTPException) as exc:
        call(fixture())
    assert exc.value.status_code == 503


@pytest.mark.parametrize('payload', [{'code': '401'}, {'code': '200', 'now': {}}, {'code': '200', 'now': {'obsTime': '2026-09-19T12:00:00'}}, []])
def test_malformed_weather_response_rejected(monkeypatch, payload):
    monkeypatch.setenv('QWEATHER_API_HOST', 'region.test.qweatherapi.com')
    monkeypatch.setenv('QWEATHER_API_KEY', 'test-key')
    response = httpx.Response(200, json=payload, request=httpx.Request('GET', 'https://region.test.qweatherapi.com/v7/weather/now'))
    client = AsyncMock()
    client.get.return_value = response
    client.__aenter__.return_value = client
    with patch('yuxi.services.changwei_weather.httpx.AsyncClient', return_value=client):
        with pytest.raises(HTTPException) as exc:
            call(fixture())
    assert exc.value.status_code == 502


@pytest.mark.parametrize('error', [httpx.ReadTimeout('timeout'), httpx.ConnectError('offline')])
def test_transient_weather_transport_is_retried_once(monkeypatch, error):
    monkeypatch.setenv('QWEATHER_API_HOST', 'test.qweatherapi.com')
    monkeypatch.setenv('QWEATHER_API_KEY', 'test-key')
    response = httpx.Response(200, json={'code': '200', 'now': {
        'obsTime': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'text': '晴', 'temp': '26', 'windScale': '2', 'windDir': '东风',
    }}, request=httpx.Request('GET', 'https://test.qweatherapi.com/v7/weather/now'))
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.side_effect = [error, response]
    with patch('yuxi.services.changwei_weather.httpx.AsyncClient', return_value=client):
        assert call(fixture())['source'] == '和风天气'
    assert client.get.await_count == 2


def test_permanent_transport_failure_is_bounded(monkeypatch):
    monkeypatch.setenv('QWEATHER_API_HOST', 'test.qweatherapi.com')
    monkeypatch.setenv('QWEATHER_API_KEY', 'test-key')
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.side_effect = httpx.ReadTimeout('secret transport detail')
    with patch('yuxi.services.changwei_weather.httpx.AsyncClient', return_value=client):
        with pytest.raises(HTTPException) as error:
            call(fixture())
    assert error.value.status_code == 502
    assert client.get.await_count == 2
    assert 'secret' not in error.value.detail


@pytest.mark.parametrize('proxy', ['', 'http://proxy.example:8080'])
def test_weather_deployment_proxy_is_explicit(monkeypatch, proxy):
    monkeypatch.setenv('QWEATHER_API_HOST', 'test.qweatherapi.com')
    monkeypatch.setenv('QWEATHER_API_KEY', 'test-key')
    monkeypatch.setenv('QWEATHER_HTTP_PROXY', proxy)
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.side_effect = httpx.ConnectError('offline')
    with patch('yuxi.services.changwei_weather.httpx.AsyncClient', return_value=client) as factory:
        with pytest.raises(HTTPException):
            call(fixture())
    assert factory.call_args.kwargs['proxy'] == (proxy or None)


@pytest.mark.parametrize('proxy', [None, 'http://user:secret@proxy.example:8080'])
def test_weather_proxy_applies_to_lookup_and_observation_without_leaking(monkeypatch, proxy):
    """一个显式代理客户端完成地名和实况请求，业务结果不泄露代理凭据。"""
    monkeypatch.setenv('QWEATHER_API_HOST', 'test.qweatherapi.com')
    monkeypatch.setenv('QWEATHER_API_KEY', 'test-key')
    if proxy is None:
        monkeypatch.delenv('QWEATHER_HTTP_PROXY', raising=False)
    else:
        monkeypatch.setenv('QWEATHER_HTTP_PROXY', proxy)
    observed = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    payloads = [
        {'code': '200', 'location': [{'id': '101221006', 'name': '歙县', 'adm2': '黄山市', 'adm1': '安徽省'}]},
        {'code': '200', 'now': {'obsTime': observed, 'text': '晴', 'temp': '26', 'windScale': '2', 'windDir': '东风'}},
    ]
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.side_effect = [httpx.Response(200, json=payload,
                                           request=httpx.Request('GET', 'https://test.qweatherapi.com/'))
                              for payload in payloads]
    with patch('yuxi.services.changwei_weather.httpx.AsyncClient', return_value=client) as factory:
        result = call(fixture(), '歙县')
    factory.assert_called_once()
    assert factory.call_args.kwargs['proxy'] == proxy
    assert factory.call_args.kwargs['follow_redirects'] is False
    assert [entry.args[0] for entry in client.get.call_args_list] == [
        'https://test.qweatherapi.com/geo/v2/city/lookup', 'https://test.qweatherapi.com/v7/weather/now']
    assert result['location_id'] == '101221006' and result['observed_at'] == observed
    assert 'secret' not in str(result) and 'test-key' not in str(result)


def test_weather_proxy_failure_keeps_error_sanitized_and_bounded(monkeypatch):
    """代理连接失败只重试一次，不把代理账户写入用户错误。"""
    monkeypatch.setenv('QWEATHER_API_HOST', 'test.qweatherapi.com')
    monkeypatch.setenv('QWEATHER_API_KEY', 'test-key')
    proxy = 'http://user:secret@proxy.example:8080'
    monkeypatch.setenv('QWEATHER_HTTP_PROXY', proxy)
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.side_effect = httpx.ProxyError(proxy)
    with patch('yuxi.services.changwei_weather.httpx.AsyncClient', return_value=client):
        with pytest.raises(HTTPException) as error:
            call(fixture(), '歙县')
    assert error.value.status_code == 502
    assert client.get.await_count == 2
    assert 'secret' not in error.value.detail and 'proxy.example' not in error.value.detail
