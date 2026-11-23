import os
import isaaclab.sim as sim_utils
from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.assets.articulation import ArticulationCfg
from robots.unitree_actuators import (
    UnitreeActuatorCfg_W4010_25,
    UnitreeActuatorCfg_N5010_16,
    UnitreeActuatorCfg_N5020_16,
    UnitreeActuatorCfg_N7520_14p3,
    UnitreeActuatorCfg_N7520_22p5,
)
from robots import ASSET_DIR
from isaaclab.utils import configclass

ARMATURE_5020 = 0.003609725
ARMATURE_7520_14 = 0.010177520
ARMATURE_7520_22 = 0.025101925
ARMATURE_4010 = 0.00425
ARMATURE_5010 = 0.0021812

NATURAL_FREQ = 10 * 2.0 * 3.1415926535  # 10Hz
DAMPING_RATIO = 2.0

STIFFNESS_5020 = ARMATURE_5020 * NATURAL_FREQ**2
STIFFNESS_7520_14 = ARMATURE_7520_14 * NATURAL_FREQ**2
STIFFNESS_7520_22 = ARMATURE_7520_22 * NATURAL_FREQ**2
STIFFNESS_4010 = ARMATURE_4010 * NATURAL_FREQ**2
STIFFNESS_5010 = ARMATURE_5010 * NATURAL_FREQ**2

DAMPING_5020 = 2.0 * DAMPING_RATIO * ARMATURE_5020 * NATURAL_FREQ
DAMPING_7520_14 = 2.0 * DAMPING_RATIO * ARMATURE_7520_14 * NATURAL_FREQ
DAMPING_7520_22 = 2.0 * DAMPING_RATIO * ARMATURE_7520_22 * NATURAL_FREQ
DAMPING_4010 = 2.0 * DAMPING_RATIO * ARMATURE_4010 * NATURAL_FREQ
DAMPING_5010 = 2.0 * DAMPING_RATIO * ARMATURE_5010 * NATURAL_FREQ


@configclass
class UnitreeArticulationCfg(ArticulationCfg):
    """Configuration for Unitree articulations."""

    name = None  # get_robot_cfg 中自动设为模块级变量名
    joint_sdk_names: list[str] = None
    soft_joint_pos_limit_factor = 0.9


