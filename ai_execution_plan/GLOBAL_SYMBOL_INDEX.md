# Global Dual-Project Symbol Index (Hydrogen High Fast Lookup)

## upper_computer (132 modules)
upper_computer/src/__init__.py | Root package marker for UniSwarm Stage Choreography & Swarm Control source modules. | __version__
upper_computer/src/algorithms/__init__.py | Swarm formation, 2-opt assignment, potential-field solver, and timeline collision detection exports. | generate_formation, assign_targets_2opt, count_path_crossings, generate_scatter_positions, PotentialFieldParams, SwarmSimulationResult, solve_swarm_potential_field, rdp_simplify, CollisionInterval, detect_timeline_collisions
upper_computer/src/algorithms/formation_generators.py | Parametric 2D multi-robot formation generators (line, circle, grid, wedge, staggered, polygon). | FormationKind, generate_formation
upper_computer/src/algorithms/potential_field_solver.py | UniUni potential-field collision-free swarm trajectory planner with 3-pass safety projection and RDP simplification. | PotentialFieldParams, SwarmSimulationResult, rdp_simplify, compute_segment_times, solve_swarm_potential_field
upper_computer/src/algorithms/scatter_stage.py | Two-ring radial intermediate scatter formation breaking high-crossing deadlocks in swarm transitions. | CROSSING_THRESHOLD, generate_scatter_positions
upper_computer/src/algorithms/spatial_hash_grid.py | O(1) spatial hash grid accelerating neighbor queries in potential-field and collision workers. | SpatialHashGrid
upper_computer/src/algorithms/target_assignment.py | Greedy nearest-neighbor + 2-opt swap solver minimizing total distance and path crossings. | count_path_crossings, assign_targets_2opt
upper_computer/src/algorithms/text_formation.py | Character/text glyph bitmap sampler converting any Chinese or ASCII text into evenly spaced 2D targets. | generate_text_formation
upper_computer/src/algorithms/timeline_collision_worker.py | Multi-robot timeline collision detector sampling every 0.05s and outputting red warning intervals. | CollisionInterval, detect_timeline_collisions
upper_computer/src/core/__init__.py | Core infrastructure exports for paths, settings, logging, event bus, and undo stack. | WorkspacePaths, get_paths, StudioSettings, get_settings, StudioEvent, StudioEventBus, get_event_bus, StudioUndoStack
upper_computer/src/core/event_bus.py | Thread-safe decoupled pub/sub event bus coordinating domain services and UniUni v3 UI panels. | StudioEvent, StudioEventBus, get_event_bus
upper_computer/src/core/logger.py | Isolated logging configurator directing Studio logs strictly under .agent_workspace/runtime/logs/. | get_studio_logger, configure_studio_logging
upper_computer/src/core/paths.py | Centralized workspace, asset, runtime, and database path resolver preventing root directory pollution. | WorkspacePaths, get_paths
upper_computer/src/core/settings.py | Strongly-typed configuration loader and persistent settings manager backed by configs/app_settings.yaml. | StageDefaults, VirtualInterfaceSettings, StudioSettings, get_settings, save_settings
upper_computer/src/core/undo_stack.py | Bounded multi-level Undo/Redo command stack for trajectory editing, timeline manipulation, and formation updates. | UndoCommand, CallableUndoCommand, StudioUndoStack
upper_computer/src/domain/__init__.py | Domain entity exports covering scenes, tasks, tracks, trajectories, actions, timeline blocks, and PCD maps. | StageConfig, SceneEntity, TaskEntity, TrackEntity, InitPointItem, InitPointConfig, ControlPoint2D, TrajectoryGroupEntity, TrajectoryEntity, ActionEntity, TimelineBlockEntity, TimelineFragmentEntity, PcdMapEntity
upper_computer/src/domain/action_entities.py | Domain entity for dance and humanoid action assets (LRMP 33 official dances and custom CSV/NPZ). | ActionEntity
upper_computer/src/domain/map_entities.py | Domain entity for local/SLAM PCD maps, 2D occupancy grid textures, and rigid calibration transforms. | PcdMapEntity
upper_computer/src/domain/scene_entities.py | Domain entities representing UniUni stage physical bounds, scenes, and choreography tasks. | StageConfig, SceneEntity, TaskEntity
upper_computer/src/domain/timeline_entities.py | Domain entities for unified timeline lane blocks (trajectory or action) and numbered quick fragments. | TimelineBlockEntity, TimelineFragmentEntity
upper_computer/src/domain/track_entities.py | Domain entities for robot timeline tracks and multi-robot initialization point presets. | TRACK_COLOR_PALETTE, TrackEntity, InitPointItem, InitPointConfig
upper_computer/src/domain/trajectory_entities.py | Domain entities for 2D control points, trajectory groups, and UniUni-compatible trajectories. | ControlPoint2D, TrajectoryGroupEntity, TrajectoryEntity
upper_computer/src/math/__init__.py | Mathematical kernels for 2D/3D splines, arc-length lookup, S-curve timing, and 50 FPS sampling. | catmull_rom_point_2d, build_arc_length_table_2d, sample_spline_equal_distance_2d, compute_min_execution_time, build_smooth_profile, sample_trajectory_50fps, evaluate_trajectory_pose
upper_computer/src/math/catmull_rom_spline.py | 2D/3D Catmull-Rom spline evaluator and 2000-sample arc-length lookup table with O(log N) inversion. | ArcLengthTable, catmull_rom_point_2d, catmull_rom_derivative_2d, catmull_rom_point_3d, build_arc_length_table_2d, u_from_s, sample_spline_equal_distance_2d
upper_computer/src/math/rigid_transform_svd.py | 2D and 3D Kabsch SVD rigid registration solvers (R, t, yaw, RMSE) for coordinate & map calibration. | RigidCalibration2D, solve_kabsch_2d, solve_kabsch_3d, apply_rigid_2d
upper_computer/src/math/s_curve_profile.py | 7-segment jerk-limited S-curve velocity profile and physical minimum duration calculator matching UniUni. | SmoothProfile, compute_min_execution_time, build_time_frames, build_smooth_profile
upper_computer/src/math/trajectory_sampler.py | 50 FPS trajectory generator and continuous pose evaluator supporting uniform S-curve, linear, holdDirection, and endTurn. | sample_trajectory_50fps, evaluate_trajectory_pose, TrajectoryMetrics
upper_computer/src/math/vec_math.py | Pure 2D angle normalization/interpolation, segment intersection, and polyline length utilities. | clamp, normalize_angle, interpolate_angle, segments_intersect, compute_polyline_length
upper_computer/src/persistence/__init__.py | Persistence layer exports for SQLite database engine, repositories, CSV points, and UniUni JSON codec. | StudioDatabase, get_database, SceneTaskRepository, TrajectoryRepository, ActionRepository, MapFragmentRepository, CsvPointCodec, UniUniJsonCodec
upper_computer/src/persistence/action_repo.py | SQLite repository managing real serial-synced actions and user-imported local motion assets. | ActionRepository
upper_computer/src/persistence/csv_point_codec.py | Encoder and decoder for UniUni trajectoryPointData CSV strings ("t,x,y,yaw\n..."). | CsvPointCodec
upper_computer/src/persistence/db_engine.py | Thread-safe SQLite database connection manager, schema bootstrapper, and transaction context. | StudioDatabase, get_database
upper_computer/src/persistence/map_fragment_repo.py | SQLite CRUD repository for PcdMapEntity local point-cloud maps and 1..99 timeline fragments. | MapFragmentRepository
upper_computer/src/persistence/pcd_grid_generator.py | Projects 3D PCD clouds into height-filtered 2D occupancy grid PNGs for StageCanvas2D overlay. | GridMapResult, generate_occupancy_grid_png
upper_computer/src/persistence/pcd_parser.py | Memory-safe streaming PCD parser supporting ASCII, binary, and binary_compressed LZF point clouds. | PcdHeader, PcdPointCloud, parse_pcd_header, load_pcd, write_ascii_pcd
upper_computer/src/persistence/scene_task_repo.py | SQLite CRUD repository for SceneEntity, TaskEntity, TrackEntity, TimelineBlockEntity, and InitPointConfig. | SceneTaskRepository
upper_computer/src/persistence/schema_ddl.py | SQLite 10-table canonical DDL schema for scenes, tasks, tracks, trajectories, actions, blocks, init points, maps, and fragments. | SCHEMA_VERSION, ALL_TABLES_DDL
upper_computer/src/persistence/seed_builtin_data.py | Bootstraps a clean 0-robot, 0-fake-action studio stage; real actions arrive exclusively via serial sync. | ensure_seeded, seed_demo_swarm_preset
upper_computer/src/persistence/trajectory_repo.py | SQLite CRUD repository for TrajectoryGroupEntity and TrajectoryEntity with track numbering rules. | TrajectoryRepository
upper_computer/src/persistence/uniuni_json_codec.py | Lossless bidirectional JSON serializer compatible with UniUni.exe exports and time-range slicing. | UniUniJsonCodec
upper_computer/src/persistence/uniuni_slice_merger.py | Merges an exported UniUni JSON slice into the currently active Choreography task at a chosen time offset. | merge_slice_into_current_task
upper_computer/src/protocol/__init__.py | LRMP V1.0-R3 protocol, arbitration, timeline compiler, and Wi-Fi HTTP/callback exports. | ControlAuthority, LrmpFrame, LrmpCodec, AuthorityStateMachine, TimelineLrmpCompiler, HttpTrajectoryClient, RobotHttpClient, RobotHttpResponse, HttpCallbackListener, SlamMappingClient
upper_computer/src/protocol/authority_state_machine.py | Enforces LRMP V1.0-R3 FREE/MANUAL/CHOREO mutual exclusion and EMERGENCY preemption per robot. | AuthorityTransitionResult, AuthorityStateMachine
upper_computer/src/protocol/http_callback_listener.py | Upper computer HTTP webhook listener receiving authentic lower computer task-chain and telemetry callbacks. | HttpCallbackListener
upper_computer/src/protocol/http_trajectory_client.py | Dual-mode HTTP client for uploading trajectory/choreography JSON packages to robots with virtual fallback. | HttpTrajectoryClient
upper_computer/src/protocol/lrmp_codec.py | Strict LRMP V1.0-R3 ASCII frame encoder/decoder ("TARGET|COMMAND[,PARAM...]\n") and target expander. | LrmpFrame, LrmpValidationError, LrmpCodec
upper_computer/src/protocol/lrmp_constants.py | Authoritative LRMP V1.0-R3 command set, control authorities, and official 33 dance registry. | ControlAuthority, LRMP_COMMANDS, BROADCAST_ALLOWED, DANCE_ALIAS_TO_NAME, is_valid_lrmp_command
upper_computer/src/protocol/robot_http_client.py | Standard Wi-Fi HTTP client covering all 22 lower-computer endpoints (actions, task chain, ROS, system, license). | RobotHttpResponse, RobotHttpClient
upper_computer/src/protocol/slam_mapping_client.py | Teleop mapping controller dispatching navctl/MOVE/PCD retrieval over Wi-Fi HTTP with LRMP frame tracking. | MappingSessionState, SlamMappingClient
upper_computer/src/protocol/timeline_lrmp_compiler.py | Compiles multi-track timeline blocks into LRMP V1.0-R3 PREP/PLAY/DANCE/BARRIER/STOP schedules and validates safety. | ScheduledLrmpCommand, CompiledShowPlan, PreDanceCheckReport, TimelineLrmpCompiler
upper_computer/src/protocol/virtual_robot_server.py | Local virtual robot HTTP receiver simulating robot-side choreography upload verification and storage. | HttpUploadReceipt, VirtualRobotServer
upper_computer/src/protocol/virtual_slam_generator.py | Virtual SLAM scan synthesizer generating realistic ASCII PCD files driven by teleop pose integration. | VirtualSlamGenerator
upper_computer/src/services/__init__.py | Public exports for StudioStateService, PlaybackCoordinator, and G1WifiProvisioner. | StudioStateService, PlaybackCoordinator, G1WifiProvisioner
upper_computer/src/services/g1_wifi_provisioner.py | Clean adapter bridging backend.g1_wifi_service & SSH channel with TrackEntity wireless IP synchronization. | G1WifiProvisioner
upper_computer/src/services/playback_coordinator.py | 50Hz multi-viewport playback clock driving 2D stage, 3D GL avatars, task chain progress, and stop-to-origin. | PlaybackCoordinator
upper_computer/src/services/studio_http_ops.py | Wi-Fi HTTP operations for action sync, task-chain upload/prep/start, stop-to-origin, and commands. | sync_actions_from_http_op, dispatch_command_http_op, compile_and_upload_chains_http_op, start_task_chains_http_op, stop_all_robots_to_origin_http_op
upper_computer/src/services/studio_state_ops.py | Transactional CRUD, Undo/Redo, collision validation, serial sync, and settings helpers for StudioStateService. | commit_block_change_op, delete_track_with_undo_op, load_fragment_at_op, apply_settings_update_op, upsert_track_validated_op, validate_init_points_op, clamp_robot_drag_xy_op, sync_actions_from_serial_op, bind_trajectory_tracks_op
upper_computer/src/services/studio_state_service.py | Central decoupled application state facade coordinating SQLite repos, event bus, undo stack, and Wi-Fi HTTP. | StudioStateService
upper_computer/src/services/task_chain_normalizer.py | Pure task-chain sequence ordering, formatting ("A - B - C"), and lower-computer payload compiler. | ordered_track_chain, sequence_track_chain, format_track_chain_summary, active_chain_node_label, compile_track_chain_payload
upper_computer/src/ui/__init__.py | UI package root for UniUni v3 Stage Choreography & Swarm Control desktop shell. | __all__
upper_computer/src/ui/choreography/__init__.py | Exports for Stage Choreography page, viewport, playback scrubber, timeline editor, and right libraries. | ActionLibPanel, BatchChoreoDrawer, ChoreographyPage, EditorOpbar, PreviewMapPanel, PlaybackProgressBar, StageCanvas2D, TaskEditorWidget, TimelineHeader, TimelineLaneView, TrackLibPanel, BLOCK_MIME_TYPE
upper_computer/src/ui/choreography/action_lib_panel.py | Right-Bottom Action Library listing all 33 LRMP dances & custom CSV/NPZ motions with filter and CRUD. | ActionLibPanel
upper_computer/src/ui/choreography/batch_choreo_drawer.py | Push drawer for batch-appending actions into all active robot task chains. | BatchChoreoDrawer
upper_computer/src/ui/choreography/choreography_page.py | Complete UniUni Page 1 Choreography layout pairing Left Stage+Timeline and Right 330px Libraries. | ChoreographyPage
upper_computer/src/ui/choreography/editor_opbar.py | Compact 2-column vertical operation toolbar for TaskEditor keeping minimum height <= 155px for 70:30 split. | EditorOpbar
upper_computer/src/ui/choreography/playback_progress_bar.py | Floating UniUni playback bar with scrubbed seek track, stop-to-origin button, collision markers, and active chain label. | PlaybackProgressBar
upper_computer/src/ui/choreography/preview_map_panel.py | UniUni PreviewMap container pairing stacked 3D/2D viewports, inline trajectory draw bar, and scrubber. | PreviewMapPanel
upper_computer/src/ui/choreography/stage_canvas_2d.py | Interactive 2D metric stage canvas with inline trajectory drawing, sketch brush, robot drag, and PCD map overlay. | StageCanvas2D
upper_computer/src/ui/choreography/stage_draw_overlay.py | UniUni-style inline stage drawing toolbar (轨迹绘制, 草图笔, 清空草图, 清空轨迹, 保存轨迹) and coord HUD. | StageDrawToolbar, StageHintFooter
upper_computer/src/ui/choreography/stage_painters.py | Modular QPainter render helpers for 2D stage grid, occupancy PNGs, splines, draft drawing, sketches, and robots. | world_to_screen, screen_to_world, paint_grid_and_stage, paint_occupancy_map, paint_trajectories, paint_robots_and_collisions, paint_draft_trajectory, paint_sketches, paint_empty_stage_hint
upper_computer/src/ui/choreography/task_editor_widget.py | UniUni TaskEditor container combining 38px TimelineHeader, 40px EditorOpbar, and scrollable TimelineLaneView. | TaskEditorWidget
upper_computer/src/ui/choreography/timeline_block_painter.py | High-contrast QPainter renderers for task-chain flow bar, robot lanes, and chained pure-name blocks. | RULER_H, LANE_H, compute_chain_block_width, paint_ruler, paint_track_sidebar, paint_lane_blocks, paint_empty_timeline_hint
upper_computer/src/ui/choreography/timeline_collision_clamp.py | Rigid-body collision clamp preventing same-type timeline blocks from overlapping on the same track. | same_type_siblings, clamp_move_start, clamp_resize_duration, resolve_non_overlapping_slot
upper_computer/src/ui/choreography/timeline_context_menus.py | Track header and task-chain node right-click context menus, chain reordering, and split/undo helpers. | show_track_context_menu, show_block_context_menu, split_block_at_time, reorder_block_in_chain
upper_computer/src/ui/choreography/timeline_header.py | 38px UniUni task-chain top control bar with play/stop-to-origin, track/task dialogs, BPM, and HTTP deploy. | TimelineHeader
upper_computer/src/ui/choreography/timeline_lane_view.py | Interactive multi-robot timeline canvas with drag-drop, undo/redo, lock/mute, track CRUD context menu, and scrub. | TimelineLaneView
upper_computer/src/ui/choreography/track_lib_panel.py | UniUni Right-Column Trajectory Library with collapsible groups, track binding, drag-to-timeline, and JSON I/O. | TrackLibPanel, BLOCK_MIME_TYPE
upper_computer/src/ui/choreography/track_lib_row.py | Trajectory Library row widget with visibility checkbox, multi-robot binding dialog, drag-drop, edit, and delete. | TrajectoryRowWidget, BindRobotsDialog
upper_computer/src/ui/design_system/__init__.py | Public exports for UniUni v3 design system tokens, icons, QSS, and U* widget primitives. | build_ugc_v3_stylesheet, render_svg_icon, get_icon_pixmap, UButton, UIconButton, USegmented, UBadge, UInputNumber, UTimeInput, USearchInput, USelect, UPanel, UCollapsibleGroup, UTable, UEmpty, UDialog, UDrawer, UFloatBar
upper_computer/src/ui/design_system/svg_icons.py | Crisp DPI-aware vector SVG icon factory eliminating blurry text/emoji icons across toolbars. | SVG_PATHS, render_svg_icon, get_icon_pixmap
upper_computer/src/ui/design_system/tokens.py | Authoritative UniUni v3 design tokens (ugc-v3.css) for dark surfaces, brand accents, typography, and layout sizing. | C_CANVAS, C_BASE, C_PANEL, C_CARD, C_CONTROL, C_CONTROL_HOVER, C_FLOAT, C_ACCENT, C_OK, C_WARN, C_DANGER, ROBOT_COLORS, C_TEXT_1, C_TEXT_2, C_TEXT_3, LINE, LINE_STRONG, H_HEADER, H_STATUS, W_RIGHT_LIB, W_OPBAR, W_TRACK_HEAD
upper_computer/src/ui/design_system/u_buttons.py | Unified UButton, UIconButton, USegmented, and UBadge controls guaranteeing zero text truncation. | UButton, UIconButton, USegmented, UBadge
upper_computer/src/ui/design_system/u_dialog.py | Floating-surface UDialog, push UDrawer, and translucent UFloatBar canvas overlay components. | UDialog, UDrawer, UFloatBar
upper_computer/src/ui/design_system/u_inputs.py | Numeric, timecode, dropdown, and search input controls conforming to UniUni v3 dark styling. | UInputNumber, UTimeInput, USearchInput, USelect
upper_computer/src/ui/design_system/u_panels.py | Structural containers UPanel, UCollapsibleGroup (.group-card), UTable, and UEmpty for UniUni v3 panels. | UPanel, UCollapsibleGroup, UTable, UEmpty
upper_computer/src/ui/design_system/ugc_v3_qss.py | Complete UniUni ugc-v3.css compiled into PySide6 QSS eliminating colorful clutter and enforcing hairlines. | build_ugc_v3_stylesheet
upper_computer/src/ui/formation/__init__.py | Public exports for Swarm Formation Design and Potential-Field Planning page. | FormationControlDock, FormationGroupDock, FormationPlannerCanvas, FormationPlanningPage
upper_computer/src/ui/formation/formation_control_dock.py | Right 310px UniUni controls.html-inspired formation parameter & potential-field solver control dock. | FormationControlDock
upper_computer/src/ui/formation/formation_group_dock.py | Left 250px robot swarm source/target table & quick scatter dock inside FormationPlanningPage. | FormationGroupDock
upper_computer/src/ui/formation/formation_planner_canvas.py | Interactive 2D swarm formation visualizer displaying sources, draggable target slots, and collision-free paths. | FormationPlannerCanvas
upper_computer/src/ui/formation/formation_planning_page.py | Complete UniUni Page 2 Swarm Formation Design & Multi-Robot Action Planning workspace. | FormationPlanningPage
upper_computer/src/ui/mapping/__init__.py | Public exports for PCD Map Library, Teleop SLAM Dock, and NavigationMapPage. | NavigationMapPage, PcdMapLibraryDock, TeleopMappingDock
upper_computer/src/ui/mapping/navigation_map_page.py | Clean 3-column UniUni Page 3 Mapping & Navigation workspace (PCD Manager | 3D/2D Viewer | Teleop SLAM). | NavigationMapPage
upper_computer/src/ui/mapping/pcd_map_library_dock.py | Clean zero-overlap PCD Map Library dock supporting local upload, stage loading, rename, calibration, and delete. | PcdMapLibraryDock
upper_computer/src/ui/mapping/teleop_mapping_dock.py | Right 290px Teleop SLAM control panel sending LRMP MOVE commands & saving simulated/live .pcd maps. | TeleopMappingDock
upper_computer/src/ui/modals/__init__.py | Public exports for all 12 UniUni choreography, track, stage, safety, calibration, and map modals. | AddTrackDialog, BpmInfoModal, CoordTransformModal, CustomMapModal, DeviceOverviewModal, FragmentSaveDialog, InitPointModal, PreDanceCheckModal, RangeExportImportDialog, StageSizeModal, SwitchTaskModal, TaskJsonViewerModal, TrajectoryDrawCanvas, TrajectoryEditorModal
upper_computer/src/ui/modals/add_track_dialog.py | Modal dialog for adding or editing a real robot timeline track with LRMP uniqueness validation. | AddTrackDialog
upper_computer/src/ui/modals/bpm_info_modal.py | Modal dialog configuring stage music BPM, time signature, and audio accompaniment path. | BpmInfoModal
upper_computer/src/ui/modals/coord_transform_modal.py | 2D SVD Kabsch coordinate calibration dialog aligning stage frame with scanned PCD map frame. | CoordTransformModal
upper_computer/src/ui/modals/custom_map_modal.py | Quick modal to import a local .pcd file with configurable occupancy grid slicing parameters. | CustomMapModal
upper_computer/src/ui/modals/device_overview_modal.py | Interactive fleet device manager modal with real robot add, edit, delete, and LRMP authority reset. | DeviceOverviewModal
upper_computer/src/ui/modals/fragment_save_dialog.py | Full CRUD manager for saving, browsing, inserting onto timeline, and deleting choreography fragments. | FragmentSaveDialog
upper_computer/src/ui/modals/init_point_modal.py | Multi-robot initial pose editor & full preset CRUD loader/saver/deleter (InitPointConfig). | InitPointModal
upper_computer/src/ui/modals/pre_dance_check_modal.py | Dual-mode Pre-performance Audit Checklist and Cluster HTTP Choreography Uploader dialog. | PreDanceCheckModal
upper_computer/src/ui/modals/range_export_import_dialog.py | Time-range JSON slice exporter and importer for merging choreography sections. | RangeExportImportDialog
upper_computer/src/ui/modals/stage_size_modal.py | Modal dialog editing physical stage width, height, and safety perimeter margin. | StageSizeModal
upper_computer/src/ui/modals/switch_task_modal.py | Task selector modal supporting task creation, switching, and deletion. | SwitchTaskModal
upper_computer/src/ui/modals/task_json_viewer_modal.py | Live JSON inspector and clipboard/file exporter for UniUni task & trajectory structures. | TaskJsonViewerModal
upper_computer/src/ui/modals/trajectory_draw_canvas.py | Interactive 2D spline & freehand sketch canvas inside TrajectoryEditorModal with live Catmull-Rom preview. | TrajectoryDrawCanvas
upper_computer/src/ui/modals/trajectory_editor_modal.py | UniUni TaskTrajectory dialog supporting 2D spline drawing, timing, orientation, CSV preview, delete, and HTTP upload. | TrajectoryEditorModal
upper_computer/src/ui/monitoring/__init__.py | Public exports for Live Show Monitor and Radar Telemetry pages. | PerformanceMonitorPage, RadarMonitorPage
upper_computer/src/ui/monitoring/performance_monitor_page.py | UniUni Page 4 Live Show Monitor executing task-chain PREP/PLAY/STOP-to-origin/EMERGENCY via Wi-Fi HTTP. | PerformanceMonitorPage
upper_computer/src/ui/monitoring/radar_monitor_page.py | UniUni Page 5 Live Radar & Safety Perimeter Telemetry monitoring view synced with playhead and tracks. | RadarMonitorPage
upper_computer/src/ui/network/__init__.py | Public exports for G1 wireless setup wizard and System Network Settings page. | SystemNetworkPage, WifiWizardPanel
upper_computer/src/ui/network/system_network_page.py | UniUni Page 6 Network Provisioning & System Settings workspace with persistent settings and stage reset. | SystemNetworkPage
upper_computer/src/ui/network/wifi_wizard_panel.py | Step-by-step Unitree G1 LoRa wireless provisioning (scan -> connect -> IPv4) -> Wi-Fi HTTP sync panel. | WifiWizardPanel
upper_computer/src/ui/shell/__init__.py | Exports UniUni shell navigation titlebar, statusbar, shortcut manager, and main shell window. | PAGE_DEFS, UTitlebar, UStatusBar, ShortcutManager, UniUniAppShell
upper_computer/src/ui/shell/app_shell_window.py | Master UniUni v3 main window shell with 32px UTitlebar, 6-page QStackedWidget, and 28px UStatusBar. | UniUniAppShell
upper_computer/src/ui/shell/shortcut_manager.py | Global UniUni shell keyboard shortcut registrar (Space, Ctrl+S, Ctrl+Z/Y, 1..6 page switch). | ShortcutManager
upper_computer/src/ui/shell/u_statusbar.py | UniUni v3 28px bottom status bar displaying version, scene, init points, music, timecode, IP, and alerts. | UStatusBar
upper_computer/src/ui/shell/u_titlebar.py | UniUni v3 32px top navigation header (uniswarm logo, 6 page tabs, global Device/Scene/Help actions). | PAGE_DEFS, UTitlebar
upper_computer/src/ui/theme/__init__.py | Transitional theme package exporting apply_uniuni_theme and apply_fusion_dark_theme for main.py compatibility. | apply_uniuni_theme, apply_fusion_dark_theme
upper_computer/src/ui/theme/fusion_dark_theme.py | Compatibility theme entry forwarding to the UniUni v3 theme engine. | apply_fusion_dark_theme
upper_computer/src/ui/theme/uniuni_inspired_theme.py | Applies complete UniUni v3 design-system QSS and dark Fusion palette to QApplication. | apply_uniuni_theme
upper_computer/src/ui/windows/__init__.py | Window facades package exposing MainStudioWindow for main.py launcher. | MainStudioWindow
upper_computer/src/ui/windows/main_studio_window.py | Studio entrypoint window composing the UniUni v3 shell and assembling all 6 functional workspace pages. | MainStudioWindow
upper_computer/src/viewport3d/__init__.py | Public exports for Unitree G1 29-DOF kinematics, STL caching, motion playback, and 3D OpenGL viewport. | DanceMotionClip, DanceMotionPlayer, G1KinematicsChain, OrbitCamera, StageViewport3D, StlVboCache, get_g1_kinematics, procedural_gait_angles
upper_computer/src/viewport3d/dance_motion_player.py | Loads preview NPZ 21-joint/joint_pos dances, G1_dance.csv 36-col mocap, and BASIC/gait 29-DOF poses. | DanceMotionClip, DanceMotionPlayer, procedural_gait_angles
upper_computer/src/viewport3d/g1_kinematics_chain.py | Vectorized 29-DOF URDF Forward Kinematics solver backed by backend/models/g1_29dof_rubber_hand/g1_29dof_mode_15.urdf. | UrdfJoint, UrdfVisualLink, G1KinematicsChain, get_g1_kinematics
upper_computer/src/viewport3d/orbit_camera.py | 3D spherical orbit, pan, and preset viewpoint camera controller for the StageViewport3D OpenGL scene. | OrbitCamera
upper_computer/src/viewport3d/stage_viewport_3d.py | Real-time 3D OpenGL stage viewport rendering articulated 29-DOF Unitree G1 robots, spline paths, and PCD clouds. | StageViewport3D
upper_computer/src/viewport3d/stl_vbo_cache.py | Fast vectorized binary/ASCII STL loader and G1 multi-material color mapper for OpenGL. | StlMeshData, StlVboCache, g1_link_material_rgb

