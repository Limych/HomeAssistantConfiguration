from base import Base
import globals
from globals import PEOPLE

class PresenceHelper(Base):
    
    def initialize(self) -> None:
        """Initialize."""
        super().initialize()

    def anyone_home(self, **kwargs:dict) -> bool:
        limych = self.get_state(PEOPLE['Limych']['device_tracker'])
        if (limych == "Just arrived" or limych == "Home"):
            return True
        else:
            return False
            
    def anyone_just_arrived(self, **kwargs:dict) -> bool:
        limych = self.get_state(PEOPLE['Limych']['device_tracker'])
        if (limych == "Just arrived"):
            return True
        else:
            return False

    def limych_home_alone(self, **kwargs:dict) -> bool:
        limych = self.get_state(PEOPLE['Limych']['device_tracker'])
        if (limych == "Just arrived" or limych == "Home"):
            return True
        else:
            return False