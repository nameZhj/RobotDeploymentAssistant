# @file: src/protocol/__init__.py
# @brief: LRMP V1.0-R3 protocol, arbitration, timeline compiler, and Wi-Fi HTTP/callback exports.
# @exports: ControlAuthority, LrmpFrame, LrmpCodec, AuthorityStateMachine, TimelineLrmpCompiler, HttpTrajectoryClient, RobotHttpClient, RobotHttpResponse, HttpCallbackListener, SlamMappingClient

from src.protocol.authority_state_machine import AuthorityStateMachine, AuthorityTransitionResult
from src.protocol.http_callback_listener import HttpCallbackListener
from src.protocol.http_trajectory_client import HttpTrajectoryClient
from src.protocol.lrmp_codec import LrmpCodec, LrmpFrame, LrmpValidationError
from src.protocol.lrmp_constants import ControlAuthority, DANCE_ALIAS_TO_NAME, LRMP_COMMANDS
from src.protocol.robot_http_client import RobotHttpClient, RobotHttpResponse
from src.protocol.slam_mapping_client import MappingSessionState, SlamMappingClient
from src.protocol.timeline_lrmp_compiler import (
    CompiledShowPlan,
    PreDanceCheckReport,
    ScheduledLrmpCommand,
    TimelineLrmpCompiler,
)
from src.protocol.virtual_robot_server import HttpUploadReceipt, VirtualRobotServer

__all__ = [
    "ControlAuthority",
    "LRMP_COMMANDS",
    "DANCE_ALIAS_TO_NAME",
    "LrmpFrame",
    "LrmpCodec",
    "LrmpValidationError",
    "AuthorityStateMachine",
    "AuthorityTransitionResult",
    "ScheduledLrmpCommand",
    "CompiledShowPlan",
    "PreDanceCheckReport",
    "TimelineLrmpCompiler",
    "HttpTrajectoryClient",
    "RobotHttpClient",
    "RobotHttpResponse",
    "HttpCallbackListener",
    "HttpUploadReceipt",
    "VirtualRobotServer",
    "MappingSessionState",
    "SlamMappingClient",
]
