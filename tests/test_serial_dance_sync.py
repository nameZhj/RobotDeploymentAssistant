import unittest
import json
import io
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.serial_manager import parse_dance_map_yaml, serial_manager
from app import app

SAMPLE_YAML = """dance_map:
  # Group 1: select key L1
  G1_TURN_JUMP:    [L1, DOWN]     # 转身跳跃 RL_Mimic_CMU_83_58
  G1_FRONT_FLIP:   [L1, RIGHT]    # 前空翻 RL_Mimic_CMU_85_07
  G1_SIDE_FLIP:    [L1, A]        # 侧空翻 RL_Mimic_CMU_90_08
  G1_CARTWHEEL:    [L1, B]        # 侧手翻 RL_Mimic_CMU_90_03
  G1_TIKTOK:       [L1, X]        # 抖音舞蹈1 RL_Mimic_TikTok_dance1_30fps
  G1_TAIJI:        [L1, Y]        # 太极 RL_Mimic_CMU_12_04
  G1_ROLL_BACK:    [L1, SELECT]   # 地面滚动-后向 RL_Mimic_CMU_90_01
  G1_GYMNASTICS:   [L1, F1]       # 单腿支撑+旋转体操 RL_Mimic_CMU_05_05
  G1_RUN:          [L1, F3]       # soma 奔跑 RL_Mimic_soma_g1_running_120fps
  G1_CXK:          [L1, START]    # ikun RL_Mimic_cxk_dance
  G1_JUMP:         [L1, L2]       # 双腿跳+单腿跳 RL_Mimic_CMU_49_02
  G1_OPPO:         [L1, R1]       # oppo 原地舞蹈 RL_Mimic_oppo_dance2_50fps

  # Group 2: select key R1
  G2_SPIN_KICK:    [R1, DOWN]     # 旋转飞踢-俯身 RL_Mimic_CMU_88_06
  G2_MOONWALK:     [R1, RIGHT]    # 太空步 RL_Mimic_CMU_90_32
  G2_TAIJI:        [R1, A]        # 太极-KungfuAthlete RL_Mimic_taichi_1307
  G2_GYMNASTICS_07: [R1, B]       # 单腿支撑+旋转体操 RL_Mimic_CMU_05_07
  G2_GYMNASTICS_13: [R1, X]       # 单腿支撑+旋转体操 RL_Mimic_CMU_05_13
  G2_GYMNASTICS_19: [R1, Y]       # 单腿支撑+旋转体操 RL_Mimic_CMU_05_19
  G2_GYMNASTICS_20: [R1, SELECT]  # 单腿支撑+旋转体操 RL_Mimic_CMU_05_20
  G2_GOPAK:        [R1, F1]       # 蹲步舞/戈帕克舞 RL_Mimic_CMU_90_30
  G2_FLYING_KICK:  [R1, F3]       # 飞旋踢 RL_Mimic_CMU_90_06
  G2_SPIN_KICK_87: [R1, START]    # 旋转飞踢-俯身 RL_Mimic_CMU_87_01

  # Group 3: select key L2
  G3_DANCE1_S1:    [L2, DOWN]     # D1S1 RL_Mimic_dance1_subject1
  G3_DANCE1_S2:    [L2, RIGHT]    # 查尔斯顿 RL_Mimic_dance1_subject2
  G3_DANCE1_S3:    [L2, A]        # D1S3 RL_Mimic_dance1_subject3
  G3_DANCE2_S1:    [L2, B]        # D2S1 RL_Mimic_dance2_subject1
  G3_DANCE2_S2:    [L2, X]        # D2S2 RL_Mimic_dance2_subject2
  G3_DANCE2_S3:    [L2, Y]        # D2S3 RL_Mimic_dance2_subject3
  G3_DANCE2_S4:    [L2, SELECT]   # 地板动作 RL_Mimic_dance2_subject4
  G3_DANCE2_S5:    [L2, F1]       # D2S5 RL_Mimic_dance2_subject5
  G3_KUNGFU:       [L2, F3]       # 功夫 RL_Mimic_fightAndSports1_subject4
  G3_ROLL_FORWARD: [L2, START]    # 地面滚动-前向 RL_Mimic_CMU_90_34
  G3_FALL_GETUP:   [L2, L1]       # 摔到恢复 RL_Mimic_fallAndGetUp1_subject1
"""


class TestSerialDanceSync(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_parse_dance_map_yaml_total_count(self):
        groups = parse_dance_map_yaml(SAMPLE_YAML)
        self.assertEqual(len(groups), 3)
        total = sum(len(g["items"]) for g in groups)
        self.assertEqual(total, 33)

    def test_chinese_vs_english_naming(self):
        groups = parse_dance_map_yaml(SAMPLE_YAML)
        item_map = {}
        for g in groups:
            for it in g["items"]:
                item_map[it["alias"]] = it

        # Chinese names
        self.assertEqual(item_map["G1_TURN_JUMP"]["name"], "转身跳跃")
        self.assertTrue(item_map["G1_TURN_JUMP"]["has_chinese"])
        self.assertEqual(item_map["G1_FRONT_FLIP"]["name"], "前空翻")
        self.assertEqual(item_map["G2_MOONWALK"]["name"], "太空步")
        self.assertEqual(item_map["G3_DANCE1_S2"]["name"], "查尔斯顿")
        self.assertEqual(item_map["G3_FALL_GETUP"]["name"], "摔到恢复")

        # English names (no Chinese in comment)
        self.assertEqual(item_map["G1_CXK"]["name"], "ikun")
        self.assertFalse(item_map["G1_CXK"]["has_chinese"])
        self.assertEqual(item_map["G3_DANCE1_S1"]["name"], "D1S1")
        self.assertFalse(item_map["G3_DANCE1_S1"]["has_chinese"])
        self.assertEqual(item_map["G3_DANCE1_S3"]["name"], "D1S3")
        self.assertEqual(item_map["G3_DANCE2_S1"]["name"], "D2S1")
        self.assertEqual(item_map["G3_DANCE2_S2"]["name"], "D2S2")
        self.assertEqual(item_map["G3_DANCE2_S3"]["name"], "D2S3")
        self.assertEqual(item_map["G3_DANCE2_S5"]["name"], "D2S5")

    def test_command_generation(self):
        groups = parse_dance_map_yaml(SAMPLE_YAML)
        for g in groups:
            for it in g["items"]:
                self.assertEqual(it["cmd"], f"DANCE,{it['alias']}")

    def test_api_parse_dances(self):
        resp = self.app.post("/api/serial/parse_dances", json={"content": SAMPLE_YAML})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["total_count"], 33)
        self.assertEqual(len(data["groups"]), 3)

    def test_api_get_dance_list(self):
        serial_manager.set_dance_list_raw(SAMPLE_YAML)
        resp = self.app.get("/api/serial/dance_list")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["total_count"], 33)


if __name__ == "__main__":
    unittest.main()
