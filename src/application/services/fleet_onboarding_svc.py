import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from src.core.config_loader import config_loader
from src.core.event_bus import event_bus
from src.infrastructure.serial.lora_serial_port import lora_port

logger = logging.getLogger("FleetOnboardingService")


@dataclass
class DiscoveredNode:
    """Represents a discovered or onboarded device node in the fleet."""
    node_id: str
    alias: str = ""
    ip: str = ""
    is_online: bool = True
    authority: str = "FREE"
    machine_digest: str = ""
    license_status: str = "UNKNOWN"
    last_seen: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)


class FleetOnboardingService:
    """
    Orchestrates device discovery, alias binding, and fleet topology inspection.
    Enforces privacy by masking hardware fingerprint IDs to digests only.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._nodes: Dict[str, DiscoveredNode] = {}
        self._target_delim = config_loader.get_target_delimiter()
        self._param_delim = config_loader.get_param_delimiter()
        self._broadcast_token = config_loader.get_broadcast_token()
        self._gw_prefix = config_loader.get_unbound_gateway_prefix()

        # Subscribe to device events and telemetry
        event_bus.subscribe("LRMP_FRAME_RECEIVED", self._on_frame_received)

    @staticmethod
    def mask_machine_id(raw_id: str) -> str:
        """Mask full hardware serial/machine ID to privacy-preserving digest."""
        clean = (raw_id or "").strip()
        if len(clean) <= 8:
            return clean
        return f"{clean[:8]}...{clean[-4:]}"

    def trigger_discovery(self) -> bool:
        """Broadcast DISCOVER request across the RF network."""
        discover_meta = config_loader.find_command_meta("DISCOVER")
        cmd_name = discover_meta.get("cmd", "DISCOVER") if discover_meta else "DISCOVER"
        raw_cmd = f"{self._broadcast_token}{self._target_delim}{cmd_name}"
        logger.info(f"Triggering fleet discovery: {raw_cmd}")
        return lora_port.send_raw(raw_cmd, src_id="CTRL", dst_id=self._broadcast_token)

    def bind_alias(self, node_id: str, alias: str) -> bool:
        """Bind a friendly alias (e.g. 'A') to a specific discovered node."""
        clean_alias = alias.strip().upper()
        bind_meta = config_loader.find_command_meta("BIND")
        cmd_name = bind_meta.get("cmd", "BIND") if bind_meta else "BIND"
        raw_cmd = f"{node_id}{self._target_delim}{cmd_name}{self._param_delim}{clean_alias}"

        ok = lora_port.send_raw(raw_cmd, src_id="CTRL", dst_id=node_id)
        if ok:
            with self._lock:
                if node_id in self._nodes:
                    node = self._nodes[node_id]
                    node.alias = clean_alias
                    self._nodes[clean_alias] = node
            event_bus.publish("FLEET_TOPOLOGY_UPDATED", self.list_nodes())
        return ok

    def send_setup(self, target: str, config_param: str) -> bool:
        """Send SETUP configuration (e.g. channel or cluster role) to target."""
        setup_meta = config_loader.find_command_meta("SETUP")
        cmd_name = setup_meta.get("cmd", "SETUP") if setup_meta else "SETUP"
        raw_cmd = f"{target}{self._target_delim}{cmd_name}{self._param_delim}{config_param}"
        return lora_port.send_raw(raw_cmd, src_id="CTRL", dst_id=target)

    def query_status(self, target: str, subkey: Optional[str] = None) -> bool:
        """Query status parameters from target device."""
        status_meta = config_loader.find_command_meta("STATUS")
        cmd_name = status_meta.get("cmd", "STATUS") if status_meta else "STATUS"
        payload = f"{cmd_name}{self._param_delim}{subkey}" if subkey else cmd_name
        raw_cmd = f"{target}{self._target_delim}{payload}"
        return lora_port.send_raw(raw_cmd, src_id="CTRL", dst_id=target)

    def register_node(self, node_id: str, alias: str = "", ip: str = "", raw_id: str = "") -> DiscoveredNode:
        """Register or update an onboarded node with masked digest."""
        digest = self.mask_machine_id(raw_id)
        with self._lock:
            node = DiscoveredNode(node_id=node_id, alias=alias or node_id, ip=ip, machine_digest=digest)
            self._nodes[node_id] = node
            if alias:
                self._nodes[alias] = node
        event_bus.publish("FLEET_TOPOLOGY_UPDATED", self.list_nodes())
        return node

    def list_nodes(self) -> List[Dict[str, Any]]:
        """Return list of distinct discovered nodes with masked IDs."""
        with self._lock:
            seen_ids = set()
            results = []
            for node in self._nodes.values():
                if node.node_id not in seen_ids:
                    seen_ids.add(node.node_id)
                    results.append({
                        "node_id": node.node_id,
                        "alias": node.alias,
                        "ip": node.ip,
                        "is_online": node.is_online,
                        "authority": node.authority,
                        "machine_digest": node.machine_digest,
                        "license_status": node.license_status,
                    })
            return results

    def _on_frame_received(self, frame_data: Any) -> None:
        """Handle incoming frame to update fleet topology asynchronously."""
        if not isinstance(frame_data, dict):
            return
        src_id = frame_data.get("src_id", "")
        if not src_id:
            return

        with self._lock:
            if src_id not in self._nodes:
                self._nodes[src_id] = DiscoveredNode(node_id=src_id, alias=src_id)
            node = self._nodes[src_id]
            node.is_online = True
            if "machine_id" in frame_data:
                node.machine_digest = self.mask_machine_id(frame_data["machine_id"])
            if "authority" in frame_data:
                node.authority = frame_data["authority"]


fleet_onboarding_svc = FleetOnboardingService()