G1_M5_IA = UnitreeArticulationCfg(
    spawn=sim_utils.UrdfFileCfg(
        fix_base=False,
        replace_cylinders_with_capsules=True,
        asset_path=f"{ASSET_DIR}/g1_29dof_mode_5.urdf",
        activate_contact_sensors=True,
        rigid_props=sim_utils.RigidBodyPropertiesCfg(
            disable_gravity=False,
            retain_accelerations=False,
            linear_damping=0.0,
            angular_damping=0.0,
            max_linear_velocity=1000.0,
            max_angular_velocity=1000.0,
            max_depenetration_velocity=1.0,
        ),
        articulation_props=sim_utils.ArticulationRootPropertiesCfg(enabled_self_collisions=True, solver_position_iteration_count=8, solver_velocity_iteration_count=4),
        joint_drive=sim_utils.UrdfConverterCfg.JointDriveCfg(gains=sim_utils.UrdfConverterCfg.JointDriveCfg.PDGainsCfg(stiffness=0, damping=0)),
    ),
    init_state=ArticulationCfg.InitialStateCfg(
        pos=(0.0, 0.0, 0.76),
        joint_pos={
            ".*_hip_pitch_joint": -0.312,
            ".*_knee_joint": 0.669,
            ".*_ankle_pitch_joint": -0.363,
            ".*_elbow_joint": 0.6,
            "left_shoulder_roll_joint": 0.2,
            "left_shoulder_pitch_joint": 0.2,
            "right_shoulder_roll_joint": -0.2,
            "right_shoulder_pitch_joint": 0.2,
        },
        joint_vel={".*": 0.0},
    ),
    soft_joint_pos_limit_factor=0.9,
    actuators={
        "legs": ImplicitActuatorCfg(
            joint_names_expr=[
                ".*_hip_yaw_joint",
                ".*_hip_roll_joint",
                ".*_hip_pitch_joint",
                ".*_knee_joint",
            ],
            effort_limit_sim={
                ".*_hip_yaw_joint": 88.0,
                ".*_hip_roll_joint": 139.0,
                ".*_hip_pitch_joint": 88.0,
                ".*_knee_joint": 139.0,
            },
            velocity_limit_sim={
                ".*_hip_yaw_joint": 32.0,
                ".*_hip_roll_joint": 20.0,
                ".*_hip_pitch_joint": 32.0,
                ".*_knee_joint": 20.0,
            },
            stiffness={
                ".*_hip_pitch_joint": STIFFNESS_7520_14,
                ".*_hip_roll_joint": STIFFNESS_7520_22,
                ".*_hip_yaw_joint": STIFFNESS_7520_14,
                ".*_knee_joint": STIFFNESS_7520_22,
            },
            damping={
                ".*_hip_pitch_joint": DAMPING_7520_14,
                ".*_hip_roll_joint": DAMPING_7520_22,
                ".*_hip_yaw_joint": DAMPING_7520_14,
                ".*_knee_joint": DAMPING_7520_22,
            },
            armature={
                ".*_hip_pitch_joint": ARMATURE_7520_14,
                ".*_hip_roll_joint": ARMATURE_7520_22,
                ".*_hip_yaw_joint": ARMATURE_7520_14,
                ".*_knee_joint": ARMATURE_7520_22,
            },
        ),
        "feet": ImplicitActuatorCfg(
            effort_limit_sim=50.0,
            velocity_limit_sim=37.0,
            joint_names_expr=[".*_ankle_pitch_joint", ".*_ankle_roll_joint"],
            stiffness=2.0 * STIFFNESS_5020,
            damping=2.0 * DAMPING_5020,
            armature=2.0 * ARMATURE_5020,
        ),
        "waist": ImplicitActuatorCfg(
            effort_limit_sim=50,
            velocity_limit_sim=37.0,
            joint_names_expr=["waist_roll_joint", "waist_pitch_joint"],
            stiffness=2.0 * STIFFNESS_5020,
            damping=2.0 * DAMPING_5020,
            armature=2.0 * ARMATURE_5020,
        ),
        "waist_yaw": ImplicitActuatorCfg(
            effort_limit_sim=88,
            velocity_limit_sim=32.0,
            joint_names_expr=["waist_yaw_joint"],
            stiffness=STIFFNESS_7520_14,
            damping=DAMPING_7520_14,
            armature=ARMATURE_7520_14,
        ),
        "arms": ImplicitActuatorCfg(
            joint_names_expr=[
                ".*_shoulder_pitch_joint",
                ".*_shoulder_roll_joint",
                ".*_shoulder_yaw_joint",
                ".*_elbow_joint",
                ".*_wrist_roll_joint",
                ".*_wrist_pitch_joint",
                ".*_wrist_yaw_joint",
            ],
            effort_limit_sim={
                ".*_shoulder_pitch_joint": 25.0,
                ".*_shoulder_roll_joint": 25.0,
                ".*_shoulder_yaw_joint": 25.0,
                ".*_elbow_joint": 25.0,
                ".*_wrist_roll_joint": 25.0,
                ".*_wrist_pitch_joint": 5.0,
                ".*_wrist_yaw_joint": 5.0,
            },
            velocity_limit_sim={
                ".*_shoulder_pitch_joint": 37.0,
                ".*_shoulder_roll_joint": 37.0,
                ".*_shoulder_yaw_joint": 37.0,
                ".*_elbow_joint": 37.0,
                ".*_wrist_roll_joint": 37.0,
                ".*_wrist_pitch_joint": 22.0,
                ".*_wrist_yaw_joint": 22.0,
            },
            stiffness={
                ".*_shoulder_pitch_joint": STIFFNESS_5020,
                ".*_shoulder_roll_joint": STIFFNESS_5020,
                ".*_shoulder_yaw_joint": STIFFNESS_5020,
                ".*_elbow_joint": STIFFNESS_5020,
                ".*_wrist_roll_joint": STIFFNESS_5020,
                ".*_wrist_pitch_joint": STIFFNESS_4010,
                ".*_wrist_yaw_joint": STIFFNESS_4010,
            },
            damping={
                ".*_shoulder_pitch_joint": DAMPING_5020,
                ".*_shoulder_roll_joint": DAMPING_5020,
                ".*_shoulder_yaw_joint": DAMPING_5020,
                ".*_elbow_joint": DAMPING_5020,
                ".*_wrist_roll_joint": DAMPING_5020,
                ".*_wrist_pitch_joint": DAMPING_4010,
                ".*_wrist_yaw_joint": DAMPING_4010,
            },
            armature={
                ".*_shoulder_pitch_joint": ARMATURE_5020,
                ".*_shoulder_roll_joint": ARMATURE_5020,
                ".*_shoulder_yaw_joint": ARMATURE_5020,
                ".*_elbow_joint": ARMATURE_5020,
                ".*_wrist_roll_joint": ARMATURE_5020,
                ".*_wrist_pitch_joint": ARMATURE_4010,
                ".*_wrist_yaw_joint": ARMATURE_4010,
            },
        ),
    },
)

