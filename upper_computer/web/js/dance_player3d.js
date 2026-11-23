/**
 * 3D 舞蹈仿真播放器 (基于 WebGL & Three.js，支持 50fps 真实机器人 3D 网格模型与运动骨骼)
 */
class DancePlayer3D {
  static geometryCache = {};

  /**
   * 基于 link_name 关键词将 G1 URDF 各部件语义映射至骨骼关键点索引。
   * 当 NPZ 没有内嵌 joint_trajectory 时，用此映射在降级渲染路径中让各部件正确跟随骨骼点位移。
   * 支持标准 21 关节（通用动捕格式）和 30 关节（G1 29-DoF 格式）。
   */
  static resolveJointIdx(lName) {
    // 21 关节语义映射: 0=pelvis,1=spine,2=torso,3=neck,4=head,
    //   5=L_shoulder,6=L_elbow,7=L_wrist,8=L_hand,
    //   9=R_shoulder,10=R_elbow,11=R_wrist,12=R_hand,
    //   13=L_hip,14=L_knee,15=L_ankle,16=L_foot,
    //   17=R_hip,18=R_knee,19=R_ankle,20=R_foot
    if (lName.includes('pelvis') || lName.includes('base_link')) return 0;
    if (lName.includes('waist_yaw') || lName.includes('spine')) return 1;
    if (lName.includes('waist_roll') || lName.includes('waist_pitch') || lName.includes('torso_link')) return 2;
    if (lName.includes('head_servo')) return 3;
    if (lName.includes('head_link') || lName === 'head') return 4;

    // 左上肢
    if (lName.includes('left_shoulder_pitch') || lName.includes('left_shoulder')) return 5;
    if (lName.includes('left_shoulder_roll') || lName.includes('left_shoulder_yaw')) return 5;
    if (lName.includes('left_elbow')) return 6;
    if (lName.includes('left_wrist')) return 7;
    if (lName.includes('left_hand') || lName.includes('left_rubber') || (lName.includes('left') && lName.includes('palm'))) return 8;

    // 右上肢
    if (lName.includes('right_shoulder_pitch') || lName.includes('right_shoulder')) return 9;
    if (lName.includes('right_shoulder_roll') || lName.includes('right_shoulder_yaw')) return 9;
    if (lName.includes('right_elbow')) return 10;
    if (lName.includes('right_wrist')) return 11;
    if (lName.includes('right_hand') || lName.includes('right_rubber') || (lName.includes('right') && lName.includes('palm'))) return 12;

    // 左下肢
    if (lName.includes('left_hip')) return 13;
    if (lName.includes('left_knee')) return 14;
    if (lName.includes('left_ankle')) return 15;
    if ((lName.includes('left') && lName.includes('foot')) || (lName.includes('left') && lName.includes('base_link'))) return 16;

    // 右下肢
    if (lName.includes('right_hip')) return 17;
    if (lName.includes('right_knee')) return 18;
    if (lName.includes('right_ankle')) return 19;
    if ((lName.includes('right') && lName.includes('foot')) || (lName.includes('right') && lName.includes('base_link'))) return 20;

    // logo/胸口装饰 → 跟随 torso
    if (lName.includes('logo') || lName.includes('torso_constraint') || lName.includes('waist_support')) return 2;

    return 0; // 兜底：跟随骨盆
  }


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
    this.headMesh = null;
    this.neckMesh = null;

    // 真实机器人 3D 网格模型与层级运动学组件
    this.robotPartsGroup = null;
    this.robotMeshParts = [];
    this.robotLinkNodes = {};
    this.robotJointPivots = {};
    this.robotRootLink = null;
    this.hasRobotModel = false;
    this.isLoadingRobotModel = false;

    // 控制器对象
    this.controls = null;

