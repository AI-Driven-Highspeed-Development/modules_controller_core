from managers.config_manager import ConfigManager

class ModulesControllerCore:
    
    def __init__(self):
        self.cm = ConfigManager()
        self.config = self.cm.config.modules_controller_core
        
    def display_module_name(self):
        print("Module Name:", self.config.module_name)