G1_M5_UA = UnitreeArticulationCfg(
    spawn=sim_utils.UrdfFileCfg(
        fix_base=False,
        replace_cylinders_with_capsules=True,
        asset_path=f"{ASSET_DIR}/g1_29dof_mode_5.urdf",
        activate_contact_sensors=True,
        rigid_props=sim_utils.RigidBodyPropertiesCfg(
            disable_gravity=False,
            retain_accelerations=False,
            linear_damping=0.0,
            angular_damping=0.0,
            max_linear_velocity=1000.0,
            max_angular_velocity=1000.0,
            max_depenetration_velocity=1.0,
        ),
        articulation_props=sim_utils.ArticulationRootPropertiesCfg(enabled_self_collisions=True, solver_position_iteration_count=8, solver_velocity_iteration_count=4),
        joint_drive=sim_utils.UrdfConverterCfg.JointDriveCfg(gains=sim_utils.UrdfConverterCfg.JointDriveCfg.PDGainsCfg(stiffness=0, damping=0)),
    ),
    init_state=ArticulationCfg.InitialStateCfg(
        pos=(0.0, 0.0, 0.76),
        joint_pos={
            ".*_hip_pitch_joint": -0.312,
            ".*_knee_joint": 0.669,
            ".*_ankle_pitch_joint": -0.363,
            ".*_elbow_joint": 0.6,
            "left_shoulder_roll_joint": 0.2,
            "left_shoulder_pitch_joint": 0.2,
            "right_shoulder_roll_joint": -0.2,
            "right_shoulder_pitch_joint": 0.2,
        },
        joint_vel={".*": 0.0},
    ),
    soft_joint_pos_limit_factor=0.9,
    actuators={
        "N7520-14.3": UnitreeActuatorCfg_N7520_14p3(
            joint_names_expr=[
                ".*_hip_pitch_.*",  # left_hip_pitch_joint, right_hip_pitch_joint
                ".*_hip_yaw_.*",  # left_hip_yaw_joint, right_hip_yaw_joint
                "waist_yaw_joint",
            ],
            effort_limit_sim=88,
            velocity_limit_sim=32.0,
            stiffness=STIFFNESS_7520_14,
            damping=DAMPING_7520_14,
            # armature=ARMATURE_7520_14,
        ),
        "N7520-22.5": UnitreeActuatorCfg_N7520_22p5(
            joint_names_expr=[
                ".*_hip_roll_.*",  # left_hip_roll_joint, right_hip_roll_joint
                ".*_knee_.*",  # left_knee_joint, right_knee_joint
            ],
            effort_limit_sim=139,
            velocity_limit_sim=20.0,
            stiffness=STIFFNESS_7520_22,
            damping=DAMPING_7520_22,
            # armature=ARMATURE_7520_22,
        ),
        "N5020-16": UnitreeActuatorCfg_N5020_16(
            joint_names_expr=[
                ".*_shoulder_.*",  # left_shoulder_pitch_joint, left_shoulder_roll_joint, left_shoulder_yaw_joint, right_shoulder_pitch_joint, right_shoulder_roll_joint, right_shoulder_yaw_joint
                ".*_elbow_.*",  # left_elbow_joint, right_elbow_joint
                ".*_wrist_roll.*",  # left_wrist_roll_joint, right_wrist_roll_joint
            ],
            effort_limit_sim=25,
            velocity_limit_sim=37,
            stiffness=STIFFNESS_5020,
            damping=DAMPING_5020,
            # armature=ARMATURE_5020,
        ),
        "N5020-16-d": UnitreeActuatorCfg_N5020_16(
            joint_names_expr=[
                ".*_ankle_.*",  # left_ankle_pitch_joint, left_ankle_roll_joint, right_ankle_pitch_joint, right_ankle_roll_joint
                "waist_roll_joint",
                "waist_pitch_joint",
            ],
            effort_limit_sim=50,
            velocity_limit_sim=37,
            stiffness=2.0 * STIFFNESS_5020,
            damping=2.0 * DAMPING_5020,
            armature=2.0 * ARMATURE_5020,
            Y1=2.0 * 24.8,
            Y2=2.0 * 31.9,
            Fs=2.0 * 0.6,
            Fd=2.0 * 0.06,
        ),
        "W4010-25": UnitreeActuatorCfg_W4010_25(
            joint_names_expr=[
                ".*_wrist_pitch.*",  # left_wrist_pitch_joint, right_wrist_pitch_joint
                ".*_wrist_yaw.*",  # left_wrist_yaw_joint, right_wrist_yaw_joint
            ],
            effort_limit_sim=5,
            velocity_limit_sim=22,
            stiffness=STIFFNESS_4010,
            damping=DAMPING_4010,
            # armature=ARMATURE_4010,
        ),
    },
    joint_sdk_names=[
        "left_hip_pitch_joint",
        "left_hip_roll_joint",
        "left_hip_yaw_joint",
        "left_knee_joint",
        "left_ankle_pitch_joint",
        "left_ankle_roll_joint",
        "right_hip_pitch_joint",
        "right_hip_roll_joint",
        "right_hip_yaw_joint",
        "right_knee_joint",
        "right_ankle_pitch_joint",
        "right_ankle_roll_joint",
        "waist_yaw_joint",
        "waist_roll_joint",
        "waist_pitch_joint",
        "left_shoulder_pitch_joint",
        "left_shoulder_roll_joint",
        "left_shoulder_yaw_joint",
        "left_elbow_joint",
        "left_wrist_roll_joint",
        "left_wrist_pitch_joint",
        "left_wrist_yaw_joint",
        "right_shoulder_pitch_joint",
        "right_shoulder_roll_joint",
        "right_shoulder_yaw_joint",
        "right_elbow_joint",
        "right_wrist_roll_joint",
        "right_wrist_pitch_joint",
        "right_wrist_yaw_joint",
    ],
)

