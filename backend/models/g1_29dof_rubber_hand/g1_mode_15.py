import isaaclab.sim as sim_utils
from isaaclab.assets.articulation import ArticulationCfg
from robots.unitree_actuators import (
    UnitreeActuatorCfg_N5010_16,
    UnitreeActuatorCfg_N5020_16,
    UnitreeActuatorCfg_N7520_14p3,
    UnitreeActuatorCfg_N7520_22p5,
)
from robots import ASSET_DIR
from .g1_common import (
    UnitreeArticulationCfg,
    STIFFNESS_7520_14, DAMPING_7520_14,
    STIFFNESS_7520_22, DAMPING_7520_22,
    STIFFNESS_5020, DAMPING_5020, ARMATURE_5020,
    STIFFNESS_5010, DAMPING_5010,
)

G1_M15_UA = UnitreeArticulationCfg(
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
            joint_names_expr=[".*_hip_yaw_.*", "waist_yaw_joint"],
            effort_limit_sim=88, velocity_limit_sim=32.0,
            stiffness=STIFFNESS_7520_14, damping=DAMPING_7520_14,
        ),
        "N7520-22.5": UnitreeActuatorCfg_N7520_22p5(
            joint_names_expr=[".*_hip_pitch_.*", ".*_hip_roll_.*", ".*_knee_.*"],
            effort_limit_sim=139, velocity_limit_sim=20.0,
            stiffness=STIFFNESS_7520_22, damping=DAMPING_7520_22,
        ),
        "N5020-16": UnitreeActuatorCfg_N5020_16(
            joint_names_expr=[".*_shoulder_.*", ".*_elbow_.*", ".*_wrist_roll.*"],
            effort_limit_sim=25, velocity_limit_sim=37,
            stiffness=STIFFNESS_5020, damping=DAMPING_5020,
        ),
        "N5020-16-d": UnitreeActuatorCfg_N5020_16(
            joint_names_expr=[".*_ankle_.*", "waist_roll_joint", "waist_pitch_joint"],
            effort_limit_sim=50, velocity_limit_sim=37,
            stiffness=2.0 * STIFFNESS_5020, damping=2.0 * DAMPING_5020,
            armature=2.0 * ARMATURE_5020, Y1=2.0 * 24.8, Y2=2.0 * 31.9, Fs=2.0 * 0.6, Fd=2.0 * 0.06,
        ),
        "W5010-16": UnitreeActuatorCfg_N5010_16(
            joint_names_expr=[".*_wrist_pitch.*", ".*_wrist_yaw.*"],
            effort_limit_sim=10, velocity_limit_sim=22,
            stiffness=STIFFNESS_5010, damping=DAMPING_5010,
        ),
    },
    joint_sdk_names=[
        "left_hip_pitch_joint", "left_hip_roll_joint", "left_hip_yaw_joint", "left_knee_joint",
        "left_ankle_pitch_joint", "left_ankle_roll_joint", "right_hip_pitch_joint", "right_hip_roll_joint",
        "right_hip_yaw_joint", "right_knee_joint", "right_ankle_pitch_joint", "right_ankle_roll_joint",
        "waist_yaw_joint", "waist_roll_joint", "waist_pitch_joint", "left_shoulder_pitch_joint",
        "left_shoulder_roll_joint", "left_shoulder_yaw_joint", "left_elbow_joint", "left_wrist_roll_joint",
        "left_wrist_pitch_joint", "left_wrist_yaw_joint", "right_shoulder_pitch_joint", "right_shoulder_roll_joint",
        "right_shoulder_yaw_joint", "right_elbow_joint", "right_wrist_roll_joint", "right_wrist_pitch_joint",
        "right_wrist_yaw_joint",
    ],
)

