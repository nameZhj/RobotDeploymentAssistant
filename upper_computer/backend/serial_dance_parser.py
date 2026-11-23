import re
from typing import Any, Dict, List

DEFAULT_DANCE_GROUPS = [
    {
        "group_id": "G1",
        "title": "G1 动作组 (L1)",
        "items": [
            {"alias": "G1_TURN_JUMP", "name": "转身跳跃", "keys": "L1 + DOWN", "cmd": "DANCE,G1_TURN_JUMP"},
            {"alias": "G1_FRONT_FLIP", "name": "前空翻", "keys": "L1 + RIGHT", "cmd": "DANCE,G1_FRONT_FLIP"},
            {"alias": "G1_SIDE_FLIP", "name": "侧空翻", "keys": "L1 + A", "cmd": "DANCE,G1_SIDE_FLIP"},
            {"alias": "G1_CARTWHEEL", "name": "侧手翻", "keys": "L1 + B", "cmd": "DANCE,G1_CARTWHEEL"},
            {"alias": "G1_TIKTOK", "name": "抖音舞蹈1", "keys": "L1 + X", "cmd": "DANCE,G1_TIKTOK"},
            {"alias": "G1_TAIJI", "name": "太极", "keys": "L1 + Y", "cmd": "DANCE,G1_TAIJI"},
            {"alias": "G1_ROLL_BACK", "name": "地面滚动-后向", "keys": "L1 + SELECT", "cmd": "DANCE,G1_ROLL_BACK"},
            {"alias": "G1_GYMNASTICS", "name": "单腿支撑+旋转体操", "keys": "L1 + F1", "cmd": "DANCE,G1_GYMNASTICS"},
            {"alias": "G1_RUN", "name": "soma 奔跑", "keys": "L1 + F3", "cmd": "DANCE,G1_RUN"},
            {"alias": "G1_CXK", "name": "ikun", "keys": "L1 + START", "cmd": "DANCE,G1_CXK"},
            {"alias": "G1_JUMP", "name": "双腿跳+单腿跳", "keys": "L1 + L2", "cmd": "DANCE,G1_JUMP"},
            {"alias": "G1_OPPO", "name": "oppo 原地舞蹈", "keys": "L1 + R1", "cmd": "DANCE,G1_OPPO"},
        ]
    },
    {
        "group_id": "G2",
        "title": "G2 动作组 (R1)",
        "items": [
            {"alias": "G2_SPIN_KICK", "name": "旋转飞踢-俯身", "keys": "R1 + DOWN", "cmd": "DANCE,G2_SPIN_KICK"},
            {"alias": "G2_MOONWALK", "name": "太空步", "keys": "R1 + RIGHT", "cmd": "DANCE,G2_MOONWALK"},
            {"alias": "G2_TAIJI", "name": "太极-KungfuAthlete", "keys": "R1 + A", "cmd": "DANCE,G2_TAIJI"},
            {"alias": "G2_GYMNASTICS_07", "name": "单腿旋转 07", "keys": "R1 + B", "cmd": "DANCE,G2_GYMNASTICS_07"},
            {"alias": "G2_GYMNASTICS_13", "name": "单腿旋转 13", "keys": "R1 + X", "cmd": "DANCE,G2_GYMNASTICS_13"},
            {"alias": "G2_GYMNASTICS_19", "name": "单腿旋转 19", "keys": "R1 + Y", "cmd": "DANCE,G2_GYMNASTICS_19"},
            {"alias": "G2_GYMNASTICS_20", "name": "单腿旋转 20", "keys": "R1 + SELECT", "cmd": "DANCE,G2_GYMNASTICS_20"},
            {"alias": "G2_GOPAK", "name": "蹲步舞/戈帕克舞", "keys": "R1 + F1", "cmd": "DANCE,G2_GOPAK"},
            {"alias": "G2_FLYING_KICK", "name": "飞旋踢", "keys": "R1 + F3", "cmd": "DANCE,G2_FLYING_KICK"},
            {"alias": "G2_SPIN_KICK_87", "name": "旋转飞踢 87", "keys": "R1 + START", "cmd": "DANCE,G2_SPIN_KICK_87"},
        ]
    },
    {
        "group_id": "G3",
        "title": "G3 动作组 (L2)",
        "items": [
            {"alias": "G3_DANCE1_S1", "name": "D1S1 舞蹈", "keys": "L2 + DOWN", "cmd": "DANCE,G3_DANCE1_S1"},
            {"alias": "G3_DANCE1_S2", "name": "查尔斯顿", "keys": "L2 + RIGHT", "cmd": "DANCE,G3_DANCE1_S2"},
            {"alias": "G3_DANCE1_S3", "name": "D1S3 舞蹈", "keys": "L2 + A", "cmd": "DANCE,G3_DANCE1_S3"},
            {"alias": "G3_DANCE2_S1", "name": "D2S1 舞蹈", "keys": "L2 + B", "cmd": "DANCE,G3_DANCE2_S1"},
            {"alias": "G3_DANCE2_S2", "name": "D2S2 舞蹈", "keys": "L2 + X", "cmd": "DANCE,G3_DANCE2_S2"},
            {"alias": "G3_DANCE2_S3", "name": "D2S3 舞蹈", "keys": "L2 + Y", "cmd": "DANCE,G3_DANCE2_S3"},
            {"alias": "G3_DANCE2_S4", "name": "地板动作", "keys": "L2 + SELECT", "cmd": "DANCE,G3_DANCE2_S4"},
            {"alias": "G3_DANCE2_S5", "name": "D2S5 舞蹈", "keys": "L2 + F1", "cmd": "DANCE,G3_DANCE2_S5"},
            {"alias": "G3_KUNGFU", "name": "功夫", "keys": "L2 + F3", "cmd": "DANCE,G3_KUNGFU"},
            {"alias": "G3_ROLL_FORWARD", "name": "地面滚动-前向", "keys": "L2 + START", "cmd": "DANCE,G3_ROLL_FORWARD"},
            {"alias": "G3_FALL_GETUP", "name": "摔到恢复", "keys": "L2 + L1", "cmd": "DANCE,G3_FALL_GETUP"},
        ]
    }
]


