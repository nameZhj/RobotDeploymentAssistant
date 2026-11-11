from enum import Enum
from typing import Any, Dict
from src.core.config_loader import config_loader


class ControlAuthority(str, Enum):
    """
    Control authority states dynamically resolved from protocol configuration.
    """
    FREE = config_loader.get_control_authorities().get("free", "FREE")
    MANUAL = config_loader.get_control_authorities().get("manual", "MANUAL")
    CHOREO = config_loader.get_control_authorities().get("choreo", "CHOREO")


class FrameType(str, Enum):
    """
    LRMP frame types.
    """
    REQ = config_loader.get_frame_types().get("request", "REQ")
    RSP = config_loader.get_frame_types().get("response", "RSP")
    EVT = config_loader.get_frame_types().get("event", "EVT")
    ACK = config_loader.get_frame_types().get("acknowledge", "ACK")


class ProtocolTokens:
    """
    Protocol token lookup helper using config_loader.
    """
    @classmethod
    def target_delimiter(cls) -> str:
        return config_loader.get_protocol_meta().get("delimiter_target", "|")

    @classmethod
    def param_delimiter(cls) -> str:
        return config_loader.get_protocol_meta().get("delimiter_param", ",")

    @classmethod
    def broadcast_target(cls) -> str:
        return config_loader.get_target_rules().get("broadcast_token", "ALL")

    @classmethod
    def accepted_token(cls) -> str:
        return config_loader.get_frame_types().get("async_accepted_token", "ACCEPTED")

    @classmethod
    def ready_token(cls) -> str:
        return config_loader.get_frame_types().get("ready_state_token", "READY")

