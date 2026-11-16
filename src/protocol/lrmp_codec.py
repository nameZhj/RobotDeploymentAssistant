# @file: src/protocol/lrmp_codec.py
# @brief: Strict LRMP V1.0-R3 ASCII frame encoder/decoder ("TARGET|COMMAND[,PARAM...]\n") and target expander.
# @exports: LrmpFrame, LrmpValidationError, LrmpCodec

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from src.protocol.lrmp_constants import DANCE_ALIAS_TO_NAME, DANCE_NAME_TO_ALIAS, is_valid_lrmp_command


class LrmpValidationError(ValueError):
    """Raised when an outgoing or incoming frame violates LRMP V1.0-R3 rules."""


@dataclass(frozen=True)
class LrmpFrame:
    """Parsed ASCII LRMP V1.0-R3 protocol frame."""

    target: str
    command: str
    params: Tuple[str, ...] = ()

    def to_ascii(self) -> str:
        """Render canonical TARGET|COMMAND[,PARAM...]\\n line."""
        cmd_part = self.command if not self.params else f"{self.command},{','.join(self.params)}"
        return f"{self.target}|{cmd_part}\n"

    def to_bytes(self) -> bytes:
        return self.to_ascii().encode("utf-8")


class LrmpCodec:
    """Validates, encodes, decodes, and expands multi-robot LRMP ASCII frames."""

    @staticmethod
    def encode(target: str, command: str, *params: object) -> bytes:
        """Encode and strictly validate TARGET|COMMAND[,PARAM...]\\n frame bytes."""
        clean_target = (target or "").strip().upper()
        if not clean_target:
            raise LrmpValidationError("Target identifier must not be empty")
        clean_cmd = (command or "").strip().upper()
        if not is_valid_lrmp_command(clean_cmd):
            raise LrmpValidationError(f"Unsupported LRMP V1.0-R3 command: {command}")

        str_params = tuple(str(p).strip() for p in params if str(p).strip() != "")
        LrmpCodec._validate_params(clean_cmd, str_params)
        return LrmpFrame(target=clean_target, command=clean_cmd, params=str_params).to_bytes()

    @staticmethod
    def encode_move(target: str, vx: float, vy: float, vyaw: float, duration_s: float) -> bytes:
        """Encode validated TARGET|MOVE,forward,left,turn,duration_s frame per YAML axis bounds."""
        for name, val in (("vx", vx), ("vy", vy), ("vyaw", vyaw)):
            if not -1.0 <= val <= 1.0:
                raise LrmpValidationError(f"MOVE {name}={val} out of documented range [-1.0, 1.0]")
        if not 0.05 <= duration_s <= 15.0:
            raise LrmpValidationError(f"MOVE duration_s={duration_s} out of range [0.05, 15.0]")
        return LrmpCodec.encode(target, "MOVE", f"{vx:.3f}", f"{vy:.3f}", f"{vyaw:.3f}", f"{duration_s:.2f}")

    @staticmethod
    def resolve_dance_alias(code_or_name: str) -> str:
        """Normalize a Chinese dance name or official alias into the LRMP dance identifier."""
        token = (code_or_name or "").strip()
        if token in DANCE_ALIAS_TO_NAME:
            return token
        if token in DANCE_NAME_TO_ALIAS:
            return DANCE_NAME_TO_ALIAS[token]
        return token.upper() if token else ""

    @staticmethod
    def expand_targets(targets: Sequence[str], command: str, *params: object) -> List[bytes]:
        """Expand multi-robot selection into per-robot TARGET|CMD frames per LRMP §6."""
        if not targets:
            raise LrmpValidationError("Selected robot target list is empty")
        return [LrmpCodec.encode(t, command, *params) for t in targets]

    @staticmethod
    def decode(raw_line: str) -> LrmpFrame:
        """Parse an ASCII TARGET|COMMAND[,PARAM...] frame line."""
        text = (raw_line or "").strip()
        if "|" not in text:
            raise LrmpValidationError(f"Missing '|' delimiter in frame: {raw_line!r}")
        target_part, cmd_body = text.split("|", 1)
        tokens = [tok.strip() for tok in cmd_body.split(",") if tok.strip() != ""]
        if not tokens:
            raise LrmpValidationError(f"Missing command in frame: {raw_line!r}")
        cmd = tokens[0].upper()
        if not is_valid_lrmp_command(cmd):
            raise LrmpValidationError(f"Unknown LRMP command in frame: {cmd}")
        return LrmpFrame(target=target_part.strip().upper(), command=cmd, params=tuple(tokens[1:]))

    @staticmethod
    def _validate_params(cmd: str, params: Iterable[str]) -> None:
        p_list = list(params)
        if cmd == "MOVE" and len(p_list) != 4:
            raise LrmpValidationError("MOVE requires 4 parameters: forward,left,turn,duration_s")
        if cmd == "DANCE" and len(p_list) < 1:
            raise LrmpValidationError("DANCE requires action_name parameter")
        if cmd == "PREP" and len(p_list) < 2:
            raise LrmpValidationError("PREP requires plan_id,run_id parameters")
        if cmd == "PLAY" and len(p_list) < 2:
            raise LrmpValidationError("PLAY requires run_id,t0_ms parameters")
        if cmd == "BARRIER" and len(p_list) < 3:
            raise LrmpValidationError("BARRIER requires run_id,barrier_id,release_ms parameters")
