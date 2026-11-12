"""
@file: tests/verify_choreo_e2e.py
@brief: 编排控制台全流程端到端自动化验收执行脚本
@exports: main
"""
import os
import sys

# 将工程根目录加入模块搜索路径
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from tests.unit.test_feature_choreo_suite import (
    test_01_trajectory_compile_and_anchor,
    test_02_formation_geometry_and_members,
    test_03_asset_registry_full_catalog,
    test_04_timeline_lrmp_compilation,
    test_05_stage_preview_engine_tracks,
    test_06_group_trajectory_safety_pipeline,
)
from tests.unit.test_legacy_pre_2026_10_01_contracts import (
    test_legacy_dance_groups_contract,
    test_legacy_serial_dance_parser,
    test_legacy_g1_urdf_models_exist,
    test_legacy_preview_manager_loaded,
)


def main() -> int:
    """运行全流程端到端校验。"""
    print("🚀 开始执行 RobotDeploymentAssistant 全流程端到端与历史契约验收...")
    try:
        # 1. 历史基线契约校验
        print("  [1/10] 验证 2026-10-01 前 33 支舞蹈动作指令契约...")
        test_legacy_dance_groups_contract()

        print("  [2/10] 验证串口舞蹈指令解析器...")
        test_legacy_serial_dance_parser()

        print("  [3/10] 验证 G1 23/29DOF URDF 骨骼资产...")
        test_legacy_g1_urdf_models_exist()

        print("  [4/10] 验证 3D 舞蹈预览管理器单例与模型注入...")
        test_legacy_preview_manager_loaded()

        # 2. 编排功能端到端校验
        print("  [5/10] 验证 2D 样条轨迹插值与弧长编译...")
        test_01_trajectory_compile_and_anchor()

        print("  [6/10] 验证几何阵型解算与间距安全校验...")
        test_02_formation_geometry_and_members()

        print("  [7/10] 验证统一素材中心真实目录检索...")
        test_03_asset_registry_full_catalog()

        print("  [8/10] 验证时间轴动作块到 LRMP 指令帧序列化...")
        test_04_timeline_lrmp_compilation(None)

        print("  [9/10] 验证 3D 虚拟预演编译引擎时空姿态生成...")
        test_05_stage_preview_engine_tracks()

        print("  [10/10] 验证群组轨迹 Frenet 局部展开与防撞筛查...")
        test_06_group_trajectory_safety_pipeline()

        print("\n✅ [SUCCESS] 全部 10 项端到端流程与历史契约检验 100% 通过！")
        return 0
    except Exception as e:
        print(f"\n❌ [FAILED] 验收流程中断: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