G1_M15_UA = UnitreeArticulationCfg(  # tag: g1 urdf
    spawn=sim_utils.UrdfFileCfg(
        fix_base=False,
        replace_cylinders_with_capsules=True,
        asset_path=f"{ASSET_DIR}/g1_29dof_mode_15.urdf",
        activate_contact_sensors=True,
        rigid_props=sim_utils.RigidBodyPropertiesCfg(
            disable_gravity=False,
            retain_accelerations=False,
            linear_damping=0.0,
            angular_damping=0.0,
            max_linear_velocity=1000.0,
            max_angular_velocity=1000.0,
            max_depenetration_velocity=1.0,
        ),
        articulation_props=sim_utils.ArticulationRootPropertiesCfg(enabled_self_collisions=True, solver_position_iteration_count=8, solver_velocity_iteration_count=4),
        joint_drive=sim_utils.UrdfConverterCfg.JointDriveCfg(gains=sim_utils.UrdfConverterCfg.JointDriveCfg.PDGainsCfg(stiffness=0, damping=0)),
    ),
    init_state=ArticulationCfg.InitialStateCfg(
        pos=(0.0, 0.0, 0.76),
        joint_pos={
            ".*_hip_pitch_joint": -0.312,
            ".*_knee_joint": 0.669,
            ".*_ankle_pitch_joint": -0.363,
            ".*_elbow_joint": 0.6,
            "left_shoulder_roll_joint": 0.2,
            "left_shoulder_pitch_joint": 0.2,
            "right_shoulder_roll_joint": -0.2,
            "right_shoulder_pitch_joint": 0.2,
        },
        joint_vel={".*": 0.0},
    ),
    soft_joint_pos_limit_factor=0.9,
    actuators={
        "N7520-14.3": UnitreeActuatorCfg_N7520_14p3(
            joint_names_expr=[
                ".*_hip_yaw_.*",  # left_hip_yaw_joint, right_hip_yaw_joint
                "waist_yaw_joint",
            ],
            effort_limit_sim=88,
            velocity_limit_sim=32.0,
            stiffness=STIFFNESS_7520_14,
            damping=DAMPING_7520_14,
            # armature=ARMATURE_7520_14,
        ),
        "N7520-22.5": UnitreeActuatorCfg_N7520_22p5(
            joint_names_expr=[
                ".*_hip_pitch_.*",  # left_hip_pitch_joint, right_hip_pitch_joint
                ".*_hip_roll_.*",  # left_hip_roll_joint, right_hip_roll_joint
                ".*_knee_.*",  # left_knee_joint, right_knee_joint
            ],
            effort_limit_sim=139,
            velocity_limit_sim=20.0,
            stiffness=STIFFNESS_7520_22,
            damping=DAMPING_7520_22,
            # armature=ARMATURE_7520_22,
        ),
        "N5020-16": UnitreeActuatorCfg_N5020_16(
            joint_names_expr=[
                ".*_shoulder_.*",  # left_shoulder_pitch_joint, left_shoulder_roll_joint, left_shoulder_yaw_joint, right_shoulder_pitch_joint, right_shoulder_roll_joint, right_shoulder_yaw_joint
                ".*_elbow_.*",  # left_elbow_joint, right_elbow_joint
                ".*_wrist_roll.*",  # left_wrist_roll_joint, right_wrist_roll_joint
            ],
            effort_limit_sim=25,
            velocity_limit_sim=37,
            stiffness=STIFFNESS_5020,
            damping=DAMPING_5020,
            # armature=ARMATURE_5020,
        ),
        "N5020-16-d": UnitreeActuatorCfg_N5020_16(
            joint_names_expr=[
                ".*_ankle_.*",  # left_ankle_pitch_joint, left_ankle_roll_joint, right_ankle_pitch_joint, right_ankle_roll_joint
                "waist_roll_joint",
                "waist_pitch_joint",
            ],
            effort_limit_sim=50,
            velocity_limit_sim=37,
            stiffness=2.0 * STIFFNESS_5020,
            damping=2.0 * DAMPING_5020,
            armature=2.0 * ARMATURE_5020,
            Y1=2.0 * 24.8,
            Y2=2.0 * 31.9,
            Fs=2.0 * 0.6,
            Fd=2.0 * 0.06,
        ),
        "W5010-16": UnitreeActuatorCfg_N5010_16(
            joint_names_expr=[
                ".*_wrist_pitch.*",  # left_wrist_pitch_joint, right_wrist_pitch_joint
                ".*_wrist_yaw.*",  # left_wrist_yaw_joint, right_wrist_yaw_joint
            ],
            effort_limit_sim=10,
            velocity_limit_sim=22,
            stiffness=STIFFNESS_5010,
            damping=DAMPING_5010,
            # armature=ARMATURE_5010,
        ),
    },
    joint_sdk_names=[
        "left_hip_pitch_joint",
        "left_hip_roll_joint",
        "left_hip_yaw_joint",
        "left_knee_joint",
        "left_ankle_pitch_joint",
        "left_ankle_roll_joint",
        "right_hip_pitch_joint",
        "right_hip_roll_joint",
        "right_hip_yaw_joint",
        "right_knee_joint",
        "right_ankle_pitch_joint",
        "right_ankle_roll_joint",
        "waist_yaw_joint",
        "waist_roll_joint",
        "waist_pitch_joint",
        "left_shoulder_pitch_joint",
        "left_shoulder_roll_joint",
        "left_shoulder_yaw_joint",
        "left_elbow_joint",
        "left_wrist_roll_joint",
        "left_wrist_pitch_joint",
        "left_wrist_yaw_joint",
        "right_shoulder_pitch_joint",
        "right_shoulder_roll_joint",
        "right_shoulder_yaw_joint",
        "right_elbow_joint",
        "right_wrist_roll_joint",
        "right_wrist_pitch_joint",
        "right_wrist_yaw_joint",
    ],
)


def compute_action_scale(cfg):
    scale = {}
    for a in cfg.actuators.values():
        e = a.effort_limit_sim
        s = a.stiffness
        names = a.joint_names_expr
        if not isinstance(e, dict):
            e = {n: e for n in names}
        if not isinstance(s, dict):
            s = {n: s for n in names}
        for n in names:
            if n in e and n in s and s[n]:
                scale[n] = 0.25 * e[n] / s[n]
    return scale


ROBOT_CFG_MAP = {
    "g1_m5_ia": G1_M5_IA,    # ImplicitActuator
    "g1_m5_ua": G1_M5_UA,    # UnitreeActuator
    "g1_m15_ua": G1_M15_UA,  # UnitreeActuator
}


def get_robot_cfg():  # 据环境变量 G1_ROBOT_TYPE 选配置，并自动把 name 设为模块级变量名
    robot_type = os.environ.get("G1_ROBOT_TYPE", "g1_m5_ua")
    cfg = ROBOT_CFG_MAP.get(robot_type, ROBOT_CFG_MAP["g1_m5_ua"])
    cfg.name = next(name for name, obj in globals().items() if obj is cfg and name.isupper())
    return cfg
