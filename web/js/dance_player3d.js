/**
 * 3D 舞蹈骨骼播放器 (基于 WebGL & Three.js 仿真渲染，50fps)
 */
class DancePlayer3D {
  constructor(viewportId) {
    this.viewport = document.getElementById(viewportId);
    this.currentDanceData = null;
    this.currentFrame = 0;
    this.isPlaying = false;
    this.playbackSpeed = 1.0;
    this.isLoop = true;
    this.fps = 50.0;
    this.lastFrameTime = 0;
    this.animFrameId = null;

    // Three.js 核心对象
    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.jointMeshes = [];
    this.boneMeshes = [];
    this.trailLine = null;
    this.trailPoints = [];

    // 控制器对象
    this.controls = null;

    this.initThree();
  }

  initThree() {
    if (!this.viewport) return;
    const width = this.viewport.clientWidth || 600;
    const height = this.viewport.clientHeight || 500;

    // 1. 场景
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x070a12);
    this.scene.fog = new THREE.FogExp2(0x070a12, 0.15);

    // 2. 相机
    this.camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 50);
    this.camera.up.set(0, 0, 1); // 设置 Z 轴向上

    // 3. 渲染器（必须先于 OrbitControls 创建）
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.shadowMap.enabled = true;
    this.viewport.appendChild(this.renderer.domElement);

    // 4. 轨道控制器（依赖 renderer.domElement，须在渲染器之后初始化）
    if (THREE.OrbitControls) {
      this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.05;
      this.controls.maxPolarAngle = Math.PI / 2 + 0.1;
      this.controls.minDistance = 1.0;
      this.controls.maxDistance = 10.0;
    }

    this.resetCamera();

    // 5. 灯光
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
    this.scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0x00f0ff, 1.2);
    dirLight1.position.set(3, 5, 4);
    this.scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x8b5cf6, 0.8);
    dirLight2.position.set(-3, -3, 2);
    this.scene.add(dirLight2);

    // 5. 赛博网格地面
    const gridHelper = new THREE.GridHelper(8, 24, 0x00d2ff, 0x1f2937);
    gridHelper.rotation.x = Math.PI / 2; // Z 为高轴
    gridHelper.position.z = 0;
    this.scene.add(gridHelper);

    // 6. 初始化关节点与骨骼连接线
    this.buildSkeletonMeshes();

    // 渲染循环
    const renderLoop = (time) => {
      this.animFrameId = requestAnimationFrame(renderLoop);
      this.update(time);
      if (this.controls) this.controls.update(); // 必须调用以更新阻尼
      this.renderer.render(this.scene, this.camera);
    };
    requestAnimationFrame(renderLoop);

    // 视口自适应
    window.addEventListener('resize', () => this.onResize());
  }

  buildSkeletonMeshes(jointCount = 21, customBonePairs = null) {
    this.jointCount = jointCount;
    // 清理可能已有的 mesh
    if (this.jointMeshes && this.jointMeshes.length > 0) {
      for (const jm of this.jointMeshes) {
        this.scene.remove(jm);
        if (jm.geometry) jm.geometry.dispose();
      }
    }
    this.jointMeshes = [];

    if (this.headMesh) {
      this.scene.remove(this.headMesh);
      if (this.headMesh.geometry) this.headMesh.geometry.dispose();
      this.headMesh = null;
    }

    if (this.neckMesh) {
      this.scene.remove(this.neckMesh);
      if (this.neckMesh.geometry) this.neckMesh.geometry.dispose();
      this.neckMesh = null;
    }

    if (this.boneMeshes && this.boneMeshes.length > 0) {
      for (const bm of this.boneMeshes) {
        this.scene.remove(bm.mesh);
        if (bm.mesh.geometry) bm.mesh.geometry.dispose();
      }
    }
    this.boneMeshes = [];

    // 关节球体
    const jointGeo = new THREE.SphereGeometry(0.024, 16, 16);
    const jointMat = new THREE.MeshStandardMaterial({
      color: 0x00f0ff,
      emissive: 0x0088cc,
      roughness: 0.2,
      metalness: 0.8
    });

    const headGeo = new THREE.SphereGeometry(0.06, 16, 16);
    const headMat = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      emissive: 0x00d2ff,
      roughness: 0.1
    });

    for (let i = 0; i < jointCount; i++) {
      const isHead = (jointCount === 21 && i === 4);
      const mesh = new THREE.Mesh(isHead ? headGeo : jointGeo, isHead ? headMat : jointMat);
      mesh.position.set(0, 0, 0);
      mesh.visible = false;
      this.scene.add(mesh);
      this.jointMeshes.push(mesh);
    }

    // 30 关节模型额外创建独立的头部球体与颈椎连接骨骼
    if (jointCount >= 29) {
      this.headMesh = new THREE.Mesh(headGeo, headMat);
      this.headMesh.visible = false;
      this.scene.add(this.headMesh);

      const neckGeom = new THREE.CylinderGeometry(0.012, 0.012, 1, 8);
      const neckMesh = new THREE.Mesh(neckGeom, new THREE.MeshStandardMaterial({
        color: 0x38bdf8,
        emissive: 0x0284c7,
        roughness: 0.3,
        metalness: 0.5
      }));
      neckMesh.visible = false;
      this.scene.add(neckMesh);
      this.neckMesh = neckMesh;
    }

    // 骨骼连线默认配置
    const default21Bones = [
      [0, 1], [1, 2], [2, 3], [3, 4],     // 躯干
      [2, 5], [5, 6], [6, 7], [7, 8],     // 左臂
      [2, 9], [9, 10], [10, 11], [11, 12], // 右臂
      [0, 13], [13, 14], [14, 15], [15, 16], // 左腿
      [0, 17], [17, 18], [18, 19], [19, 20]  // 右腿
    ];

    const default30Bones = [
      // 躯干与胸腔 (0: pelvis -> 6: waist_roll -> 12, 13: shoulders)
      [0, 6], [6, 12], [6, 13], [12, 13],
      // 左腿 (0 -> 1 -> 4 -> 7 -> 10 -> 14 -> 18)
      [0, 1], [1, 4], [4, 7], [7, 10], [10, 14], [14, 18],
      // 右腿 (0 -> 2 -> 5 -> 8 -> 11 -> 15 -> 19)
      [0, 2], [2, 5], [5, 8], [8, 11], [11, 15], [15, 19],
      // 左臂 (12 -> 16 -> 20 -> 22 -> 24 -> 26 -> 28)
      [12, 16], [16, 20], [20, 22], [22, 24], [24, 26], [26, 28],
      // 右臂 (13 -> 17 -> 21 -> 23 -> 25 -> 27 -> 29)
      [13, 17], [17, 21], [21, 23], [23, 25], [25, 27], [27, 29]
    ];

    const bonePairs = customBonePairs || (jointCount >= 29 ? default30Bones : default21Bones);

    const boneMat = new THREE.MeshStandardMaterial({
      color: 0x38bdf8,
      emissive: 0x0284c7,
      roughness: 0.3,
      metalness: 0.5
    });

    for (let i = 0; i < bonePairs.length; i++) {
      const p1 = bonePairs[i][0];
      const p2 = bonePairs[i][1];
      if (p1 < jointCount && p2 < jointCount) {
        const geom = new THREE.CylinderGeometry(0.012, 0.012, 1, 8);
        const mesh = new THREE.Mesh(geom, boneMat);
        mesh.visible = false;
        this.scene.add(mesh);
        this.boneMeshes.push({ mesh, p1, p2 });
      }
    }
  }

  loadDance(danceData) {
    this.currentDanceData = danceData;
    const jointCount = danceData.joint_count || (danceData.frames && danceData.frames[0] ? danceData.frames[0].length : 21);
    this.buildSkeletonMeshes(jointCount, danceData.bone_pairs);
    this.currentFrame = 0;
    this.fps = danceData.fps || 50.0;
    this.isPlaying = true;

    // 根据第一帧的初始位置重设相机视角
    if (danceData.frames && danceData.frames[0] && danceData.frames[0][0]) {
      const p0 = danceData.frames[0][0];
      if (this.controls) {
        this.controls.target.set(p0[0], p0[1], p0[2]);
        this.camera.position.set(p0[0], p0[1] - 2.6, p0[2] + 0.5);
        this.controls.update();
      }
    }

    this.updateControlsUI();
    this.renderFrame(0);
  }

  renderFrame(frameIdx) {
    if (!this.currentDanceData || !this.currentDanceData.frames) return;
    const frames = this.currentDanceData.frames;
    if (frameIdx >= frames.length) frameIdx = frames.length - 1;
    const frame = frames[frameIdx];

    // 更新关节坐标 (使用绝对统一的机器人基坐标系 X, Y, Z)
    for (let i = 0; i < this.jointMeshes.length; i++) {
      if (frame[i]) {
        const [x, y, z] = frame[i];
        this.jointMeshes[i].position.set(x, y, z);
        this.jointMeshes[i].visible = true;
      } else {
        this.jointMeshes[i].visible = false;
      }
    }

    const yAxis = new THREE.Vector3(0, 1, 0);

    // 若为 30 关节 G1 模型，更新头部与颈部
    if (this.headMesh) {
      if (frame[12] && frame[13]) {
        const midChest = new THREE.Vector3(
          (frame[12][0] + frame[13][0]) * 0.5,
          (frame[12][1] + frame[13][1]) * 0.5,
          (frame[12][2] + frame[13][2]) * 0.5
        );
        const headPos = new THREE.Vector3(midChest.x, midChest.y, midChest.z + 0.18);
        this.headMesh.position.copy(headPos);
        this.headMesh.visible = true;

        if (this.neckMesh) {
          const neckDist = midChest.distanceTo(headPos);
          this.neckMesh.scale.set(1, Math.max(0.001, neckDist), 1);
          const neckMid = new THREE.Vector3().addVectors(midChest, headPos).multiplyScalar(0.5);
          this.neckMesh.position.copy(neckMid);
          const neckDir = new THREE.Vector3().subVectors(headPos, midChest).normalize();
          this.neckMesh.quaternion.setFromUnitVectors(yAxis, neckDir);
          this.neckMesh.visible = true;
        }
      } else {
        this.headMesh.visible = false;
        if (this.neckMesh) this.neckMesh.visible = false;
      }
    }

    // 更新骨骼圆柱连接体
    const vSource = new THREE.Vector3();
    const vTarget = new THREE.Vector3();
    const vMid = new THREE.Vector3();

    for (let i = 0; i < this.boneMeshes.length; i++) {
      const { mesh, p1, p2 } = this.boneMeshes[i];
      if (frame[p1] && frame[p2]) {
        vSource.set(frame[p1][0], frame[p1][1], frame[p1][2]);
        vTarget.set(frame[p2][0], frame[p2][1], frame[p2][2]);
        
        const dist = vSource.distanceTo(vTarget);
        if (dist < 0.005 || isNaN(dist)) {
          mesh.visible = false;
          continue;
        }
        mesh.visible = true;
        mesh.scale.set(1, dist, 1);

        vMid.addVectors(vSource, vTarget).multiplyScalar(0.5);
        mesh.position.copy(vMid);

        const dir = new THREE.Vector3().subVectors(vTarget, vSource).normalize();
        mesh.quaternion.setFromUnitVectors(yAxis, dir);
      } else {
        mesh.visible = false;
      }
    }

    // 相机目标平滑追踪机器人骨盆 root (使机器人位移漫步时始终在视野内)
    if (frame[0] && this.controls) {
      const currentTarget = this.controls.target;
      const targetX = THREE.MathUtils.lerp(currentTarget.x, frame[0][0], 0.05);
      const targetY = THREE.MathUtils.lerp(currentTarget.y, frame[0][1], 0.05);
      const targetZ = THREE.MathUtils.lerp(currentTarget.z, frame[0][2], 0.05);
      this.controls.target.set(targetX, targetY, targetZ);
    }

    // 更新进度条和文本
    const scrubber = document.getElementById('dance-scrubber');
    const timeText = document.getElementById('dance-time-text');
    if (scrubber) scrubber.value = frameIdx;
    if (timeText) {
      const curSec = (frameIdx / this.fps).toFixed(1);
      const totalSec = (frames.length / this.fps).toFixed(1);
      timeText.textContent = `${curSec}s / ${totalSec}s (帧 ${frameIdx}/${frames.length})`;
    }
  }

  update(time) {
    if (!this.isPlaying || !this.currentDanceData || !this.currentDanceData.frames) return;

    if (!this.lastFrameTime) this.lastFrameTime = time;
    const interval = (1000 / this.fps) / this.playbackSpeed;
    const delta = time - this.lastFrameTime;

    if (delta >= interval) {
      this.lastFrameTime = time;
      this.currentFrame++;
      if (this.currentFrame >= this.currentDanceData.frames.length) {
        if (this.isLoop) {
          this.currentFrame = 0;
        } else {
          this.currentFrame = this.currentDanceData.frames.length - 1;
          this.isPlaying = false;
          this.updatePlayBtnState();
        }
      }
      this.renderFrame(this.currentFrame);
    }
  }

  play() {
    this.isPlaying = true;
    this.updatePlayBtnState();
  }

  pause() {
    this.isPlaying = false;
    this.updatePlayBtnState();
  }

  togglePlay() {
    if (this.isPlaying) this.pause();
    else this.play();
  }

  seek(frame) {
    this.currentFrame = Math.max(0, parseInt(frame));
    this.renderFrame(this.currentFrame);
  }

  updatePlayBtnState() {
    const btn = document.getElementById('btn-dance-play');
    if (btn) {
      btn.innerHTML = this.isPlaying ? '⏸️ 暂停' : '▶️ 播放';
    }
  }

  updateControlsUI() {
    const scrubber = document.getElementById('dance-scrubber');
    if (scrubber && this.currentDanceData) {
      scrubber.max = this.currentDanceData.frames.length - 1;
      scrubber.value = this.currentFrame;
    }
    this.updatePlayBtnState();
  }

  resetCamera() {
    this.camera.position.set(1.5, -1.5, 3.5);
    this.controls.target.set(0, 0, 0.7);
    this.controls.update();
  }

  onResize() {
    if (!this.viewport || !this.renderer || !this.camera) return;
    const width = this.viewport.clientWidth;
    const height = this.viewport.clientHeight;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }
}

// 全局 3D 播放器实例
let dancePlayer = null;
