class App {
    constructor() {
        this.baseUrl = '';
        this.currentModalType = null;
        this.currentEditId = null;
        this.statusInterval = null;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadAttachments();
        this.loadSearchEngines();
        this.loadSkills();
        this.loadSkillHistory();
        this.startStatusPolling();
        this.loadVersion();
    }
    
    async loadVersion() {
        try {
            const response = await fetch(`${this.baseUrl}/api/version`);
            const result = await response.json();
            const versionEl = document.getElementById('version-number');
            if (versionEl && result.version) {
                versionEl.textContent = result.version;
            }
        } catch (error) {
            console.error('获取版本号失败:', error);
        }
    }

    setupEventListeners() {
        // 左侧导航切换
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const navBtn = e.target.closest('.nav-btn');
                if (navBtn && navBtn.dataset.tab) {
                    this.switchPanel(navBtn.dataset.tab);
                }
            });
        });

        // 模型相关
        document.getElementById('add-model-btn').addEventListener('click', () => this.openModelModal());
        document.getElementById('models-list').addEventListener('click', (e) => this.handleModelAction(e));

        // Agent相关
        document.getElementById('add-agent-btn').addEventListener('click', () => this.openAgentModal());
        document.getElementById('agents-list').addEventListener('click', (e) => this.handleAgentAction(e));

        // 搜索引擎相关
        document.getElementById('add-search-btn').addEventListener('click', () => this.openSearchModal());
        document.getElementById('search-list').addEventListener('click', (e) => this.handleSearchAction(e));
        document.getElementById('test-search-btn').addEventListener('click', () => this.testSearch());
        
        // Skills相关
        document.getElementById('open-skill-config-btn').addEventListener('click', () => this.openSkillConfigModal());
        document.getElementById('add-new-skill-btn').addEventListener('click', () => this.createNewSkill());
        document.getElementById('skills-list').addEventListener('click', (e) => this.handleSkillAction(e));
        
        // 快速搜索相关
        document.getElementById('quick-search-btn').addEventListener('click', () => this.quickSearch());
        document.getElementById('quick-search-clear-btn').addEventListener('click', () => this.clearQuickSearch());
        document.getElementById('quick-search-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.quickSearch();
        });

        // 附件相关
        document.getElementById('file-upload').addEventListener('change', (e) => this.uploadFiles(e));
        const attachmentsList = document.getElementById('attachments-list');
        if (attachmentsList) {
            attachmentsList.addEventListener('click', (e) => this.handleAttachmentAction(e));
        }
        document.getElementById('clear-attachments-btn').addEventListener('click', () => this.clearAttachments());

        // 设置相关
        document.getElementById('save-settings-btn').addEventListener('click', () => this.saveSettings());

        // 处理相关
        document.getElementById('start-btn').addEventListener('click', () => this.startProcessing());
        document.getElementById('stop-btn').addEventListener('click', () => this.stopProcessing());
        document.getElementById('clear-btn').addEventListener('click', () => this.clearAll());

        // 保存文档
        document.getElementById('save-btn').addEventListener('click', () => this.saveDocument());

        // 导出日志
        document.getElementById('export-log-btn').addEventListener('click', () => this.exportLogs());

        // 日志清空
        document.getElementById('clear-log-btn').addEventListener('click', () => this.clearLog());
        
        // 模型调用日志
        document.getElementById('model-calls-btn').addEventListener('click', () => this.showModelCallsDialog());

        // 预览切换
        document.querySelectorAll('.toggle-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.switchPreview(e.target.dataset.view));
        });

        // 最大化按钮
        document.querySelectorAll('.maximize-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.toggleMaximize(e.target.closest('.maximize-btn').dataset.target));
        });

        // 模态框
        document.getElementById('modal-close').addEventListener('click', () => this.closeModal());
        document.getElementById('modal-cancel').addEventListener('click', () => this.closeModal());
        document.getElementById('modal-save').addEventListener('click', () => this.saveModalData());
    }

    toggleSidebar() {
        const sidebar = document.querySelector('.sidebar');
        sidebar.classList.toggle('collapsed');
    }

    switchPanel(tabName) {
        // 切换左侧导航按钮状态
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.classList.remove('active');
            btn.style.background = 'transparent';
            btn.style.color = 'rgba(255,255,255,0.6)';
        });
        const activeBtn = document.querySelector(`.nav-btn[data-tab="${tabName}"]`);
        if (activeBtn) {
            activeBtn.classList.add('active');
            activeBtn.style.background = 'rgba(255,255,255,0.15)';
            activeBtn.style.color = 'white';
        }

        // 切换右侧面板显示
        document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));
        const targetPanel = document.getElementById(`${tabName}-panel`);
        if (targetPanel) {
            targetPanel.classList.add('active');
        }

        // 如果切换到搜索面板，加载搜索引擎列表
        if (tabName === 'search') {
            this.loadSearchEngines();
        }
        
        // 如果切换到模型面板，加载模型列表
        if (tabName === 'models') {
            this.loadModels();
        }
        
        // 如果切换到Agent面板，加载Agent列表
        if (tabName === 'agents') {
            this.loadAgents();
        }
        
        // 如果切换到Skills面板，加载Skills列表
        if (tabName === 'skills') {
            this.loadSkills();
        }
    }

    async loadAgents() {
        try {
            const response = await fetch(`${this.baseUrl}/api/agents`);
            const agents = await response.json();
            this.renderAgents(agents);
        } catch (error) {
            console.error('加载Agents失败:', error);
        }
    }

    renderAgents(agents) {
        const list = document.getElementById('agents-list');
        if (agents.length === 0) {
            list.innerHTML = '<p style="text-align: center; color: #94a3b8; padding: 20px;">暂无Agent</p>';
            return;
        }

        list.innerHTML = agents.map(agent => `
            <div class="config-card" data-id="${agent.id}">
                <div class="card-header">
                    <span class="card-title">${agent.name}</span>
                    <div class="card-actions">
                        <button class="action-btn edit-btn" title="编辑">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="action-btn delete-btn" title="删除">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
                <div class="card-body">
                    <div class="badge-row">
                        <span class="badge badge-info">${agent.model_id || '未绑定'}</span>
                        ${agent.enabled ? '<span class="badge badge-success">已启用</span>' : '<span class="badge badge-warning">已禁用</span>'}
                    </div>
                </div>
            </div>
        `).join('');
    }

    async loadModels() {
        // 模型列表通过后端模板渲染，暂不需要动态加载
        // 如果需要动态加载，可以取消下面的注释
        // try {
        //     const response = await fetch(`${this.baseUrl}/api/models`);
        //     const models = await response.json();
        //     this.renderModels(models);
        // } catch (error) {
        //     console.error('加载模型失败:', error);
        // }
    }

    async loadAttachments() {
        try {
            const response = await fetch(`${this.baseUrl}/api/attachments`);
            const files = await response.json();
            this.renderAttachments(files);
        } catch (error) {
            console.error('加载附件失败:', error);
        }
    }

    async loadSearchEngines() {
        try {
            const response = await fetch(`${this.baseUrl}/api/search_engines`);
            const engines = await response.json();
            this.renderSearchEngines(engines);
        } catch (error) {
            console.error('加载搜索引擎失败:', error);
        }
    }

    async loadSkills() {
        try {
            const response = await fetch(`${this.baseUrl}/api/skills`);
            const data = await response.json();
            this.renderSkills(data.skills);
            this.renderSkillConfigList(data.skills);
        } catch (error) {
            console.error('加载Skills失败:', error);
        }
    }

    async loadSkillHistory() {
        // Skill历史记录功能预留
        console.log('Skill历史记录加载');
    }

    renderSkills(skills) {
        const container = document.getElementById('skills-list');
        if (!container) return;
        
        container.innerHTML = skills.map(skill => `
            <div class="config-item" data-id="${skill.id}">
                <div class="config-header">
                    <span class="config-name">
                        <i class="${skill.icon}"></i>
                        ${skill.name}
                    </span>
                    <div class="config-actions">
                        <button class="action-btn execute-btn" title="执行" onclick="app.executeSkillDirectly('${skill.id}')">
                            <i class="fas fa-play"></i>
                        </button>
                    </div>
                </div>
                <div class="config-details">
                    <span class="badge badge-info">${skill.skill_type}</span>
                    <span class="badge badge-secondary">${skill.executor}</span>
                    ${skill.enabled ? 
                        '<span class="badge badge-success">已启用</span>' : 
                        '<span class="badge badge-warning">已禁用</span>'
                    }
                </div>
                <div class="config-description" style="font-size: 12px; color: #64748b; margin-top: 5px;">
                    ${skill.description}
                </div>
            </div>
        `).join('');
    }

    async handleSkillAction(event) {
        const item = event.target.closest('.config-item');
        if (!item) return;

        const skillId = item.dataset.id;

        // 点击执行按钮
        if (event.target.closest('.execute-btn')) {
            this.executeSkillDirectly(skillId);
            return;
        }

        // 点击编辑按钮或技能项本身，打开编辑弹窗
        if (event.target.closest('.edit-btn') || event.target.closest('.config-item')) {
            this.openSkillConfigModal();
            this.editSkillInModal(skillId);
        }
    }

    renderSkillConfigList(skills) {
        const container = document.getElementById('skill-config-list');
        if (!container) return;
        
        container.innerHTML = skills.map(skill => `
            <div class="config-item ${skill.enabled ? '' : 'disabled'}" data-id="${skill.id}" 
                 onclick="app.editSkillInModal('${skill.id}')" style="cursor: pointer;">
                <div class="config-header">
                    <span class="config-name">
                        <i class="${skill.icon}"></i>
                        ${skill.name}
                    </span>
                    <span class="badge badge-${skill.enabled ? 'success' : 'warning'}" style="font-size: 10px;">
                        ${skill.enabled ? '启用' : '禁用'}
                    </span>
                </div>
                <div style="font-size: 11px; color: #64748b; margin-top: 5px;">
                    ${skill.executor} · ${skill.skill_type}
                </div>
            </div>
        `).join('');
    }

    openSkillConfigModal() {
        const modal = document.getElementById('skill-config-modal');
        if (modal) {
            modal.style.display = 'flex';
            this.loadSkillsForConfig();
        }
    }

    async loadSkillsForConfig() {
        try {
            const response = await fetch(`${this.baseUrl}/api/skills`);
            const data = await response.json();
            this.renderSkillConfigList(data.skills);
        } catch (error) {
            console.error('加载Skills失败:', error);
        }
    }

    async editSkillInModal(skillId) {
        const skill = await this.getSkill(skillId);
        if (!skill) return;
        
        const editorArea = document.getElementById('skill-editor-area');
        
        editorArea.innerHTML = `
            <div style="margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <h4><i class="${skill.icon}"></i> 编辑 Skill</h4>
                    <div style="display: flex; gap: 10px;">
                        <button class="btn btn-primary btn-sm" onclick="app.saveSkill('${skill.id}')">
                            <i class="fas fa-save"></i> 保存
                        </button>
                        <button class="btn btn-danger btn-sm" onclick="app.deleteSkill('${skill.id}')">
                            <i class="fas fa-trash"></i> 删除
                        </button>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>名称</label>
                    <input type="text" id="skill-edit-name" class="form-control" value="${skill.name}">
                </div>
                
                <div class="form-group">
                    <label>描述</label>
                    <textarea id="skill-edit-description" class="form-control" rows="2">${skill.description || ''}</textarea>
                </div>
                
                <div style="display: flex; gap: 15px;">
                    <div class="form-group" style="flex: 1;">
                        <label>类型</label>
                        <select id="skill-edit-type" class="form-control">
                            <option value="search" ${skill.skill_type === 'search' ? 'selected' : ''}>搜索</option>
                            <option value="analysis" ${skill.skill_type === 'analysis' ? 'selected' : ''}>分析</option>
                            <option value="generation" ${skill.skill_type === 'generation' ? 'selected' : ''}>生成</option>
                            <option value="transform" ${skill.skill_type === 'transform' ? 'selected' : ''}>转换</option>
                            <option value="validation" ${skill.skill_type === 'validation' ? 'selected' : ''}>验证</option>
                            <option value="custom" ${skill.skill_type === 'custom' ? 'selected' : ''}>自定义</option>
                        </select>
                    </div>
                    
                    <div class="form-group" style="flex: 1;">
                        <label>执行器</label>
                        <select id="skill-edit-executor" class="form-control">
                            <option value="search" ${skill.executor === 'search' ? 'selected' : ''}>搜索引擎</option>
                            <option value="llm" ${skill.executor === 'llm' ? 'selected' : ''}>AI模型</option>
                            <option value="script" ${skill.executor === 'script' ? 'selected' : ''}>脚本</option>
                            <option value="api" ${skill.executor === 'api' ? 'selected' : ''}>API调用</option>
                        </select>
                    </div>
                    
                    <div class="form-group" style="flex: 0 0 100px;">
                        <label>启用</label>
                        <div style="padding-top: 8px;">
                            <input type="checkbox" id="skill-edit-enabled" ${skill.enabled ? 'checked' : ''}>
                        </div>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>图标 (FontAwesome类名)</label>
                    <input type="text" id="skill-edit-icon" class="form-control" value="${skill.icon}" placeholder="fas fa-cog">
                </div>
                
                <div class="form-group">
                    <label>提示模板 (使用{变量名}作为占位符)</label>
                    <textarea id="skill-edit-prompt" class="form-control" rows="4" placeholder="请输入提示模板...">${skill.prompt_template || ''}</textarea>
                </div>
                
                <div class="form-group">
                    <label>标签 (用逗号分隔)</label>
                    <input type="text" id="skill-edit-tags" class="form-control" value="${(skill.tags || []).join(', ')}" placeholder="标签1, 标签2">
                </div>
            </div>
        `;
    }

    async saveSkill(skillId) {
        const skillData = {
            name: document.getElementById('skill-edit-name').value,
            description: document.getElementById('skill-edit-description').value,
            skill_type: document.getElementById('skill-edit-type').value,
            executor: document.getElementById('skill-edit-executor').value,
            enabled: document.getElementById('skill-edit-enabled').checked,
            icon: document.getElementById('skill-edit-icon').value,
            prompt_template: document.getElementById('skill-edit-prompt').value,
            tags: document.getElementById('skill-edit-tags').value.split(',').map(t => t.trim()).filter(t => t)
        };
        
        try {
            const response = await fetch(`${this.baseUrl}/api/skills/${skillId}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(skillData)
            });
            
            const data = await response.json();
            if (data.status === 'success') {
                alert('保存成功');
                await this.loadSkillsForConfig();
                await this.loadSkills();
            } else {
                alert('保存失败: ' + data.message);
            }
        } catch (error) {
            alert('保存失败: ' + error.message);
        }
    }

    createNewSkill() {
        const editorArea = document.getElementById('skill-editor-area');
        
        editorArea.innerHTML = `
            <div style="margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <h4><i class="fas fa-plus"></i> 新建 Skill</h4>
                    <button class="btn btn-primary btn-sm" onclick="app.saveNewSkill()">
                        <i class="fas fa-save"></i> 创建
                    </button>
                </div>
                
                <div class="form-group">
                    <label>名称 <span style="color: red;">*</span></label>
                    <input type="text" id="skill-new-name" class="form-control" placeholder="Skill名称">
                </div>
                
                <div class="form-group">
                    <label>描述</label>
                    <textarea id="skill-new-description" class="form-control" rows="2" placeholder="描述这个Skill的功能..."></textarea>
                </div>
                
                <div style="display: flex; gap: 15px;">
                    <div class="form-group" style="flex: 1;">
                        <label>类型</label>
                        <select id="skill-new-type" class="form-control">
                            <option value="search">搜索</option>
                            <option value="analysis">分析</option>
                            <option value="generation" selected>生成</option>
                            <option value="transform">转换</option>
                            <option value="validation">验证</option>
                            <option value="custom">自定义</option>
                        </select>
                    </div>
                    
                    <div class="form-group" style="flex: 1;">
                        <label>执行器</label>
                        <select id="skill-new-executor" class="form-control">
                            <option value="search">搜索引擎</option>
                            <option value="llm" selected>AI模型</option>
                            <option value="script">脚本</option>
                            <option value="api">API调用</option>
                        </select>
                    </div>
                    
                    <div class="form-group" style="flex: 0 0 100px;">
                        <label>启用</label>
                        <div style="padding-top: 8px;">
                            <input type="checkbox" id="skill-new-enabled" checked>
                        </div>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>图标 (FontAwesome类名)</label>
                    <input type="text" id="skill-new-icon" class="form-control" value="fas fa-cog" placeholder="fas fa-cog">
                </div>
                
                <div class="form-group">
                    <label>提示模板 (使用{变量名}作为占位符)</label>
                    <textarea id="skill-new-prompt" class="form-control" rows="4" placeholder="请处理以下内容：\n{content}"></textarea>
                </div>
                
                <div class="form-group">
                    <label>标签 (用逗号分隔)</label>
                    <input type="text" id="skill-new-tags" class="form-control" placeholder="标签1, 标签2">
                </div>
            </div>
        `;
    }

    async saveNewSkill() {
        const name = document.getElementById('skill-new-name').value.trim();
        if (!name) {
            alert('请输入Skill名称');
            return;
        }
        
        const skillData = {
            name: name,
            description: document.getElementById('skill-new-description').value,
            skill_type: document.getElementById('skill-new-type').value,
            executor: document.getElementById('skill-new-executor').value,
            enabled: document.getElementById('skill-new-enabled').checked,
            icon: document.getElementById('skill-new-icon').value || 'fas fa-cog',
            prompt_template: document.getElementById('skill-new-prompt').value,
            tags: document.getElementById('skill-new-tags').value.split(',').map(t => t.trim()).filter(t => t),
            parameters: [],
            input_type: 'text',
            output_type: 'text'
        };
        
        try {
            const response = await fetch(`${this.baseUrl}/api/skills`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(skillData)
            });
            
            const data = await response.json();
            if (data.status === 'success') {
                alert('创建成功');
                await this.loadSkillsForConfig();
                await this.loadSkills();
            } else {
                alert('创建失败: ' + data.message);
            }
        } catch (error) {
            alert('创建失败: ' + error.message);
        }
    }

    async openSkillExecuteModal(skillId) {
        const skill = await this.getSkill(skillId);
        if (!skill) {
            alert('获取Skill信息失败');
            return;
        }

        currentExecuteSkillId = skillId;
        document.getElementById('skill-execute-title').innerHTML = `<i class="fas fa-play"></i> 执行: ${skill.name}`;

        const form = document.getElementById('skill-execute-form');

        if (!skill.parameters || skill.parameters.length === 0) {
            // 如果没有参数，显示提示
            form.innerHTML = `
                <div style="text-align: center; padding: 20px; color: #64748b;">
                    <p>此Skill没有可配置参数</p>
                    <p style="font-size: 12px; margin-top: 10px;">直接点击"执行"按钮即可运行</p>
                </div>
            `;
        } else {
            // 生成参数表单
            form.innerHTML = skill.parameters.map(param => {
                const defaultValue = param.default !== null && param.default !== undefined ? param.default : '';
                const requiredMark = param.required ? '<span style="color: red;">*</span>' : '';

                if (param.type === 'boolean') {
                    return `
                        <div class="form-group">
                            <label>
                                <input type="checkbox" name="${param.name}" ${defaultValue ? 'checked' : ''}>
                                ${param.description || param.name}
                            </label>
                        </div>
                    `;
                } else if (param.type === 'select' && param.options && param.options.length > 0) {
                    return `
                        <div class="form-group">
                            <label>${param.description || param.name} ${requiredMark}</label>
                            <select name="${param.name}" class="form-control">
                                ${param.options.map(opt => `
                                    <option value="${opt}" ${opt === defaultValue ? 'selected' : ''}>${opt}</option>
                                `).join('')}
                            </select>
                        </div>
                    `;
                } else if (param.type === 'textarea') {
                    return `
                        <div class="form-group">
                            <label>${param.description || param.name} ${requiredMark}</label>
                            <textarea name="${param.name}" class="form-control" rows="4" placeholder="请输入...">${defaultValue}</textarea>
                        </div>
                    `;
                } else {
                    const inputType = param.type === 'number' ? 'number' : 'text';
                    const stepAttr = param.type === 'number' ? 'step="any"' : '';
                    return `
                        <div class="form-group">
                            <label>${param.description || param.name} ${requiredMark}</label>
                            <input type="${inputType}" name="${param.name}" class="form-control" value="${defaultValue}" ${stepAttr} placeholder="请输入...">
                        </div>
                    `;
                }
            }).join('');
        }

        document.getElementById('skill-execute-modal').style.display = 'flex';
    }

    async executeSkill(skillId, params) {
        try {
            const response = await fetch(`${this.baseUrl}/api/skills/${skillId}/execute`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({params: params})
            });

            const data = await response.json();

            if (data.result && data.result.success) {
                this.showSkillResult(data.result);
            } else {
                alert('执行失败: ' + (data.result?.error || data.message || '未知错误'));
            }
        } catch (error) {
            alert('执行失败: ' + error.message);
        }
    }

    showSkillResult(result) {
        const resultModal = document.createElement('div');
        resultModal.className = 'modal';
        resultModal.style.display = 'flex';
        resultModal.innerHTML = `
            <div class="modal-content" style="width: 700px; max-width: 90%; max-height: 80vh;">
                <div class="modal-header">
                    <h3><i class="fas fa-check-circle" style="color: #22c55e;"></i> 执行成功</h3>
                    <button class="modal-close" onclick="this.closest('.modal').remove()">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="modal-body" style="max-height: calc(80vh - 120px); overflow-y: auto;">
                    <div style="margin-bottom: 15px; padding: 10px; background: #f0fdf4; border-radius: 8px;">
                        <span style="color: #64748b;">执行时间:</span> <strong>${result.execution_time?.toFixed(2) || 0}秒</span>
                        &nbsp;&nbsp;
                        <span style="color: #64748b;">Token:</span> <strong>${result.tokens_used || 0}</strong>
                    </div>
                    <div style="background: #f8fafc; padding: 15px; border-radius: 8px; white-space: pre-wrap; word-break: break-all;">${result.output || '无输出'}</div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-primary" onclick="this.closest('.modal').remove()">关闭</button>
                </div>
            </div>
        `;
        document.body.appendChild(resultModal);
    }

    async executeSkillDirectly(skillId) {
        this.openSkillExecuteModal(skillId);
    }

    async getSkill(skillId) {
        try {
            const response = await fetch(`${this.baseUrl}/api/skills/${skillId}`);
            const data = await response.json();
            return data.skill;
        } catch (error) {
            console.error('获取Skill失败:', error);
            return null;
        }
    }

    async deleteSkill(skillId) {
        if (!confirm('确定删除此Skill?')) return;
        
        try {
            const response = await fetch(`${this.baseUrl}/api/skills/${skillId}`, {
                method: 'DELETE'
            });
            
            const data = await response.json();
            if (data.status === 'success') {
                alert('删除成功');
                await this.loadSkillsForConfig();
                await this.loadSkills();
                document.getElementById('skill-editor-area').innerHTML = `
                    <div style="text-align: center; color: #94a3b8; padding: 50px;">
                        <i class="fas fa-mouse-pointer" style="font-size: 48px; margin-bottom: 15px;"></i>
                        <p>点击左侧列表中的Skill进行编辑</p>
                        <p>或点击"新建"创建新的Skill</p>
                    </div>
                `;
            } else {
                alert('删除失败: ' + data.message);
            }
        } catch (error) {
            alert('删除失败: ' + error.message);
        }
    }

    renderAttachments(files) {
        const list = document.getElementById('attachments-list');
        const miniList = document.getElementById('attachments-mini');
        
        // 工具栏中的小附件显示
        if (miniList) {
            if (files.length === 0) {
                miniList.innerHTML = '';
            } else {
                miniList.innerHTML = files.map(file => `
                    <span class="attachment-tag" style="background: #e2e8f0; padding: 4px 10px; border-radius: 12px; font-size: 12px; color: #475569; display: flex; align-items: center; gap: 4px;">
                        <i class="fas fa-paperclip" style="font-size: 10px;"></i>
                        ${file.length > 15 ? file.substring(0, 15) + '...' : file}
                    </span>
                `).join('');
            }
        }
        
        // 旧列表保持兼容
        if (list) {
            if (files.length === 0) {
                list.innerHTML = '<p style="text-align: center; color: #94a3b8; padding: 20px;">暂无附件</p>';
                return;
            }

            list.innerHTML = files.map(file => `
                <div class="config-item" data-filename="${file}">
                    <div class="config-header">
                        <span class="config-name">${file}</span>
                        <button class="action-btn delete-btn" title="删除">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `).join('');
        }
    }

    renderSearchEngines(engines) {
        const list = document.getElementById('search-list');
        if (engines.length === 0) {
            list.innerHTML = '<p style="text-align: center; color: #94a3b8; padding: 20px;">暂无搜索引擎</p>';
            return;
        }

        list.innerHTML = engines.map(engine => `
            <div class="config-card" data-id="${engine.id}">
                <div class="card-header">
                    <span class="card-title">${engine.name}</span>
                    <div class="card-actions">
                        <button class="action-btn edit-btn" title="编辑">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="action-btn delete-btn" title="删除">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
                <div class="card-body">
                    <div class="badge-row">
                        <span class="badge badge-info">${engine.adapter_type}</span>
                        ${engine.enabled ? '<span class="badge badge-success">已启用</span>' : '<span class="badge badge-warning">已禁用</span>'}
                    </div>
                </div>
            </div>
        `).join('');
    }

    async uploadFiles(event) {
        const files = event.target.files;
        if (!files.length) return;

        for (const file of files) {
            const formData = new FormData();
            formData.append('file', file);

            try {
                const response = await fetch(`${this.baseUrl}/api/attachments/upload`, {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.addLog(`附件上传成功: ${result.filename}`);
                } else {
                    this.addLog(`附件上传失败: ${result.message}`);
                }
            } catch (error) {
                this.addLog(`上传失败: ${error.message}`);
            }
        }

        await this.loadAttachments();
        event.target.value = '';
    }

    async handleAttachmentAction(event) {
        const deleteBtn = event.target.closest('.delete-btn');
        if (deleteBtn) {
            const item = deleteBtn.closest('.config-item');
            const filename = item.dataset.filename;

            if (confirm(`确定要删除附件 "${filename}" 吗？`)) {
                try {
                    const response = await fetch(`${this.baseUrl}/api/attachments/${filename}`, {
                        method: 'DELETE'
                    });
                    const result = await response.json();
                    
                    if (result.status === 'success') {
                        this.addLog(`附件已删除: ${filename}`);
                        await this.loadAttachments();
                    }
                } catch (error) {
                    this.addLog(`删除失败: ${error.message}`);
                }
            }
        }
    }

    async clearAttachments() {
        if (confirm('确定要清空所有附件吗？')) {
            try {
                const response = await fetch(`${this.baseUrl}/api/attachments/clear`, {
                    method: 'POST'
                });
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.addLog(result.message);
                    await this.loadAttachments();
                }
            } catch (error) {
                this.addLog(`清空失败: ${error.message}`);
            }
        }
    }

    openModelModal(model = null) {
        this.currentModalType = 'model';
        this.currentEditId = model?.id || null;

        document.getElementById('modal-title').textContent = model ? '编辑模型' : '添加模型';
        document.querySelector('.model-fields').style.display = 'block';
        document.querySelector('.agent-fields').style.display = 'none';
        document.querySelector('.search-fields').style.display = 'none';

        // 填充表单
        document.getElementById('form-id').value = model?.id || '';
        document.getElementById('form-name').value = model?.name || '';
        document.getElementById('form-api-type').value = model?.api_type || 'openai';
        document.getElementById('form-api-url').value = model?.api_url || '';
        document.getElementById('form-api-key').value = model?.api_key || '';
        document.getElementById('form-model-name').value = model?.model_name || '';
        document.getElementById('form-enabled').checked = model?.enabled !== false;

        document.getElementById('modal').classList.add('active');
    }

    openAgentModal(agent = null) {
        this.currentModalType = 'agent';
        this.currentEditId = agent?.id || null;

        document.getElementById('modal-title').textContent = agent ? '编辑Agent' : '添加Agent';
        document.querySelector('.model-fields').style.display = 'none';
        document.querySelector('.agent-fields').style.display = 'block';
        document.querySelector('.search-fields').style.display = 'none';

        // 填充表单
        document.getElementById('form-id').value = agent?.id || '';
        document.getElementById('form-name').value = agent?.name || '';
        document.getElementById('form-role-description').value = agent?.role_description || '';
        document.getElementById('form-model-id').value = agent?.model_id || '';
        document.getElementById('form-enabled').checked = agent?.enabled !== false;

        document.getElementById('modal').classList.add('active');
    }

    openSearchModal(engine = null) {
        this.currentModalType = 'search';
        this.currentEditId = engine?.id || null;

        document.getElementById('modal-title').textContent = engine ? '编辑搜索引擎' : '添加搜索引擎';
        document.querySelector('.model-fields').style.display = 'none';
        document.querySelector('.agent-fields').style.display = 'none';
        document.querySelector('.search-fields').style.display = 'block';

        // 填充表单
        document.getElementById('form-id').value = engine?.id || '';
        document.getElementById('form-name').value = engine?.name || '';
        document.getElementById('form-adapter-type').value = engine?.adapter_type || 'bing';
        document.getElementById('form-api-key-search').value = engine?.api_key || '';
        // 添加API URL字段（如果引擎有的话）
        const apiUrlInput = document.getElementById('form-search-api-url');
        if (apiUrlInput) {
            apiUrlInput.value = engine?.api_url || '';
        }
        document.getElementById('form-enabled').checked = engine?.enabled !== false;

        document.getElementById('modal').classList.add('active');
    }

    closeModal() {
        document.getElementById('modal').classList.remove('active');
        document.getElementById('modal-form').reset();
        this.currentModalType = null;
        this.currentEditId = null;
    }

    async saveModalData() {
        const data = {
            name: document.getElementById('form-name').value,
            enabled: document.getElementById('form-enabled').checked
        };

        if (this.currentModalType === 'model') {
            data.api_type = document.getElementById('form-api-type').value;
            data.api_url = document.getElementById('form-api-url').value;
            data.api_key = document.getElementById('form-api-key').value;
            data.model_name = document.getElementById('form-model-name').value;
        } else if (this.currentModalType === 'agent') {
            data.role_description = document.getElementById('form-role-description').value;
            data.model_id = document.getElementById('form-model-id').value;
        } else if (this.currentModalType === 'search') {
            data.adapter_type = document.getElementById('form-adapter-type').value;
            data.api_key = document.getElementById('form-api-key-search').value;
            const apiUrlInput = document.getElementById('form-search-api-url');
            data.api_url = apiUrlInput ? apiUrlInput.value : '';
        }

        try {
            let response;
            // 确定API端点路径
            const endpoint = this.currentModalType === 'search' ? 'search_engines' : `${this.currentModalType}s`;
            
            if (this.currentEditId) {
                // 更新
                response = await fetch(`${this.baseUrl}/api/${endpoint}/${this.currentEditId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
            } else {
                // 创建
                response = await fetch(`${this.baseUrl}/api/${endpoint}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
            }

            const result = await response.json();
            if (result.status === 'success') {
                this.addLog(result.message);
                // 保存后不跳转，只关闭弹窗并刷新当前面板
                this.closeModal();
                if (this.currentModalType === 'model') {
                    this.loadModels();
                } else if (this.currentModalType === 'agent') {
                    this.loadAgents();
                } else if (this.currentModalType === 'search') {
                    this.loadSearchEngines();
                } else if (this.currentModalType === 'skill') {
                    this.loadSkills();
                }
            } else {
                alert(result.message);
            }
        } catch (error) {
            alert(`保存失败: ${error.message}`);
        }
    }

    async handleModelAction(event) {
        const item = event.target.closest('.config-card');
        if (!item) return;

        const modelId = item.dataset.id;

        if (event.target.closest('.edit-btn')) {
            // 编辑模型
            try {
                const response = await fetch(`${this.baseUrl}/api/models`);
                const models = await response.json();
                const model = models.find(m => m.id === modelId);
                if (model) {
                    this.openModelModal(model);
                }
            } catch (error) {
                console.error('获取模型失败:', error);
            }
        } else if (event.target.closest('.delete-btn')) {
            // 删除模型
            if (confirm('确定要删除这个模型吗？')) {
                try {
                    const response = await fetch(`${this.baseUrl}/api/models/${modelId}`, {
                        method: 'DELETE'
                    });
                    const result = await response.json();
                    
                    if (result.status === 'success') {
                        this.addLog(result.message);
                        this.loadModels();
                    }
                } catch (error) {
                    alert(`删除失败: ${error.message}`);
                }
            }
        } else if (event.target.closest('.test-btn')) {
            // 测试连接
            this.testModelConnection(modelId);
        }
    }

    async handleAgentAction(event) {
        const item = event.target.closest('.config-card');
        if (!item) return;

        const agentId = item.dataset.id;

        if (event.target.closest('.edit-btn')) {
            // 编辑Agent
            try {
                const response = await fetch(`${this.baseUrl}/api/agents`);
                const agents = await response.json();
                const agent = agents.find(a => a.id === agentId);
                if (agent) {
                    this.openAgentModal(agent);
                }
            } catch (error) {
                console.error('获取Agent失败:', error);
            }
        } else if (event.target.closest('.delete-btn')) {
            // 删除Agent
            if (confirm('确定要删除这个Agent吗？')) {
                try {
                    const response = await fetch(`${this.baseUrl}/api/agents/${agentId}`, {
                        method: 'DELETE'
                    });
                    const result = await response.json();
                    
                    if (result.status === 'success') {
                        this.addLog(result.message);
                        this.loadAgents();
                    }
                } catch (error) {
                    alert(`删除失败: ${error.message}`);
                }
            }
        }
    }

    async handleSearchAction(event) {
        const item = event.target.closest('.config-card');
        if (!item) return;

        const engineId = item.dataset.id;

        if (event.target.closest('.edit-btn')) {
            // 编辑搜索引擎
            try {
                const response = await fetch(`${this.baseUrl}/api/search_engines`);
                const engines = await response.json();
                const engine = engines.find(e => e.id === engineId);
                if (engine) {
                    this.openSearchModal(engine);
                }
            } catch (error) {
                console.error('获取搜索引擎失败:', error);
            }
        } else if (event.target.closest('.delete-btn')) {
            // 删除搜索引擎
            if (confirm('确定要删除这个搜索引擎吗？')) {
                try {
                    const response = await fetch(`${this.baseUrl}/api/search_engines/${engineId}`, {
                        method: 'DELETE'
                    });
                    const result = await response.json();
                    
                    if (result.status === 'success') {
                        this.addLog(result.message);
                        await this.loadSearchEngines();
                    }
                } catch (error) {
                    alert(`删除失败: ${error.message}`);
                }
            }
        }
    }

    async testSearch() {
        const query = document.getElementById('search-query').value.trim();
        if (!query) {
            alert('请输入搜索关键词');
            return;
        }

        const resultsDiv = document.getElementById('search-results');
        resultsDiv.innerHTML = '<div style="text-align: center; padding: 10px;"><i class="fas fa-spinner fa-spin"></i> 搜索中...</div>';

        try {
            const formData = new FormData();
            formData.append('query', query);
            
            const response = await fetch(`${this.baseUrl}/api/search_test`, {
                method: 'POST',
                body: formData
            });
            const result = await response.json();

            if (result.status === 'success') {
                if (result.results && result.results.length > 0) {
                    resultsDiv.innerHTML = result.results.map((r, i) => `
                        <div class="search-result">
                            <h4>${i + 1}. ${r.title}</h4>
                            <p>${r.snippet}</p>
                            <a href="${r.url}" target="_blank">${r.url}</a>
                        </div>
                    `).join('');
                } else {
                    resultsDiv.innerHTML = '<p style="text-align: center; color: #94a3b8;">未找到搜索结果</p>';
                }
            } else {
                resultsDiv.innerHTML = `<p style="text-align: center; color: #ef4444;">${result.message}</p>`;
            }
        } catch (error) {
            resultsDiv.innerHTML = `<p style="text-align: center; color: #ef4444;">搜索失败: ${error.message}</p>`;
        }
    }

    async quickSearch() {
        const query = document.getElementById('quick-search-input').value.trim();
        if (!query) {
            alert('请输入搜索关键词');
            return;
        }

        const resultsDiv = document.getElementById('quick-search-results');
        resultsDiv.innerHTML = '<div style="text-align: center; padding: 20px; color: white;"><i class="fas fa-spinner fa-spin"></i> 搜索中...</div>';

        try {
            const response = await fetch(`${this.baseUrl}/api/search/quick`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({query: query, num_results: 5})
            });
            const result = await response.json();

            if (result.status === 'success') {
                let html = '<div style="background: white; border-radius: 8px; padding: 15px; max-height: 400px; overflow-y: auto;">';
                html += `<div style="margin-bottom: 10px; color: #666; font-size: 13px;">找到 ${result.results.length} 条结果</div>`;
                result.results.forEach((r, i) => {
                    html += `
                        <div style="margin-bottom: 15px; padding-bottom: 15px; border-bottom: 1px solid #eee;">
                            <div style="font-weight: 600; color: #1e293b; margin-bottom: 5px;">
                                <span style="background: #667eea; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-right: 8px;">${i + 1}</span>
                                ${r.title}
                            </div>
                            <div style="color: #6366f1; font-size: 12px; margin-bottom: 5px;">
                                <a href="${r.url}" target="_blank" style="color: inherit; text-decoration: none;">${r.url}</a>
                            </div>
                            <div style="color: #64748b; font-size: 13px; line-height: 1.6;">${r.content}</div>
                        </div>
                    `;
                });
                html += '</div>';
                resultsDiv.innerHTML = html;
            } else {
                resultsDiv.innerHTML = `<div style="background: white; border-radius: 8px; padding: 20px; text-align: center; color: #f59e0b;">${result.message}</div>`;
            }
        } catch (error) {
            resultsDiv.innerHTML = `<div style="background: white; border-radius: 8px; padding: 20px; text-align: center; color: #ef4444;">搜索失败: ${error.message}</div>`;
        }
    }

    clearQuickSearch() {
        document.getElementById('quick-search-input').value = '';
        document.getElementById('quick-search-results').innerHTML = '';
    }

    async testModelConnection(modelId) {
        const testBtn = document.querySelector(`.config-card[data-id="${modelId}"] .test-btn`);
        if (!testBtn) {
            alert('错误：找不到测试按钮');
            return;
        }
        const originalIcon = testBtn.innerHTML;
        
        try {
            testBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            
            const response = await fetch(`${this.baseUrl}/api/models/${modelId}/test`, {
                method: 'POST'
            });
            const result = await response.json();

            if (result.status === 'success') {
                testBtn.innerHTML = '<i class="fas fa-check" style="color: #22c55e;"></i>';
                this.showModelMessage(modelId, 'success', `连接成功: ${result.message}`);
            } else {
                testBtn.innerHTML = '<i class="fas fa-xmark" style="color: #ef4444;"></i>';
                this.showModelMessage(modelId, 'error', `连接失败: ${result.message}`);
            }

            setTimeout(() => {
                testBtn.innerHTML = originalIcon;
            }, 2000);
        } catch (error) {
            testBtn.innerHTML = '<i class="fas fa-xmark" style="color: #ef4444;"></i>';
            this.showModelMessage(modelId, 'error', `测试失败: ${error.message}`);
            setTimeout(() => {
                testBtn.innerHTML = originalIcon;
            }, 2000);
        }
    }

    showModelMessage(modelId, type, message) {
        // 移除旧消息
        const oldMsg = document.querySelector(`.config-card[data-id="${modelId}"] .model-message`);
        if (oldMsg) oldMsg.remove();
        
        // 创建新消息
        const modelCard = document.querySelector(`.config-card[data-id="${modelId}"] .card-body`);
        if (!modelCard) return;
        
        const msgEl = document.createElement('div');
        msgEl.className = `model-message`;
        msgEl.style.cssText = `margin-top: 8px; padding: 8px 12px; border-radius: 6px; font-size: 12px; ${type === 'success' ? 'background: #dcfce7; color: #166534;' : 'background: #fee2e2; color: #991b1b;'}`;
        msgEl.innerHTML = `<i class="fas ${type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'}" style="margin-right: 6px;"></i>${message}`;
        
        modelCard.appendChild(msgEl);
        
        // 3秒后自动移除
        setTimeout(() => msgEl.remove(), 3000);
    }

    async saveSettings() {
        const settings = {
            iterations: parseInt(document.getElementById('setting-iterations').value),
            enable_search: document.getElementById('setting-enable-search').checked,
            max_search_per_iter: parseInt(document.getElementById('setting-max-search').value),
            default_log_level: document.getElementById('setting-log-level').value
        };

        try {
            const response = await fetch(`${this.baseUrl}/api/settings`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
            const result = await response.json();
            
            if (result.status === 'success') {
                this.addLog(result.message);
            } else {
                alert(result.message);
            }
        } catch (error) {
            alert(`保存设置失败: ${error.message}`);
        }
    }

    async startProcessing() {
        const content = document.getElementById('input-content').value.trim();
        if (!content) {
            alert('请先输入内容');
            return;
        }

        const iterations = parseInt(document.getElementById('iterations').value) || 10;
        const enableSearch = document.getElementById('enable-search-setting')?.checked || false;

        // 先分析是否需要调用Skill
        try {
            const analyzeResponse = await fetch(`${this.baseUrl}/api/skills/analyze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            });
            const analyzeResult = await analyzeResponse.json();

            let finalContent = content;

            // 如果找到匹配的Skills，弹出选择对话框
            if (analyzeResult.matched_skills && analyzeResult.matched_skills.length > 0) {
                const skillSelection = await this.showSkillSelectionDialog(analyzeResult.matched_skills);

                if (skillSelection === null) {
                    // 用户取消，不继续处理
                    return;
                }

                if (skillSelection.selected.length > 0) {
                    this.addLog(`📋 准备执行 ${skillSelection.selected.length} 个Skill...`);

                    // 执行选中的Skills
                    for (const skillId of skillSelection.selected) {
                        const skillInfo = analyzeResult.matched_skills.find(s => s.skill_id === skillId);
                        const skillName = skillInfo?.skill_name || skillId;
                        this.addLog(`⚙️ 执行Skill: ${skillName}...`);

                        try {
                            // 对于搜索类skill，显示参数输入对话框
                            let queryParams = { query: content };
                            
                            // 获取skill详情判断类型
                            const skillDetailResp = await fetch(`${this.baseUrl}/api/skills/${skillId}`);
                            const skillDetail = await skillDetailResp.json();
                            
                            if (skillDetail?.skill?.executor === 'search') {
                                // 弹出查询参数输入框
                                queryParams = await this.showSearchQueryDialog(content);
                                if (!queryParams) {
                                    this.addLog(`⏭️ 跳过Skill执行`);
                                    continue;
                                }
                            }

                            const execResponse = await fetch(`${this.baseUrl}/api/skills/${skillId}/execute`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ params: queryParams })
                            });

                            if (!execResponse.ok) {
                                this.addLog(`✗ Skill执行失败: HTTP ${execResponse.status}`);
                                continue;
                            }

                            const execResult = await execResponse.json();
                            this.addLog(`📜 Skill返回: ${JSON.stringify(execResult).substring(0, 200)}`);

                            if (execResult.result?.success) {
                                const skillOutput = execResult.result.output || '';
                                this.addLog(`✓ Skill执行成功，输出: ${skillOutput.substring(0, 100)}...`);
                                // 将Skill输出追加到内容
                                finalContent = `${finalContent}\n\n【Skill: ${skillName} 执行结果】\n${skillOutput}`;
                            } else {
                                this.addLog(`✗ Skill执行失败: ${execResult.result?.error || execResult.message || '未知错误'}`);
                            }
                        } catch (err) {
                            this.addLog(`✗ Skill执行异常: ${err.message}`);
                        }
                    }
                }
            }

            // 更新状态为处理中
            const statusDot = document.getElementById('status-dot');
            const statusText = document.getElementById('status-text');
            const startBtn = document.getElementById('start-btn');
            const stopBtn = document.getElementById('stop-btn');
            statusDot.classList.add('processing');
            statusText.textContent = '处理中';
            startBtn.disabled = true;
            stopBtn.disabled = false;
            
            // 开始主处理流程 - 使用流式API
            await this.startStreamProcessing(finalContent, iterations, enableSearch);
        } catch (error) {
            this.addLog(`启动失败: ${error.message}`);
            const statusDot = document.getElementById('status-dot');
            const statusText = document.getElementById('status-text');
            const startBtn = document.getElementById('start-btn');
            const stopBtn = document.getElementById('stop-btn');
            statusDot.classList.remove('processing');
            statusText.textContent = '错误';
            startBtn.disabled = false;
            stopBtn.disabled = true;
        }
    }

    showSkillSelectionDialog(matchedSkills) {
        return new Promise((resolve) => {
            // 创建对话框
            const modal = document.createElement('div');
            modal.className = 'modal';
            modal.style.display = 'flex';
            modal.id = 'skill-selection-modal';

            const skillsList = matchedSkills.map((s, idx) => `
                <label style="display: flex; align-items: center; padding: 10px; border-bottom: 1px solid #e2e8f0; cursor: pointer;">
                    <input type="checkbox" value="${s.skill_id}" data-idx="${idx}" checked style="margin-right: 10px;">
                    <div>
                        <div style="font-weight: 600;">${s.skill_name}</div>
                        <div style="font-size: 12px; color: #64748b;">匹配度: ${s.score.toFixed(1)} - ${s.reasons.join(', ')}</div>
                    </div>
                </label>
            `).join('');

            modal.innerHTML = `
                <div class="modal-content" style="width: 500px; max-width: 90%;">
                    <div class="modal-header">
                        <h3><i class="fas fa-magic"></i> 检测到可能需要调用的Skill</h3>
                        <button class="modal-close" id="skill-sel-close-btn">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="modal-body" style="max-height: 400px; overflow-y: auto;">
                        <p style="color: #64748b; margin-bottom: 15px;">根据您的输入内容，系统建议使用以下Skill（可选择）：</p>
                        <div id="skill-sel-checkboxes">
                            ${skillsList}
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" id="skill-sel-skip-btn">跳过Skill</button>
                        <button class="btn btn-primary" id="skill-sel-go-btn">执行选中的Skill并继续</button>
                    </div>
                </div>
            `;

            document.body.appendChild(modal);

            // 绑定事件
            document.getElementById('skill-sel-close-btn').onclick = () => {
                modal.remove();
                resolve(null);
            };

            document.getElementById('skill-sel-skip-btn').onclick = () => {
                modal.remove();
                resolve(null);
            };

            document.getElementById('skill-sel-go-btn').onclick = () => {
                const selected = Array.from(
                    document.querySelectorAll('#skill-sel-checkboxes input:checked')
                ).map(cb => cb.value);
                modal.remove();
                resolve({ selected });
            };
        });
    }

    showSearchQueryDialog(originalContent) {
        return new Promise((resolve) => {
            // 从原内容中提取可能的查询关键词
            const commonPrefixes = ['查询', '搜索', '查找', '帮我', '请', '给我', '我想', '帮我查一下', '帮我搜索'];
            let extractedQuery = originalContent;
            
            // 尝试移除常见前缀
            for (const prefix of commonPrefixes) {
                if (originalContent.includes(prefix)) {
                    // 移除前缀及后面的部分，保留查询主体
                    const idx = originalContent.indexOf(prefix);
                    let afterPrefix = originalContent.substring(idx + prefix.length);
                    // 取到第一个句号、逗号或"信息"之后
                    const cutPoints = ['。', '，', '。', '的信息', '情况', '资料', '报告', '一下', '一下，', '一下。'];
                    for (const cut of cutPoints) {
                        const cutIdx = afterPrefix.indexOf(cut);
                        if (cutIdx > 0 && cutIdx < 20) {
                            afterPrefix = afterPrefix.substring(0, cutIdx);
                            break;
                        }
                    }
                    if (afterPrefix.trim().length > 1) {
                        extractedQuery = afterPrefix.trim();
                        break;
                    }
                }
            }

            const modal = document.createElement('div');
            modal.className = 'modal';
            modal.style.display = 'flex';
            modal.id = 'search-query-modal';

            modal.innerHTML = `
                <div class="modal-content" style="width: 600px; max-width: 90%;">
                    <div class="modal-header">
                        <h3><i class="fas fa-search"></i> 设置搜索参数</h3>
                        <button class="modal-close" id="search-query-cancel-btn">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="modal-body">
                        <p style="color: #64748b; margin-bottom: 10px;">请编辑要搜索的关键词：</p>
                        <div style="margin-bottom: 15px;">
                            <label style="display: block; color: #475569; margin-bottom: 5px; font-weight: 500;">原始输入：</label>
                            <div style="background: #f1f5f9; padding: 10px; border-radius: 6px; color: #64748b; font-size: 13px; max-height: 60px; overflow-y: auto;">${originalContent}</div>
                        </div>
                        <div>
                            <label style="display: block; color: #475569; margin-bottom: 5px; font-weight: 500;">搜索关键词 <span style="color: #ef4444;">*</span>：</label>
                            <input type="text" id="search-query-input" value="${extractedQuery}" 
                                style="width: 100%; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px; box-sizing: border-box;"
                                placeholder="输入要搜索的关键词">
                        </div>
                        <div style="margin-top: 15px;">
                            <label style="display: block; color: #475569; margin-bottom: 5px; font-weight: 500;">返回结果数量：</label>
                            <select id="search-num-results" style="width: 100%; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;">
                                <option value="3">3 条结果</option>
                                <option value="5" selected>5 条结果</option>
                                <option value="10">10 条结果</option>
                                <option value="15">15 条结果</option>
                            </select>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" id="search-query-cancel-btn2">取消</button>
                        <button class="btn btn-primary" id="search-query-confirm-btn">
                            <i class="fas fa-search"></i> 执行搜索
                        </button>
                    </div>
                </div>
            `;

            document.body.appendChild(modal);

            // 绑定事件
            const closeAndResolve = (result) => {
                modal.remove();
                resolve(result);
            };

            document.getElementById('search-query-cancel-btn').onclick = () => closeAndResolve(null);
            document.getElementById('search-query-cancel-btn2').onclick = () => closeAndResolve(null);
            
            document.getElementById('search-query-confirm-btn').onclick = () => {
                const query = document.getElementById('search-query-input').value.trim();
                const numResults = parseInt(document.getElementById('search-num-results').value);
                
                if (!query) {
                    alert('请输入搜索关键词');
                    return;
                }
                
                closeAndResolve({ query, num_results: numResults });
            };

            // 回车确认
            document.getElementById('search-query-input').addEventListener('keyup', (e) => {
                if (e.key === 'Enter') {
                    document.getElementById('search-query-confirm-btn').click();
                }
            });
        });
    }

    async showModelCallsDialog() {
        try {
            const modal = document.createElement('div');
            modal.className = 'modal';
            modal.style.display = 'flex';
            modal.id = 'model-calls-modal';

            // 初始加载日志
            const renderLogs = async () => {
                try {
                    const response = await fetch(`${this.baseUrl}/api/model_calls?limit=50`);
                    const result = await response.json();
                    const logs = result.logs || [];

                    let logsHtml = '';
                    if (logs.length === 0) {
                        logsHtml = `
                            <div style="text-align: center; padding: 40px; color: #94a3b8;">
                                <i class="fas fa-inbox" style="font-size: 48px; margin-bottom: 16px;"></i>
                                <p>暂无模型调用记录</p>
                            </div>
                        `;
                    } else {
                        logsHtml = logs.map((log, index) => `
                            <div class="model-call-item" style="border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 16px; overflow: hidden;">
                                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center;">
                                    <div>
                                        <span style="font-weight: 600; font-size: 14px;">📡 调用 #${logs.length - index}</span>
                                        <span style="margin-left: 12px; font-size: 12px; opacity: 0.9;">${log.model_name}</span>
                                    </div>
                                    <div style="font-size: 12px; opacity: 0.9;">
                                        ${new Date(log.timestamp).toLocaleString('zh-CN')}
                                    </div>
                                </div>
                                <div style="padding: 16px;">
                                    ${log.error ? `
                                        <div style="background: #fef2f2; border-left: 4px solid #ef4444; padding: 12px; margin-bottom: 12px; border-radius: 0 4px 4px 0;">
                                            <span style="color: #dc2626; font-weight: 600;">❌ 调用失败</span>
                                            <p style="color: #991b1b; margin-top: 8px; font-size: 13px;">${log.error}</p>
                                        </div>
                                    ` : ''}
                                    <div style="margin-bottom: 12px;">
                                        <div style="color: #3b82f6; font-weight: 600; margin-bottom: 8px; font-size: 13px;">📤 输入 (${log.prompt_tokens} tokens)</div>
                                        <div style="background: #f8fafc; padding: 12px; border-radius: 6px; font-family: 'Consolas', 'Monaco', monospace; font-size: 13px; max-height: 150px; overflow-y: auto; line-height: 1.6;">
                                            ${this.formatMessages(log.messages)}
                                        </div>
                                    </div>
                                    <div>
                                        <div style="color: #10b981; font-weight: 600; margin-bottom: 8px; font-size: 13px;">📥 输出 (${log.completion_tokens} tokens)</div>
                                        <div style="background: #f0fdf4; padding: 12px; border-radius: 6px; font-family: 'Consolas', 'Monaco', monospace; font-size: 13px; max-height: 200px; overflow-y: auto; line-height: 1.6; white-space: pre-wrap;">
                                            ${log.response || '(空响应)'}
                                        </div>
                                    </div>
                                    <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #e2e8f0; display: flex; gap: 20px; font-size: 12px; color: #64748b;">
                                        <span>⏱️ 耗时: ${log.duration.toFixed(2)}秒</span>
                                        <span>📊 总tokens: ${log.total_tokens}</span>
                                        <span>📝 输入: ${log.prompt_tokens}</span>
                                        <span>📤 输出: ${log.completion_tokens}</span>
                                    </div>
                                </div>
                            </div>
                        `).join('');
                    }

                    const contentDiv = document.getElementById('model-calls-content');
                    if (contentDiv) {
                        contentDiv.innerHTML = logsHtml;
                        document.getElementById('model-calls-count').textContent = `共 ${logs.length} 条记录`;
                    }
                } catch (error) {
                    console.error('刷新日志失败:', error);
                }
            };

            modal.innerHTML = `
                <div class="modal-content" id="model-calls-modal-content" style="width: 85%; max-width: 900px; max-height: 80vh; overflow-y: auto; transition: all 0.3s ease;">
                    <div class="modal-header" style="display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid #e2e8f0;">
                        <h3 style="margin: 0; font-size: 16px;"><i class="fas fa-brain"></i> 模型调用日志</h3>
                        <div style="display: flex; gap: 8px;">
                            <button id="model-calls-refresh-btn" class="btn btn-sm btn-info" style="background: #3b82f6; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer;" title="手动刷新">
                                <i class="fas fa-sync-alt"></i>
                            </button>
                            <button id="model-calls-auto-refresh-btn" class="btn btn-sm btn-success" style="background: #10b981; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer;" title="开启/关闭实时刷新">
                                <i class="fas fa-refresh"></i> 实时
                            </button>
                            <button id="model-calls-maximize-btn" class="btn btn-sm btn-secondary" style="background: #64748b; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer;" title="最大化">
                                <i class="fas fa-expand"></i>
                            </button>
                            <button class="modal-close" id="model-calls-close-btn" style="background: none; border: none; cursor: pointer; padding: 4px; color: #64748b;">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    </div>
                    <div class="modal-body" style="padding: 16px; max-height: calc(100% - 100px); overflow-y: auto;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                            <span id="model-calls-count" style="color: #64748b; font-size: 14px;">共 0 条记录</span>
                            <button id="clear-model-calls-btn" class="btn btn-danger btn-sm" style="background: #ef4444; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer;">
                                <i class="fas fa-trash"></i> 清空日志
                            </button>
                        </div>
                        <div id="model-calls-content"></div>
                    </div>
                    <div class="modal-footer" style="padding: 12px 16px; border-top: 1px solid #e2e8f0; text-align: right;">
                        <button class="btn btn-secondary" id="model-calls-cancel-btn" style="background: #64748b; color: white; border: none; padding: 6px 16px; border-radius: 4px; cursor: pointer;">关闭</button>
                    </div>
                </div>
            `;

            document.body.appendChild(modal);

            // 初始渲染日志
            await renderLogs();

            let isMaximized = false;
            let autoRefreshInterval = null;
            let isAutoRefreshEnabled = true;

            const closeModal = () => {
                if (autoRefreshInterval) {
                    clearInterval(autoRefreshInterval);
                }
                modal.remove();
            };

            const toggleMaximize = () => {
                const content = document.getElementById('model-calls-modal-content');
                const btn = document.getElementById('model-calls-maximize-btn');
                if (isMaximized) {
                    content.style.width = '85%';
                    content.style.maxWidth = '900px';
                    content.style.maxHeight = '80vh';
                    btn.innerHTML = '<i class="fas fa-expand"></i>';
                    btn.title = '最大化';
                } else {
                    content.style.width = '98%';
                    content.style.maxWidth = 'none';
                    content.style.maxHeight = '98vh';
                    btn.innerHTML = '<i class="fas fa-compress"></i>';
                    btn.title = '还原';
                }
                isMaximized = !isMaximized;
            };

            const toggleAutoRefresh = () => {
                const btn = document.getElementById('model-calls-auto-refresh-btn');
                if (isAutoRefreshEnabled) {
                    if (autoRefreshInterval) {
                        clearInterval(autoRefreshInterval);
                        autoRefreshInterval = null;
                    }
                    btn.style.background = '#f59e0b';
                    btn.innerHTML = '<i class="fas fa-pause"></i> 暂停';
                } else {
                    autoRefreshInterval = setInterval(renderLogs, 3000);
                    btn.style.background = '#10b981';
                    btn.innerHTML = '<i class="fas fa-refresh"></i> 实时';
                }
                isAutoRefreshEnabled = !isAutoRefreshEnabled;
            };

            // 绑定事件
            document.getElementById('model-calls-close-btn').onclick = closeModal;
            document.getElementById('model-calls-cancel-btn').onclick = closeModal;
            document.getElementById('model-calls-refresh-btn').onclick = renderLogs;
            document.getElementById('model-calls-auto-refresh-btn').onclick = toggleAutoRefresh;
            document.getElementById('model-calls-maximize-btn').onclick = toggleMaximize;

            // 开启自动刷新
            autoRefreshInterval = setInterval(renderLogs, 3000);

            document.getElementById('clear-model-calls-btn').onclick = async () => {
                if (!confirm('确定要清空所有模型调用日志吗？')) return;
                try {
                    const response = await fetch(`${this.baseUrl}/api/model_calls`, { method: 'DELETE' });
                    const result = await response.json();
                    if (result.status === 'success') {
                        await renderLogs();
                    }
                } catch (error) {
                    alert('清空失败: ' + error.message);
                }
            };

            // ESC键关闭
            const handleEscape = (e) => {
                if (e.key === 'Escape') {
                    closeModal();
                    document.removeEventListener('keydown', handleEscape);
                }
            };
            document.addEventListener('keydown', handleEscape);
        } catch (error) {
            alert('获取模型调用日志失败: ' + error.message);
        }
    }

    formatMessages(messages) {
        if (!messages || !Array.isArray(messages)) return '';
        return messages.map(msg => {
            const roleColors = {
                system: 'color: #8b5cf6;',
                user: 'color: #3b82f6;',
                assistant: 'color: #10b981;'
            };
            const roleLabels = {
                system: '系统',
                user: '用户',
                assistant: '助手'
            };
            const color = roleColors[msg.role] || 'color: #64748b;';
            const label = roleLabels[msg.role] || msg.role;
            return `<span style="${color} font-weight: 600;">[${label}]</span> ${msg.content}`;
        }).join('\n\n');
    }

    async stopProcessing() {
        try {
            const response = await fetch(`${this.baseUrl}/api/stop`, {
                method: 'POST'
            });

            const result = await response.json();
            if (result.status === 'success') {
                this.addLog(result.message);
            }
        } catch (error) {
            this.addLog(`停止失败: ${error.message}`);
        }
    }

    async clearAll() {
        if (!confirm('⚠️ 确定要清空所有内容吗？\n\n这将清除：\n• 输入文档\n• 预览内容\n• 处理日志\n• 所有附件')) {
            return;
        }
        
        try {
            const response = await fetch(`${this.baseUrl}/api/clear`, {
                method: 'POST'
            });
            const result = await response.json();
            
            if (result.status === 'success') {
                this.addLog(result.message);
                
                // 安全地重置元素
                const safeSetText = (id, value) => {
                    const el = document.getElementById(id);
                    if (el) el.textContent = value;
                };
                
                const safeSetValue = (id, value) => {
                    const el = document.getElementById(id);
                    if (el) el.value = value;
                };
                
                const safeSetStyle = (id, prop, value) => {
                    const el = document.getElementById(id);
                    if (el) el.style[prop] = value;
                };
                
                // 重置输入和预览
                safeSetValue('input-content', '');
                const previewEl = document.getElementById('preview-content');
                if (previewEl) {
                    previewEl.innerHTML = '<div class="empty-state"><i class="fas fa-file-text"></i><p>处理后的文档将在这里显示</p></div>';
                }
                
                this.clearLog();
                await this.loadAttachments();
                
                // 重置统计信息
                const iterationsEl = document.getElementById('iterations');
                const iterationsValue = iterationsEl ? iterationsEl.value : '3';
                safeSetText('stat-iteration', '0/' + iterationsValue);
                safeSetText('iteration-progress', '步骤 0/0');
                safeSetText('stat-tokens', '0');
                safeSetText('stat-searches', '0');
                safeSetText('stat-time', '00:00:00');
                safeSetText('stat-wordcount', '0');
                
                // 重置进度条
                safeSetStyle('progress-fill', 'width', '0%');
                safeSetText('progress-text', '0%');
                
                // 重置Agent状态表格
                const agentRows = document.querySelectorAll('#agent-status-body tr');
                agentRows.forEach(row => {
                    const badge = row.querySelector('.status-badge');
                    if (badge) {
                        badge.textContent = '就绪';
                        badge.className = 'status-badge badge-ready';
                    }
                    const cells = row.querySelectorAll('td');
                    if (cells.length >= 7) {
                        if (cells[2]) cells[2].textContent = '-';
                        if (cells[3]) cells[3].textContent = '0';
                        if (cells[4]) cells[4].textContent = '0';
                        if (cells[5]) cells[5].textContent = '0';
                        if (cells[6]) cells[6].textContent = '0s';
                    }
                });
            }
        } catch (error) {
            this.addLog(`清空失败: ${error.message}`);
        }
    }

    async saveDocument() {
        const content = document.getElementById('input-content').value.trim();
        if (!content) {
            alert('没有可保存的内容');
            return;
        }

        const filename = prompt('请输入文件名:', 'document');
        if (!filename) return;

        const formData = new FormData();
        formData.append('content', content);
        formData.append('filename', filename);

        try {
            const response = await fetch(`${this.baseUrl}/api/save`, {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            if (result.status === 'success') {
                this.addLog(result.message);
            } else {
                alert(result.message);
            }
        } catch (error) {
            alert(`保存失败: ${error.message}`);
        }
    }

    async exportLogs() {
        try {
            const response = await fetch(`${this.baseUrl}/api/logs/export`, {
                method: 'POST'
            });
            
            if (!response.ok) {
                const result = await response.json();
                alert(result.message || '导出失败');
                return;
            }
            
            const blob = await response.blob();
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = 'logs_export.txt';
            if (contentDisposition) {
                const match = contentDisposition.match(/filename="?([^"]+)"?/);
                if (match) {
                    filename = match[1];
                }
            }
            
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            
            this.addLog(`日志已导出: ${filename}`);
        } catch (error) {
            alert(`导出失败: ${error.message}`);
        }
    }

    startStatusPolling() {
        this.statusInterval = setInterval(async () => {
            try {
                const response = await fetch(`${this.baseUrl}/api/status`);
                const status = await response.json();

                // 更新状态显示
                const statusDot = document.getElementById('status-dot');
                const statusText = document.getElementById('status-text');

                statusDot.className = 'status-dot';
                if (status.status === 'processing') {
                    statusDot.classList.add('processing');
                    statusText.textContent = '处理中';
                    document.getElementById('start-btn').disabled = true;
                    document.getElementById('stop-btn').disabled = false;
                } else if (status.status === 'completed') {
                    statusDot.classList.add('completed');
                    statusText.textContent = '已完成';
                    document.getElementById('start-btn').disabled = false;
                    document.getElementById('stop-btn').disabled = true;
                } else if (status.status === 'error') {
                    statusDot.classList.add('error');
                    statusText.textContent = '出错';
                    document.getElementById('start-btn').disabled = false;
                    document.getElementById('stop-btn').disabled = true;
                } else if (status.status === 'stopped') {
                    statusDot.classList.add('error');
                    statusText.textContent = '已停止';
                    document.getElementById('start-btn').disabled = false;
                    document.getElementById('stop-btn').disabled = true;
                } else {
                    statusText.textContent = '空闲';
                }

                // 更新文档内容
                if (status.current_document) {
                    document.getElementById('input-content').value = status.current_document;
                    this.updatePreview(status.current_document);
                    
                    // 更新字数统计
                    document.getElementById('stat-wordcount').textContent = status.current_document.length;
                }

                // 更新统计信息
                if (status.state) {
                    const totalIterations = status.state.total_iterations || 1;
                    document.getElementById('stat-iteration').textContent = 
                        `${status.state.current_iteration || 0}/${totalIterations}`;
                    document.getElementById('stat-tokens').textContent = 
                        (status.state.total_tokens || 0).toLocaleString();
                    document.getElementById('stat-searches').textContent = 
                        status.state.search_count || 0;
                    
                    // 更新运行时长
                    if (status.state.elapsed_time) {
                        const seconds = Math.floor(status.state.elapsed_time);
                        const hh = String(Math.floor(seconds / 3600)).padStart(2, '0');
                        const mm = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
                        const ss = String(seconds % 60).padStart(2, '0');
                        document.getElementById('stat-time').textContent = `${hh}:${mm}:${ss}`;
                    }

                    // 更新进度条 - 使用精确进度计算
                    if (status.state.progress_percent !== undefined) {
                        const progress = status.state.progress_percent;
                        document.getElementById('progress-fill').style.width = `${progress}%`;
                        document.getElementById('progress-text').textContent = `${progress}%`;
                    } else if (totalIterations > 0 && status.state.current_iteration) {
                        // 兼容旧版本
                        const progress = Math.round((status.state.current_iteration / totalIterations) * 100);
                        document.getElementById('progress-fill').style.width = `${progress}%`;
                        document.getElementById('progress-text').textContent = `${progress}%`;
                    }

                    // 更新迭代进度显示
                    const iterationProgress = document.getElementById('iteration-progress');
                    if (iterationProgress) {
                        if (status.state.current_step !== undefined && status.state.total_steps !== undefined) {
                            iterationProgress.textContent = `步骤 ${status.state.current_step || 0}/${status.state.total_steps}`;
                        } else if (totalIterations > 0) {
                            // 兼容旧版本
                            iterationProgress.textContent = `步骤 0/${totalIterations}`;
                        }
                    }

                    // 更新当前运行的Agent状态
                    if (status.state.current_agent_id) {
                        const agentRow = document.querySelector(`#agent-status-body tr[data-id="${status.state.current_agent_id}"]`);
                        if (agentRow) {
                            const statusBadge = agentRow.querySelector('.status-badge');
                            statusBadge.textContent = '运行中';
                            statusBadge.className = 'status-badge running';
                            agentRow.querySelector('td:nth-child(3)').textContent = status.state.current_model || '-';
                            agentRow.querySelector('td:nth-child(4)').textContent = status.state.current_iteration || 0;
                        }
                    }

                    // 更新已完成的Agent结果
                    if (status.agent_results) {
                        for (const [agentId, result] of Object.entries(status.agent_results)) {
                            const agentRow = document.querySelector(`#agent-status-body tr[data-id="${agentId}"]`);
                            if (agentRow) {
                                const statusBadge = agentRow.querySelector('.status-badge');
                                statusBadge.textContent = result.success ? '完成' : '失败';
                                statusBadge.className = result.success ? 'status-badge completed' : 'status-badge error';
                                agentRow.querySelector('td:nth-child(3)').textContent = result.model_name || '-';
                                agentRow.querySelector('td:nth-child(4)').textContent = result.iteration || 0;
                                agentRow.querySelector('td:nth-child(5)').textContent = result.prompt_tokens || 0;
                                agentRow.querySelector('td:nth-child(6)').textContent = result.completion_tokens || 0;
                                agentRow.querySelector('td:nth-child(7)').textContent = `${result.time_spent?.toFixed(1) || 0}s`;
                            }
                        }
                    }
                }

                // 更新日志
                if (status.log && status.log.length > 0) {
                    const logContent = document.getElementById('log-content');
                    const logItems = logContent.querySelectorAll('.log-item');
                    const existingLogs = Array.from(logItems).map(item => item.textContent);
                    
                    status.log.forEach(entry => {
                        if (!existingLogs.includes(entry)) {
                            this.addLog(entry, true);  // 自动滚动到最新
                        }
                    });
                }

            } catch (error) {
                console.error('获取状态失败:', error);
            }
        }, 1000);
    }

    addLog(message, scroll = true) {
        const logContent = document.getElementById('log-content');
        const logEntry = document.createElement('div');
        logEntry.className = 'log-item';
        
        // 根据内容添加不同的样式类
        let logClass = 'log-default';
        if (message.includes('✓') || message.includes('成功')) {
            logClass = 'log-success';
        } else if (message.includes('✗') || message.includes('失败') || message.includes('错误')) {
            logClass = 'log-error';
        } else if (message.includes('⚠') || message.includes('警告') || message.includes('注意')) {
            logClass = 'log-warning';
        } else if (message.includes('┌') || message.includes('│') || message.includes('└') || message.includes('═') || message.includes('迭代') || message.includes('阶段')) {
            logClass = 'log-header';
        } else if (message.includes('▶') || message.includes('Agent:') || message.includes('模型:')) {
            logClass = 'log-info';
        } else if (message.includes('Token') || message.includes('耗时') || message.includes('长度') || message.includes('字符')) {
            logClass = 'log-stats';
        } else if (message.match(/^\s*$/)) {
            logClass = 'log-empty';
        }
        
        logEntry.classList.add(logClass);
        logEntry.textContent = message;
        logContent.appendChild(logEntry);

        if (scroll) {
            logContent.scrollTop = logContent.scrollHeight;
        }
    }

    clearLog() {
        document.getElementById('log-content').innerHTML = '';
        this.addLog('日志已清空');
    }

    updateStatus(status) {
        const startBtn = document.getElementById('start-btn');
        const stopBtn = document.getElementById('stop-btn');
        const statusDot = document.getElementById('status-dot');
        const statusText = document.getElementById('status-text');
        
        if (status === 'completed') {
            startBtn.disabled = false;
            stopBtn.disabled = true;
            statusDot.classList.remove('processing');
            statusText.textContent = '就绪';
        } else if (status === 'error') {
            startBtn.disabled = false;
            stopBtn.disabled = true;
            statusDot.classList.remove('processing');
            statusText.textContent = '错误';
        } else if (status === 'processing') {
            startBtn.disabled = true;
            stopBtn.disabled = false;
            statusDot.classList.add('processing');
            statusText.textContent = '处理中';
        }
    }

    toggleMaximize(targetId) {
        const panel = document.getElementById(targetId);
        const btn = document.querySelector(`.maximize-btn[data-target="${targetId}"]`);
        
        if (panel.classList.contains('panel-maximized')) {
            // 还原
            panel.classList.remove('panel-maximized');
            btn.classList.remove('maximized');
            btn.innerHTML = '<i class="fas fa-expand"></i>';
            btn.title = '最大化';
            
            // 移除遮罩层
            const overlay = document.querySelector('.panel-maximized-overlay');
            if (overlay) overlay.remove();
        } else {
            // 先还原其他已最大化的面板
            document.querySelectorAll('.panel-maximized').forEach(p => {
                const pBtn = document.querySelector(`.maximize-btn[data-target="${p.id}"]`);
                if (pBtn) {
                    pBtn.classList.remove('maximized');
                    pBtn.innerHTML = '<i class="fas fa-expand"></i>';
                    pBtn.title = '最大化';
                }
                p.classList.remove('panel-maximized');
            });
            
            // 移除旧遮罩层
            const oldOverlay = document.querySelector('.panel-maximized-overlay');
            if (oldOverlay) oldOverlay.remove();
            
            // 最大化当前面板
            panel.classList.add('panel-maximized');
            btn.classList.add('maximized');
            btn.innerHTML = '<i class="fas fa-compress"></i>';
            btn.title = '还原';
            
            // 添加遮罩层（点击可还原）
            const overlay = document.createElement('div');
            overlay.className = 'panel-maximized-overlay';
            overlay.addEventListener('click', () => this.toggleMaximize(targetId));
            document.body.appendChild(overlay);
        }
    }

    switchPreview(view) {
        document.querySelectorAll('.toggle-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelector(`[data-view="${view}"]`).classList.add('active');

        const previewContent = document.getElementById('preview-content');
        const content = document.getElementById('input-content').value;

        if (view === 'markdown') {
            previewContent.innerHTML = `<pre class="markdown-source">${content || '处理后的文档将在这里显示'}</pre>`;
        } else {
            // 简单的Markdown渲染
            let html = content || '<div class="empty-state"><i class="fas fa-file-text"></i><p>处理后的文档将在这里显示</p></div>';
            if (content) {
                html = this.markdownToHtml(content);
            }
            previewContent.innerHTML = html;
        }
    }

    updatePreview(content, stream = true) {
        if (stream) {
            this.streamPreview(content);
        } else {
            this._updatePreviewDirect(content);
        }
    }

    _updatePreviewDirect(content) {
        const activeView = document.querySelector('.toggle-btn.active').dataset.view;
        
        if (activeView === 'markdown') {
            document.getElementById('preview-content').innerHTML = 
                `<pre class="markdown-source">${content || ''}</pre>`;
        } else {
            document.getElementById('preview-content').innerHTML = 
                content ? this.markdownToHtml(content) : 
                '<div class="empty-state"><i class="fas fa-file-text"></i><p>处理后的文档将在这里显示</p></div>';
        }
    }

    streamPreview(content) {
        if (this.streamTimer) {
            clearInterval(this.streamTimer);
            this.streamTimer = null;
        }

        const activeView = document.querySelector('.toggle-btn.active').dataset.view;
        const previewContent = document.getElementById('preview-content');
        const isMarkdown = activeView === 'markdown';
        
        let index = 0;
        const totalLength = content.length;
        
        const speed = Math.max(5, Math.floor(1000 / totalLength));

        this.streamTimer = setInterval(() => {
            if (index >= totalLength) {
                clearInterval(this.streamTimer);
                this.streamTimer = null;
                return;
            }

            const chunkSize = Math.min(10, totalLength - index);
            const currentContent = content.substring(0, index + chunkSize);
            
            if (isMarkdown) {
                previewContent.innerHTML = `<pre class="markdown-source">${currentContent}</pre>`;
            } else {
                previewContent.innerHTML = this.markdownToHtml(currentContent);
            }

            previewContent.scrollTop = previewContent.scrollHeight;
            
            index += chunkSize;
        }, speed);
    }

    async startStreamProcessing(content, iterations, enableSearch) {
        const self = this;
        try {
            const startBtn = document.getElementById('start-btn');
            const stopBtn = document.getElementById('stop-btn');
            const statusDot = document.getElementById('status-dot');
            const statusText = document.getElementById('status-text');
            const inputContent = document.getElementById('input-content');
            const statWordcount = document.getElementById('stat-wordcount');
            
            startBtn.disabled = true;
            stopBtn.disabled = false;
            statusDot.classList.add('processing');
            statusText.textContent = '处理中';

            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/process`;
            const socket = new WebSocket(wsUrl);

            let accumulatedContent = content;
            let pendingUpdate = false;
            let updateTimeout = null;
            let currentIteration = 0;

            const scheduleUpdate = () => {
                if (pendingUpdate || updateTimeout) return;
                pendingUpdate = true;
                
                updateTimeout = setTimeout(() => {
                    pendingUpdate = false;
                    updateTimeout = null;
                    
                    inputContent.value = accumulatedContent;
                    self._updatePreviewDirect(accumulatedContent);
                    statWordcount.textContent = accumulatedContent.length;
                    
                    // 自动滚动预览区域到底部
                    const previewContent = document.getElementById('preview-content');
                    if (previewContent) {
                        previewContent.scrollTop = previewContent.scrollHeight;
                    }
                }, 50);
            };

            socket.onopen = () => {
                console.log('WebSocket connected, sending data...');
                
                // 重置所有Agent状态为"就绪"
                const agentRows = document.querySelectorAll('#agent-status-body tr');
                agentRows.forEach(row => {
                    const statusBadge = row.querySelector('.status-badge');
                    if (statusBadge) {
                        statusBadge.textContent = '就绪';
                        statusBadge.className = 'status-badge badge-ready';
                    }
                    const cells = row.querySelectorAll('td');
                    if (cells.length >= 7) {
                        cells[2].textContent = '-';
                        cells[3].textContent = '0';
                        cells[4].textContent = '0';
                        cells[5].textContent = '0';
                        cells[6].textContent = '-';
                    }
                });
                
                socket.send(JSON.stringify({
                    content: content,
                    iterations: iterations,
                    enable_search: enableSearch
                }));
            };

            socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    console.log('Received WebSocket message:', data);
                    
                    // 处理所有类型的日志消息
                    if (data.status === 'log') {
                        self.addLog(`📝 ${data.message}`);
                        return;
                    }
                    
                    if (data.status === 'error') {
                        self.addLog(`✗ ${data.message}`);
                        self.updateStatus('error');
                        socket.close();
                        return;
                    }
                    
                    if (data.status === 'started') {
                        self.addLog(`▶ ${data.message}`);
                        statusDot.classList.add('processing');
                        statusText.textContent = '处理中';
                        
                        // 注意：Token统计是累计的，不应该在任务开始时清零
                        // 只重置迭代进度和运行时长
                        const statIteration = document.getElementById('stat-iteration');
                        const statTime = document.getElementById('stat-time');
                        if (statIteration) statIteration.textContent = '0/1';
                        if (statTime) statTime.textContent = '00:00:00';
                    }
                    
                    // 处理统计信息更新
                    if (data.status === 'stats') {
                        // 更新迭代进度
                        const statIteration = document.getElementById('stat-iteration');
                        if (statIteration) {
                            statIteration.textContent = `${data.iteration || 0}/${data.total_iterations || 0}`;
                        }
                        
                        // 更新步骤进度（使用current_step和total_steps）
                        const iterationProgress = document.getElementById('iteration-progress');
                        if (iterationProgress) {
                            iterationProgress.textContent = `步骤 ${data.current_step || 0}/${data.total_steps || 0}`;
                        }
                        
                        // 更新进度条
                        const totalSteps = data.total_steps || 1;
                        const currentStep = data.current_step || 0;
                        const progressPercent = totalSteps > 0 ? Math.round((currentStep / totalSteps) * 100) : 0;
                        const progressFill = document.getElementById('progress-fill');
                        const progressText = document.getElementById('progress-text');
                        if (progressFill) {
                            progressFill.style.width = `${progressPercent}%`;
                        }
                        if (progressText) {
                            progressText.textContent = `${progressPercent}%`;
                        }
                        
                        // 更新总Token
                        const statTokens = document.getElementById('stat-tokens');
                        if (statTokens) {
                            statTokens.textContent = (data.total_tokens || 0).toLocaleString();
                        }
                        
                        // 更新搜索次数
                        const statSearches = document.getElementById('stat-searches');
                        if (statSearches) {
                            statSearches.textContent = data.searches || 0;
                        }
                        
                        // 更新运行时长
                        const statTime = document.getElementById('stat-time');
                        if (statTime) {
                            statTime.textContent = data.elapsed_time || '00:00:00';
                        }
                    }
                    
                    if (data.status === 'iteration') {
                        self.addLog(`📌 ${data.message}`);
                    }
                    
                    if (data.status === 'agent_start') {
                        self.addLog(`⚡ ${data.agent} (${data.model})`);
                        // 更新当前迭代次数
                        currentIteration = data.iteration || 0;
                        // 更新Agent状态表格 - 使用模糊匹配找到对应的Agent行
                        const agentRows = document.querySelectorAll('#agent-status-body tr');
                        agentRows.forEach(row => {
                            const cells = row.querySelectorAll('td');
                            if (cells.length > 0) {
                                const cellAgentName = cells[0].textContent.trim();
                                // 模糊匹配：完全匹配或者名称包含
                                if (cellAgentName === data.agent || 
                                    cellAgentName.includes(data.agent) || 
                                    data.agent.includes(cellAgentName)) {
                                    const statusBadge = row.querySelector('.status-badge');
                                    if (statusBadge) {
                                        statusBadge.textContent = '运行中';
                                        statusBadge.className = 'status-badge badge-running';
                                    }
                                    // cells[0]: Agent名称, cells[1]: 状态, cells[2]: 模型
                                    if (cells.length >= 3) {
                                        cells[2].textContent = data.model || '-';
                                    }
                                    // cells[3]: 迭代次数
                                    if (cells.length >= 4) {
                                        cells[3].textContent = currentIteration;
                                    }
                                }
                            }
                        });
                    }
                    
                    if (data.status === 'chunk' && data.content) {
                        accumulatedContent += data.content;
                        scheduleUpdate();
                    }
                    
                    if (data.status === 'agent_complete') {
                        self.addLog(`✓ ${data.agent} 完成`);
                        // 更新Agent状态表格 - 使用模糊匹配找到对应的Agent行并填充统计信息
                        const agentRows = document.querySelectorAll('#agent-status-body tr');
                        agentRows.forEach(row => {
                            const cells = row.querySelectorAll('td');
                            if (cells.length > 0) {
                                const cellAgentName = cells[0].textContent.trim();
                                // 模糊匹配：完全匹配或者名称包含
                                if (cellAgentName === data.agent || 
                                    cellAgentName.includes(data.agent) || 
                                    data.agent.includes(cellAgentName)) {
                                    const statusBadge = row.querySelector('.status-badge');
                                    if (statusBadge) {
                                        statusBadge.textContent = '完成';
                                        statusBadge.className = 'status-badge badge-completed';
                                    }
                                    // 更新统计信息列
                                    // cells[0]: Agent名称, cells[1]: 状态, cells[2]: 模型
                                    // cells[3]: 迭代, cells[4]: Prompt Tokens, cells[5]: Completion Tokens, cells[6]: 耗时
                                    if (data.stats) {
                                        if (cells.length >= 4) cells[3].textContent = currentIteration || 0;
                                        if (cells.length >= 5) cells[4].textContent = data.stats.prompt_tokens || 0;
                                        if (cells.length >= 6) cells[5].textContent = data.stats.completion_tokens || 0;
                                        if (cells.length >= 7) cells[6].textContent = `${(data.stats.duration || 0).toFixed(2)}s`;
                                    }
                                }
                            }
                        });
                    }
                    
                    if (data.status === 'completed' && data.content) {
                        accumulatedContent = data.content;
                        inputContent.value = accumulatedContent;
                        self._updatePreviewDirect(accumulatedContent);
                        statWordcount.textContent = accumulatedContent.length;
                        self.addLog('✓ 处理完成');
                        statusDot.classList.remove('processing');
                        statusText.textContent = '就绪';
                        startBtn.disabled = false;
                        stopBtn.disabled = true;
                        
                        // 处理完成后确保滚动到预览底部
                        const previewContent = document.getElementById('preview-content');
                        if (previewContent) {
                            previewContent.scrollTop = previewContent.scrollHeight;
                        }
                        
                        // 将所有Agent状态更新为"完成"
                        const agentRows = document.querySelectorAll('#agent-status-body tr');
                        agentRows.forEach(row => {
                            const statusBadge = row.querySelector('.status-badge');
                            if (statusBadge && statusBadge.textContent === '运行中') {
                                statusBadge.textContent = '完成';
                                statusBadge.className = 'status-badge badge-completed';
                            }
                        });
                        
                        socket.close();
                    }
                } catch (e) {
                    console.error('解析WebSocket数据失败:', e);
                }
            };

            socket.onerror = (error) => {
                console.error('WebSocket error:', error);
                self.addLog(`✗ WebSocket错误: ${error.message || '未知错误'}`);
                statusDot.classList.remove('processing');
                statusText.textContent = '错误';
                startBtn.disabled = false;
                stopBtn.disabled = true;
            };

            socket.onclose = (event) => {
                console.log('WebSocket closed:', event);
                if (updateTimeout) {
                    clearTimeout(updateTimeout);
                }
            };

        } catch (error) {
            console.error('Stream processing error:', error);
            self.addLog(`✗ 流式处理失败: ${error.message}`);
            self.updateStatus('error');
        }
    }

    markdownToHtml(text) {
        let html = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        // 先提取所有表格，避免被其他规则干扰
        const tables = [];
        const tableRegex = /\|[^\n]+\|\n\|[-:| ]+\|\n(\|[^\n]+\|\n?)+/g;
        html = html.replace(tableRegex, (match) => {
            const placeholder = `__TABLE_${tables.length}__`;
            tables.push(match.trim());
            return placeholder;
        });

        // 按双换行分割成块
        const blocks = html.split(/\n\n+/);
        const result = [];

        blocks.forEach(block => {
            block = block.trim();
            if (!block) return;

            // 检查是否包含表格占位符
            if (block.includes('__TABLE_')) {
                // 处理包含表格的块
                const parts = block.split(/(__TABLE_\d+__)/);
                parts.forEach(part => {
                    if (part.startsWith('__TABLE_')) {
                        const idx = parseInt(part.match(/\d+/)[0]);
                        result.push(this._parseTable(tables[idx]));
                    } else if (part.trim()) {
                        result.push(`<p>${this._escapeBlock(part.trim())}</p>`);
                    }
                });
            } else if (block.startsWith('```')) {
                const match = block.match(/```(\w*)\n([\s\S]*?)```/);
                if (match) {
                    result.push(`<pre><code class="language-${match[1]}">${match[2]}</code></pre>`);
                } else {
                    result.push(this._escapeBlock(block));
                }
            } else if (block.startsWith('>')) {
                const lines = block.split('\n');
                const quoted = lines.map(l => l.replace(/^>\s*/, '').trim()).filter(l => l);
                result.push(`<blockquote>${quoted.join('<br>')}</blockquote>`);
            } else if (/^---+$/.test(block)) {
                result.push('<hr>');
            } else if (/^#+\s/.test(block)) {
                const match = block.match(/^(#+)\s(.*)/);
                if (match) {
                    const level = match[1].length;
                    const content = match[2];
                    result.push(`<h${level}>${content}</h${level}>`);
                } else {
                    result.push(this._escapeBlock(block));
                }
            } else if (/^- /.test(block) || /^\d+\. /.test(block)) {
                const lines = block.split('\n');
                const items = lines
                    .map(l => l.replace(/^- |^\d+\. /, '').trim())
                    .filter(l => l);
                if (items.length > 0) {
                    const listType = /^\d+\. /.test(lines[0]) ? 'ol' : 'ul';
                    result.push(`<${listType}>` + items.map(item => `<li>${this._escapeInline(item)}</li>`).join('') + `</${listType}>`);
                } else {
                    result.push(this._escapeBlock(block));
                }
            } else {
                result.push(`<p>${this._escapeBlock(block)}</p>`);
            }
        });

        return result.join('');
    }

    _parseTable(tableText) {
        const lines = tableText.split('\n');
        if (lines.length < 2) return `<p>${this._escapeBlock(tableText)}</p>`;

        const headerLine = lines[0];
        const headers = headerLine.split('|').filter(h => h.trim()).map(h => h.trim());

        const separatorLine = lines[1];
        const separators = separatorLine.split('|').filter(s => s.trim());
        const alignments = separators.map(s => {
            if (s.startsWith(':') && s.endsWith(':')) return 'center';
            if (s.endsWith(':')) return 'right';
            return 'left';
        });

        const dataLines = lines.slice(2);
        const rows = dataLines.map(line => {
            return line.split('|').filter(c => c.trim()).map(c => c.trim());
        });

        let tableHtml = '<table class="markdown-table"><thead><tr>';
        headers.forEach((h, i) => {
            const align = alignments[i] || 'left';
            tableHtml += `<th style="text-align:${align}">${h}</th>`;
        });
        tableHtml += '</tr></thead><tbody>';

        rows.forEach(row => {
            tableHtml += '<tr>';
            row.forEach((cell, i) => {
                const align = alignments[i] || 'left';
                tableHtml += `<td style="text-align:${align}">${cell}</td>`;
            });
            tableHtml += '</tr>';
        });
        tableHtml += '</tbody></table>';

        return tableHtml;
    }

    _escapeBlock(text) {
        let html = text;
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
        html = html.replace(/\n/g, '<br>');
        return html;
    }

    _escapeInline(text) {
        let html = text;
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
        return html;
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    window.app = new App();
});