    this.initThree();
  }

  /**
   * 原生高效解析二进制 STL 资产为 THREE.BufferGeometry
   */
  static parseBinarySTL(buffer) {
    const reader = new DataView(buffer);
    const faces = reader.getUint32(80, true);
    const dataOffset = 84;
    const faceLength = 50;
    const positions = new Float32Array(faces * 9);
    const normals = new Float32Array(faces * 9);

    for (let face = 0; face < faces; face++) {
      const start = dataOffset + face * faceLength;
      const nx = reader.getFloat32(start, true);
      const ny = reader.getFloat32(start + 4, true);
      const nz = reader.getFloat32(start + 8, true);

      for (let i = 1; i <= 3; i++) {
        const vertexstart = start + i * 12;
        const idx = face * 9 + (i - 1) * 3;
        positions[idx] = reader.getFloat32(vertexstart, true);
        positions[idx + 1] = reader.getFloat32(vertexstart + 4, true);
        positions[idx + 2] = reader.getFloat32(vertexstart + 8, true);
        normals[idx] = nx;
        normals[idx + 1] = ny;
        normals[idx + 2] = nz;
      }
    }

    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geom.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
    try {
      geom.computeVertexNormals();
    } catch (e) {}
    return geom;
  }

  initThree() {
    if (!this.viewport) return;
    const width = this.viewport.clientWidth || 600;
    const height = this.viewport.clientHeight || 500;

    // 1. 场景
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a0f1d);
    // 移除阻隔光照的浓厚死黑雾气，确保高对比度科技通透视野
    this.scene.fog = null;

    // 2. 相机
    this.camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 50);
    this.camera.up.set(0, 0, 1); // 设置 Z 轴向上
    this.scene.add(this.camera);

    // 3. 渲染器
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setSize(width, height);
    if (this.renderer.shadowMap) {
      this.renderer.shadowMap.enabled = true;
    }
    this.viewport.appendChild(this.renderer.domElement);

    // 4. 轨道控制器
    if (THREE.OrbitControls) {
      this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.05;
      this.controls.maxPolarAngle = Math.PI / 2 + 0.05;
      this.controls.minDistance = 0.5;
      this.controls.maxDistance = 10.0;
    }

    this.resetCamera();

    // 5. 摄影棚级三点布光系统 + 相机跟随探照灯 (彻底解决机器人黑成剪影、无法看清细节的异常)
    // 基础环境半球光 (天际浅蓝冰白，地面深沉微光)
    const hemiLight = new THREE.HemisphereLight(0xe0f2fe, 0x1e293b, 1.15);
    this.scene.add(hemiLight);

    // 正前方主光源 (Key Light) - 照射机器人前胸、面罩与双臂正面
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.5);
    keyLight.position.set(3.0, -1.2, 2.6);
    this.scene.add(keyLight);

    // 侧前辅助光 (Fill Light) - 柔化阴影与机械缝隙
    const fillLight = new THREE.DirectionalLight(0x7dd3fc, 0.80);
    fillLight.position.set(1.5, 2.5, 1.8);
    this.scene.add(fillLight);

    // 顶部背面轮廓光 (Rim Light) - 勾勒机械外壳与肩甲高光线条
    const rimLight = new THREE.DirectionalLight(0x38bdf8, 1.20);
    rimLight.position.set(-2.0, 0.0, 2.8);
    this.scene.add(rimLight);

    // 相机跟随补光 (Headlight) - 无论用户如何旋转视角，正面细节始终清晰明亮
    const headlight = new THREE.PointLight(0xffffff, 0.50, 15);
    this.camera.add(headlight);

    // 6. 赛博网格地面
    const gridHelper = new THREE.GridHelper(8, 24, 0x00d2ff, 0x1f2937);
    gridHelper.rotation.x = Math.PI / 2; // Z 为高轴
    gridHelper.position.z = 0;
    this.scene.add(gridHelper);

    // 7. 机器人 3D 实体部件容器
    this.robotPartsGroup = new THREE.Group();
    this.scene.add(this.robotPartsGroup);

    // 8. 默认线框骨骼网格
    this.buildSkeletonMeshes();

    // 渲染主循环
    const renderLoop = (time) => {
      this.animFrameId = requestAnimationFrame(renderLoop);
      this.update(time);
      if (this.controls) this.controls.update();
      this.renderer.render(this.scene, this.camera);
    };
    requestAnimationFrame(renderLoop);

    window.addEventListener('resize', () => this.onResize());
  }

  buildSkeletonMeshes(jointCount = 21, customBonePairs = null) {
    this.jointCount = jointCount;

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
      mesh.visible = !this.hasRobotModel;
      this.scene.add(mesh);
      this.jointMeshes.push(mesh);
    }

    if (jointCount >= 29) {
      this.headMesh = new THREE.Mesh(headGeo, headMat);
      this.headMesh.visible = !this.hasRobotModel;
      this.scene.add(this.headMesh);

      const neckGeom = new THREE.CylinderGeometry(0.012, 0.012, 1, 8);
      const neckMesh = new THREE.Mesh(neckGeom, new THREE.MeshStandardMaterial({
        color: 0x38bdf8,
        emissive: 0x0284c7,
        roughness: 0.3,
        metalness: 0.5
      }));
      neckMesh.visible = !this.hasRobotModel;
      this.scene.add(neckMesh);
      this.neckMesh = neckMesh;
    }

    const default21Bones = [
      [0, 1], [1, 2], [2, 3], [3, 4],     // 躯干
      [2, 5], [5, 6], [6, 7], [7, 8],     // 左臂
      [2, 9], [9, 10], [10, 11], [11, 12], // 右臂
      [0, 13], [13, 14], [14, 15], [15, 16], // 左腿
      [0, 17], [17, 18], [18, 19], [19, 20]  // 右腿
    ];

    const default30Bones = [
      [0, 6], [6, 12], [6, 13], [12, 13],
      [0, 1], [1, 4], [4, 7], [7, 10], [10, 14], [14, 18],
      [0, 2], [2, 5], [5, 8], [8, 11], [11, 15], [15, 19],
      [12, 16], [16, 20], [20, 22], [22, 24], [24, 26], [26, 28],
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
        mesh.visible = !this.hasRobotModel;
        this.scene.add(mesh);
        this.boneMeshes.push({ mesh, p1, p2 });
      }
    }
  }

  clear() {
    this.isPlaying = false;
    this.currentDanceData = null;
    this.currentFrame = 0;
    this.hasRobotModel = false;
    this.isLoadingRobotModel = false;
    this.basePose = null;
    this.robotLinkNodes = {};
    this.robotJointPivots = {};
    this.robotRootLink = null;
    this._bodyLinksDetached = false;

    // 清空 3D 机器人部件
    if (this.robotPartsGroup) {
      while (this.robotPartsGroup.children.length > 0) {
        const obj = this.robotPartsGroup.children[0];
        this.robotPartsGroup.remove(obj);
        if (obj.geometry) obj.geometry.dispose();
      }
    }
    this.robotMeshParts = [];

    // 清空骨骼
    this.setSkeletonVisibility(false);
    if (this.jointMeshes) {
      for (const jm of this.jointMeshes) {
        this.scene.remove(jm);
        if (jm.geometry) jm.geometry.dispose();
      }
      this.jointMeshes = [];
    }
    if (this.boneMeshes) {
      for (const bm of this.boneMeshes) {
        this.scene.remove(bm.mesh);
        if (bm.mesh.geometry) bm.mesh.geometry.dispose();
      }
      this.boneMeshes = [];
    }
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

    // 重置进度条与时间显示
    const scrubber = document.getElementById('dance-scrubber');
    if (scrubber) { scrubber.value = 0; scrubber.max = 0; }
    const timeText = document.getElementById('dance-time-text');
    if (timeText) { timeText.textContent = '0.0s / 0.0s'; }
    this.updatePlayBtnState();
  }

  async loadRobotMeshModel(modelInfo) {
    if (!modelInfo || !modelInfo.parts || modelInfo.parts.length === 0) return;
    this.isLoadingRobotModel = true;
    this.hasRobotModel = true;

    // 清理旧的机器人零件与层级树
    while (this.robotPartsGroup.children.length > 0) {
      const obj = this.robotPartsGroup.children[0];
      this.robotPartsGroup.remove(obj);
      if (obj.geometry) obj.geometry.dispose();
    }
    this.robotMeshParts = [];
    this.robotLinkNodes = {};
    this.robotJointPivots = {};
    this.robotRootLink = null;
    this._bodyLinksDetached = false;

    // 严密隐藏动捕球体与圆柱骨架
    this.setSkeletonVisibility(false);

    // 材质方案：Unitree G1 科技金属与碳素装甲 (双面渲染，杜绝翻转面破洞)
    const titaniumMat = new THREE.MeshStandardMaterial({
      color: 0xcfd8e3,       // 亮色科技钛银金属
      metalness: 0.85,
      roughness: 0.22,
      side: THREE.DoubleSide
    });

    const armorMat = new THREE.MeshStandardMaterial({
      color: 0x222730,       // Unitree G1 经典深空碳素装甲外壳
      metalness: 0.70,
      roughness: 0.32,
      side: THREE.DoubleSide
    });

    const rubberHandMat = new THREE.MeshStandardMaterial({
      color: 0x181c24,       // 橡胶夹爪碳黑磨砂质感
      metalness: 0.15,
      roughness: 0.85,
      side: THREE.DoubleSide
    });

    const headMat = new THREE.MeshStandardMaterial({
      color: 0x181e28,       // Unitree G1 头部深空黑碳素金属 (杜绝刺眼外星蓝色大灯泡)
      metalness: 0.78,
      roughness: 0.25,
      side: THREE.DoubleSide
    });

    const logoMat = new THREE.MeshStandardMaterial({
      color: 0x00f0ff,       // 胸口 Unitree Logo 科技荧光青蓝
      emissive: 0x0088cc,
      emissiveIntensity: 0.55,
      metalness: 0.5,
      roughness: 0.2,
      side: THREE.DoubleSide
    });

    // 1. 构建 Link 节点映射
    const links = modelInfo.links || [];
    const linkMap = {};
    for (const item of links) {
      const linkName = (typeof item === 'string') ? item : (item.name || item.link_name);
      if (!linkName) continue;
      const grp = new THREE.Group();
      grp.name = 'link_' + linkName;
      linkMap[linkName] = grp;
    }
    this.robotLinkNodes = linkMap;

    // 2. 根据 URDF 关节层级组装 Kinematic Tree (运动学父子层级关系)
    const joints = modelInfo.joints || [];
    const jointPivots = {};
    const parentLinkNames = new Set();
    const childLinkNames = new Set();

    for (const j of joints) {
      if (!j.parent || !j.child) continue;
      parentLinkNames.add(j.parent);
      childLinkNames.add(j.child);

      // 若节点在链接映射中尚未初始化，则动态补全
      if (!linkMap[j.parent]) {
        linkMap[j.parent] = new THREE.Group();
        linkMap[j.parent].name = 'link_' + j.parent;
      }
      if (!linkMap[j.child]) {
        linkMap[j.child] = new THREE.Group();
        linkMap[j.child].name = 'link_' + j.child;
      }

      const parentNode = linkMap[j.parent];
      const childNode = linkMap[j.child];

      const pivot = new THREE.Group();
      pivot.name = 'joint_' + j.name;

      // 施加 URDF 关节原点相对位移
      if (j.origin_xyz) {
        pivot.position.set(j.origin_xyz[0], j.origin_xyz[1], j.origin_xyz[2]);
      }
      // 施加 URDF 关节原点相对旋转 (RPY)
      if (j.origin_rpy) {
        pivot.rotation.order = 'ZYX';
        const euler = new THREE.Euler(j.origin_rpy[0], j.origin_rpy[1], j.origin_rpy[2], 'ZYX');
        pivot.quaternion.setFromEuler(euler);
      }

      parentNode.add(pivot);
      pivot.add(childNode);

      const axisVec = new THREE.Vector3(...(j.axis || [0, 0, 1])).normalize();
      jointPivots[j.name] = {
        pivot,
        defaultQuat: pivot.quaternion.clone(),
        axis: axisVec,
        type: j.type
      };
    }
    this.robotJointPivots = jointPivots;

    // 3. 确定 Root Link 并挂载到零件主容器
    let rootName = modelInfo.root_link || 'pelvis';
    if (!linkMap[rootName]) {
      for (const p of parentLinkNames) {
        if (!childLinkNames.has(p)) {
          rootName = p;
          break;
        }
      }
    }
    this.robotRootLink = linkMap[rootName] || linkMap['pelvis'];
    if (this.robotRootLink) {
      this.robotPartsGroup.add(this.robotRootLink);
    }

    // 建立 body_index → linkNode 映射（与 IsaacLab / PhysX body_pos_w 顺序严格一致：URDF 广度优先 BFS 遍历顺序）
    const G1_BODY_LINK_NAMES = [
      'pelvis',
      'left_hip_pitch_link', 'right_hip_pitch_link', 'waist_yaw_link',
      'left_hip_roll_link', 'right_hip_roll_link', 'waist_roll_link',
      'left_hip_yaw_link', 'right_hip_yaw_link', 'torso_link',
      'left_knee_link', 'right_knee_link',
      'left_shoulder_pitch_link', 'right_shoulder_pitch_link',
      'left_ankle_pitch_link', 'right_ankle_pitch_link',
      'left_shoulder_roll_link', 'right_shoulder_roll_link',
      'left_ankle_roll_link', 'right_ankle_roll_link',
      'left_shoulder_yaw_link', 'right_shoulder_yaw_link',
      'left_elbow_link', 'right_elbow_link',
      'left_wrist_roll_link', 'right_wrist_roll_link',
      'left_wrist_pitch_link', 'right_wrist_pitch_link',
      'left_wrist_yaw_link', 'right_wrist_yaw_link'
    ];
    const bodyNames = (modelInfo && Array.isArray(modelInfo.body_link_names) && modelInfo.body_link_names.length === 30)
      ? modelInfo.body_link_names
      : G1_BODY_LINK_NAMES;
    this.bodyIndexToLinkNode = bodyNames.map(n => linkMap[n] || null);


    // 4. 并行加载 STL 3D 网格并挂载至对应 Link 节点
    const loadPromises = modelInfo.parts.map(async (part) => {
      try {
        let geom = DancePlayer3D.geometryCache[part.mesh_url];
        if (!geom) {
          const resp = await fetch(part.mesh_url);
          if (!resp.ok) return null;
          const buf = await resp.arrayBuffer();
          geom = DancePlayer3D.parseBinarySTL(buf);
          DancePlayer3D.geometryCache[part.mesh_url] = geom;
        }

        const lName = (part.link_name || '').toLowerCase();
        let mat = titaniumMat;
        if (lName.includes('rubber_hand') || lName.includes('palm') || lName.includes('hand')) {
          mat = rubberHandMat;
        } else if (lName.includes('head')) {
          mat = headMat;
        } else if (lName.includes('logo')) {
          mat = logoMat;
        } else if (lName.includes('torso') || lName.includes('pelvis') || lName.includes('waist')) {
          mat = armorMat;
        }

        const mesh = new THREE.Mesh(geom, mat);
        mesh.castShadow = true;
        mesh.receiveShadow = true;

        const targetLink = this.robotLinkNodes[part.link_name];
        if (targetLink) {
          targetLink.add(mesh);
        } else {
          this.robotPartsGroup.add(mesh);
        }

        // 计算 link → joint_idx：优先使用 part 内嵌值，否则按语义关键词映射
        let joint_idx = (typeof part.joint_idx === 'number') ? part.joint_idx : -1;
        if (joint_idx < 0) {
          joint_idx = DancePlayer3D.resolveJointIdx(lName);
        }

        return {
          mesh,
          part,
          joint_idx,
          link_name: part.link_name,
          base_pos: part.base_pos || null,
          origin_xyz: part.origin_xyz || [0, 0, 0],
          origin_rpy: part.origin_rpy || [0, 0, 0]
        };
      } catch (err) {
        console.warn('加载机器人 3D 部件失败:', part.mesh_url, err);
        return null;
      }
    });


    const loaded = await Promise.all(loadPromises);
    this.robotMeshParts = loaded.filter(Boolean);
    this.hasRobotModel = this.robotMeshParts.length > 0;
    this.isLoadingRobotModel = false;

    // 成功装配后再次确保骨架彻底隐藏
    if (this.hasRobotModel) {
      this.setSkeletonVisibility(false);
    }
    this.renderFrame(this.currentFrame || 0);
  }

  setSkeletonVisibility(visible) {
    if (this.jointMeshes) this.jointMeshes.forEach(m => m.visible = visible);
    if (this.boneMeshes) this.boneMeshes.forEach(b => b.mesh.visible = visible);
    if (this.headMesh) this.headMesh.visible = visible;
    if (this.neckMesh) this.neckMesh.visible = visible;
  }

  async loadDance(danceData) {
    this.currentDanceData = danceData;
    const jointCount = danceData.joint_count || (danceData.frames && danceData.frames[0] ? danceData.frames[0].length : 21);

    // 检查是否有 3D 机器人网格模型
    const modelInfo = danceData.model_info;
    if (modelInfo && modelInfo.has_robot_model && modelInfo.parts && modelInfo.parts.length > 0) {
      this.hasRobotModel = true;
      this.basePose = (modelInfo.base_pose && modelInfo.base_pose.length > 0) 
        ? modelInfo.base_pose 
        : (danceData.frames ? danceData.frames[0] : null);
      this.setSkeletonVisibility(false);
      await this.loadRobotMeshModel(modelInfo);
    } else {
      this.hasRobotModel = false;
      this.basePose = null;
      // 清空机器人零件与树形节点
      while (this.robotPartsGroup.children.length > 0) {
        const obj = this.robotPartsGroup.children[0];
        this.robotPartsGroup.remove(obj);
        if (obj.geometry) obj.geometry.dispose();
      }
      this.robotMeshParts = [];
      this.robotLinkNodes = {};
      this.robotJointPivots = {};
      this.robotRootLink = null;
      this.buildSkeletonMeshes(jointCount, danceData.bone_pairs);
      this.setSkeletonVisibility(true);
    }

    this.currentFrame = 0;
    this.fps = danceData.fps || 50.0;
    this.isPlaying = true;

    // 视角对齐 (正前微斜 20° 黄金视角对焦于机器人躯干核心)
    if (this.controls) {
      if (modelInfo && modelInfo.has_robot_model) {
        this.controls.target.set(0, 0, 0.70);
        this.camera.position.set(2.2, -0.8, 1.25);
        this.controls.update();
      } else if (danceData.frames && danceData.frames[0] && danceData.frames[0][0]) {
        const p0 = danceData.frames[0][0];
        this.controls.target.set(p0[0], p0[1], p0[2] || 0.7);
        this.camera.position.set(p0[0] + 2.0, p0[1] - 0.8, (p0[2] || 0.7) + 0.35);
        this.controls.update();
      }
    }

    this.updateControlsUI();
    this.renderFrame(0);
  }

  renderFrame(frameIdx) {
    if (!this.currentDanceData || !this.currentDanceData.frames || this.currentDanceData.frames.length === 0) {
      this.setSkeletonVisibility(false);
      if (this.robotPartsGroup) {
        this.robotPartsGroup.children.forEach(c => c.visible = false);
      }
      return;
    }
    const frames = this.currentDanceData.frames;
    if (frameIdx >= frames.length) frameIdx = frames.length - 1;
    const frame = frames[frameIdx];
    const yAxis = new THREE.Vector3(0, 1, 0);

    // ==========================================
    // 场景 A: 渲染真实 3D 机器人网格模型 (URDF 树形运动学姿态驱动)
    // ==========================================
    if (this.hasRobotModel) {
      this.setSkeletonVisibility(false);

      const motion = (this.currentDanceData.model_info && this.currentDanceData.model_info.motion)
        ? this.currentDanceData.model_info.motion
        : null;

      if (motion && motion.body_world_trajectory && motion.body_world_trajectory[frameIdx]) {
        // === 路径 A: IsaacLab body_world_trajectory ===
        // 直接用每个刚体的世界位置 + 四元数设置对应 link 节点的世界变换。
        // 关键：link 节点被挂在 URDF 层级树中，setWorldPosition/Quaternion 需先 detach 到 scene。
        // 最简方案：将所有 link 节点从层级树中解绑，直接设置 position/quaternion（世界坐标）。
        const bodyTraj = motion.body_world_trajectory[frameIdx]; // [30, 7]
        const bodyLinks = this.bodyIndexToLinkNode;
        if (bodyLinks && bodyLinks.length > 0) {
          // 第一帧初始化时：将所有 body link 节点从 URDF 层级树解绑，直接挂在 robotPartsGroup 下
          if (!this._bodyLinksDetached) {
            this._bodyLinksDetached = true;
            // 先将 URDF 层级树从 robotPartsGroup 移除
            if (this.robotRootLink) this.robotPartsGroup.remove(this.robotRootLink);
            // 将每个可动 body link 直接挂在 robotPartsGroup（脱离 URDF 层级）
            for (let b = 0; b < bodyLinks.length; b++) {
              const lNode = bodyLinks[b];
              if (lNode) {
                // 把 lNode 从原父节点移除，直接加入 robotPartsGroup
                if (lNode.parent) lNode.parent.remove(lNode);
                this.robotPartsGroup.add(lNode);
              }
            }
          }
          for (let b = 0; b < bodyLinks.length && b < bodyTraj.length; b++) {
            const lNode = bodyLinks[b];
            if (!lNode) continue;
            const bd = bodyTraj[b]; // [px, py, pz, qx, qy, qz, qw]
            lNode.position.set(bd[0], bd[1], bd[2]);
            lNode.quaternion.set(bd[3], bd[4], bd[5], bd[6]);
          }
        }

      } else if (motion && motion.joint_trajectory && motion.joint_trajectory[frameIdx]) {
        // === 路径 B: URDF 关节角度驱动（内置演示舞蹈）===
        if (this.robotRootLink && motion.pelvis_trajectory && motion.pelvis_trajectory[frameIdx]) {
          const p = motion.pelvis_trajectory[frameIdx];
          const px = Array.isArray(p) ? p[0] : p.x;
          const py = Array.isArray(p) ? p[1] : p.y;
          const pz = Array.isArray(p) ? p[2] : p.z;
          this.robotRootLink.position.set(px, py, pz);
          if (Array.isArray(p) && p.length >= 7) {
            const qx = p[3], qy = p[4], qz = p[5], qw = p[6];
            this.robotRootLink.quaternion.set(qx, qy, qz, qw);
          }
        }


        // 2. 29 自由度真实关节角驱动 (父子层级旋转轴角度积分，肢体绝对不会脱节或断裂)
        const frameAngles = motion.joint_trajectory[frameIdx];
        for (const [jName, angle] of Object.entries(frameAngles)) {
          const jInfo = this.robotJointPivots[jName];
          if (jInfo && jInfo.pivot) {
            const rotDelta = new THREE.Quaternion().setFromAxisAngle(jInfo.axis, angle);
            jInfo.pivot.quaternion.copy(jInfo.defaultQuat).multiply(rotDelta);
          }
        }
      } else if (this.robotRootLink) {
        // 降级兜底：无关节角度轨迹时，将 URDF 树整体平移至 NPZ 骨盆关节点位置。
        // 机器人各部件保持 URDF 定义的静态相对位置，作为整体刚体跟随运动，不会散落。
        const pelvisJoint = frame[0]; // 骨盆 (标准21关节中索引0)
        if (pelvisJoint) {
          this.robotRootLink.position.set(pelvisJoint[0], pelvisJoint[1], pelvisJoint[2]);
        }

        // 简单躯干旋转估计：从骨盆(0) → 躯干(2)向量推算机器人朝向（Z轴为上）
        const pelvis = frame[0];
        const torso = frame[2] || frame[1];
        if (pelvis && torso) {
          const dx = torso[0] - pelvis[0];
          const dy = torso[1] - pelvis[1];
          // 仅做 XY 平面的偏航近似，防止机器人莫名倾倒
          if (Math.abs(dx) > 0.01 || Math.abs(dy) > 0.01) {
            this.robotRootLink.rotation.z = Math.atan2(dy, dx) - Math.PI / 2;
          }
        }
      }

    } else {
      // 场景 B: 渲染动捕骨骼球体与连线圆柱
      this.setSkeletonVisibility(true);

      for (let i = 0; i < this.jointMeshes.length; i++) {
        if (frame[i]) {
          const [x, y, z] = frame[i];
          this.jointMeshes[i].position.set(x, y, z);
          this.jointMeshes[i].visible = true;
        } else {
          this.jointMeshes[i].visible = false;
        }
      }

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
    }

    // 相机目标平滑追踪机器人骨盆 root
    if (this.controls) {
      let targetX = 0, targetY = 0, targetZ = 0.65;
      if (this.hasRobotModel && this.robotRootLink) {
        targetX = this.robotRootLink.position.x;
        targetY = this.robotRootLink.position.y;
        targetZ = (this.robotRootLink.position.z || 0.76) * 0.85;
      } else if (frame && frame[0]) {
        targetX = frame[0][0];
        targetY = frame[0][1];
        targetZ = frame[0][2] || 0.65;
      }
      const currentTarget = this.controls.target;
      currentTarget.x = THREE.MathUtils.lerp(currentTarget.x, targetX, 0.05);
      currentTarget.y = THREE.MathUtils.lerp(currentTarget.y, targetY, 0.05);
      currentTarget.z = THREE.MathUtils.lerp(currentTarget.z, targetZ, 0.05);
    }

    // 更新进度条和播放时间
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
    this.camera.position.set(2.2, -0.8, 1.25);
    if (this.controls) {
      this.controls.target.set(0, 0, 0.70);
      this.controls.update();
    }
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

// 显式挂载全局
if (typeof window !== 'undefined') {
  window.DancePlayer3D = DancePlayer3D;
}

// 全局 3D 播放器实例
let dancePlayer = null;
