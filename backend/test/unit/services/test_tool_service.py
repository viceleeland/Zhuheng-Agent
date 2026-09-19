from __future__ import annotations

from types import SimpleNamespace

import pytest
from yuxi.agents.toolkits import service as tool_service


@pytest.mark.parametrize("requires_workspace_runtime", [False, True])
def test_get_tool_metadata_includes_config_guide(monkeypatch, requires_workspace_runtime):
    monkeypatch.setattr(tool_service, "_metadata_cache", [])

    fake_tool = SimpleNamespace(
        name="demo_tool",
        description="demo description",
        metadata={},
        args_schema=None,
    )
    fake_extra = SimpleNamespace(
        category="buildin",
        tags=["demo"],
        display_name="演示工具",
        config_guide="请先配置 DEMO_API_KEY",
        requires_workspace_runtime=requires_workspace_runtime,
    )

    monkeypatch.setattr(
        "yuxi.agents.toolkits.registry.get_all_tool_instances",
        lambda: [fake_tool],
    )
    monkeypatch.setattr(
        "yuxi.agents.toolkits.registry.get_all_extra_metadata",
        lambda: {"demo_tool": fake_extra},
    )

    result = tool_service.get_tool_metadata()

    assert result == [
        {
            "slug": "demo_tool",
            "name": "演示工具",
            "description": "demo description",
            "metadata": {},
            "args": [],
            "category": "buildin",
            "tags": ["demo"],
            "config_guide": "请先配置 DEMO_API_KEY",
            "requires_workspace_runtime": requires_workspace_runtime,
        }
    ]
