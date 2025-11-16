from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class ModuleTypeEnum(str, Enum):
    CORE = "core"
    MANAGER = "manager"
    PLUGIN = "plugin"
    UTIL = "util"
    MCP = "mcp"


@dataclass
class ModuleType:
    enum: ModuleTypeEnum
    name: str
    plural_name: str
    path: Path
    shows_in_workspace: bool = False

    def __init__(self, module_type: ModuleTypeEnum, plural_name: str, path: Optional[Path] = None, shows_in_workspace: bool = False) -> None:
        self.enum = module_type
        self.name = module_type.value
        self.plural_name = plural_name
        self.path = path if path else Path("./" + plural_name)
        self.shows_in_workspace = shows_in_workspace

class ModuleTypes:
    _instance = None

    def __new__(cls) -> "ModuleTypes":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self.module_types: dict[ModuleTypeEnum, ModuleType] = {
            ModuleTypeEnum.CORE: ModuleType(ModuleTypeEnum.CORE, "cores", shows_in_workspace=False),
            ModuleTypeEnum.MANAGER: ModuleType(ModuleTypeEnum.MANAGER, "managers", shows_in_workspace=True),
            ModuleTypeEnum.PLUGIN: ModuleType(ModuleTypeEnum.PLUGIN, "plugins", shows_in_workspace=True),
            ModuleTypeEnum.UTIL: ModuleType(ModuleTypeEnum.UTIL, "utils", shows_in_workspace=True),
            ModuleTypeEnum.MCP: ModuleType(ModuleTypeEnum.MCP, "mcps", shows_in_workspace=True),
        }
        self._initialized = True
    
    def get_module_type(self, name: ModuleTypeEnum | str) -> ModuleType:
        if isinstance(name, ModuleTypeEnum):
            key = name
        else:
            try:
                key = ModuleTypeEnum(name)
            except ValueError as exc:
                raise KeyError(f"Module type '{name}' not recognized.") from exc
        return self.module_types[key]
    
    def get_all_types(self) -> list[ModuleType]:
        return list(self.module_types.values())
    
    def get_all_type_names(self) -> list[str]:
        return [mt.name for mt in self.module_types.values()]