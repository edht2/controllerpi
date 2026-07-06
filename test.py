from app.config.config import state
from app.control.actuator import Actuator

print('Test Script For Actuator x')
relayIndex = [state[1]["sideWindows"][4]['actuatorRelayIndexExtend'],state[1]["sideWindows"][4]['actuatorRelayIndexRetract']]

print('relayIndex: ', relayIndex)
actuator = Actuator(relayIndex, 40)
actuator.extend()