## lower_computer (21 modules)
lower_computer/src/__init__.py | Lower computer package root for ROS 1.17.4 navigation bridge, LRMP command executor, task chain engine, and HTTP server. | __version__
lower_computer/src/api/__init__.py | Exports for lower computer standard HTTP REST router and threaded server. | LowerComputerContext, dispatch_http_request, LowerComputerHttpServer
lower_computer/src/api/http_server.py | Standard HTTP/1.1 multi-threaded REST server hosting lower computer routes. | LowerComputerHttpServer
lower_computer/src/api/routes.py | Standard HTTP REST route dispatcher for lower computer ROS navigation, task chain, motion, and system ops. | LowerComputerContext, dispatch_http_request
lower_computer/src/api/system_routes.py | Sub-router handling /api/v1/system/*, /api/v1/license/*, /api/v1/dance/*, and /api/v1/lora_wifi/* routes. | dispatch_system_route
lower_computer/src/commands/__init__.py | Exports for lower computer LRMP V1.0-R3 control arbiter, motion executor, system ops, and LoRa Wi-Fi agent. | ControlAuthority, ArbiterDecision, ControlArbiter, CommandExecutionResult, MotionCommandExecutor, SystemOpsService, LoraWifiAgent
lower_computer/src/commands/control_arbiter.py | Enforces LRMP V1.0-R3 FREE/MANUAL/CHOREO authority mutual exclusion and timeout safety. | ControlAuthority, ArbiterDecision, ControlArbiter
lower_computer/src/commands/lora_serial_daemon.py | Onboard LoRa serial listener receiving TARGET|WIFI_* provisioning frames and replying with WIFI_ACK JSON. | LoraSerialWifiDaemon
lower_computer/src/commands/lora_wifi_agent.py | Lower-computer LoRa serial Wi-Fi provisioning receiver executing authentic nmcli probe/scan/connect/IPv4 commands. | LoraWifiAgent
lower_computer/src/commands/motion_command_executor.py | Implements known G1 LRMP/ROS commands and reserves structured extension slots for unexposed dances. | CommandExecutionResult, MotionCommandExecutor
lower_computer/src/commands/system_ops_service.py | Onboard system service for machine ID, license deployment, dance package hot-update, processes, and logs. | SystemOpsService
lower_computer/src/config/__init__.py | Exports for lower computer ROS environment constants and onboard configuration readers. | ROS_COMPONENTS, ROS_LAUNCH_COMMANDS, NAVCTL_BIN, NAVCTL_ACTIONS, ROS_TOPICS, ROS_SERVICES, RosEnvConfig, RobotConfigReader
lower_computer/src/config/robot_config_reader.py | Reads authentic onboard robot_id, lora_recv_group.yaml dance_map, license, and hardware machine ID. | RobotConfigReader
lower_computer/src/config/ros_env_config.py | Authoritative ROS 1.17.4, navctl, topic/service, and G1 deploy path definitions from 下位机ros信息. | ROS_COMPONENTS, ROS_LAUNCH_COMMANDS, NAVCTL_BIN, NAVCTL_ACTIONS, ROS_TOPICS, ROS_SERVICES, RosEnvConfig
lower_computer/src/ros_bridge/__init__.py | Exports for real ROS 1.17.4 navctl runner, topic/service/TF bridge, and ROS diagnostics inspector. | NavctlRunner, NavctlResult, RosTopicServiceBridge, RosTelemetrySnapshot, RosNavDiagnostics
lower_computer/src/ros_bridge/navctl_runner.py | Executes real /opt/vsis_nav/navctl commands and parses authentic process output. | NavctlResult, NavctlRunner
lower_computer/src/ros_bridge/ros_nav_diagnostics.py | Deep ROS 1.17.4 graph, topic rate, TF map->base_link, global path, and TEB parameter inspector. | RosNavDiagnostics
lower_computer/src/ros_bridge/ros_topic_service_bridge.py | Authentic ROS 1.17.4 topic/TF/service bridge without synthetic or demo telemetry. | RosTelemetrySnapshot, RosTopicServiceBridge
lower_computer/src/task_chain/__init__.py | Exports for lower computer sequential task chain executor and real HTTP webhook callback dispatcher. | CallbackReceipt, WebhookDispatcher, TaskChainState, TaskChainExecutor
lower_computer/src/task_chain/task_chain_executor.py | Arrival-driven sequential task chain executor with BARRIER gates, ROS pose telemetry, and return-to-origin tracking. | TaskChainState, TaskChainExecutor
lower_computer/src/task_chain/webhook_dispatcher.py | Sends authentic HTTP POST JSON callbacks to upper computer without synthetic or fake success. | CallbackReceipt, WebhookDispatcher

