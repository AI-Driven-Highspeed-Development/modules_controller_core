from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class ModuleLayer(str, Enum):
    """Layer classification for modules.
    
    - FOUNDATION: Bootstrap modules required for framework initialization
    - RUNTIME: Production application modules
    - DEV: Development-only tools and utilities
    """
    FOUNDATION = "foundation"
    RUNTIME = "runtime"
    DEV = "dev"
    
    @classmethod
    def from_string(cls, value: str | None) -> "ModuleLayer | None":
        """Convert string to ModuleLayer, returning None for invalid values."""
        if value is None:
            return None
        try:
            return cls(value.lower())
        except ValueError:
            return None
    
    @classmethod
    def validate(cls, value: str | None) -> bool:
        """Check if a string is a valid layer value."""
        if value is None:
            return False
        return value.lower() in [layer.value for layer in cls]
    
    @classmethod
    def get_valid_layers_for_type(cls, module_type: "ModuleTypeEnum") -> list["ModuleLayer"]:
        """Get valid layers for a given module type.
        
        Cores can only be FOUNDATION or DEV (never RUNTIME).
        Other types can be any layer.
        """
        if module_type == ModuleTypeEnum.CORE:
            return [cls.FOUNDATION, cls.DEV]
        return list(cls)


class ModuleTypeEnum(str, Enum):
    CORE = ("core", "cores")
    MANAGER = ("manager", "managers")
    PLUGIN = ("plugin", "plugins")
    UTIL = ("util", "utils")
    MCP = ("mcp", "mcps")

    def __new__(cls, singular: str, plural: str) -> "ModuleTypeEnum":
        obj = str.__new__(cls, singular)
        obj._value_ = singular
        obj._plural = plural
        return obj

    @property
    def plural(self) -> str:
        return self._plural


@dataclass
class ModuleType:
    enum: ModuleTypeEnum
    name: str
    plural_name: str
    path: Path
    shows_in_workspace: bool = False

    def __init__(
        self,
        module_type: ModuleTypeEnum,
        plural_name: str,
        path: Optional[Path] = None,
        shows_in_workspace: bool = False,
    ) -> None:
        self.enum = module_type
        self.name = module_type.value
        self.plural_name = plural_name
        self.path = path if path else Path("./" + plural_name)
        self.shows_in_workspace = shows_in_workspace


class ModuleTypes:
    _instances: dict[Path, "ModuleTypes"] = {}

    def __new__(cls, root_path: Optional[Path] = None) -> "ModuleTypes":
        root = (root_path or Path.cwd()).resolve()
        instance = cls._instances.get(root)
        if instance is None:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instances[root] = instance
        return instance

    def __init__(self, root_path: Optional[Path] = None) -> None:
        root = (root_path or Path.cwd()).resolve()
        if getattr(self, "_initialized", False) and getattr(self, "root_path", None) == root:
            return
        self.root_path = root
        self.module_types: dict[ModuleTypeEnum, ModuleType] = {
            ModuleTypeEnum.CORE: ModuleType(
                ModuleTypeEnum.CORE,
                ModuleTypeEnum.CORE.plural,
                path=root / ModuleTypeEnum.CORE.plural,
                shows_in_workspace=False,
            ),
            ModuleTypeEnum.MANAGER: ModuleType(
                ModuleTypeEnum.MANAGER,
                ModuleTypeEnum.MANAGER.plural,
                path=root / ModuleTypeEnum.MANAGER.plural,
                shows_in_workspace=True,
            ),
            ModuleTypeEnum.PLUGIN: ModuleType(
                ModuleTypeEnum.PLUGIN,
                ModuleTypeEnum.PLUGIN.plural,
                path=root / ModuleTypeEnum.PLUGIN.plural,
                shows_in_workspace=True,
            ),
            ModuleTypeEnum.UTIL: ModuleType(
                ModuleTypeEnum.UTIL,
                ModuleTypeEnum.UTIL.plural,
                path=root / ModuleTypeEnum.UTIL.plural,
                shows_in_workspace=True,
            ),
            ModuleTypeEnum.MCP: ModuleType(
                ModuleTypeEnum.MCP,
                ModuleTypeEnum.MCP.plural,
                path=root / ModuleTypeEnum.MCP.plural,
                shows_in_workspace=True,
            ),
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
