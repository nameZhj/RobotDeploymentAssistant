/**
 * VSISLAB 机器人群控控制台 (RobotControl 模块)
 * 遵循《群控商业化补充说明.md》：
 * 1. 机器人 ID 为用户在 lora_robot_id.txt 中自定义配置的任意标识（不仅限于 A/B/C/D）；
 * 2. 统一使用全屏模态弹窗添加机器人 ID，移除冗余重复按钮；
 * 3. 自由选择与多选组合：支持鼠标左键单选、Ctrl+左键任意多选排列组合、全选 (ALL)；
 * 4. 严格按照 TARGET|COMMAND\\n 协议下发指令（多选组合按序列寻址下发，全选使用 ALL 广播下发）；
 * 5. 零点击串口自动连接与 5Hz 运控。
 */

const RobotControl = {
  // 用户自定义配置的受控机器人 ID 列表（无添加时为空列表，不设默认机器人）
  activeRobots: [],

  // 当前选中的目标集合：Set(['ALL']) 或 Set(['A']) 或 Set(['A', 'C'])
  selectedTargets: new Set(),

  isConnected: false,
  activePort: '',
  activeBaud: 9600,
  activeDesc: '',

  // Dual-Track Movement State
  activeTranslationKeys: new Set(),
  activeRotationKeys: new Set(),
  movementTimer: null,

  // Port Polling Timer for Zero-Click Auto-Connect
  autoConnectInterval: null,

  // Key mappings matching 《群控商业化补充说明.md》
  ONE_SHOT_KEYS: {
    '1': 'STAND',
    '2': 'GAIT',
    'x': 'STOP',
    'X': 'STOP',
    '0': 'PASSIVE'
  },
  TRANSLATION_KEYS: {
    'w': 'FORWARD,2',
    'W': 'FORWARD,2',
    's': 'BACKWARD,2',
    'S': 'BACKWARD,2',
    'a': 'MOVE_LEFT,2',
    'A': 'MOVE_LEFT,2',
    'd': 'MOVE_RIGHT,2',
    'D': 'MOVE_RIGHT,2'
  },
  ROTATION_KEYS: {
    'q': 'TURN_LEFT,1',
    'Q': 'TURN_LEFT,1',
    'e': 'TURN_RIGHT,1',
    'E': 'TURN_RIGHT,1'
  },

  async init() {
    this.loadStoredFleet();
    this.bindEvents();
    this.bindKeyboardListeners();
    this.renderTargetCards();

    this.logTerminal('system', '[SYSTEM] 机器人群控控制台已就绪。正在自动检测串口通信通道...');

    // 0. 初始化加载并渲染舞蹈列表
    this.fetchAndRenderDanceList(false);

    // 1. 自动检测并连接最佳串口（零点击自动连接 CH340/CH341）
    await this.autoDetectAndConnectSerial(false);

    // 2. 启动后台串口热插拔与状态监听（每 4 秒检测一次，若插入新串口自动连接）
    this.startAutoPortMonitor();

    // 3. 启动实时串口 TX/RX 字符串双向监听与控制台打印
    this.startMessagePolling();
  },

  loadStoredFleet() {
    try {
      const stored = localStorage.getItem('g1_custom_robot_fleet');
      if (stored !== null) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          this.activeRobots = parsed.map(r => String(r).trim().toUpperCase()).filter(r => r && r !== 'ALL');
          // 选中状态：若存在机器人，默认全选现有机器人；若为空则为空集合
          if (this.activeRobots.length === 1) {
            this.selectedTargets = new Set([this.activeRobots[0]]);
          } else if (this.activeRobots.length > 1) {
            this.selectedTargets = new Set(['ALL']);
          } else {
            this.selectedTargets = new Set();
          }
          return;
        }
      }
    } catch (_) { }
    // 用户未添加机器人时不要有默认的机器人
    this.activeRobots = [];
    this.selectedTargets = new Set();
  },

  saveStoredFleet() {
    try {
      localStorage.setItem('g1_custom_robot_fleet', JSON.stringify(this.activeRobots));
    } catch (_) { }
  },

  bindEvents() {
    // 串口连接/断开按钮
    const connectBtn = document.getElementById('ctrl-serial-connect-btn');
    if (connectBtn) {
      connectBtn.addEventListener('click', () => {
        if (this.isConnected) {
          this.disconnectSerial();
        } else {
          this.autoDetectAndConnectSerial(true);
        }
      });
    }

    // 刷新串口按钮
    const refreshBtn = document.getElementById('ctrl-serial-refresh-btn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => {
        this.logTerminal('system', '[SERIAL] 正在重新扫描可用串口设备...');
        this.refreshPortList();
      });
    }

    // 串口下拉框切换
    const portSelect = document.getElementById('ctrl-serial-port-select');
    if (portSelect) {
      portSelect.addEventListener('change', () => {
        const val = portSelect.value;
        if (val) {
          this.connectSpecificPort(val);
        }
      });
    }

    // 全选 (ALL) 按钮
    const btnSelectAll = document.getElementById('btn-select-all-action');
    if (btnSelectAll) {
      btnSelectAll.addEventListener('click', () => {
        this.toggleSelectAll();
      });
    }

    // 统一添加机器人按钮（唤起自定义模态弹窗）
    const btnAddRobot = document.getElementById('btn-add-robot-action');
    if (btnAddRobot) {
      btnAddRobot.addEventListener('click', () => {
        this.openAddRobotModal();
      });
    }

    // 模态弹窗内部事件绑定
    this.bindModalEvents();

    // 清空日志按钮
    const clearLogBtn = document.getElementById('ctrl-clear-log-btn');
    if (clearLogBtn) {
      clearLogBtn.addEventListener('click', () => {
        const terminalEl = document.getElementById('ctrl-terminal-output');
        if (terminalEl) terminalEl.innerHTML = '';
        this.logTerminal('system', '[SYSTEM] 日志已清空。');
      });
    }

    // 自定义指令发送
    const sendCustomBtn = document.getElementById('ctrl-send-custom-btn');
    const customInput = document.getElementById('ctrl-custom-cmd-input');
    if (sendCustomBtn && customInput) {
      const doSend = () => {
        const cmd = customInput.value.trim();
        if (cmd) {
          this.sendCommand(cmd);
          customInput.value = '';
        }
      };
      sendCustomBtn.addEventListener('click', doSend);
      customInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') doSend();
      });
    }

    // 刷新舞蹈列表按钮 (ALL|GETDANCELIST)
    const refreshDanceBtn = document.getElementById('ctrl-refresh-dance-btn');
    if (refreshDanceBtn) {
      refreshDanceBtn.addEventListener('click', () => {
        this.logTerminal('system', '[DANCE] 正在向机器人发送 ALL|GETDANCELIST 重新同步舞蹈列表...');
        this.fetchAndRenderDanceList(true);
      });
    }

    // 绑定动作按钮 (D-pad & Posture & Dance)
    this.bindCommandButtons();
  },

  // --- 自定义添加机器人模态框 (无原生 prompt，完全兼容所有环境) ---
  bindModalEvents() {
    const modal = document.getElementById('modal-add-robot');
    const btnClose = document.getElementById('btn-close-add-robot-modal');
    const btnCancel = document.getElementById('btn-cancel-add-robot');
    const btnSubmit = document.getElementById('btn-submit-add-robot');
    const inputField = document.getElementById('input-new-robot-id');

    if (btnClose) btnClose.addEventListener('click', () => this.closeAddRobotModal());
    if (btnCancel) btnCancel.addEventListener('click', () => this.closeAddRobotModal());
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) this.closeAddRobotModal();
      });
    }

    if (btnSubmit) btnSubmit.addEventListener('click', () => this.submitAddRobot());
    if (inputField) {
      inputField.addEventListener('input', () => {
        const errEl = document.getElementById('add-robot-id-error');
        if (errEl && errEl.style.display !== 'none') {
          this.validateInputId(true);
        }
      });
      inputField.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          this.submitAddRobot();
        } else if (e.key === 'Escape') {
          this.closeAddRobotModal();
        }
      });
    }
  },

  validateInputId(showIfInvalid = false) {
    const inputField = document.getElementById('input-new-robot-id');
    const errEl = document.getElementById('add-robot-id-error');
    if (!inputField) return { valid: false, error: '输入框未就绪' };

    const valResult = window.validateRobotId ? window.validateRobotId(inputField.value) : { valid: true, cleanId: inputField.value.trim().toUpperCase(), error: '' };
    if (!valResult.valid) {
      if (showIfInvalid) {
        if (errEl) {
          errEl.innerHTML = `⚠️ ${valResult.error}`;
          errEl.style.display = 'block';
        }
        inputField.classList.add('input-invalid');
      }
      return valResult;
    }

    const cleanId = valResult.cleanId;
    if (this.activeRobots.includes(cleanId)) {
      const dupError = `机器人 ID [${cleanId}] 已存在于受控列表中！`;
      if (showIfInvalid) {
        if (errEl) {
          errEl.innerHTML = `⚠️ ${dupError}`;
          errEl.style.display = 'block';
        }
        inputField.classList.add('input-invalid');
      }
      return { valid: false, cleanId, error: dupError };
    }

    if (errEl) {
      errEl.innerHTML = '';
      errEl.style.display = 'none';
    }
    inputField.classList.remove('input-invalid');
    return { valid: true, cleanId, error: '' };
  },

  openAddRobotModal() {
    const modal = document.getElementById('modal-add-robot');
    const inputField = document.getElementById('input-new-robot-id');
    const chipsContainer = document.getElementById('add-robot-chips-container');
    if (!modal) return;

    this.validateInputId(false);

    // 计算下一个推荐 ID
    const nextId = this.getNextSuggestedId();
    if (inputField) {
      inputField.value = nextId;
    }

    // 生成快捷推荐 Chips
    if (chipsContainer) {
      chipsContainer.innerHTML = '';
      const suggestions = [];
      for (let i = 0; i < 26; i++) {
        const char = String.fromCharCode(65 + i);
        if (!this.activeRobots.includes(char)) {
          suggestions.push(char);
          if (suggestions.length >= 4) break;
        }
      }
      suggestions.push(`R${this.activeRobots.length + 1}`, 'G1_02');

      suggestions.forEach(s => {
        const chip = document.createElement('button');
        chip.className = 'chip-btn';
        chip.textContent = `+${s}`;
        chip.type = 'button';
        chip.addEventListener('click', () => {
          if (inputField) {
            inputField.value = s;
            this.validateInputId(false);
            inputField.focus();
          }
        });
        chipsContainer.appendChild(chip);
      });
    }

    modal.style.display = 'flex';
    setTimeout(() => {
      if (inputField) {
        inputField.focus();
        inputField.select();
      }
    }, 50);
  },

  closeAddRobotModal() {
    const modal = document.getElementById('modal-add-robot');
    this.validateInputId(false);
    if (modal) modal.style.display = 'none';
  },

  submitAddRobot() {
    const inputField = document.getElementById('input-new-robot-id');
    if (!inputField) return;

    const valResult = this.validateInputId(true);
    if (!valResult.valid) {
      if (typeof showToast === 'function') {
        showToast(valResult.error, 'error');
      }
      inputField.focus();
      return;
    }
    const cleanId = valResult.cleanId;

    this.activeRobots.push(cleanId);
    this.saveStoredFleet();
    // 默认选中新添加的机器
    this.selectedTargets.add(cleanId);
    this.renderTargetCards();
    this.closeAddRobotModal();
    if (typeof showToast === 'function') {
      showToast(`成功添加受控机器人 [${cleanId}]`, 'success');
    }
    this.logTerminal('system', `[FLEET] 成功添加受控机器人: [${cleanId}] (当前共 ${this.activeRobots.length} 台)`);
  },

  getNextSuggestedId() {
    for (let i = 0; i < 26; i++) {
      const candidate = String.fromCharCode(65 + i);
      if (!this.activeRobots.includes(candidate)) {
        return candidate;
      }
    }
    return `R${this.activeRobots.length + 1}`;
  },

  removeRobot(robotId) {
    // 允许用户删除所有机器人，不再强制保留 1 台
    this.activeRobots = this.activeRobots.filter(r => r !== robotId);
    this.saveStoredFleet();

    // 更新选中状态
    this.selectedTargets.delete(robotId);
    if (this.activeRobots.length === 0) {
      this.selectedTargets.clear();
    } else if (this.selectedTargets.size === 0) {
      // 若还有剩余机器且未选中任何目标，默认选中第一台
      this.selectedTargets = new Set([this.activeRobots[0]]);
    }

    this.renderTargetCards();
    this.logTerminal('system', `[FLEET] 已移除机器人: [${robotId}] (当前共 ${this.activeRobots.length} 台)`);
  },

  // --- 核心：获取当前实际生效的选中机器人列表 ---
  getEffectiveSelectedRobots() {
    if (this.activeRobots.length === 0) {
      return [];
    }
    // 如果选中了广播 ALL，或者勾选了 activeRobots 中的所有机器人
    if (this.selectedTargets.has('ALL') || (this.activeRobots.length > 0 && this.activeRobots.every(r => this.selectedTargets.has(r)))) {
      return [...this.activeRobots];
    }
    return this.activeRobots.filter(r => this.selectedTargets.has(r));
  },

  // --- 自由单选、Ctrl+左键多选组合、全选控制 ---
  handleCardClick(robotId, isCtrlKey) {
    if (this.activeRobots.length === 0) return;

    if (isCtrlKey) {
      // Ctrl + 鼠标左键：多选与排列组合切换
      if (this.selectedTargets.has('ALL')) {
        // 原本是全选 -> 降级为除点击机之外的所有机器（取消该机）
        this.selectedTargets = new Set(this.activeRobots);
        this.selectedTargets.delete(robotId);
        if (this.selectedTargets.size === 0) {
          this.selectedTargets = new Set([robotId]);
        }
      } else {
        if (this.selectedTargets.has(robotId)) {
          this.selectedTargets.delete(robotId);
          // 取消后若变空，保留空选
        } else {
          this.selectedTargets.add(robotId);
          // 若包含所有机器且数量 > 1，升级为 ALL
          if (this.activeRobots.length > 1 && this.activeRobots.every(r => this.selectedTargets.has(r))) {
            this.selectedTargets = new Set(['ALL']);
          }
        }
      }
    } else {
      // 普通左键单击：单选该机器
      this.selectedTargets = new Set([robotId]);
    }

    this.renderTargetCards();
    this.logSelectionChange();
  },

  toggleSelectAll() {
    if (this.activeRobots.length === 0) {
      this.logTerminal('system', '[TARGET] 当前尚未添加机器人，请先点击「+ 添加机器人」');
      return;
    }

    const effective = this.getEffectiveSelectedRobots();
    const isAllMode = effective.length === this.activeRobots.length;

    if (isAllMode) {
      // 再次点击全选 -> 取消全选
      this.selectedTargets.clear();
    } else {
      // 全选：若仅有 1 台机器人，直接选中该机器单机；若有多台，使用 ALL 标识
      if (this.activeRobots.length === 1) {
        this.selectedTargets = new Set([this.activeRobots[0]]);
      } else {
        this.selectedTargets = new Set(['ALL']);
      }
    }
    this.renderTargetCards();
    this.logSelectionChange();
  },

  selectAll() {
    if (this.activeRobots.length === 0) return;
    if (this.activeRobots.length === 1) {
      this.selectedTargets = new Set([this.activeRobots[0]]);
    } else {
      this.selectedTargets = new Set(['ALL']);
    }
    this.renderTargetCards();
    this.logSelectionChange();
  },

  logSelectionChange() {
    const summary = this.getSelectionSummaryText();
    this.logTerminal('system', `[TARGET] 控制目标已切换: ${summary}`);
  },

  getSelectionSummaryText() {
    if (this.activeRobots.length === 0) {
      return '暂无机器人 (请先添加)';
    }
    const effective = this.getEffectiveSelectedRobots();
    if (effective.length === 0) {
      return '未选择机器 (请点击卡片或勾选目标)';
    }
    // 有且仅有一台机器人被选中
    if (effective.length === 1) {
      return `Robot ${effective[0]} (单机)`;
    }
    // 全部选中且机队大于 1 台
    if (effective.length === this.activeRobots.length) {
      return `全选 [${effective.join(',')}] (共 ${effective.length} 台)`;
    }
    return `多选 [${effective.join(',')}] (共 ${effective.length} 台)`;
  },

  getCommandPrefixText() {
    if (this.activeRobots.length === 0) {
      return 'NONE|';
    }
    const effective = this.getEffectiveSelectedRobots();
    if (effective.length === 0) {
      return 'NONE|';
    }
    // 无论是单选、多选还是全选，目标均以逗号隔开 (如 A| 或 A,B|)，不再发送 ALL
    return `${effective.join(',')}|`;
  },

  // --- 动态渲染目标控制卡片流 ---
  renderTargetCards() {
    const container = document.getElementById('ctrl-target-grid-container');
    if (!container) return;

    container.innerHTML = '';

    // 0. 若未添加任何机器人，展示友好引导空状态
    if (this.activeRobots.length === 0) {
      const emptyDiv = document.createElement('div');
      emptyDiv.className = 'empty-fleet-hint';
      emptyDiv.innerHTML = `
        <div class="empty-fleet-title">暂无受控机器人</div>
        <div class="empty-fleet-desc">请点击右上角「+ 添加机器人」输入唯一机身标识（如 A、B、R1）即可纳入实时群控</div>
      `;
      container.appendChild(emptyDiv);

      const btnSelectAll = document.getElementById('btn-select-all-action');
      if (btnSelectAll) {
        btnSelectAll.className = 'btn btn-secondary btn-sm';
        btnSelectAll.disabled = true;
        btnSelectAll.innerHTML = '<span>👑</span> 全选';
        btnSelectAll.title = '暂无机器人可用';
      }

      const summaryEl = document.getElementById('ctrl-selected-summary');
      if (summaryEl) summaryEl.textContent = '已选: 暂无机器人 (请先添加)';

      const prefixEl = document.getElementById('ctrl-active-target-prefix');
      if (prefixEl) prefixEl.textContent = 'NONE|';
      return;
    }

    const effective = this.getEffectiveSelectedRobots();
    const isAllMode = effective.length === this.activeRobots.length;

    // 1. 渲染每台机器人卡片
    this.activeRobots.forEach((robotId, index) => {
      const card = document.createElement('div');
      const isSelected = effective.includes(robotId);
      card.className = `target-card ${isSelected ? 'active' : ''}`;
      card.setAttribute('data-target', robotId);

      // Top Bar: Badge (with Checkbox) + Delete Button
      const topBar = document.createElement('div');
      topBar.className = 'target-card-top';

      const badge = document.createElement('div');
      badge.className = 'target-badge';

      // 多选复选框
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'target-card-checkbox';
      checkbox.checked = isSelected;
      checkbox.title = `多选勾选 Robot ${robotId}`;
      checkbox.addEventListener('click', (e) => {
        e.stopPropagation();
        this.handleCardClick(robotId, true);
      });

      const labelSpan = document.createElement('span');
      labelSpan.textContent = `Robot ${robotId}`;

      badge.appendChild(checkbox);
      badge.appendChild(labelSpan);
      topBar.appendChild(badge);

      // 允许删除（包括只有 1 台时也能删除）
      const removeBtn = document.createElement('button');
      removeBtn.className = 'btn-card-remove';
      removeBtn.innerHTML = '✕';
      removeBtn.title = `移除 Robot ${robotId}`;
      removeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.removeRobot(robotId);
      });
      topBar.appendChild(removeBtn);

      // Center: Big Target ID
      const idDiv = document.createElement('div');
      idDiv.className = 'target-id';
      idDiv.textContent = `T ${robotId}`;

      // Bottom: Shortcut & Mode Desc
      const desc = document.createElement('div');
      desc.className = 'target-desc';
      desc.innerHTML = `<span>${isSelected ? '✓ 已选中' : '单击选中'}</span><span>Ctrl+${index + 1}</span>`;

      card.appendChild(topBar);
      card.appendChild(idDiv);
      card.appendChild(desc);

      // 监听左键与 Ctrl+左键
      card.addEventListener('click', (e) => {
        this.handleCardClick(robotId, e.ctrlKey || e.metaKey);
      });

      container.appendChild(card);
    });

    // 2. 更新工具栏全选按钮状态
    const btnSelectAll = document.getElementById('btn-select-all-action');
    if (btnSelectAll) {
      btnSelectAll.disabled = false;
      if (isAllMode && this.activeRobots.length > 0) {
        btnSelectAll.className = 'btn btn-primary btn-sm';
        btnSelectAll.innerHTML = '<span>👑</span> 取消全选';
        btnSelectAll.title = '当前已全选，再次点击取消全选';
      } else {
        btnSelectAll.className = 'btn btn-secondary btn-sm';
        btnSelectAll.innerHTML = '<span>👑</span> 全选';
        btnSelectAll.title = '全选所有受控机器人 (Ctrl+A)';
      }
    }

    // 3. 更新已选摘要与指令前缀
    const summaryText = this.getSelectionSummaryText();
    const summaryEl = document.getElementById('ctrl-selected-summary');
    if (summaryEl) {
      summaryEl.textContent = `已选: ${summaryText}`;
    }

    const prefixEl = document.getElementById('ctrl-active-target-prefix');
    if (prefixEl) {
      prefixEl.textContent = this.getCommandPrefixText();
    }
  },

  // --- 指令发送 (支持单机与多机逗号隔开下发) ---
  async sendCommand(commandStr) {
    if (!commandStr) return;
    const command = commandStr.trim().toUpperCase();

    const effective = this.getEffectiveSelectedRobots();

    // 安全检查：未选择任何目标时拦截提示
    if (effective.length === 0) {
      this.logTerminal('error', `[TX WARN] 未选中任何受控目标！请先添加或勾选机器人卡片（拟下发: ${command}）`);
      return;
    }

    // 规范：单选、多选或全选，均采用逗号隔开的目标格式 (如 "A" 或 "A,B")，单次发送，不再发送 ALL，也不必发送多次
    const target = effective.join(',');
    await this.sendSinglePacket(target, command);
  },

  async sendSinglePacket(target, command) {
    const packet = `${target}|${command}\n`;

    try {
      const res = await API.sendSerialCmd(target, command);
      if (res && res.success) {
        this.logTerminal('tx', `[TX] ${packet.trim()}`);
      } else {
        this.logTerminal('error', `[TX WARN] 发送未成功: ${res?.msg || '串口未连接'} (拟发送: ${packet.trim()})`);
      }
    } catch (e) {
      this.logTerminal('error', `[TX ERROR] 串口发送异常: ${e.message || e}`);
    }
  },

  // --- 零点击串口自动检测与连接 ---
  async autoDetectAndConnectSerial(isUserTriggered = false) {
    const statusBadge = document.getElementById('ctrl-serial-status-badge');
    const statusText = document.getElementById('ctrl-serial-status-text');
    const connectBtn = document.getElementById('ctrl-serial-connect-btn');

    if (statusBadge) statusBadge.className = 'status-badge warning';
    if (statusText) statusText.textContent = '连接中';

    try {
      await this.refreshPortList();

      const baudSelect = document.getElementById('ctrl-baud-rate-select');
      const baud = baudSelect ? parseInt(baudSelect.value, 10) : 9600;

      const res = await API.autoConnectSerial(baud);
      if (res && res.success && res.connected) {
        this.isConnected = true;
        this.activePort = res.port;
        this.activeBaud = res.baudrate || baud;
        this.activeDesc = res.description || '';

        if (statusBadge) statusBadge.className = 'status-badge connected';
        if (statusText) statusText.textContent = '已连接';
        if (connectBtn) {
          const btnText = connectBtn.querySelector('.btn-text');
          if (btnText) btnText.textContent = '断开串口';
        }

        const portSelect = document.getElementById('ctrl-serial-port-select');
        if (portSelect && this.activePort) {
          portSelect.value = this.activePort;
        }

        this.logTerminal('system', `[SERIAL AUTO] 成功自动识别并连接串口: ${this.activePort} (${this.activeDesc}) @ ${this.activeBaud} Baud`);
        // 首次连接成功后后台已触发一次同步，前端读取缓存渲染，避免二次发送 GETDANCELIST
        this.fetchAndRenderDanceList(false);
      } else {
        this.isConnected = false;
        if (statusBadge) statusBadge.className = 'status-badge disconnected';
        if (statusText) statusText.textContent = '未连接';
        if (connectBtn) {
          const btnText = connectBtn.querySelector('.btn-text');
          if (btnText) btnText.textContent = '连接串口';
        }

        if (isUserTriggered) {
          this.logTerminal('error', `[SERIAL WARN] ${res?.msg || '未找到可连接的串口设备'}`);
        }
      }
    } catch (e) {
      this.isConnected = false;
      if (statusBadge) statusBadge.className = 'status-badge disconnected';
      if (statusText) statusText.textContent = '未连接';
      if (isUserTriggered) {
        this.logTerminal('error', `[SERIAL ERROR] 串口检测异常: ${e.message || e}`);
      }
    }
  },

  async refreshPortList() {
    const portSelect = document.getElementById('ctrl-serial-port-select');
    if (!portSelect) return;

    try {
      const res = await API.getSerialPorts();
      const ports = (res && res.ports) ? res.ports : [];

      portSelect.innerHTML = '';
      if (ports.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = '未检测到串口';
        portSelect.appendChild(opt);
      } else {
        ports.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.port;
          opt.textContent = `${p.port} - ${p.description}`;
          if (p.port === this.activePort || (p.is_ch341 && !this.activePort)) {
            opt.selected = true;
          }
          portSelect.appendChild(opt);
        });
      }
    } catch (e) {
      console.warn('Refresh port list failed:', e);
    }
  },

  async connectSpecificPort(portName) {
    const baudSelect = document.getElementById('ctrl-baud-rate-select');
    const baud = baudSelect ? parseInt(baudSelect.value, 10) : 9600;

    const statusBadge = document.getElementById('ctrl-serial-status-badge');
    const statusText = document.getElementById('ctrl-serial-status-text');
    if (statusBadge) statusBadge.className = 'status-badge warning';
    if (statusText) statusText.textContent = '连接中';

    this.logTerminal('system', `[SERIAL] 正在连接指定串口: ${portName}...`);
    try {
      const res = await API.connectSerial(portName, baud);
      if (res && res.success && res.connected) {
        this.isConnected = true;
        this.activePort = portName;
        this.activeBaud = baud;

        if (statusBadge) statusBadge.className = 'status-badge connected';
        if (statusText) statusText.textContent = '已连接';
        const connectBtn = document.getElementById('ctrl-serial-connect-btn');
        if (connectBtn) {
          const btnText = connectBtn.querySelector('.btn-text');
          if (btnText) btnText.textContent = '断开串口';
        }

        this.logTerminal('system', `[SERIAL SUCCESS] 成功连接串口: ${portName}`);
        await this.refreshPortList();
        this.fetchAndRenderDanceList(false);
      } else {
        if (statusBadge) statusBadge.className = 'status-badge disconnected';
        if (statusText) statusText.textContent = '未连接';
        this.logTerminal('error', `[SERIAL ERROR] 连接失败: ${res?.msg || '未知原因'}`);
      }
    } catch (e) {
      if (statusBadge) statusBadge.className = 'status-badge disconnected';
      if (statusText) statusText.textContent = '未连接';
      this.logTerminal('error', `[SERIAL ERROR] ${e.message || e}`);
    }
  },


  async disconnectSerial() {
    const target = this.activeRobots.length > 0 ? this.activeRobots.join(',') : 'ALL';
    this.logTerminal('system', `[SERIAL] 断开前主动下发安全复位 (${target}|GAIT)...`);

    // 断开连接时自动发安全复位 (优先当前受控机器人，若无则 ALL)
    try {
      await API.sendSerialCmd(target, 'GAIT');
      this.logTerminal('tx', `[TX] ${target}|GAIT  (断开保护)`);
    } catch (_) {
      this.logTerminal('error', '[TX WARN] 断开前指令下发失败（串口可能已离线）');
    }

    try {
      await API.disconnectSerial(true);
    } catch (_) { }

    this.isConnected = false;
    this.activePort = '';
    const statusBadge = document.getElementById('ctrl-serial-status-badge');
    const statusText = document.getElementById('ctrl-serial-status-text');
    const connectBtn = document.getElementById('ctrl-serial-connect-btn');

    if (statusBadge) statusBadge.className = 'status-badge disconnected';
    if (statusText) statusText.textContent = '未连接';
    if (connectBtn) {
      const btnText = connectBtn.querySelector('.btn-text');
      if (btnText) btnText.textContent = '连接串口';
    }

    this.logTerminal('system', '[SERIAL] 串口连接已安全断开释放。');
    await this.refreshPortList();
  },

  startAutoPortMonitor() {
    if (this.autoConnectInterval) clearInterval(this.autoConnectInterval);
    this.autoConnectInterval = setInterval(async () => {
      if (!this.isConnected) {
        try {
          const res = await API.getSerialPorts();
          if (res && res.ports && res.ports.some(p => p.is_ch341)) {
            await this.autoDetectAndConnectSerial(false);
          }
        } catch (_) { }
      } else {
        try {
          const statusRes = await API.getSerialStatus();
          if (statusRes && statusRes.data && !statusRes.data.connected) {
            this.isConnected = false;
            this.activePort = '';
            const statusBadge = document.getElementById('ctrl-serial-status-badge');
            const statusText = document.getElementById('ctrl-serial-status-text');
            if (statusBadge) statusBadge.className = 'status-badge disconnected';
            if (statusText) statusText.textContent = '未连接';
          }
        } catch (_) { }
      }
    }, 4000);
  },

  // --- 双轨 5Hz 运控循环与按键绑定 ---
  tickMovementLoop() {
    if (this.activeTranslationKeys.size > 0) {
      const activeKey = Array.from(this.activeTranslationKeys).pop();
      const cmd = this.TRANSLATION_KEYS[activeKey];
      if (cmd) this.sendCommand(cmd);
    }
    if (this.activeRotationKeys.size > 0) {
      const activeKey = Array.from(this.activeRotationKeys).pop();
      const cmd = this.ROTATION_KEYS[activeKey];
      if (cmd) this.sendCommand(cmd);
    }
  },

  startMovementTimerIfNeeded() {
    this.tickMovementLoop();
    if (!this.movementTimer) {
      this.movementTimer = setInterval(() => {
        this.tickMovementLoop();
      }, 200); // 5Hz 运控频率
    }
  },

  stopMovementTimerIfEmpty() {
    if (this.activeTranslationKeys.size === 0 && this.activeRotationKeys.size === 0) {
      if (this.movementTimer) {
        clearInterval(this.movementTimer);
        this.movementTimer = null;
      }
      document.querySelectorAll('.btn-cmd').forEach(btn => {
        const key = btn.getAttribute('data-key');
        if (key && (this.TRANSLATION_KEYS[key] || this.ROTATION_KEYS[key])) {
          btn.classList.remove('key-active');
        }
      });
      this.logTerminal('system', '[MOVEMENT] 抬手松开所有移动/旋转按键，下发停止指令 (STOP)');
      this.sendCommand('STOP');
    }
  },

  clearAllMovement() {
    this.activeTranslationKeys.clear();
    this.activeRotationKeys.clear();
    if (this.movementTimer) {
      clearInterval(this.movementTimer);
      this.movementTimer = null;
    }
    document.querySelectorAll('.btn-cmd').forEach(btn => {
      const key = btn.getAttribute('data-key');
      if (key && (this.TRANSLATION_KEYS[key] || this.ROTATION_KEYS[key])) {
        btn.classList.remove('key-active');
      }
    });
    this.sendCommand('STOP');
  },

  bindCommandButtons() {
    document.querySelectorAll('.tab-robot-control .btn-cmd').forEach(btn => {
      const key = btn.getAttribute('data-key');
      const cmd = btn.getAttribute('data-cmd');

      // WASD / QE 连续按压
      if (key && (this.TRANSLATION_KEYS[key] || this.ROTATION_KEYS[key])) {
        const handlePress = (e) => {
          e.preventDefault();
          btn.classList.add('key-active');
          if (this.TRANSLATION_KEYS[key]) {
            this.activeTranslationKeys.add(key);
          } else {
            this.activeRotationKeys.add(key);
          }
          this.startMovementTimerIfNeeded();
        };

        const handleRelease = (e) => {
          e.preventDefault();
          btn.classList.remove('key-active');
          if (this.TRANSLATION_KEYS[key]) {
            this.activeTranslationKeys.delete(key);
          } else {
            this.activeRotationKeys.delete(key);
          }
          this.stopMovementTimerIfEmpty();
        };

        btn.addEventListener('mousedown', handlePress);
        btn.addEventListener('mouseup', handleRelease);
        btn.addEventListener('mouseleave', handleRelease);
        btn.addEventListener('touchstart', handlePress);
        btn.addEventListener('touchend', handleRelease);
      } else {
        // 单击按钮 (STAND, GAIT, EMERGENCY, DANCE 等)
        btn.addEventListener('click', () => {
          if (cmd) {
            this.sendCommand(cmd);
            btn.classList.add('key-active');
            setTimeout(() => btn.classList.remove('key-active'), 200);
          }
        });
      }
    });
  },

  bindKeyboardListeners() {
    document.addEventListener('keydown', (e) => {
      if (App.activeTab !== 'tab-robot-control') return;
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;

      // Ctrl + A 或 Ctrl + 0 或 Ctrl + G -> 全选 (ALL)
      if (e.ctrlKey && !e.shiftKey && !e.altKey) {
        if (e.key.toLowerCase() === 'a' || e.key === '0' || e.key.toLowerCase() === 'g' || e.key === '`') {
          e.preventDefault();
          this.selectAll();
          return;
        }

        // Ctrl + 1..N 切换至单机
        const num = parseInt(e.key, 10);
        if (!isNaN(num) && num >= 1 && num <= this.activeRobots.length) {
          e.preventDefault();
          const targetId = this.activeRobots[num - 1];
          this.handleCardClick(targetId, false);
          return;
        }
      }

      const rawKey = e.key;

      // WASD
      if (this.TRANSLATION_KEYS[rawKey]) {
        e.preventDefault();
        if (e.repeat) return;
        this.activeTranslationKeys.add(rawKey);
        this.highlightBtn(rawKey);
        this.startMovementTimerIfNeeded();
        return;
      }

      // QE
      if (this.ROTATION_KEYS[rawKey]) {
        e.preventDefault();
        if (e.repeat) return;
        this.activeRotationKeys.add(rawKey);
        this.highlightBtn(rawKey);
        this.startMovementTimerIfNeeded();
        return;
      }

      // One-shot keys (1, 2, 0, X)
      if (this.ONE_SHOT_KEYS[rawKey]) {
        e.preventDefault();
        if (e.repeat) return;
        const cmd = this.ONE_SHOT_KEYS[rawKey];
        this.sendCommand(cmd);
        this.highlightBtn(rawKey);
      }
    });

    document.addEventListener('keyup', (e) => {
      if (App.activeTab !== 'tab-robot-control') return;
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;

      const rawKey = e.key;
      if (this.TRANSLATION_KEYS[rawKey] || this.ROTATION_KEYS[rawKey]) {
        e.preventDefault();
        if (this.TRANSLATION_KEYS[rawKey]) this.activeTranslationKeys.delete(rawKey);
        if (this.ROTATION_KEYS[rawKey]) this.activeRotationKeys.delete(rawKey);
        this.unhighlightBtn(rawKey);
        this.stopMovementTimerIfEmpty();
      }
    });

    window.addEventListener('blur', () => {
      if (this.activeTranslationKeys.size > 0 || this.activeRotationKeys.size > 0 || this.movementTimer) {
        this.clearAllMovement();
      }
    });
  },

  highlightBtn(key) {
    document.querySelectorAll('.tab-robot-control .btn-cmd').forEach(b => {
      if (b.getAttribute('data-key') && b.getAttribute('data-key').toLowerCase() === key.toLowerCase()) {
        b.classList.add('key-active');
      }
    });
  },

  unhighlightBtn(key) {
    document.querySelectorAll('.tab-robot-control .btn-cmd').forEach(b => {
      if (b.getAttribute('data-key') && b.getAttribute('data-key').toLowerCase() === key.toLowerCase()) {
        b.classList.remove('key-active');
      }
    });
  },

  logTerminal(type, text) {
    const terminal = document.getElementById('ctrl-terminal-output');
    if (!terminal) return;

    const timeStr = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    const line = document.createElement('div');
    line.className = `log-line ${type}`;

    const timeSpan = document.createElement('span');
    timeSpan.className = 'timestamp';
    timeSpan.textContent = `[${timeStr}]`;

    line.appendChild(timeSpan);
    line.appendChild(document.createTextNode(text));

    terminal.appendChild(line);
    terminal.scrollTop = terminal.scrollHeight;

    while (terminal.children.length > 200) {
      terminal.removeChild(terminal.firstChild);
    }
  },

  // --- 实时串口 TX / RX 字符串消息双向轮询与实时展示 ---
  lastMsgTimestamp: 0,
  msgPollingTimer: null,
  _lastRenderedDanceCount: 0,

  startMessagePolling() {
    if (this.msgPollingTimer) clearInterval(this.msgPollingTimer);
    let pollCount = 0;
    this.msgPollingTimer = setInterval(async () => {
      // 仅在当前处于群控页面且串口处于连接时轮询
      if (App.activeTab !== 'tab-robot-control' || !this.isConnected) return;
      pollCount++;
      try {
        const res = await API.getSerialMessages(this.lastMsgTimestamp);
        let hasDanceMsg = false;
        if (res && res.success && Array.isArray(res.messages) && res.messages.length > 0) {
          res.messages.forEach(msg => {
            if (msg.timestamp > this.lastMsgTimestamp) {
              this.lastMsgTimestamp = msg.timestamp;
            }
            // 仅在监视器中打印下位机回传 (RX) 消息（TX 指令已在发送时即时打印，避免重复记录）
            if (msg.type === 'rx') {
              this.logTerminal('rx', `[RX] ${msg.text}`);
              if (msg.text.includes(':') || msg.text.includes('Group') || msg.text.includes('[')) {
                hasDanceMsg = true;
              }
            }
          });
        }

        // 若收到动作列表相关回传，或每 3 秒检测一次后端最新解析缓存（自动同步全部舞蹈）
        if (hasDanceMsg || pollCount % 6 === 0) {
          this.syncDanceListFromCache();
        }
      } catch (_) { }
    }, 500);
  },

  async syncDanceListFromCache() {
    if (!this.isConnected) return;
    try {
      const res = await API.getSerialDanceList(false);
      if (res && res.success && Array.isArray(res.groups) && res.groups.length > 0) {
        const total = res.total_count || res.groups.reduce((acc, g) => acc + (g.items ? g.items.length : 0), 0);
        if (total !== this._lastRenderedDanceCount || this.currentDanceGroups.length === 0) {
          this._lastRenderedDanceCount = total;
          this.currentDanceGroups = res.groups;
          this.renderDanceGroups(res.groups);
        }
      }
    } catch (_) { }
  },

  // --- 动态串口舞蹈列表状态与渲染逻辑 (严格由串口 ALL|GETDANCELIST 驱动，绝不硬编码) ---
  currentDanceGroups: [],

  async fetchAndRenderDanceList(isForceRefresh = false) {
    const countTag = document.getElementById('ctrl-dance-count-tag');

    // 1. 若串口未连接，直接渲染未连接状态
    if (!this.isConnected) {
      this.currentDanceGroups = [];
      this.renderDisconnectedState();
      return;
    }

    // 2. 串口已连接，展示同步等待态
    this.renderLoadingState(isForceRefresh);
    if (countTag) countTag.textContent = isForceRefresh ? '正在下发 ALL|GETDANCELIST...' : '正在同步动作列表...';

    try {
      let res;
      if (isForceRefresh) {
        res = await API.refreshSerialDanceList(5.5);
      } else {
        res = await API.getSerialDanceList(false);
      }

      if (res && res.success && res.groups && res.groups.length > 0) {
        this.currentDanceGroups = res.groups;
        this.renderDanceGroups(res.groups);
        const total = res.total_count || res.groups.reduce((acc, g) => acc + (g.items ? g.items.length : 0), 0);
        this.logTerminal('system', `[DANCE SYNC] 成功从串口接收并动态解析 ${total} 支机载动作 (来源: ALL|GETDANCELIST)`);
        return;
      }
    } catch (e) {
      console.warn('获取串口舞蹈列表失败:', e);
      this.logTerminal('error', `[DANCE ERROR] 串口动作列表同步异常: ${e.message || e}`);
    }

    // 3. 串口已连接但机载端暂无响应或未返回 dance_map
    this.renderNoDataState();
  },

  renderDisconnectedState() {
    const container = document.getElementById('ctrl-dance-scroll-container');
    const countTag = document.getElementById('ctrl-dance-count-tag');
    if (countTag) countTag.textContent = '🔌 串口未连接';
    if (!container) return;

    container.innerHTML = `
      <div class="dance-status-card">
        <div class="dance-status-icon">🔌</div>
        <div class="dance-status-title">LoRa 串口通信未连接</div>
        <div class="dance-status-desc">
          动作与特技列表完全由目标机器人机载主控动态提供。<br>
          请插入 USB LoRa 串口发射器 (CH340/CH341) 并连接，系统将自动下发 <code>ALL|GETDANCELIST</code> 实时拉取机载动作映射表。
        </div>
      </div>
    `;
  },

  renderLoadingState(isForce = false) {
    const container = document.getElementById('ctrl-dance-scroll-container');
    if (!container) return;

    container.innerHTML = `
      <div class="dance-status-card">
        <div class="dance-loading-spinner"></div>
        <div class="dance-status-title">正在通过串口同步机载动作列表...</div>
        <div class="dance-status-desc">
          正在向机器人发送 <code>ALL|GETDANCELIST</code>，等待机载端 <code>lora_recv_group</code> 返回 <code>dance_map</code> YAML 映射...
        </div>
      </div>
    `;
  },

  renderNoDataState() {
    const container = document.getElementById('ctrl-dance-scroll-container');
    const countTag = document.getElementById('ctrl-dance-count-tag');
    if (countTag) countTag.textContent = '⚠️ 暂未获取到机载动作';
    if (!container) return;

    container.innerHTML = `
      <div class="dance-status-card">
        <div class="dance-status-icon">📡</div>
        <div class="dance-status-title">暂未收到机载响应</div>
        <div class="dance-status-desc">
          串口已连接，但机载主控暂未返回有效的动作配置。<br>
          请确认机器人机载程序处于正常运行状态且 LoRa 频段一致。
        </div>
        <button class="btn btn-primary btn-xs" style="margin-top: 10px; padding: 4px 14px; font-size: 0.8rem;" onclick="RobotControl.fetchAndRenderDanceList(true)">
          🔄 重新获取列表
        </button>
      </div>
    `;
  },

  renderDanceGroups(groups) {
    const container = document.getElementById('ctrl-dance-scroll-container');
    if (!container) return;

    container.innerHTML = '';
    let totalCount = 0;

    groups.forEach(group => {
      const catDiv = document.createElement('div');
      catDiv.className = 'dance-category';

      const titleDiv = document.createElement('div');
      titleDiv.className = 'category-title';
      titleDiv.textContent = group.title || `${group.group_id} 动作组`;
      catDiv.appendChild(titleDiv);

      const gridDiv = document.createElement('div');
      gridDiv.className = 'dance-grid';

      (group.items || []).forEach(item => {
        totalCount++;
        const btn = document.createElement('button');
        btn.className = 'btn-cmd btn-dance';
        btn.setAttribute('data-cmd', item.cmd || `DANCE,${item.alias}`);

        const keyInfo = (item.keys && item.keys.length > 0) ? ` [${item.keys.join(', ')}]` : '';
        btn.title = `${item.name} (${item.alias})${keyInfo}`;

        const titleSpan = document.createElement('span');
        titleSpan.className = 'dance-title';
        titleSpan.textContent = item.name;

        const codeSpan = document.createElement('span');
        codeSpan.className = 'dance-code';
        codeSpan.textContent = item.short_code || item.alias;

        btn.appendChild(titleSpan);
        btn.appendChild(codeSpan);

        // 绑定点击发送与高亮反馈
        btn.addEventListener('click', () => {
          const cmd = btn.getAttribute('data-cmd');
          if (cmd) {
            this.sendCommand(cmd);
            btn.classList.add('key-active');
            setTimeout(() => btn.classList.remove('key-active'), 200);
          }
        });

        gridDiv.appendChild(btn);
      });

      catDiv.appendChild(gridDiv);
      container.appendChild(catDiv);
    });

    const countTag = document.getElementById('ctrl-dance-count-tag');
    if (countTag) {
      countTag.textContent = `🟢 串口实时同步 (共 ${totalCount} 项动作)`;
    }
  }
};
