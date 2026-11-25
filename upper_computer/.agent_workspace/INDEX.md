# upper_computer Module Index (Auto-Generated for Hydrogen High)

Format: `path | brief | exported_symbols`

src/__init__.py | Root package marker for Stage Stage Choreography & Swarm Control source modules. | __version__
src/algorithms/__init__.py | Swarm formation, 2-opt assignment, potential-field solver, and timeline collision detection exports. | generate_formation, assign_targets_2opt, count_path_crossings, generate_scatter_positions, PotentialFieldParams, SwarmSimulationResult, solve_swarm_potential_field, rdp_simplify, CollisionInterval, detect_timeline_collisions
src/algorithms/formation_generators.py | Parametric 2D multi-robot formation generators (line, circle, grid, wedge, staggered, polygon). | FormationKind, generate_formation
src/algorithms/potential_field_solver.py | stage potential-field collision-free swarm trajectory planner with 3-pass safety projection and RDP simplification. | PotentialFieldParams, SwarmSimulationResult, rdp_simplify, compute_segment_times, solve_swarm_potential_field
src/algorithms/scatter_stage.py | Two-ring radial intermediate scatter formation breaking high-crossing deadlocks in swarm transitions. | CROSSING_THRESHOLD, generate_scatter_positions
src/algorithms/spatial_hash_grid.py | O(1) spatial hash grid accelerating neighbor queries in potential-field and collision workers. | SpatialHashGrid
src/algorithms/target_assignment.py | Greedy nearest-neighbor + 2-opt swap solver minimizing total distance and path crossings. | count_path_crossings, assign_targets_2opt
src/algorithms/text_formation.py | Character/text glyph bitmap sampler converting any Chinese or ASCII text into evenly spaced 2D targets. | generate_text_formation
src/algorithms/timeline_collision_worker.py | Multi-robot timeline collision detector sampling every 0.05s and outputting red warning intervals. | CollisionInterval, detect_timeline_collisions
src/core/__init__.py | Core infrastructure exports for paths, settings, logging, event bus, and undo stack. | WorkspacePaths, get_paths, StudioSettings, get_settings, StudioEvent, StudioEventBus, get_event_bus, StudioUndoStack
src/core/event_bus.py | Thread-safe decoupled pub/sub event bus coordinating domain services and desktop v3 UI panels with cross-thread marshalling. | StudioEvent, StudioEventBus, get_event_bus
src/core/logger.py | Isolated logging configurator directing Studio logs strictly under .agent_workspace/runtime/logs/. | get_studio_logger, configure_studio_logging
src/core/paths.py | Centralized workspace, asset, runtime, and database path resolver preventing root directory pollution. | WorkspacePaths, get_paths
src/core/settings.py | Strongly-typed configuration loader and persistent settings manager backed by configs/app_settings.yaml. | StageDefaults, VirtualInterfaceSettings, StudioSettings, get_settings, save_settings
src/core/undo_stack.py | Bounded multi-level Undo/Redo command stack for trajectory editing, timeline manipulation, and formation updates. | UndoCommand, CallableUndoCommand, StudioUndoStack
src/domain/__init__.py | Domain entity exports covering scenes, tasks, tracks, trajectories, actions, timeline blocks, and PCD maps. | StageConfig, SceneEntity, TaskEntity, TrackEntity, InitPointItem, InitPointConfig, ControlPoint2D, TrajectoryGroupEntity, TrajectoryEntity, ActionEntity, TimelineBlockEntity, TimelineFragmentEntity, PcdMapEntity
src/domain/action_entities.py | Domain entity for dance and humanoid action assets (LRMP 33 official dances and custom CSV/NPZ). | ActionEntity
src/domain/map_entities.py | Domain entity for local/SLAM PCD maps, 2D occupancy grid textures, and rigid calibration transforms. | PcdMapEntity
src/domain/scene_entities.py | Domain entities representing stage stage physical bounds, scenes, and choreography tasks. | StageConfig, SceneEntity, TaskEntity
src/domain/timeline_entities.py | Domain entities for unified timeline lane blocks (trajectory or action) and numbered quick fragments. | TimelineBlockEntity, TimelineFragmentEntity
src/domain/track_entities.py | Domain entities for robot timeline tracks and multi-robot initialization point presets. | TRACK_COLOR_PALETTE, TrackEntity, InitPointItem, InitPointConfig
src/domain/trajectory_entities.py | Domain entities for 2D control points, trajectory groups, and stage-compatible trajectories. | ControlPoint2D, TrajectoryGroupEntity, TrajectoryEntity
src/math/__init__.py | Mathematical kernels for 2D/3D splines, arc-length lookup, S-curve timing, and 50 FPS sampling. | catmull_rom_point_2d, build_arc_length_table_2d, sample_spline_equal_distance_2d, compute_min_execution_time, build_smooth_profile, sample_trajectory_50fps, evaluate_trajectory_pose
src/math/catmull_rom_spline.py | 2D/3D Catmull-Rom spline evaluator and 2000-sample arc-length lookup table with O(log N) inversion. | ArcLengthTable, catmull_rom_point_2d, catmull_rom_derivative_2d, catmull_rom_point_3d, build_arc_length_table_2d, u_from_s, sample_spline_equal_distance_2d
src/math/rigid_transform_svd.py | 2D and 3D Kabsch SVD rigid registration solvers (R, t, yaw, RMSE) for coordinate & map calibration. | RigidCalibration2D, solve_kabsch_2d, solve_kabsch_3d, apply_rigid_2d
src/math/s_curve_profile.py | 7-segment jerk-limited S-curve velocity profile and physical minimum duration calculator matching standard stage specs. | SmoothProfile, compute_min_execution_time, build_time_frames, build_smooth_profile
src/math/trajectory_sampler.py | 50 FPS trajectory generator and continuous pose evaluator supporting uniform S-curve, linear, holdDirection, and endTurn. | sample_trajectory_50fps, evaluate_trajectory_pose, TrajectoryMetrics
src/math/vec_math.py | Pure 2D angle normalization/interpolation, segment intersection, and polyline length utilities. | clamp, normalize_angle, interpolate_angle, segments_intersect, compute_polyline_length
src/persistence/__init__.py | Persistence layer exports for SQLite database engine, repositories, CSV points, and stage JSON codec. | StudioDatabase, get_database, SceneTaskRepository, TrajectoryRepository, ActionRepository, MapFragmentRepository, CsvPointCodec, StudioJsonCodec
src/persistence/action_repo.py | SQLite repository managing real serial-synced actions and user-imported local motion assets. | ActionRepository
src/persistence/csv_point_codec.py | Encoder and decoder for stage trajectoryPointData CSV strings ("t,x,y,yaw\n..."). | CsvPointCodec
src/persistence/db_engine.py | Thread-safe SQLite database connection manager, schema bootstrapper, and transaction context. | StudioDatabase, get_database
src/persistence/map_fragment_repo.py | SQLite CRUD repository for PcdMapEntity local point-cloud maps and 1..99 timeline fragments. | MapFragmentRepository
src/persistence/pcd_grid_generator.py | Projects 3D PCD clouds into height-filtered 2D occupancy grid PNGs for StageCanvas2D overlay. | GridMapResult, generate_occupancy_grid_png
src/persistence/pcd_parser.py | Memory-safe streaming PCD parser supporting ASCII, binary, and binary_compressed LZF point clouds. | PcdHeader, PcdPointCloud, parse_pcd_header, load_pcd, write_ascii_pcd
src/persistence/scene_task_repo.py | SQLite CRUD repository for SceneEntity, TaskEntity, TrackEntity, TimelineBlockEntity, and InitPointConfig. | SceneTaskRepository
src/persistence/schema_ddl.py | SQLite 10-table canonical DDL schema for scenes, tasks, tracks, trajectories, actions, blocks, init points, maps, and fragments. | SCHEMA_VERSION, ALL_TABLES_DDL
src/persistence/seed_builtin_data.py | Bootstraps a clean 0-robot, 0-fake-action studio stage; real actions arrive exclusively via serial sync. | ensure_seeded, seed_demo_swarm_preset
src/persistence/studio_json_codec.py | Lossless bidirectional JSON serializer for stage choreography tasks, tracks, trajectories, actions, and slices. | StudioJsonCodec
src/persistence/studio_slice_merger.py | Merges an exported stage JSON slice into the currently active Choreography task at a chosen time offset. | merge_slice_into_current_task
src/persistence/trajectory_repo.py | SQLite CRUD repository for TrajectoryGroupEntity and TrajectoryEntity with track numbering rules. | TrajectoryRepository
src/protocol/__init__.py | LRMP V1.0-R3 protocol, arbitration, timeline compiler, and Wi-Fi HTTP/callback exports. | ControlAuthority, LrmpFrame, LrmpCodec, AuthorityStateMachine, TimelineLrmpCompiler, HttpTrajectoryClient, RobotHttpClient, RobotHttpResponse, HttpCallbackListener, SlamMappingClient
src/protocol/authority_state_machine.py | Enforces LRMP V1.0-R3 FREE/MANUAL/CHOREO mutual exclusion and EMERGENCY preemption per robot. | AuthorityTransitionResult, AuthorityStateMachine
src/protocol/http_callback_listener.py | Upper computer HTTP webhook listener receiving authentic lower computer task-chain and telemetry callbacks. | HttpCallbackListener
src/protocol/http_trajectory_client.py | Dual-mode HTTP client for uploading trajectory/choreography JSON packages to robots with virtual fallback. | HttpTrajectoryClient
src/protocol/lrmp_codec.py | Strict LRMP V1.0-R3 ASCII frame encoder/decoder ("TARGET|COMMAND[,PARAM...]\n") and target expander. | LrmpFrame, LrmpValidationError, LrmpCodec
src/protocol/lrmp_constants.py | Authoritative LRMP V1.0-R3 command set, control authorities, and official 33 dance registry. | ControlAuthority, LRMP_COMMANDS, BROADCAST_ALLOWED, DANCE_ALIAS_TO_NAME, is_valid_lrmp_command
src/protocol/robot_http_client.py | Standard Wi-Fi HTTP client covering all lower-computer endpoints (actions, task chain, motion, ROS relocalize, system). | RobotHttpResponse, RobotHttpClient
src/protocol/robot_http_system_mixin.py | System, container, license, dance ZIP, and PCD transfer HTTP methods mixed into RobotHttpClient. | RobotHttpResponse, RobotHttpSystemMixin
src/protocol/slam_mapping_client.py | Authentic ROS/Wi-Fi HTTP teleop SLAM mapping client without synthetic point cloud or fake map fallbacks. | MappingSessionState, SlamMappingClient
src/protocol/timeline_lrmp_compiler.py | Compiles multi-track timeline blocks into LRMP V1.0-R3 PREP/PLAY/DANCE/BARRIER/STOP schedules and validates safety. | ScheduledLrmpCommand, CompiledShowPlan, PreDanceCheckReport, TimelineLrmpCompiler
src/protocol/virtual_robot_server.py | Local virtual robot HTTP receiver simulating robot-side choreography upload verification and storage. | HttpUploadReceipt, VirtualRobotServer
src/protocol/virtual_slam_generator.py | Virtual SLAM scan synthesizer generating realistic ASCII PCD files driven by teleop pose integration. | VirtualSlamGenerator
src/services/__init__.py | Public exports for StudioStateService and PlaybackCoordinator. | StudioStateService, PlaybackCoordinator
src/services/playback_coordinator.py | 50Hz multi-viewport playback clock driving 2D stage, 3D GL avatars, task chain progress, and stop-to-origin. | PlaybackCoordinator
src/services/studio_http_ops.py | Wi-Fi HTTP operations for action sync, fleet health, task-chain upload/prep/start, barrier, stop-to-origin, and commands (all blocking; run via BackgroundTaskRunner). | sync_actions_from_http_op, fleet_health_op, dispatch_command_http_op, dispatch_targets_http_op, compile_and_upload_chains_http_op, start_task_chains_http_op, barrier_task_chains_http_op, stop_all_robots_to_origin_http_op
src/services/studio_state_ops.py | Transactional CRUD, Undo/Redo, collision validation, serial sync, and settings helpers for StudioStateService. | commit_block_change_op, delete_track_with_undo_op, load_fragment_at_op, apply_settings_update_op, upsert_track_validated_op, validate_init_points_op, clamp_robot_drag_xy_op, sync_actions_from_serial_op, bind_trajectory_tracks_op
src/services/studio_state_service.py | Central decoupled application state facade coordinating SQLite repos, event bus, undo stack, and Wi-Fi HTTP. | StudioStateService
src/services/task_chain_normalizer.py | Pure task-chain sequence ordering, formatting ("A - B - C"), and lower-computer payload compiler. | ordered_track_chain, sequence_track_chain, format_track_chain_summary, active_chain_node_label, compile_track_chain_payload
src/ui/__init__.py | UI package root for desktop v3 Stage Choreography & Swarm Control desktop shell. | __all__
src/ui/choreography/__init__.py | Exports for Stage Choreography page, viewport, playback scrubber, timeline editor, and right libraries. | ActionLibPanel, BatchChoreoDrawer, ChoreographyPage, EditorOpbar, PreviewMapPanel, PlaybackProgressBar, StageCanvas2D, TaskEditorWidget, TimelineHeader, TimelineLaneView, TrackLibPanel, BLOCK_MIME_TYPE
src/ui/choreography/action_lib_panel.py | Right-Bottom Action Library listing all 33 LRMP dances & custom CSV/NPZ motions with filter and CRUD. | ActionLibPanel
src/ui/choreography/batch_choreo_drawer.py | Push drawer for batch-appending actions into all active robot task chains. | BatchChoreoDrawer
src/ui/choreography/choreography_page.py | Complete stage Page 1 Choreography layout pairing Left Stage+Timeline and Right 330px Libraries. | ChoreographyPage
src/ui/choreography/editor_opbar.py | Clean single-column task-chain editing toolbar with 4 large ergonomic action buttons (<=160px height). | EditorOpbar
src/ui/choreography/playback_progress_bar.py | Floating playback bar with scrubbed seek track, stop-to-origin button, collision markers, and active chain label. | PlaybackProgressBar
src/ui/choreography/preview_map_panel.py | PreviewMap container pairing stacked 3D/2D viewports, inline trajectory draw bar, and scrubber. | PreviewMapPanel
src/ui/choreography/stage_canvas_2d.py | Interactive 2D metric stage canvas with inline trajectory drawing, sketch brush, robot drag, and PCD map overlay. | StageCanvas2D
src/ui/choreography/stage_draw_overlay.py | Inline stage drawing toolbar (选择/移动, 轨迹绘制, 草图笔, 清空草图, 清空轨迹, 保存轨迹) and coord HUD. | StageDrawToolbar, StageHintFooter
src/ui/choreography/stage_live_nav_painter.py | Renders real-time ROS robot pose, global path, /cad_scan contour, goal marker, and pose-drag arrow on 2D map. | LiveNavOverlayState, paint_live_nav_overlay
src/ui/choreography/stage_painters.py | Modular QPainter render helpers for 2D stage grid, occupancy PNGs, splines, draft drawing, sketches, and robots. | world_to_screen, screen_to_world, paint_grid_and_stage, paint_occupancy_map, paint_trajectories, paint_robots_and_collisions, paint_draft_trajectory, paint_sketches, paint_empty_stage_hint
src/ui/choreography/task_editor_widget.py | stage TaskEditor container combining 38px TimelineHeader, 40px EditorOpbar, and scrollable TimelineLaneView. | TaskEditorWidget
src/ui/choreography/timeline_block_painter.py | High-contrast QPainter renderers for task-chain flow bar, robot lanes, and chained pure-name blocks. | RULER_H, LANE_H, compute_chain_block_width, paint_ruler, paint_track_sidebar, paint_lane_blocks, paint_empty_timeline_hint
src/ui/choreography/timeline_collision_clamp.py | Rigid-body collision clamp preventing same-type timeline blocks from overlapping on the same track. | same_type_siblings, clamp_move_start, clamp_resize_duration, resolve_non_overlapping_slot
src/ui/choreography/timeline_context_menus.py | Track header and task-chain node right-click context menus, chain reordering, and split/undo helpers. | show_track_context_menu, show_block_context_menu, split_block_at_time, reorder_block_in_chain
src/ui/choreography/timeline_header.py | 38px stage task-chain top control bar with local preview controls, track/task dialogs, and HTTP deploy. | TimelineHeader
src/ui/choreography/timeline_lane_view.py | Interactive multi-robot timeline canvas with drag-drop, undo/redo, lock/mute, track CRUD context menu, and scrub. | TimelineLaneView
src/ui/choreography/track_lib_panel.py | Right-Column Trajectory Library with collapsible groups, track binding, drag-to-timeline, and JSON I/O. | TrackLibPanel, BLOCK_MIME_TYPE
src/ui/choreography/track_lib_row.py | Trajectory Library row widget with visibility checkbox, multi-robot binding dialog, drag-drop, edit, and delete. | TrajectoryRowWidget, BindRobotsDialog
src/ui/common/__init__.py | Shared UI infrastructure: background task runner keeping blocking robot I/O off the Qt GUI thread. | BackgroundTaskRunner, TaskHandle, get_task_runner, run_in_background, wait_for_all_tasks
src/ui/common/async_task.py | Qt-friendly background runner executing blocking network/SSH/PCD work on QThreadPool with GUI-thread result delivery. | BackgroundTaskRunner, TaskHandle, get_task_runner, run_in_background, wait_for_all_tasks, reset_task_runner
src/ui/design_system/__init__.py | Public exports for desktop v3 design system tokens, icons, QSS, and U* widget primitives. | build_ugc_v3_stylesheet, render_svg_icon, get_icon_pixmap, UButton, UIconButton, USegmented, UBadge, UHelpIcon, UInputNumber, UTimeInput, USearchInput, USelect, UPanel, UCollapsibleGroup, UTable, UEmpty, UDialog, UDrawer, UFloatBar
src/ui/design_system/svg_icons.py | Crisp DPI-aware vector SVG icon factory eliminating blurry text/emoji icons across toolbars. | SVG_PATHS, render_svg_icon, get_icon_pixmap
src/ui/design_system/tokens.py | Authoritative desktop v3 design tokens (ugc-v3.css) for dark surfaces, brand accents, typography, and layout sizing. | C_CANVAS, C_BASE, C_PANEL, C_CARD, C_CONTROL, C_CONTROL_HOVER, C_FLOAT, C_ACCENT, C_OK, C_WARN, C_DANGER, ROBOT_COLORS, C_TEXT_1, C_TEXT_2, C_TEXT_3, LINE, LINE_STRONG, H_HEADER, H_STATUS, W_RIGHT_LIB, W_OPBAR, W_TRACK_HEAD
src/ui/design_system/u_buttons.py | Unified UButton, UIconButton, USegmented, UBadge, and UHelpIcon controls guaranteeing zero text truncation. | UButton, UIconButton, USegmented, UBadge, UHelpIcon
src/ui/design_system/u_dialog.py | Floating-surface UDialog, push UDrawer, and translucent UFloatBar canvas overlay components. | UDialog, UDrawer, UFloatBar
src/ui/design_system/u_inputs.py | Numeric, timecode, dropdown, and search input controls conforming to desktop v3 dark styling. | UInputNumber, UTimeInput, USearchInput, USelect
src/ui/design_system/u_panels.py | Structural containers UPanel, UCollapsibleGroup (.group-card), UTable, and UEmpty for desktop v3 panels. | UPanel, UCollapsibleGroup, UTable, UEmpty
src/ui/design_system/ugc_v3_qss.py | Complete desktop QSS stylesheet eliminating colorful clutter and enforcing hairline borders. | build_ugc_v3_stylesheet
src/ui/formation/__init__.py | Public exports for Swarm Formation Design and Potential-Field Planning page. | FormationControlDock, FormationGroupDock, FormationPlannerCanvas, FormationPlanningPage
src/ui/formation/formation_control_dock.py | Right 310px stage controls.html-inspired formation parameter & potential-field solver control dock. | FormationControlDock
src/ui/formation/formation_group_dock.py | Left 250px robot swarm source/target table & quick scatter dock inside FormationPlanningPage. | FormationGroupDock
src/ui/formation/formation_planner_canvas.py | Interactive 2D swarm formation visualizer displaying sources, draggable target slots, and collision-free paths. | FormationPlannerCanvas
src/ui/formation/formation_planning_page.py | Complete stage Page 2 Swarm Formation Design & Multi-Robot Action Planning workspace. | FormationPlanningPage
src/ui/mapping/__init__.py | Public exports for PCD Map Library, Teleop SLAM Dock, live SSE worker, and NavigationMapPage. | NavigationMapPage, PcdMapLibraryDock, TeleopMappingDock, NavLiveStreamWorker
src/ui/mapping/nav_live_poller.py | Persistent HTTP/1.1 SSE client with non-blocking cloud fetch, generation-guarded non-blocking stop, and UI frame coalescing. | NavLiveStreamWorker
src/ui/mapping/nav_relocalize_helper.py | Helper utilities for relocalization seed lookup and compact G1 robot_state telemetry/alert formatting. | extract_track_fallback_pose, format_robot_state_tags, evaluate_nav_alert, format_nav_telemetry_line
src/ui/mapping/navigation_map_page.py | 3-column Mapping & Navigation workspace with SSE stream, auto/manual ROS relocalization, 2D goals, and teleop SLAM. | NavigationMapPage
src/ui/mapping/pcd_map_library_dock.py | Clean zero-overlap PCD Map Library dock supporting local upload, background robot push/pull, stage loading, rename, calibration, and delete. | PcdMapLibraryDock
src/ui/mapping/pcd_remote_sync.py | Blocking Wi-Fi HTTP PCD helpers (remote map listing, download, push, local import into the map library) designed for background tasks. | list_remote_pcds, download_remote_pcd, push_pcd_to_robot, import_pcd_entity
src/ui/mapping/teleop_mapping_dock.py | Right 296px Teleop SLAM control panel sending real HTTP velocity hold commands in background tasks and downloading authentic .pcd maps. | TeleopMappingDock
src/ui/modals/__init__.py | Public exports for all active choreography, track, stage, safety, calibration, and map modals. | AddTrackDialog, CoordTransformModal, CustomMapModal, DeviceOverviewModal, FragmentSaveDialog, InitPointModal, PreDanceCheckModal, StageSizeModal, SwitchTaskModal, TaskJsonViewerModal, TrajectoryDrawCanvas, TrajectoryEditorModal
src/ui/modals/add_track_dialog.py | Modal dialog for adding or editing a real robot timeline track with LRMP uniqueness validation. | AddTrackDialog
src/ui/modals/coord_transform_modal.py | 2D SVD Kabsch coordinate calibration dialog aligning stage frame with scanned PCD map frame. | CoordTransformModal
src/ui/modals/custom_map_modal.py | Quick modal to import a local .pcd file with configurable occupancy grid slicing parameters. | CustomMapModal
src/ui/modals/device_overview_modal.py | Interactive fleet device manager modal with real robot add, edit, delete, and LRMP authority reset. | DeviceOverviewModal
src/ui/modals/fragment_save_dialog.py | Full CRUD manager for saving, browsing, inserting onto timeline, and deleting choreography fragments. | FragmentSaveDialog
src/ui/modals/init_point_modal.py | Multi-robot initial pose editor & full preset CRUD loader/saver/deleter (InitPointConfig). | InitPointModal
src/ui/modals/pre_dance_check_modal.py | Pure Wi-Fi HTTP Pre-performance Audit Checklist with background online ROS health probe and Cluster Task-Chain Uploader. | PreDanceCheckModal
src/ui/modals/stage_size_modal.py | Modal dialog editing physical stage width, height, and safety perimeter margin. | StageSizeModal
src/ui/modals/switch_task_modal.py | Task selector modal supporting task creation, switching, and deletion. | SwitchTaskModal
src/ui/modals/task_json_viewer_modal.py | Live JSON inspector and clipboard/file exporter for stage task & trajectory structures. | TaskJsonViewerModal
src/ui/modals/trajectory_draw_canvas.py | Interactive 2D spline & freehand sketch canvas inside TrajectoryEditorModal with live Catmull-Rom preview. | TrajectoryDrawCanvas
src/ui/modals/trajectory_editor_modal.py | Clean ROS-aligned waypoint editor dialog supporting 2D map drawing, real task-chain HTTP upload, and deletion. | TrajectoryEditorModal
src/ui/monitoring/__init__.py | Public exports for Live Show Monitor page and its background show-control mixin. | PerformanceMonitorPage, ShowControlMixin
src/ui/monitoring/performance_monitor_page.py | Live Show Monitor page UI with real ROS pose 3D sync, clearance table, and background show control mixin. | PerformanceMonitorPage
src/ui/monitoring/show_control_mixin.py | Background-task show control (fleet health, PREP/BARRIER/PLAY/STOP/EMERGENCY) mixed into PerformanceMonitorPage. | ShowControlMixin
src/ui/shell/__init__.py | Exports shell navigation titlebar, statusbar, shortcut manager, and main shell window. | PAGE_DEFS, UTitlebar, UStatusBar, ShortcutManager, StudioAppShell
src/ui/shell/app_shell_window.py | Master main window shell with 32px UTitlebar, 4-page QStackedWidget, 28px UStatusBar, and GUI-thread event bus bridge. | StudioAppShell
src/ui/shell/shortcut_manager.py | Global stage shell keyboard shortcut registrar (Space, Ctrl+S, Ctrl+Z/Y, 1..6 page switch). | ShortcutManager
src/ui/shell/u_statusbar.py | desktop v3 28px bottom status bar displaying version, scene, init points, task status, local LAN IP, and alerts. | UStatusBar
src/ui/shell/u_titlebar.py | 32px top navigation header housing the 4 core workspace tabs and global Device/Scene/Help actions. | PAGE_DEFS, UTitlebar
src/ui/theme/__init__.py | Theme package exporting apply_studio_theme and apply_fusion_dark_theme. | apply_studio_theme, apply_fusion_dark_theme
src/ui/theme/fusion_dark_theme.py | Compatibility theme entry forwarding to the studio dark theme engine. | apply_fusion_dark_theme
src/ui/theme/studio_dark_theme.py | Applies complete desktop design-system QSS and dark Fusion palette to QApplication. | apply_studio_theme
src/ui/windows/__init__.py | Window facades package exposing MainStudioWindow for main.py launcher. | MainStudioWindow
src/ui/windows/main_studio_window.py | Studio entrypoint window composing the desktop shell and assembling all 4 authentic workspace pages. | MainStudioWindow
src/viewport3d/__init__.py | Public exports for G1 29-DOF kinematics, STL/VBO cache, studio shader, live motion & 3D viewport. | DanceMotionClip, DanceMotionPlayer, G1KinematicsChain, G1StudioShader, LiveMotionController, OrbitCamera, StageViewport3D, StlGpuVboPool, StlVboCache, get_g1_kinematics, procedural_gait_angles
src/viewport3d/dance_motion_player.py | Loads 21-joint/29-DOF NPZ dances, 36-col G1_dance.csv mocap, and grounded g1.py walking gaits. | DanceMotionClip, DanceMotionPlayer, procedural_gait_angles
src/viewport3d/g1_config_parser.py | URDF math primitives, joint/visual dataclasses, and AST-based g1.py init_state parser (no isaaclab dependency). | UrdfJoint, UrdfVisualLink, rpy_matrix, quat_xyzw_to_mat3, rodrigues_4x4, origin_to_mat, parse_g1_py_cfg
src/viewport3d/g1_kinematics_chain.py | Vectorized 29-DOF URDF Forward Kinematics, joint limits, foot contact geometry, and g1.py init_state grounding. | UrdfJoint, UrdfVisualLink, G1KinematicsChain, get_g1_kinematics
src/viewport3d/g1_studio_shader.py | GLSL 120 3-point + hemisphere studio metallic shader matching official G1 silver-grey & charcoal look. | G1StudioShader
src/viewport3d/live_motion_controller.py | Tracks live ROS robot poses, velocity-estimated walking gaits, and active NPZ dance sync for StageViewport3D. | LiveMotionController
src/viewport3d/orbit_camera.py | 3D spherical orbit, pan, and preset viewpoint camera controller for the StageViewport3D OpenGL scene. | OrbitCamera
src/viewport3d/robot_render_style.py | Official G1 URDF+rubber_hand materials, ground positioning halo ring, and single-QPainter HiDPI ID badges. | draw_stage_grid, robot_link_material, robot_link_style, draw_ground_positioning_ring, collect_robot_label, draw_robot_id_labels, project_to_screen
src/viewport3d/stage_scene_layers.py | Static environment layers for StageViewport3D: calibrated PCD loading, spline trajectories, and nav overlay. | load_calibrated_map_cloud, draw_trajectories, draw_live_nav_3d
src/viewport3d/stage_viewport_3d.py | Real-time 3D OpenGL stage viewport rendering G1 robots with VBOs, GLSL shader, ground halo rings & IDs. | StageViewport3D
src/viewport3d/stl_vbo_cache.py | Vectorized binary/ASCII STL loader with crease-angle smooth normals, GPU VBO pool, and fallback G1 colors. | StlMeshData, StlVboCache, StlGpuVboPool, PointCloudVbo, g1_link_material_rgb
