---
name: robot-deployment-assistant
description: Core architectural, protocol, algorithm, and UI/UX engineering specification for RobotDeploymentAssistant (Stage Choreography, Swarm Formation Potential-Field Planning, Dance Timeline Editor, 3D G1 29-DOF Skeletal Preview, PCD Map Management, and G1 Wi-Fi Setup). Read before any step.
---

# RobotDeploymentAssistant Core Engineering Skill

## 1. Prime Directives & Non-Regression Boundary

1. **Pre-`2026-10-01` Git Baseline Protection (`a5973d4`, `2026-09-11`)**:
   - The commit `a5973d4` is the golden baseline for existing robot deployment functionality.
   - **Protected Files (Functional Equivalence Mandatory)**:
     - `app.py`, `main.py`
     - `backend/`: `character_service.py`, `command_service.py`, `config_manager.py`, `dance_packager.py`, `dance_sync_service.py`, `driver_manager.py`, `file_manager.py`, `process_manager.py`, `pt_to_onnx_service.py`, `serial_service.py`, `ssh_manager.py`, `test_runner.py`, `urdf_loader.py`, and `backend/assets/g1_29dof/meshes/*.STL`.
     - `web/`: `index.html`, `js/main.js`, `js/robot-3d-viewer.js`, `css/style.css`, and vendor libraries.
     - `tests/` (9 baseline tests restored from `a5973d4`): `test_all_features.py`, `test_dance_zip_update.py`, `test_driver_manager.py`, `test_folder_upload.py`, `test_frontend_structure.py`, `test_preview_import.py`, `test_robot_id_and_target.py`, `test_serial_dance_sync.py`, `test_serial_sync_policy.py`.
   - New features enter via two homepage (`web/index.html`) buttons: **“舞台编导” (Stage Choreography)** and **“网络管理” (Network Management)**, bridged via `QWebChannel` (`pyBridge.openStageChoreography()`, `pyBridge.openNetworkManager()`).

2. **Strict Data & Protocol Authority**:
   - **ONLY** `docs/LRMP V1.0-R3 精简指令规范(1).md` and `群控商业化补充说明.md` define robot communication frames (`TARGET|COMMAND[,PARAM...]\n`).
   - **NEVER** invent binary opcodes (`PREPARE_EPOCH`, `SET_INIT_POSE`, `APPEND_WAYPOINT` are forbidden).
   - For robot-side HTTP trajectory upload (`POST /api/v1/lrmp/trajectories/upload`) and real-time SLAM PCD streaming (`WS /api/v1/slam/stream`), provide standard **Virtual Interfaces** (`VirtualRobotHttpClient`, `VirtualSlamStreamService`) backed by a local deterministic simulation engine so all client workflows operate end-to-end offline and can switch to real robot endpoints via configuration.

3. **Code Hygiene & Low-Coupling Rules (`<RULE[user_global]>`)**:
   - **Max 300 lines per code file** (split at 250 lines by Single Responsibility Principle).
   - **Mandatory Header Contract** on every code file:
     ```python
     # @file: <relative/path.py>
     # @brief: <Single-sentence responsibility>
     # @exports: <Comma-separated public classes/functions>
     ```
   - **Workspace Partitioning**:
     - `src/`: Pure domain, math, algorithms, protocol, persistence, services, and PySide6/OpenGL UI modules.
     - `utils/` & `scripts/`: Stateless helpers and verification scripts.
     - `.agent_workspace/`: All agent caches, runtime SQLite DBs (`.agent_workspace/runtime/stage_studio.db`), user settings overrides (`.agent_workspace/runtime/user_settings.yaml`), logs, and `.agent_workspace/INDEX.md`. Never create `runtime/` or `cache/` in the project root.

4. **Zero-Demo Startup & Mandatory Closed-Loop Standards**:
   - **Never auto-seed Demo robots**: `ensure_seeded(db)` creates ONLY the blank active scene, blank task, and LRMP action catalog (`0` tracks by default). All robots on stage MUST be explicitly added by the user via `+ 轨道` or `DeviceOverviewModal` (or explicit on-demand `seed_demo_swarm_preset(db)`).
   - **Full CRUD & Cascade**: Every editable entity (Tracks, Trajectories, Groups, Timeline Blocks, Init Point Presets, Fragments, Custom Actions, PCD Maps) MUST support Create, Read, Edit, Delete, DB persistence, EventBus broadcast, and cascade cleanup of orphaned references.
   - **3-Round Functional Closure Gate**: Any feature change MUST pass 3 audit rounds verifying every button trigger, Undo/Redo wiring, settings persistence, and zero broken/read-only black-hole UI controls.

---

## 2. Desktop Design System (`design-system/LAYOUT.md` & `COMPONENTS.md`)