def parse_dance_map_yaml(raw_text: str) -> List[Dict[str, Any]]:
    if not raw_text or not raw_text.strip():
        return []
    lines = raw_text.strip().splitlines()
    pattern = re.compile(r'^\s*([A-Za-z0-9_]+)\s*:\s*\[([^\]]+)\](?:\s*#\s*(.*))?$')
    groups_dict = {}
    group_order = []
    seen_aliases = set()

    for line in lines:
        stripped = re.sub(r'^[A-Za-z0-9_-]{1,16}\|', '', line.strip().rstrip('|')).strip()
        if not stripped or stripped.startswith("dance_map:"):
            continue

        match = pattern.match(stripped)
        if match:
            alias = match.group(1).strip()
            if alias in seen_aliases:
                continue
            seen_aliases.add(alias)
            raw_keys = [k.strip() for k in match.group(2).split(',') if k.strip()]
            comment = (match.group(3) or "").strip()
            first_key = raw_keys[0] if raw_keys else ""
            gid = "G1" if first_key == "L1" else ("G2" if first_key == "R1" else ("G3" if first_key == "L2" else ("G1" if "L1" in raw_keys else "G4")))
            if gid not in groups_dict:
                groups_dict[gid] = {"group_id": gid, "title": f"{gid} 动作组", "items": []}
                group_order.append(gid)
            name = comment.split()[0] if comment else alias
            select_key = raw_keys[0] if raw_keys else ""
            action_key = raw_keys[1] if len(raw_keys) > 1 else ""
            has_chinese = bool(re.search(r'[\u4e00-\u9fa5]', name))
            groups_dict[gid]["items"].append({
                "alias": alias,
                "name": name,
                "has_chinese": has_chinese,
                "keys": " + ".join(raw_keys),
                "select_key": select_key,
                "action_key": action_key,
                "cmd": f"DANCE,{alias}",
            })

    res = [groups_dict[gid] for gid in group_order if groups_dict[gid]["items"]]
    return res if res else DEFAULT_DANCE_GROUPS


def parse_robot_blocks(raw_text: str) -> Dict[str, str]:
    blocks: Dict[str, List[str]] = {}
    current_robot = "ALL"
    for line in raw_text.splitlines():
        match_prefix = re.match(r'^([A-Za-z0-9_-]{1,16})\|(.*)$', line.strip())
        if match_prefix:
            current_robot = match_prefix.group(1).strip()
            rest = match_prefix.group(2).strip()
            if rest.endswith("|"):
                rest = rest[:-1].strip()
            if current_robot not in blocks:
                blocks[current_robot] = []
            if rest:
                blocks[current_robot].append(rest)
        elif line.strip():
            if current_robot not in blocks:
                blocks[current_robot] = []
            clean_l = line.strip().rstrip("|")
            blocks[current_robot].append(clean_l)
    return {k: "\n".join(v) for k, v in blocks.items()}


def parse_multi_robot_dance_map(raw_text: str) -> Dict[str, List[Dict[str, Any]]]:
    blocks = parse_robot_blocks(raw_text)
    return {r_id: parse_dance_map_yaml(b_text) for r_id, b_text in blocks.items()}


def intersect_dance_groups(multi_groups: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if not multi_groups:
        return []
    robot_alias_sets = []
    first_groups = None
    for r_id, grps in multi_groups.items():
        if first_groups is None:
            first_groups = grps
        aliases = {it["alias"] for g in grps for it in g.get("items", [])}
        robot_alias_sets.append(aliases)

    if not robot_alias_sets:
        return []
    common_aliases = set.intersection(*robot_alias_sets)

    result_groups = []
    for g in (first_groups or []):
        filtered_items = [it for it in g.get("items", []) if it.get("alias") in common_aliases]
        if filtered_items:
            result_groups.append({
                "group_id": g.get("group_id", ""),
                "title": g.get("title", ""),
                "items": filtered_items
            })
    return result_groups


for _g in DEFAULT_DANCE_GROUPS:
    for _it in _g.get("items", []):
        _parts = [k.strip() for k in _it.get("keys", "").split("+") if k.strip()]
        _it["select_key"] = _parts[0] if _parts else ""
        _it["action_key"] = _parts[1] if len(_parts) > 1 else ""
        _it["has_chinese"] = bool(re.search(r'[\u4e00-\u9fa5]', _it.get("name", "")))

