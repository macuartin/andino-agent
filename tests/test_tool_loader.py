from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import pytest

from andino.tool_loader import load_tools


class TestLoadTools:
    def test_empty_string(self):
        assert load_tools("") == []

    def test_none(self):
        assert load_tools(None) == []

    def test_whitespace_only(self):
        assert load_tools("   ") == []

    def test_valid_colon_format(self):
        mock_module = types.ModuleType("fake_mod")
        mock_tool = MagicMock()
        mock_tool.tool_name = "my_tool"
        mock_module.my_tool = mock_tool

        with patch("andino.tool_loader.importlib.import_module", return_value=mock_module):
            tools = load_tools("fake_mod:my_tool")
        assert len(tools) == 1
        assert tools[0] is mock_tool

    def test_valid_dot_format(self):
        mock_module = types.ModuleType("fake.mod")
        mock_tool = MagicMock()
        mock_tool.tool_name = "func"
        mock_module.func = mock_tool

        with patch("andino.tool_loader.importlib.import_module", return_value=mock_module):
            tools = load_tools("fake.mod.func")
        assert len(tools) == 1
        assert tools[0] is mock_tool

    def test_multiple_tools(self):
        mock_module = types.ModuleType("mod")
        tool_a = MagicMock(tool_name="a")
        tool_b = MagicMock(tool_name="b")
        mock_module.a = tool_a
        mock_module.b = tool_b

        with patch("andino.tool_loader.importlib.import_module", return_value=mock_module):
            tools = load_tools("mod:a,mod:b")
        assert len(tools) == 2

    def test_invalid_format_no_separator(self):
        with pytest.raises(ValueError, match="Invalid tool reference"):
            load_tools("just_a_name")

    def test_missing_module(self):
        with pytest.raises(ModuleNotFoundError):
            load_tools("nonexistent.module:thing")

    def test_missing_attribute(self):
        mock_module = types.ModuleType("real_mod")
        with patch("andino.tool_loader.importlib.import_module", return_value=mock_module):
            with pytest.raises(ValueError, match="not found in module"):
                load_tools("real_mod:missing_attr")

    def test_old_style_tool_returns_module(self):
        mock_module = types.ModuleType("old_mod")
        mock_module.TOOL_SPEC = {"name": "old_tool"}

        def plain_func():
            pass

        mock_module.old_tool = plain_func

        with patch("andino.tool_loader.importlib.import_module", return_value=mock_module):
            tools = load_tools("old_mod:old_tool")
        assert tools[0] is mock_module

    def test_whitespace_in_refs(self):
        mock_module = types.ModuleType("mod")
        mock_tool = MagicMock(tool_name="t")
        mock_module.t = mock_tool

        with patch("andino.tool_loader.importlib.import_module", return_value=mock_module):
            tools = load_tools("  mod:t  ,  mod:t  ")
        assert len(tools) == 2