### 2.1 Color & Surface Tokens (`ugc-v3.css`)
- **Surfaces**:
  - `--c-canvas`: `#060708` (2D/3D viewport deep background)
  - `--c-base`: `#0b0c0f` (App window base background)
  - `--c-panel`: `#101114` (Standard panel background)
  - `--c-card`: `#15161a` (Card / group header / elevated row)
  - `--c-control`: `#191a20` (Inputs, buttons, table headers)
  - `--c-control-hover`: `#20222a` (Hover state for controls)
- **Floating Overlays**:
  - `--c-float`: `#0e0f12`, `--c-float-2`: `#121317`, `--c-float-3`: `#16171c`
  - `--c-float-edge`: `rgba(236, 239, 243, 0.22)`
- **Brand & Semantic Status**:
  - `--c-accent`: `#2e7bf7`, `--c-accent-dim`: `rgba(46, 123, 247, 0.16)`, `--c-accent-border`: `rgba(46, 123, 247, 0.45)`, `--c-accent-bright`: `#6fa3ff`
  - `--c-ok`: `#2bb673`, `--c-warn`: `#f0a228`, `--c-danger`: `#ee4d5a`
- **Robot Track Palette**:
  - `--robot-1`: `#2e7bf7`, `--robot-2`: `#8b7cff`, `--robot-3`: `#e06fc4`, `--robot-4`: `#f0a228`, `--robot-5`: `#2bb673`
- **Typography & Hairlines**:
  - `--c-text-1`: `#e4e6ea`, `--c-text-2`: `#9ba0aa`, `--c-text-3`: `#6a6f78`
  - `--line`: `rgba(236, 239, 243, 0.10)`, `--line-strong`: `rgba(236, 239, 243, 0.18)`
  - Control heights: `32px` (`.btn`), `28px` (`.btn-sm`), `24px` (`.btn-xs`); radii: `8px` card, `6px` button, `4px` inner control.

### 2.2 Canonical App Shell & Choreography Page Layout (`choreography.html`)
- **Top `UTitlebar` (`32px` fixed height)**:
  - Left: Horizontal Page Menu (`舞蹈编排`, `队形规划`, `导航地图`, `表演监测` — the duplicate `系统设置` page was removed; network provisioning/license/settings live in the homepage `网络管理` console).
  - Right: Global actions (`设备总览`, `场景▾`, `帮助▾`).
- **Center `ChoreographyPage` (2-Column Split)**:
  - **`col-left` (`flex: 1`)**:
    - **Top `PreviewMapPanel` (`flex: 1`, min-height `220px`)**:
      - Unified 2D/3D stage viewport (`#060708`) with clickable stage button (`舞台 12×8m` -> `StageSizeModal`), `预览轨迹` toggle, `重置视角`, and `3D | 2D` segmented switch.
      - **Inline `StageDrawToolbar` (`轨迹绘制`, `草图笔`, `清空草图`, `清空轨迹`, `保存轨迹`) & `StageHintFooter`**: direct point-and-click spline drawing (`①②③...`), freehand reference sketching, live `X/Y` world coordinate HUD, `Alt+Left` pan, `Ctrl+Z` undo step, and right-click finish opening `TrajectoryEditorModal` prefilled with drawn waypoints (`uniform/linear`, `runMode`, `holdDirection`, `endTurn`, 50FPS CSV inspection, HTTP upload, and delete).
      - In `view` mode, clicking and dragging a robot directly adjusts its initial stage pose `(init_x, init_y)` with Undo/Redo support.
      - `StageViewport3D` subscribes to `MAP_LOADED` and applies `calib_matrix` rigid transforms to render calibrated PCD clouds alongside 29-DOF G1 skeletons across Pages 1, 3, and 4.
      - Bottom-center floating `PlaybackProgressBar`: Replay, Play/Pause, mono timecode (`00:18.4 / 01:30.0`), scrubbable timeline with red `.pb-collision` warning segments, speed selector (`0.5x / 1.0x / 1.5x / 2.0x`), fullscreen toggle.
    - **Horizontal `ResizeBar` (`5px`)**
    - **Bottom `EditorPanel` (`height: 300px` resizable)**:
      - Left `EditorOperationBar` (`40px` vertical icon rail, 10 tools): Play/Pause, Delete Robot (`modalDelRobot`), Vertical Zoom slider + `%`, Select All, Range Export (`modalRangeExport`), Ignore/Restore Block, BPM Info (`BPMInfoModal`), View Task JSON, Refresh Snapshot, Export Current Init Points.
      - Right `EditorContent`:
        - `TimelineHeader` (`38px`): Left (`播放/暂停`, `保存编辑`), Center (`SwitchTaskModal` trigger showing task title), Right (`PlaybackStatus`: `小节·节拍`, `拍号 4/4`, `速度 120`, `节拍器`, `音乐`, `节拍轴`).
        - `TaskEditor`: Left sticky column (`168px` wide: `tl-corner` `轨道 / 秒 ＋` -> `AddTrackDialog`; `tl-track-info` per robot with color bar, `轨道 1 · G1-01`, `192.168.123.101`, `初始化点: (x, y)`) + Right scrollable canvas (`tl-ruler` where double-clicking saves a fragment `1..99`, `tl-playhead`, and unified `tl-lane` rows containing `.tl-block.is-trajectory` and `.tl-block.is-action` blocks with `#no`, name, resize handles, `.is-selected`, `.is-ignored`, `.is-error` overlap states).
  - **`col-right` (`330px` fixed width)**:
    - **Top `TrackLibPanel` (`轨迹库`, `flex: 1`)**: Header (`添加分组` + 7 icon actions: `按轨道排序`, `新增轨迹`, `导出轨迹库`, `导入轨迹库`, `批量复制`, `批量修改`, `批量删除`) + collapsible `.group-card` list (`group-name`, `robot-badge`, `group-count`, `轨道 N` binding button, delete button, and 3-column table `编号 | 名称 | 时间`).
    - **Bottom `ActionLibPanel` (`动作库`, `flex: 1`)**: Header (`添加动作`, `导出动作`, `导入动作`, `获取动作库`, `批量管理`) + `filter-row` (`编号/名称` search + `全部型号` filter) + 4-column table `编号 | 名称 | 型号 | 时间`.
