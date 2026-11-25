/**
 * VSISLAB 机器人群控控制台 (纯 Wi-Fi 局域网 HTTP 通信模式)
 * 规范：
 * 1. 本页面及全部非无线配网业务均通过 Wi-Fi 局域网 HTTP (http://<IP>:<Port>/api/v1/...) 与下位机通信，不再使用串口；
 * 2. 支持单选、Ctrl+左键多选组合、全选，按各机器人绑定的局域网 IP 并发下发 HTTP 控制指令；
 * 3. 支持一键扫描当前 Wi-Fi 局域网中在线的下位机 HTTP 服务并自动加入编队；
 * 4. 动作列表通过 GET /api/v1/actions/list 实时从下位机拉取，多机编队自动求共有动作交集。
 */

const RobotControl = {
  // 受控机器人列表: [{ id: 'A', ip: '192.168.50.101', port: 8090 }]
  fleet: [],
  // 兼容旧代码读取 ID 数组
  get activeRobots() {
    return this.fleet.map(r => r.id);
  },

  // 当前选中的目标集合
  selectedTargets: new Set(),
  // 实时 HTTP 健康状态映射 { A: { online: true, latency_ms: 12.3, authority: 'FREE' } }
  healthMap: {},

  // 双轨 5Hz 运控按键状态
  activeTranslationKeys: new Set(),
  activeRotationKeys: new Set(),
  movementTimer: null,
  healthPollTimer: null,
  _danceSyncDebounceTimer: null,
  _danceRequestId: 0,
  currentDanceGroups: [],

  ONE_SHOT_KEYS: { '1': 'STAND', '2': 'GAIT', 'x': 'STOP', 'X': 'STOP', '0': 'PASSIVE' },
  TRANSLATION_KEYS: {
    'w': 'FORWARD,2', 'W': 'FORWARD,2', 's': 'BACKWARD,2', 'S': 'BACKWARD,2',
    'a': 'MOVE_LEFT,2', 'A': 'MOVE_LEFT,2', 'd': 'MOVE_RIGHT,2', 'D': 'MOVE_RIGHT,2'
  },
  ROTATION_KEYS: { 'q': 'TURN_LEFT,1', 'Q': 'TURN_LEFT,1', 'e': 'TURN_RIGHT,1', 'E': 'TURN_RIGHT,1' },

  async init() {
    this.loadStoredFleet();
    this.bindEvents();
    this.bindKeyboardListeners();
    this.renderTargetCards();

    await this.syncFleetFromBackend();
    this.renderTargetCards();

    this.logTerminal('system', '[SYSTEM] 机器人群控控制台已就绪（Wi-Fi 局域网 HTTP 通信模式，仅修改 Wi-Fi 配网使用 LoRa）。');
    await this.refreshFleetHealth(false);
    this.fetchAndRenderDanceList(false);
    this.startHttpHealthMonitor();
  },

  _normalizeRobotItem(item) {
    if (typeof item === 'string') {
      const id = item.trim().toUpperCase();
      return id && id !== 'ALL' ? { id, ip: '', port: 8090 } : null;
    }
    if (item && typeof item === 'object' && item.id) {
      const id = String(item.id).trim().toUpperCase();
      if (!id || id === 'ALL') return null;
      return { id, ip: String(item.ip || '').trim(), port: parseInt(item.port, 10) || 8090 };
    }
    return null;
  },

  loadStoredFleet() {
    try {
      const raw = localStorage.getItem('g1_http_robot_fleet') || localStorage.getItem('g1_custom_robot_fleet');
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          this.fleet = parsed.map(x => this._normalizeRobotItem(x)).filter(Boolean);
        }
      }
      const storedSel = localStorage.getItem('g1_custom_selected_targets');
      if (storedSel) {
        const sel = JSON.parse(storedSel);
        if (Array.isArray(sel) && sel.length > 0) {
          this.selectedTargets = new Set(sel.filter(s => s === 'ALL' || this.activeRobots.includes(s)));
          return;
        }
      }
      this.selectedTargets = this.fleet.length === 1 ? new Set([this.fleet[0].id]) : (this.fleet.length > 1 ? new Set(['ALL']) : new Set());
    } catch (_) {
      this.fleet = [];
      this.selectedTargets = new Set();
    }
  },

  async syncFleetFromBackend() {
    try {
      if (typeof API === 'undefined' || typeof API.getFleet !== 'function') return;
      const res = await API.getFleet();
      if (res && res.success && Array.isArray(res.robots)) {
        if (res.robots.length > 0) {
          this.fleet = res.robots.map(x => this._normalizeRobotItem(x)).filter(Boolean);
          if (Array.isArray(res.selected) && res.selected.length > 0) {
            this.selectedTargets = new Set(res.selected);
          } else {
            this.selectedTargets = this.fleet.length === 1 ? new Set([this.fleet[0].id]) : new Set(['ALL']);
          }
          this._persistLocalOnly();
        } else if (this.fleet.length > 0) {
          API.saveFleet(this.fleet, Array.from(this.selectedTargets)).catch(() => {});
        }
      }
    } catch (e) {
      console.warn('从后端同步 Wi-Fi HTTP 机队失败:', e);
    }
  },

  _persistLocalOnly() {
    try {
      localStorage.setItem('g1_http_robot_fleet', JSON.stringify(this.fleet));
      localStorage.setItem('g1_custom_selected_targets', JSON.stringify(Array.from(this.selectedTargets)));
    } catch (_) { }
  },

  saveStoredFleet() {
    this._persistLocalOnly();
    if (typeof API !== 'undefined' && typeof API.saveFleet === 'function') {
      API.saveFleet(this.fleet, Array.from(this.selectedTargets)).catch(err => {
        console.warn('持久化保存 HTTP 机队配置失败:', err);
      });
    }
  },

  getTargetsMap() {
    const map = {};
    this.fleet.forEach(r => { map[r.id] = { ip: r.ip, port: r.port || 8090 }; });
    return map;
  },

  upsertRobotEndpoint(id, ip, port = 8090) {
    const cleanId = String(id || 'A').trim().toUpperCase();
    const cleanIp = String(ip || '').trim();
    const usePort = parseInt(port, 10) || 8090;
    const existing = this.fleet.find(r => r.id === cleanId);
    if (existing) {
      existing.ip = cleanIp;
      existing.port = usePort;
    } else {
      this.fleet.push({ id: cleanId, ip: cleanIp, port: usePort });
      if (this.fleet.length === 1) this.selectedTargets = new Set([cleanId]);
    }
    this.saveStoredFleet();
    this.renderTargetCards();
    this.refreshFleetHealth(false);
  },

  bindEvents() {
    const btnSelectAll = document.getElementById('btn-select-all-action');
    if (btnSelectAll) btnSelectAll.addEventListener('click', () => this.toggleSelectAll());

    const btnAddRobot = document.getElementById('btn-add-robot-action');
    if (btnAddRobot) btnAddRobot.addEventListener('click', () => this.openAddRobotModal());

    const btnScanLan = document.getElementById('btn-scan-http-robots');
    if (btnScanLan) btnScanLan.addEventListener('click', () => this.scanLanRobots());

    const btnProbeMotion = document.getElementById('btn-probe-motion-action');
    if (btnProbeMotion) btnProbeMotion.addEventListener('click', () => this.probeSelectedMotion());

    this.bindModalEvents();

    const clearLogBtn = document.getElementById('ctrl-clear-log-btn');
    if (clearLogBtn) {
      clearLogBtn.addEventListener('click', () => {
        const terminalEl = document.getElementById('ctrl-terminal-output');
        if (terminalEl) terminalEl.innerHTML = '';
        this.logTerminal('system', '[SYSTEM] 日志已清空。');
      });
    }

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
      customInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') doSend(); });
    }

    const refreshDanceBtn = document.getElementById('ctrl-refresh-dance-btn');
    if (refreshDanceBtn) {
      refreshDanceBtn.addEventListener('click', () => {
        const effective = this.getEffectiveSelectedRobots();
        if (effective.length === 0) {
          if (typeof showToast === 'function') showToast('请先在上方勾选受控机器人后再刷新动作列表', 'warning');
          this.renderUnselectedTargetState();
          return;
        }
        const targetStr = effective.join(',');
        this.logTerminal('system', `[HTTP DANCE] 正在通过 Wi-Fi HTTP 从 [${targetStr}] 拉取动作列表...`);
        this.fetchAndRenderDanceList(true, targetStr);
      });
    }

    this.bindCommandButtons();
  },

  async scanLanRobots() {
    const btn = document.getElementById('btn-scan-http-robots');
    if (btn) btn.disabled = true;
    this.logTerminal('system', '[HTTP SCAN] 正在并发扫描 Wi-Fi 局域网中在线的下位机 HTTP 服务 (端口 8090)...');
    try {
      const res = await API.scanLanHttpRobots('', 8090);
      const devices = (res && Array.isArray(res.devices)) ? res.devices : [];
      if (devices.length === 0) {
        this.logTerminal('error', `[HTTP SCAN] 未在网段 ${res?.subnet || '局域网'} 发现运行下位机 HTTP(8090) 的机器人，请确认已连入同一 Wi-Fi 或手动添加 IP。`);
        if (typeof showToast === 'function') showToast('未扫描到在线 Wi-Fi HTTP 机器人，可点击「+ 添加机器人」手动填入 IP', 'warning');
      } else {
        let added = 0;
        devices.forEach(dev => {
          const rid = (dev.robot_id && dev.robot_id !== 'UNCONFIGURED') ? dev.robot_id : this.getNextSuggestedId();
          const exists = this.fleet.find(r => r.ip === dev.ip);
          if (!exists) {
            this.fleet.push({ id: rid, ip: dev.ip, port: dev.port || 8090 });
            added++;
          } else {
            exists.port = dev.port || 8090;
          }
          this.healthMap[exists ? exists.id : rid] = { online: true, ip: dev.ip, port: dev.port || 8090, authority: dev.authority };
        });
        if (this.fleet.length === 1) this.selectedTargets = new Set([this.fleet[0].id]);
        else if (this.selectedTargets.size === 0 && this.fleet.length > 0) this.selectedTargets = new Set(['ALL']);
        this.saveStoredFleet();
        this.renderTargetCards();
        this.updateNavbarHttpStatus();
        this.logTerminal('rx', `[HTTP SCAN] 发现 ${devices.length} 台在线下位机（新增 ${added} 台）: ${devices.map(d => `${d.robot_id}@${d.ip}:${d.port}`).join(', ')}`);
        this.fetchAndRenderDanceList(true);
      }
    } catch (e) {
      this.logTerminal('error', `[HTTP SCAN] 局域网扫描异常: ${e.message || e}`);
    } finally {
      if (btn) btn.disabled = false;
    }
  },

  // --- 添加机器人模态弹窗 (ID + Wi-Fi 局域网 IP + 端口) ---
  bindModalEvents() {
    const modal = document.getElementById('modal-add-robot');
    const btnClose = document.getElementById('btn-close-add-robot-modal');
    const btnCancel = document.getElementById('btn-cancel-add-robot');
    const btnSubmit = document.getElementById('btn-submit-add-robot');
    const inputField = document.getElementById('input-new-robot-id');
    const ipField = document.getElementById('input-new-robot-ip');

    if (btnClose) btnClose.addEventListener('click', () => this.closeAddRobotModal());
    if (btnCancel) btnCancel.addEventListener('click', () => this.closeAddRobotModal());
    if (modal) modal.addEventListener('click', (e) => { if (e.target === modal) this.closeAddRobotModal(); });
    if (btnSubmit) btnSubmit.addEventListener('click', () => this.submitAddRobot());

    const onEnter = (e) => {
      if (e.key === 'Enter') { e.preventDefault(); this.submitAddRobot(); }
      else if (e.key === 'Escape') this.closeAddRobotModal();
    };
    if (inputField) {
      inputField.addEventListener('input', () => {
        const errEl = document.getElementById('add-robot-id-error');
        if (errEl && errEl.style.display !== 'none') this.validateInputId(true);
      });
      inputField.addEventListener('keydown', onEnter);
    }
    if (ipField) ipField.addEventListener('keydown', onEnter);
  },

  validateInputId(showIfInvalid = false) {
    const inputField = document.getElementById('input-new-robot-id');
    const errEl = document.getElementById('add-robot-id-error');
    if (!inputField) return { valid: false, error: '输入框未就绪' };
    const valResult = window.validateRobotId ? window.validateRobotId(inputField.value) : { valid: true, cleanId: inputField.value.trim().toUpperCase(), error: '' };
    if (!valResult.valid) {
      if (showIfInvalid) {
        if (errEl) { errEl.innerHTML = `⚠️ ${valResult.error}`; errEl.style.display = 'block'; }
        inputField.classList.add('input-invalid');
      }
      return valResult;
    }
    if (this.activeRobots.includes(valResult.cleanId)) {
      const dupError = `机器人 ID [${valResult.cleanId}] 已存在于受控列表中！`;
      if (showIfInvalid) {
        if (errEl) { errEl.innerHTML = `⚠️ ${dupError}`; errEl.style.display = 'block'; }
        inputField.classList.add('input-invalid');
      }
      return { valid: false, cleanId: valResult.cleanId, error: dupError };
    }
    if (errEl) { errEl.innerHTML = ''; errEl.style.display = 'none'; }
    inputField.classList.remove('input-invalid');
    return { valid: true, cleanId: valResult.cleanId, error: '' };
  },

  openAddRobotModal() {
    const modal = document.getElementById('modal-add-robot');
    const inputField = document.getElementById('input-new-robot-id');
    const ipField = document.getElementById('input-new-robot-ip');
    const chipsContainer = document.getElementById('add-robot-chips-container');
    if (!modal) return;

    this.validateInputId(false);
    if (inputField) inputField.value = this.getNextSuggestedId();
    if (ipField && !ipField.value.trim()) ipField.value = `192.168.50.${101 + this.fleet.length}`;

    if (chipsContainer) {
      chipsContainer.innerHTML = '';
      const suggestions = [];
      for (let i = 0; i < 26; i++) {
        const ch = String.fromCharCode(65 + i);
        if (!this.activeRobots.includes(ch)) {
          suggestions.push(ch);
          if (suggestions.length >= 4) break;
        }
      }
      suggestions.push(`R${this.fleet.length + 1}`, 'G1_02');
      suggestions.forEach(s => {
        const chip = document.createElement('button');
        chip.className = 'chip-btn';
        chip.textContent = `+${s}`;
        chip.type = 'button';
        chip.addEventListener('click', () => {
          if (inputField) { inputField.value = s; this.validateInputId(false); inputField.focus(); }
        });
        chipsContainer.appendChild(chip);
      });
    }

    modal.style.display = 'flex';
    setTimeout(() => { if (inputField) { inputField.focus(); inputField.select(); } }, 50);
  },

  closeAddRobotModal() {
    const modal = document.getElementById('modal-add-robot');
    this.validateInputId(false);
    if (modal) modal.style.display = 'none';
  },

  async submitAddRobot() {
    const inputField = document.getElementById('input-new-robot-id');
    const ipField = document.getElementById('input-new-robot-ip');
    const portField = document.getElementById('input-new-robot-port');
    if (!inputField) return;

    const valResult = this.validateInputId(true);
    if (!valResult.valid) {
      if (typeof showToast === 'function') showToast(valResult.error, 'error');
      inputField.focus();
      return;
    }
    const cleanId = valResult.cleanId;
    const ip = ipField ? ipField.value.trim() : '';
    const port = portField ? (parseInt(portField.value, 10) || 8090) : 8090;
    if (!ip) {
      if (typeof showToast === 'function') showToast('请输入机器人 Wi-Fi 局域网 IP 地址', 'warning');
      if (ipField) ipField.focus();
      return;
    }

    const isFirst = this.fleet.length === 0;
    this.fleet.push({ id: cleanId, ip, port });
    if (isFirst) {
      this.selectedTargets = new Set([cleanId]);
    } else if (this.selectedTargets.has('ALL')) {
      this.selectedTargets = new Set(this.activeRobots.filter(r => r !== cleanId));
    }
    this.saveStoredFleet();
    API.bindHttpRobot(cleanId, ip, port).catch(() => {});

    this.closeAddRobotModal();
    inputField.value = '';
    this.renderTargetCards();
    this.logTerminal('system', `[HTTP FLEET] 已添加机器人 [${cleanId}] -> http://${ip}:${port}`);
    await this.refreshFleetHealth(false);
    if (isFirst) {
      this.logSelectionChange();
    }
  },

  getNextSuggestedId() {
    for (let i = 0; i < 26; i++) {
      const c = String.fromCharCode(65 + i);
      if (!this.activeRobots.includes(c)) return c;
    }
    return `R${this.fleet.length + 1}`;
  },

  removeRobot(robotId) {
    this.fleet = this.fleet.filter(r => r.id !== robotId);
    delete this.healthMap[robotId];
    this.saveStoredFleet();

    this.selectedTargets.delete(robotId);
    if (this.fleet.length === 0) this.selectedTargets.clear();
    else if (this.selectedTargets.size === 0) this.selectedTargets = new Set([this.fleet[0].id]);

    this.renderTargetCards();
    this.updateNavbarHttpStatus();
    this.logTerminal('system', `[HTTP FLEET] 已移除机器人: [${robotId}] (当前共 ${this.fleet.length} 台)`);
    this.logSelectionChange();
  },

  getEffectiveSelectedRobots() {
    if (this.fleet.length === 0) return [];
    const ids = this.activeRobots;
    if (this.selectedTargets.has('ALL') || ids.every(r => this.selectedTargets.has(r))) return [...ids];
    return ids.filter(r => this.selectedTargets.has(r));
  },

  handleCardClick(robotId, isCtrlKey) {
    if (this.fleet.length === 0) return;
    const ids = this.activeRobots;
    if (isCtrlKey) {
      if (this.selectedTargets.has('ALL')) {
        this.selectedTargets = new Set(ids);
        this.selectedTargets.delete(robotId);
        if (this.selectedTargets.size === 0) this.selectedTargets = new Set([robotId]);
      } else if (this.selectedTargets.has(robotId)) {
        this.selectedTargets.delete(robotId);
      } else {
        this.selectedTargets.add(robotId);
        if (ids.length > 1 && ids.every(r => this.selectedTargets.has(r))) this.selectedTargets = new Set(['ALL']);
      }
    } else {
      this.selectedTargets = new Set([robotId]);
    }
    this.renderTargetCards();
    this.logSelectionChange();
  },

  toggleSelectAll() {
    if (this.fleet.length === 0) {
      this.logTerminal('system', '[TARGET] 当前尚未添加机器人，请先点击「+ 添加机器人」或「🔍 扫描局域网」');
      return;
    }
    const effective = this.getEffectiveSelectedRobots();
    if (effective.length === this.fleet.length) this.selectedTargets.clear();
    else this.selectedTargets = this.fleet.length === 1 ? new Set([this.fleet[0].id]) : new Set(['ALL']);
    this.renderTargetCards();
    this.logSelectionChange();
  },

  selectAll() {
    if (this.fleet.length === 0) return;
    this.selectedTargets = this.fleet.length === 1 ? new Set([this.fleet[0].id]) : new Set(['ALL']);
    this.renderTargetCards();
    this.logSelectionChange();
  },

  logSelectionChange() {
    this.logTerminal('system', `[TARGET] 控制目标已切换: ${this.getSelectionSummaryText()}`);
    if (this._danceSyncDebounceTimer) clearTimeout(this._danceSyncDebounceTimer);
    this._danceSyncDebounceTimer = setTimeout(() => {
      const effective = this.getEffectiveSelectedRobots();
      if (effective.length === 0) { this.renderUnselectedTargetState(); return; }
      this.fetchAndRenderDanceList(true, effective.join(','));
    }, 200);
  },

  getSelectionSummaryText() {
    if (this.fleet.length === 0) return '暂无机器人 (请先添加)';
    const eff = this.getEffectiveSelectedRobots();
    if (eff.length === 0) return '未选择机器 (请点击卡片勾选)';
    if (eff.length === 1) {
      const r = this.fleet.find(x => x.id === eff[0]);
      return `Robot ${eff[0]} (${r?.ip || '未配IP'})`;
    }
    if (eff.length === this.fleet.length) return `全选 [${eff.join(',')}] (共 ${eff.length} 台)`;
    return `多选 [${eff.join(',')}] (共 ${eff.length} 台)`;
  },

  getCommandPrefixText() {
    const eff = this.getEffectiveSelectedRobots();
    return eff.length === 0 ? 'HTTP|' : `${eff.join(',')}|`;
  },

  renderTargetCards() {
    const container = document.getElementById('ctrl-target-grid-container');
    if (!container) return;
    container.innerHTML = '';

    if (this.fleet.length === 0) {
      const emptyDiv = document.createElement('div');
      emptyDiv.className = 'empty-fleet-hint';
      emptyDiv.innerHTML = `
        <div class="empty-fleet-title">暂无在线机器人</div>
        <div class="empty-fleet-desc">点击右上角扫描或添加设备</div>
      `;
      container.appendChild(emptyDiv);
      const btnSelectAll = document.getElementById('btn-select-all-action');
      if (btnSelectAll) { btnSelectAll.disabled = true; btnSelectAll.innerHTML = '<span>👑</span> 全选'; }
      const summaryEl = document.getElementById('ctrl-selected-summary');
      if (summaryEl) summaryEl.textContent = '已选: 无';
      const prefixEl = document.getElementById('ctrl-active-target-prefix');
      if (prefixEl) prefixEl.textContent = 'HTTP|';
      return;
    }

    const effective = this.getEffectiveSelectedRobots();
    const isAllMode = effective.length === this.fleet.length;

    this.fleet.forEach((robot, index) => {
      const robotId = robot.id;
      const isSelected = effective.includes(robotId);
      const h = this.healthMap[robotId];
      const onlineTag = h ? (h.online ? `🟢 ${h.latency_ms ?? 0}ms` : '🔴 离线') : '⚪ 检测中';

      const card = document.createElement('div');
      card.className = `target-card ${isSelected ? 'active' : ''} ${h?.safety_locked ? 'safety-locked' : ''}`.trim();
      card.setAttribute('data-target', robotId);

      const topBar = document.createElement('div');
      topBar.className = 'target-card-top';
      const badge = document.createElement('div');
      badge.className = 'target-badge';

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'target-card-checkbox';
      checkbox.checked = isSelected;
      checkbox.addEventListener('click', (e) => { e.stopPropagation(); this.handleCardClick(robotId, true); });

      const labelSpan = document.createElement('span');
      labelSpan.textContent = `Robot ${robotId}`;
      badge.appendChild(checkbox);
      badge.appendChild(labelSpan);
      topBar.appendChild(badge);

      const removeBtn = document.createElement('button');
      removeBtn.className = 'btn-card-remove';
      removeBtn.innerHTML = '✕';
      removeBtn.title = `移除 Robot ${robotId}`;
      removeBtn.addEventListener('click', (e) => { e.stopPropagation(); this.removeRobot(robotId); });
      topBar.appendChild(removeBtn);

      const idDiv = document.createElement('div');
      idDiv.className = 'target-id';
      idDiv.style.fontSize = '1.05rem';
      idDiv.textContent = robot.ip ? `${robot.ip}:${robot.port || 8090}` : `T ${robotId} (未配IP)`;

      const desc = document.createElement('div');
      desc.className = 'target-desc';
      desc.innerHTML = `<span>${onlineTag}</span><span>Ctrl+${index + 1}</span>`;

      card.appendChild(topBar);
      card.appendChild(idDiv);
      card.appendChild(desc);

      if (h && h.online) {
        const stateRow = document.createElement('div');
        stateRow.className = 'robot-state-row';
        const modeTxt = h.active_dance ? `💃 ${h.active_dance}` : (h.motion_state || '');
        if (modeTxt) {
          const p = document.createElement('span');
          if (h.safety_locked) {
            p.className = 'fault-pill fatal';
          } else {
            const modeCls = ['GAIT', 'STAND'].includes(h.motion_state) ? 'ok' : '';
            p.className = `state-pill ${modeCls}`.trim();
          }
          p.textContent = modeTxt;
          stateRow.appendChild(p);
        }
        if (h.nav_input) {
          const np = document.createElement('span');
          np.className = `state-pill ${['READY', 'ACTIVE'].includes(h.nav_input) ? 'ok' : ''}`.trim();
          np.textContent = h.nav_input;
          stateRow.appendChild(np);
        }
        if (h.nav_status === 'FAILED') {
          const nfp = document.createElement('span');
          nfp.className = 'fault-pill fatal';
          nfp.textContent = `NAV:${h.nav_reason || 'FAILED'}`;
          stateRow.appendChild(nfp);
        }
        if (h.motion_udp_enabled) {
          const up = document.createElement('span');
          const reach = h.motion_udp && h.motion_udp.reachable === true;
          up.className = `state-pill ${reach ? 'ok' : 'warn'}`;
          up.textContent = reach ? 'UDP✓' : 'UDP✕';
          stateRow.appendChild(up);
        }
        (h.active_faults || []).forEach(f => {
          const fp = document.createElement('span');
          const fatal = f.level === 'ERROR' || f.level === 'FATAL';
          fp.className = `fault-pill ${fatal ? 'fatal' : 'warn'}`;
          fp.textContent = f.code || f.level || 'FAULT';
          stateRow.appendChild(fp);
        });
        if (stateRow.children.length > 0) card.appendChild(stateRow);
      }

      card.addEventListener('click', (e) => this.handleCardClick(robotId, e.ctrlKey || e.metaKey));
      container.appendChild(card);
    });

    const btnSelectAll = document.getElementById('btn-select-all-action');
    if (btnSelectAll) {
      btnSelectAll.disabled = false;
      btnSelectAll.className = isAllMode ? 'btn btn-primary btn-sm' : 'btn btn-secondary btn-sm';
      btnSelectAll.innerHTML = isAllMode ? '<span>👑</span> 取消全选' : '<span>👑</span> 全选';
    }
    const summaryEl = document.getElementById('ctrl-selected-summary');
    if (summaryEl) summaryEl.textContent = `已选: ${this.getSelectionSummaryText()}`;
    const prefixEl = document.getElementById('ctrl-active-target-prefix');
    if (prefixEl) prefixEl.textContent = this.getCommandPrefixText();
  },

  async probeSelectedMotion() {
    const effective = this.getEffectiveSelectedRobots();
    if (effective.length === 0) {
      if (typeof showToast === 'function') showToast('请先在上方选择机器人后再探测运控', 'warning');
      return;
    }
    const targetStr = effective.join(',');
    this.logTerminal('system', `[UDP PROBE] 正在探测 [${targetStr}] G1 运控 UDP 连通并同步状态...`);
    try {
      const res = await API.probeHttpMotion(targetStr, this.getTargetsMap());
      if (res && Array.isArray(res.results)) {
        res.results.forEach(r => this.logTerminal(r.ok ? 'rx' : 'error', `[UDP PROBE ${r.target}] ${r.msg || (r.ok ? '可达' : '超时')}`));
      } else {
        this.logTerminal(res?.ok ? 'rx' : 'error', `[UDP PROBE] ${res?.msg || '探测失败'}`);
      }
      await this.refreshFleetHealth(true);
    } catch (e) {
      this.logTerminal('error', `[UDP PROBE] 探测异常: ${e.message || e}`);
    }
  },

  _diffHealthChanges(prevMap, nextMap) {
    Object.entries(nextMap || {}).forEach(([tid, cur]) => {
      if (!cur || !cur.online) return;
      const prev = prevMap?.[tid];
      const prevMode = prev?.motion_state || '';
      if (cur.motion_state && prevMode && cur.motion_state !== prevMode) {
        const isLock = ['ESTOP', 'FAULT', 'MANUAL_OVERRIDE'].includes(cur.motion_state);
        this.logTerminal(isLock ? 'error' : 'rx', `[STATE ${tid}] ${prevMode} -> ${cur.motion_state}${cur.nav_input ? ` (${cur.nav_input})` : ''}`);
      }
      const prevCodes = new Map((prev?.active_faults || []).map(f => [f.code, f.level]));
      const nextCodes = new Map((cur.active_faults || []).map(f => [f.code, f.level]));
      nextCodes.forEach((lvl, code) => {
        if (!prevCodes.has(code)) {
          const fatal = lvl === 'FATAL' || lvl === 'ERROR';
          this.logTerminal(fatal ? 'error' : 'system', `[FAULT ${tid}] ${lvl}:${code}`);
          if (fatal && typeof showToast === 'function') showToast(`Robot ${tid} ${lvl}: ${code}`, 'error');
        }
      });
      prevCodes.forEach((_lvl, code) => {
        if (!nextCodes.has(code)) this.logTerminal('rx', `[FAULT CLEAR ${tid}] ${code} 已清除`);
      });
      if (cur.nav_status === 'FAILED' && (prev?.nav_status !== 'FAILED' || prev?.nav_reason !== cur.nav_reason)) {
        const reason = cur.nav_reason || 'FAILED';
        this.logTerminal('error', `[NAV FAIL ${tid}] ${reason}`);
        if (reason === 'LOC_LOST' && typeof showToast === 'function') showToast(`Robot ${tid} 定位丢失 (LOC_LOST)`, 'error');
      }
    });
  },

  scheduleHealthRefresh(delayMs = 350) {
    if (this._quickRefreshTimer) clearTimeout(this._quickRefreshTimer);
    this._quickRefreshTimer = setTimeout(() => {
      this._quickRefreshTimer = null;
      if (this.fleet.length > 0) this.refreshFleetHealth(true);
    }, delayMs);
  },

  // --- Wi-Fi 局域网 HTTP 健康轮询 ---
  startHttpHealthMonitor() {
    if (this.healthPollTimer) clearInterval(this.healthPollTimer);
    this.healthPollTimer = setInterval(() => {
      if (this.fleet.length > 0) this.refreshFleetHealth(true);
    }, 4000);
  },

  async refreshFleetHealth(silent = true) {
    if (this.fleet.length === 0) {
      this.updateNavbarHttpStatus();
      return;
    }
    try {
      const res = await API.checkHttpHealth(this.fleet);
      if (res && res.robots) {
        const prevMap = this.healthMap || {};
        this.healthMap = res.robots;
        this._diffHealthChanges(prevMap, res.robots);
        this.renderTargetCards();
        this.updateNavbarHttpStatus();
        if (!silent) {
          this.logTerminal('system', `[HTTP HEALTH] 局域网在线检测完成: ${res.online_count}/${res.total_count} 台在线`);
        }
      }
    } catch (_) {
      this.updateNavbarHttpStatus();
    }
  },

  updateNavbarHttpStatus() {
    const statusBadge = document.getElementById('ctrl-serial-status-badge');
    const statusText = document.getElementById('ctrl-serial-status-text');
    if (!statusBadge || !statusText) return;
    if (this.fleet.length === 0) {
      statusBadge.className = 'status-badge disconnected';
      statusText.textContent = 'HTTP 待添加';
      return;
    }
    const onlineCnt = Object.values(this.healthMap).filter(h => h && h.online).length;
    if (onlineCnt > 0) {
      statusBadge.className = 'status-badge connected';
      statusText.textContent = `HTTP 在线 (${onlineCnt}/${this.fleet.length})`;
    } else {
      statusBadge.className = 'status-badge disconnected';
      statusText.textContent = `HTTP 离线 (0/${this.fleet.length})`;
    }
  },

  // --- 纯 Wi-Fi 局域网 HTTP 指令下发 ---
  async sendCommand(commandStr) {
    if (!commandStr) return;
    const command = commandStr.trim().toUpperCase();
    const effective = this.getEffectiveSelectedRobots();
    if (effective.length === 0) {
      this.logTerminal('error', `[HTTP WARN] 未选中任何受控目标！请先添加或勾选机器人（拟下发: ${command}）`);
      return;
    }
    const target = effective.join(',');
    try {
      const res = await API.sendHttpCommand(target, command, '', null, this.getTargetsMap());
      if (res && res.success) {
        const list = Array.isArray(res.results) ? res.results : [];
        const hasReserved = list.some(r => r?.data?.execution_mode === 'RESERVED_SLOT');
        const tag = hasReserved ? ' [RESERVED_SLOT·待DDS挂载]' : '';
        if (res.all_ok === false && list.length > 0) {
          list.filter(r => r.ok).forEach(r => this.logTerminal('tx', `[HTTP TX] ${r.target}|${command} -> ${r.msg}`));
          list.filter(r => !r.ok).forEach(r => this.logTerminal('error', `[HTTP REJECT] ${r.target}|${command} -> ${r.msg}`));
        } else {
          this.logTerminal('tx', `[HTTP TX] ${target}|${command}${tag} -> ${res.msg || 'OK'}`);
        }
        const head = command.split(',')[0];
        if (['STAND', 'GAIT', 'PASSIVE', 'STOP', 'EMERGENCY', 'RELEASE', 'DANCE'].includes(head)) {
          this.scheduleHealthRefresh(350);
        }
      } else {
        this.logTerminal('error', `[HTTP FAIL] ${target}|${command} -> ${res?.msg || '下位机 HTTP 不可达'}`);
      }
    } catch (e) {
      this.logTerminal('error', `[HTTP ERROR] ${target}|${command}: ${e.message || e}`);
    }
  },

  // --- 双轨 5Hz 运控循环与按键绑定 ---
  tickMovementLoop() {
    if (this.activeTranslationKeys.size > 0) {
      const k = Array.from(this.activeTranslationKeys).pop();
      if (this.TRANSLATION_KEYS[k]) this.sendCommand(this.TRANSLATION_KEYS[k]);
    }
    if (this.activeRotationKeys.size > 0) {
      const k = Array.from(this.activeRotationKeys).pop();
      if (this.ROTATION_KEYS[k]) this.sendCommand(this.ROTATION_KEYS[k]);
    }
  },

  startMovementTimerIfNeeded() {
    this.tickMovementLoop();
    if (!this.movementTimer) this.movementTimer = setInterval(() => this.tickMovementLoop(), 200);
  },

  stopMovementTimerIfEmpty() {
    if (this.activeTranslationKeys.size === 0 && this.activeRotationKeys.size === 0) {
      if (this.movementTimer) { clearInterval(this.movementTimer); this.movementTimer = null; }
      document.querySelectorAll('.btn-cmd').forEach(btn => {
        const key = btn.getAttribute('data-key');
        if (key && (this.TRANSLATION_KEYS[key] || this.ROTATION_KEYS[key])) btn.classList.remove('key-active');
      });
      this.logTerminal('system', '[MOVEMENT] 松开移动/转向按键，通过 HTTP 下发停止指令 (STOP)');
      this.sendStopCommand(false);
    }
  },

  clearAllMovement() {
    this.activeTranslationKeys.clear();
    this.activeRotationKeys.clear();
    if (this.movementTimer) { clearInterval(this.movementTimer); this.movementTimer = null; }
    this.sendStopCommand(false);
  },

  // W-10: 停止/急停统一改走结构化端点 /api/http/stop（emergency 标志位），不再用自由文本 'STOP' 指令。
  // 该端点不接受 targets_map，多目标时逐台下发。
  async sendStopCommand(emergency = false) {
    const effective = this.getEffectiveSelectedRobots();
    if (effective.length === 0) {
      this.logTerminal('error', `[HTTP WARN] 未选中任何受控目标！请先添加或勾选机器人（拟下发: ${emergency ? '急停' : '停止'}）`);
      return;
    }
    const tmap = this.getTargetsMap();
    const results = await Promise.all(effective.map(async (tid) => {
      const ep = tmap && tmap[tid] ? tmap[tid] : {};
      try {
        const res = await API.stopHttpRobot(tid, emergency, ep.ip || '', ep.port || null);
        return { target: tid, ok: !!(res && res.success), msg: (res && res.msg) ? res.msg : (res && res.success ? 'OK' : '下位机 HTTP 不可达') };
      } catch (e) {
        return { target: tid, ok: false, msg: e.message || String(e) };
      }
    }));
    results.forEach(r => this.logTerminal(r.ok ? 'tx' : 'error', `[HTTP ${emergency ? 'ESTOP' : 'STOP'}] ${r.target} -> ${r.msg}`));
    this.scheduleHealthRefresh(350);
  },

  bindCommandButtons() {
    document.querySelectorAll('.tab-robot-control .btn-cmd').forEach(btn => {
      const key = btn.getAttribute('data-key');
      const cmd = btn.getAttribute('data-cmd');
      if (key && (this.TRANSLATION_KEYS[key] || this.ROTATION_KEYS[key])) {
        const onPress = (e) => {
          e.preventDefault();
          btn.classList.add('key-active');
          if (this.TRANSLATION_KEYS[key]) this.activeTranslationKeys.add(key);
          else this.activeRotationKeys.add(key);
          this.startMovementTimerIfNeeded();
        };
        const onRel = (e) => {
          e.preventDefault();
          btn.classList.remove('key-active');
          const wasActive = this.TRANSLATION_KEYS[key]
            ? this.activeTranslationKeys.delete(key)
            : this.activeRotationKeys.delete(key);
          if (!wasActive) return;
          this.stopMovementTimerIfEmpty();
        };
        btn.addEventListener('mousedown', onPress);
        btn.addEventListener('mouseup', onRel);
        btn.addEventListener('mouseleave', onRel);
        btn.addEventListener('touchstart', onPress);
        btn.addEventListener('touchend', onRel);
      } else {
        btn.addEventListener('click', () => {
          if (cmd) {
            // W-10: 停止/急停按钮 (data-cmd="STOP") 改走结构化端点 /api/http/stop (emergency=true)
            if (cmd === 'STOP') this.sendStopCommand(true);
            else this.sendCommand(cmd);
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
      if (e.ctrlKey && !e.shiftKey && !e.altKey) {
        if (['a', '0', 'g', '`'].includes(e.key.toLowerCase())) { e.preventDefault(); this.selectAll(); return; }
        const num = parseInt(e.key, 10);
        if (!isNaN(num) && num >= 1 && num <= this.fleet.length) {
          e.preventDefault();
          this.handleCardClick(this.fleet[num - 1].id, false);
          return;
        }
      }
      const k = e.key;
      if (this.TRANSLATION_KEYS[k]) { e.preventDefault(); if (e.repeat) return; this.activeTranslationKeys.add(k); this.highlightBtn(k); this.startMovementTimerIfNeeded(); return; }
      if (this.ROTATION_KEYS[k]) { e.preventDefault(); if (e.repeat) return; this.activeRotationKeys.add(k); this.highlightBtn(k); this.startMovementTimerIfNeeded(); return; }
      if (this.ONE_SHOT_KEYS[k]) {
        e.preventDefault();
        if (e.repeat) return;
        // W-10: X 键急停 (ONE_SHOT 'STOP') 改走结构化端点 /api/http/stop (emergency=true)
        if (this.ONE_SHOT_KEYS[k] === 'STOP') this.sendStopCommand(true);
        else this.sendCommand(this.ONE_SHOT_KEYS[k]);
        this.highlightBtn(k);
      }
    });
    document.addEventListener('keyup', (e) => {
      if (App.activeTab !== 'tab-robot-control') return;
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;
      const k = e.key;
      if (this.TRANSLATION_KEYS[k] || this.ROTATION_KEYS[k]) {
        e.preventDefault();
        this.activeTranslationKeys.delete(k);
        this.activeRotationKeys.delete(k);
        this.unhighlightBtn(k);
        this.stopMovementTimerIfEmpty();
      }
    });
    window.addEventListener('blur', () => {
      if (this.activeTranslationKeys.size > 0 || this.activeRotationKeys.size > 0 || this.movementTimer) this.clearAllMovement();
    });
  },

  highlightBtn(key) {
    document.querySelectorAll('.tab-robot-control .btn-cmd').forEach(b => {
      if (b.getAttribute('data-key') && b.getAttribute('data-key').toLowerCase() === key.toLowerCase()) b.classList.add('key-active');
    });
  },

  unhighlightBtn(key) {
    document.querySelectorAll('.tab-robot-control .btn-cmd').forEach(b => {
      if (b.getAttribute('data-key') && b.getAttribute('data-key').toLowerCase() === key.toLowerCase()) b.classList.remove('key-active');
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
    while (terminal.children.length > 200) terminal.removeChild(terminal.firstChild);
  },

  // --- 纯 Wi-Fi 局域网 HTTP 动作列表拉取与渲染 ---
  async fetchAndRenderDanceList(isForceRefresh = false, targetStr = null) {
    const countTag = document.getElementById('ctrl-dance-count-tag');
    if (!targetStr) {
      const effective = this.getEffectiveSelectedRobots();
      if (effective.length === 0) {
        this.currentDanceGroups = [];
        this.renderUnselectedTargetState();
        return;
      }
      targetStr = effective.join(',');
    }

    const reqId = ++this._danceRequestId;
    this.renderLoadingState(targetStr);
    if (countTag) countTag.textContent = `HTTP 正在拉取 [${targetStr}] 动作...`;

    try {
      const res = await API.getHttpDanceList(targetStr, this.getTargetsMap());
      if (reqId !== this._danceRequestId) return;
      if (res && res.success && Array.isArray(res.groups) && res.groups.length > 0) {
        this.currentDanceGroups = res.groups;
        const total = res.total_count || res.groups.reduce((acc, g) => acc + (g.items ? g.items.length : 0), 0);
        this.renderDanceGroups(res.groups, targetStr, total, res.per_robot_counts);
        this.logTerminal('rx', `[HTTP DANCE] 成功通过 Wi-Fi HTTP 从 [${targetStr}] 同步 ${total} 项动作`);
        return;
      }
      if (res && res.success && targetStr.includes(',')) {
        this.currentDanceGroups = [];
        this.renderNoCommonDancesState(targetStr, res.per_robot_counts);
        return;
      }
      this.renderNoDataState(targetStr, res?.msg || '下位机 HTTP 不可达');
    } catch (e) {
      if (reqId !== this._danceRequestId) return;
      this.logTerminal('error', `[HTTP DANCE] 动作列表拉取异常: ${e.message || e}`);
      this.renderNoDataState(targetStr, e.message || String(e));
    }
  },

  renderLoadingState(targetStr) {
    const container = document.getElementById('ctrl-dance-scroll-container');
    if (!container) return;
    container.innerHTML = `
      <div class="dance-status-card">
        <div class="dance-loading-spinner"></div>
        <div class="dance-status-title">正在同步 [${targetStr}] 动作列表...</div>
      </div>`;
  },

  renderUnselectedTargetState() {
    const container = document.getElementById('ctrl-dance-scroll-container');
    const countTag = document.getElementById('ctrl-dance-count-tag');
    if (countTag) countTag.textContent = '请选择目标';
    if (!container) return;
    container.innerHTML = `
      <div class="dance-status-card">
        <div class="dance-status-icon">🌐</div>
        <div class="dance-status-title">未选择控制目标</div>
        <div class="dance-status-desc">请在上方添加或勾选机器人后自动同步动作。</div>
      </div>`;
  },

  renderNoCommonDancesState(targetStr, perRobotCounts = null) {
    const container = document.getElementById('ctrl-dance-scroll-container');
    const countTag = document.getElementById('ctrl-dance-count-tag');
    if (countTag) countTag.textContent = `[${targetStr}] 无共有动作`;
    if (!container) return;
    let perInfo = '';
    if (perRobotCounts) {
      const parts = Object.entries(perRobotCounts).map(([k, v]) => `<b>Robot ${escapeHtml(k)}</b>: ${escapeHtml(v)} 首`);
      if (parts.length > 0) perInfo = `<div style="margin-top: 8px; font-size: 0.82rem; color: var(--accent-cyan);">${parts.join('  |  ')}</div>`;
    }
    container.innerHTML = `
      <div class="dance-status-card">
        <div class="dance-status-icon">🤝</div>
        <div class="dance-status-title">[${escapeHtml(targetStr)}] 无共有动作</div>
        <div class="dance-status-desc">所选设备动作交集为空。${perInfo}</div>
      </div>`;
  },

  renderNoDataState(targetStr, reason = '') {
    const container = document.getElementById('ctrl-dance-scroll-container');
    const countTag = document.getElementById('ctrl-dance-count-tag');
    if (countTag) countTag.textContent = `[${targetStr}] 未就绪`;
    if (!container) return;
    // W-6: reason 来自服务端响应/异常消息，必须转义后才能插入 innerHTML
    const safeReason = window.escapeHtml ? escapeHtml(reason) : String(reason || '');
    container.innerHTML = `
      <div class="dance-status-card">
        <div class="dance-status-icon">📡</div>
        <div class="dance-status-title">未获取到 [${escapeHtml(targetStr)}] 动作列表</div>
        <div class="dance-status-desc">
          ${safeReason ? `${safeReason} · ` : ''}请检查局域网连通性与下位机服务状态。
        </div>
      </div>`;
  },

  renderDanceGroups(groups, targetStr, totalCount = 0, perRobotCounts = null) {
    const container = document.getElementById('ctrl-dance-scroll-container');
    if (!container) return;
    container.innerHTML = '';
    let count = 0;

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
        count++;
        const btn = document.createElement('button');
        btn.className = 'btn-cmd btn-dance';
        btn.setAttribute('data-cmd', item.cmd || `DANCE,${item.alias}`);
        btn.title = `${item.name} (${item.alias}) - HTTP 目标: ${targetStr}`;
        btn.innerHTML = `<span class="dance-title"></span><span class="dance-code"></span>`;
        btn.querySelector('.dance-title').textContent = item.name;
        btn.querySelector('.dance-code').textContent = item.short_code || item.alias;
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
      countTag.textContent = targetStr.includes(',')
        ? `🟢 多机 HTTP 共有 (${count} 项)`
        : `🟢 [${targetStr}] HTTP 动作 (${count} 项)`;
    }
  }
};
