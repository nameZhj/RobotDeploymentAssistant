from typing import Any, Dict, List, Optional


class SerialCommandHelper:
    """群控与运控协议帧构造器"""

    @staticmethod
    def build_frame(target: str, command: str) -> str:
        return f"{target.strip().upper()}|{command.strip()}\n"

    @staticmethod
    def build_motion_command(action_type: str, step: float = 2.0) -> Optional[str]:
        action_map = {
            "forward": f"FORWARD,{step}",
            "backward": f"BACKWARD,{step}",
            "move_left": f"MOVE_LEFT,{step}",
            "move_right": f"MOVE_RIGHT,{step}",
            "turn_left": f"TURN_LEFT,{step}",
            "turn_right": f"TURN_RIGHT,{step}",
            "stand": "STAND",
            "gait": "GAIT",
            "passive": "PASSIVE",
            "stop": "STOP",
            "emergency": "EMERGENCY",
        }
        return action_map.get(action_type.lower())


serial_command_helper = SerialCommandHelper()