- **Bottom `UStatusBar` (`28px` fixed height)**:
  - Left: `系统版本 v3.2.0` | `场景: <name>` | `初始化点: <config>` (opens `InitPointModal`) | `音乐: <file>` | `时间码 00:18.42`.
  - Right: `联网状态` | `IP` | `机器人数量` | `消息通知`.

---

## 3. Core Mathematical & Algorithmic Specifications

1. **Catmull-Rom Spline & S-Curve Trajectory Engine (`splineTrajectory` & `trajectoryProcessing`)**:
   - Centripetal/standard Catmull-Rom 2D/3D interpolation over control points $P_0, \dots, P_n$.
   - 2000-sample cumulative arc-length lookup table $s(u)$ with binary search inversion $u(s)$.
   - 7-segment jerk-limited S-curve velocity profile (`accelRatio = 0.2`, `jerkRatio = 0.3`, `maxAcc = 1.5 m/s²`, `maxSpeed = 3.0 m/s`), minimum execution time validator `computeMinExecutionTime(L, a_max, v_max)`.
   - 50 FPS (`dt = 0.02s`) resampling outputting `"t,x,y,yaw\n..."` (`trajectoryPointData`), supporting `holdDirection` (`holdDirectionYaw`) and `endTurn` (`endTurnYaw`).
2. **Swarm Formation & Potential-Field Collision-Free Planner (`algorithms-RYCS08SV.js`)**:
   - Formation generators: Line, Circle, Rectangle/Grid, V-Wedge, Staggered Column, Custom Freehand.
   - Optimal target assignment (`assignTargets`): Greedy nearest-neighbor + 2-opt swap minimization of $\sum \|p_i - q_{\pi(i)}\|^2$ + crossing reduction.
   - Crossing counter (`countPathCrossings`) + Two-ring scatter intermediate stage (`generateScatterPositions`) when crossings exceed threshold.
   - Potential-field solver (`SIM_DT = 0.02s`, `MAX_SIM_FRAMES = 6000`, `K_ATTRACT = 3.0`, `K_REPEL = 8.0..10.0`, `K_AVOID = 2.0`, 25-frame staggered start delay, 3-pass hard safety distance projection, 25-frame Hermite smooth landing $e^2(3-2e)$, Ramer-Douglas-Peucker `rdpSimplify` $\varepsilon = 0.01..0.03\text{ m}$).
3. **Timeline Pairwise Collision Worker (`collision.worker-CdUf4EN0.js`)**:
   - Samples all active tracks at $\Delta t = 0.05\text{ s}$ across $[0, T_{\text{total}}]$, holding each robot's last trajectory endpoint when idle, flagging intervals where $\min_{i < j} \|p_i(t) - p_j(t)\| < d_{\text{safe}}$ as red `.pb-collision` segments on the playback progress bar.
4. **PCD Map & Coordinate Calibration (`pcdGridWorker.js` & `TrajectoryCoordTransformModal`)**:
   - Parses ASCII, `binary`, and `binary_compressed` (LZF) `.pcd` files; voxel grid downsampling; height-clipped 2D occupancy grid PNG generation.
   - 2-point or N-point SVD rigid transform ($R, t, \Delta\psi$) transforming trajectories between Stage coordinates and SLAM Map coordinates.
5. **LRMP V1.0-R3 Protocol Engine**:
   - Exact ASCII frame syntax `TARGET|COMMAND[,PARAM1,PARAM2...]\n` over UDP/TCP/Serial/HTTP bridge.
   - Authority state machine (`FREE` <-> `MANUAL` <-> `CHOREO`) enforcing mutual exclusion between manual control and choreography playback.
