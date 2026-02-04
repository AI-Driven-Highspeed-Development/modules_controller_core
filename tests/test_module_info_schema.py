"""Tests for ModuleInfo schema after monorepo migration.

This validates that ModuleInfo has:
- is_mcp: bool field for MCP modules
- folder: str field for parent folder name (cores, managers, etc.)
- Does NOT have module_type field (deprecated)
"""

import pytest
from dataclasses import fields
from pathlib import Path

from modules_controller_core import ModuleInfo
from modules_controller_core.module_types import ModuleLayer


class TestModuleInfoSchema:
    """Test ModuleInfo dataclass schema matches post-migration expectations."""

    def test_module_info_has_is_mcp_field(self):
        """ModuleInfo must have 'is_mcp' field."""
        field_names = {f.name for f in fields(ModuleInfo)}
        assert "is_mcp" in field_names

    def test_module_info_has_folder_field(self):
        """ModuleInfo must have 'folder' field."""
        field_names = {f.name for f in fields(ModuleInfo)}
        assert "folder" in field_names

    def test_module_info_does_not_have_module_type(self):
        """ModuleInfo must NOT have deprecated 'module_type' field."""
        field_names = {f.name for f in fields(ModuleInfo)}
        assert "module_type" not in field_names, (
            "module_type is deprecated. Use 'folder' for path-based type detection "
            "and 'is_mcp' for MCP module flag."
        )

    def test_module_info_has_required_fields(self):
        """ModuleInfo must have all required fields for monorepo migration."""
        field_names = {f.name for f in fields(ModuleInfo)}
        required_fields = {
            "name",
            "version",
            "folder",
            "path",
            "is_mcp",
            "repo_url",
            "requirements",
            "issues",
            "shows_in_workspace",
            "layer",
        }
        assert required_fields <= field_names


class TestModuleInfoIsMcpField:
    """Test the is_mcp field behavior."""

    def test_is_mcp_defaults_to_false(self):
        """is_mcp should default to False when not specified."""
        module = ModuleInfo(
            name="test_module",
            version="1.0.0",
            folder="managers",
            path=Path("/test"),
        )
        assert module.is_mcp is False

    def test_is_mcp_can_be_set_true(self):
        """is_mcp can be explicitly set to True."""
        module = ModuleInfo(
            name="test_mcp",
            version="1.0.0",
            folder="mcps",
            path=Path("/test"),
            is_mcp=True,
        )
        assert module.is_mcp is True

    def test_is_mcp_is_independent_of_folder(self):
        """is_mcp should be independent of folder name.
        
        A module in mcps/ folder is NOT automatically an MCP.
        The is_mcp flag comes from pyproject.toml [tool.adhd] mcp = true.
        """
        # Module in mcps/ folder without mcp=true
        module_in_mcps_not_mcp = ModuleInfo(
            name="cli_tool",
            version="1.0.0",
            folder="mcps",
            path=Path("/test"),
            is_mcp=False,
        )
        assert module_in_mcps_not_mcp.is_mcp is False
        
        # Module in managers/ folder with mcp=true (hypothetical edge case)
        module_in_managers_is_mcp = ModuleInfo(
            name="manager_mcp",
            version="1.0.0",
            folder="managers",
            path=Path("/test"),
            is_mcp=True,
        )
        assert module_in_managers_is_mcp.is_mcp is True


class TestModuleInfoFolderField:
    """Test the folder field behavior."""

    def test_folder_accepts_valid_folders(self):
        """folder field should accept standard module folder names."""
        valid_folders = ["cores", "managers", "utils", "plugins", "mcps"]
        
        for folder in valid_folders:
            module = ModuleInfo(
                name="test_module",
                version="1.0.0",
                folder=folder,
                path=Path("/test"),
            )
            assert module.folder == folder

    def test_folder_is_string_type(self):
        """folder field should be a string."""
        module = ModuleInfo(
            name="test_module",
            version="1.0.0",
            folder="managers",
            path=Path("/test"),
        )
        assert isinstance(module.folder, str)

    def test_folder_used_instead_of_deprecated_module_type(self):
        """folder provides the same info that module_type used to provide."""
        # Previously: module_type="manager" 
        # Now: folder="managers"
        module = ModuleInfo(
            name="config_manager",
            version="1.0.0",
            folder="managers",
            path=Path("/project/managers/config_manager"),
        )
        
        # Can determine module type from folder
        assert module.folder == "managers"
        # And from path
        assert "managers" in str(module.path)


class TestModuleInfoLayerField:
    """Test the layer field for module classification."""

    def test_layer_field_accepts_module_layer_enum(self):
        """layer field should accept ModuleLayer enum values."""
        for layer in ModuleLayer:
            module = ModuleInfo(
                name="test_module",
                version="1.0.0",
                folder="managers",
                path=Path("/test"),
                layer=layer,
            )
            assert module.layer == layer

    def test_layer_field_can_be_none(self):
        """layer field should be optional (can be None)."""
        module = ModuleInfo(
            name="test_module",
            version="1.0.0",
            folder="managers",
            path=Path("/test"),
            layer=None,
        )
        assert module.layer is None

    def test_layer_field_defaults_to_none(self):
        """layer field should default to None when not specified."""
        module = ModuleInfo(
            name="test_module",
            version="1.0.0",
            folder="managers",
            path=Path("/test"),
        )
        assert module.layer is None


class TestModuleInfoUtilityMethods:
    """Test utility methods on ModuleInfo."""

    def test_initializer_path(self, tmp_path: Path):
        """initializer_path should return path to __init__.py."""
        module = ModuleInfo(
            name="test_module",
            version="1.0.0",
            folder="managers",
            path=tmp_path,
        )
        expected = tmp_path / "__init__.py"
        assert module.initializer_path() == expected

    def test_has_initializer_when_exists(self, tmp_path: Path):
        """has_initializer should return True when __init__.py exists."""
        (tmp_path / "__init__.py").write_text("")
        
        module = ModuleInfo(
            name="test_module",
            version="1.0.0",
            folder="managers",
            path=tmp_path,
        )
        assert module.has_initializer() is True

    def test_has_initializer_when_missing(self, tmp_path: Path):
        """has_initializer should return False when __init__.py doesn't exist."""
        module = ModuleInfo(
            name="test_module",
            version="1.0.0",
            folder="managers",
            path=tmp_path,
        )
        assert module.has_initializer() is False

    def test_refresh_script_path(self, tmp_path: Path):
        """refresh_script_path should return path to refresh.py."""
        module = ModuleInfo(
            name="test_module",
            version="1.0.0",
            folder="managers",
            path=tmp_path,
        )
        expected = tmp_path / "refresh.py"
        assert module.refresh_script_path() == expected

    def test_has_refresh_script_when_exists(self, tmp_path: Path):
        """has_refresh_script should return True when refresh.py exists."""
        (tmp_path / "refresh.py").write_text("")
        
        module = ModuleInfo(
            name="test_module",
            version="1.0.0",
            folder="managers",
            path=tmp_path,
        )
        assert module.has_refresh_script() is True

    def test_default_shows_in_workspace_for_cores(self):
        """cores folder should default to NOT showing in workspace."""
        module = ModuleInfo(
            name="test_core",
            version="1.0.0",
            folder="cores",
            path=Path("/test"),
        )
        assert module.default_shows_in_workspace() is False

    def test_default_shows_in_workspace_for_managers(self):
        """managers folder should default to showing in workspace."""
        module = ModuleInfo(
            name="test_manager",
            version="1.0.0",
            folder="managers",
            path=Path("/test"),
        )
        assert module.default_shows_in_workspace() is True
