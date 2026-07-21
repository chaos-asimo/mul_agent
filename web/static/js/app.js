class App {
    constructor() {
        this.baseUrl = '';
        this.currentModalType = null;
        this.currentEditId = null;
        this.statusInterval = null;
        this.statusIntervalTime = 3000;
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
        this.initAIChat();
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
        
        // 搜索日志弹窗
        document.getElementById('stat-search-item').addEventListener('click', () => this.openSearchLogModal());
        
        // Skills相关
        document.getElementById('open-skill-config-btn').addEventListener('click', () => this.openSkillConfigModal());
        document.getElementById('add-new-skill-btn').addEventListener('click', () => this.createNewSkill());
        document.getElementById('skills-list').addEventListener('click', (e) => this.handleSkillAction(e));
        
        // 视频模型相关
        document.getElementById('generate-video-btn').addEventListener('click', () => this.generateVideo());
        document.getElementById('clear-video-btn').addEventListener('click', () => this.clearVideoForm());
        document.getElementById('optimize-prompt-btn').addEventListener('click', () => this.optimizePrompt());
        
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
        document.getElementById('processing-select-agents-btn').addEventListener('click', () => this.openProcessingAgentSelectDialog());

        // 保存文档
        document.getElementById('save-btn').addEventListener('click', () => this.saveDocument());

        // 导出日志
        document.getElementById('export-log-btn').addEventListener('click', () => this.exportLogs());

        // 退出登录
        document.getElementById('logout-btn').addEventListener('click', () => this.logout());

        // 日志清空
        document.getElementById('clear-log-btn').addEventListener('click', () => this.clearLog());
        
        // 模型调用日志
        document.getElementById('model-calls-btn').addEventListener('click', () => this.showModelCallsDialog());

        // 卜卦相关
        document.getElementById('start-divination-btn').addEventListener('click', () => this.startDivination());
        document.getElementById('reset-divination-btn').addEventListener('click', () => this.resetDivination());
        document.getElementById('ai-explain-btn').addEventListener('click', () => this.startAiExplain());
        document.getElementById('yijing-history-btn').addEventListener('click', () => this.openYijingHistory());
        
        // 龙虾Claw相关
        this.initClawChat();

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
        
        // 如果切换到视频模型面板，加载视频模型列表
        if (tabName === 'video-models') {
            this.loadVideoModels();
        }
        
        // 如果切换到统计面板，加载统计数据
        if (tabName === 'statistics') {
            this.loadStatistics();
        }
    }

    async loadAgents() {
        try {
            const response = await fetch(`${this.baseUrl}/api/agents`);
            const result = await response.json();
            const groups = result.groups || [];
            this.renderAgents(groups);
        } catch (error) {
            console.error('加载Agents失败:', error);
        }
    }

    renderAgents(groups) {
        const list = document.getElementById('agents-list');
        
        let allAgents = [];
        groups.forEach(group => {
            if (group.agents) {
                allAgents = allAgents.concat(group.agents);
            }
        });
        
        if (allAgents.length === 0) {
            list.innerHTML = '<p style="text-align: center; color: #94a3b8; padding: 20px;">暂无Agent</p>';
            return;
        }

        let html = '';
        groups.forEach(group => {
            if (!group.agents || group.agents.length === 0) return;
            
            html += `
                <div style="margin-bottom: 25px;">
                    <h3 style="color: ${group.color}; margin-bottom: 15px; font-size: 16px; font-weight: 600;">
                        <i class="fas ${group.icon}"></i> ${group.name} (${group.agents.length})
                    </h3>
                    <div class="config-grid">
            `;
            
            group.agents.sort((a, b) => a.order - b.order);
            
            group.agents.forEach((agent, index) => {
                html += `
                    <div class="config-card" data-id="${agent.id}" draggable="true" data-order="${agent.order}">
                        <div class="card-header">
                            <span class="drag-handle" title="拖拽排序">
                                <i class="fas fa-grip-vertical"></i>
                            </span>
                            <span class="order-badge">#${index + 1}</span>
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
                                <span class="badge badge-info">${agent.model_name || agent.model_id || '未绑定'}</span>
                                ${agent.enabled ? '<span class="badge badge-success">已启用</span>' : '<span class="badge badge-warning">已禁用</span>'}
                            </div>
                        </div>
                    </div>
                `;
            });
            
            html += '</div></div>';
        });

        list.innerHTML = html;
        this.setupDragSorting();
    }

    setupDragSorting() {
        const list = document.getElementById('agents-list');
        let draggedItem = null;
        let dragOverItem = null;

        list.addEventListener('dragstart', (e) => {
            draggedItem = e.target.closest('.config-card');
            draggedItem.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
        });

        list.addEventListener('dragend', (e) => {
            draggedItem?.classList.remove('dragging');
            draggedItem = null;
            dragOverItem = null;
        });

        list.addEventListener('dragover', (e) => {
            e.preventDefault();
            const target = e.target.closest('.config-card');
            if (target && target !== draggedItem) {
                dragOverItem = target;
                target.classList.add('drag-over');
            }
        });

        list.addEventListener('dragleave', (e) => {
            const target = e.target.closest('.config-card');
            target?.classList.remove('drag-over');
        });

        list.addEventListener('drop', (e) => {
            e.preventDefault();
            const target = e.target.closest('.config-card');
            if (target && draggedItem && target !== draggedItem) {
                target.classList.remove('drag-over');
                
                const list = document.getElementById('agents-list');
                const cards = Array.from(list.querySelectorAll('.config-card'));
                const draggedIndex = cards.indexOf(draggedItem);
                const targetIndex = cards.indexOf(target);
                
                if (draggedIndex < targetIndex) {
                    list.insertBefore(draggedItem, target.nextSibling);
                } else {
                    list.insertBefore(draggedItem, target);
                }
                
                this.saveAgentOrder();
            }
        });
    }

    async saveAgentOrder() {
        const list = document.getElementById('agents-list');
        const cards = list.querySelectorAll('.config-card');
        
        try {
            const response = await fetch(`${this.baseUrl}/api/agents`);
            const result = await response.json();
            const groups = result.groups || [];
            
            const agentMap = {};
            groups.forEach(group => {
                if (group.agents) {
                    group.agents.forEach(agent => {
                        agentMap[agent.id] = agent;
                    });
                }
            });

            for (let index = 0; index < cards.length; index++) {
                const card = cards[index];
                const agentId = card.dataset.id;
                const agent = agentMap[agentId];
                
                if (agent) {
                    agent.order = index;
                    
                    const response = await fetch(`${this.baseUrl}/api/agents/${agentId}`, {
                        method: 'PUT',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify(agent)
                    });
                    
                    if (!response.ok) {
                        throw new Error('保存失败');
                    }
                }
            }
            
            this.loadAgents();
            this.updateAgentStatusOrder();
        } catch (error) {
            console.error('保存排序失败:', error);
            alert('保存排序失败，请重试');
        }
    }

    updateAgentStatusOrder() {
        const configCards = document.querySelectorAll('#agents-list .config-card');
        const statusBody = document.getElementById('agent-status-body');
        const statusRows = Array.from(statusBody.querySelectorAll('tr'));
        
        const sortedRows = [];
        configCards.forEach(card => {
            const agentId = card.dataset.id;
            const row = statusRows.find(r => r.dataset.id === agentId);
            if (row) {
                sortedRows.push(row);
            }
        });
        
        statusBody.innerHTML = '';
        sortedRows.forEach(row => {
            statusBody.appendChild(row);
        });
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
                    <textarea id="skill-new-prompt" class="form-control" rows="4" placeholder="请处理以下内容：\n{content}">请处理以下内容：
{content}</textarea>
                </div>
                
                <div class="form-group">
                    <label>脚本内容 (Python)</label>
                    <textarea id="skill-new-script" class="form-control" rows="4" placeholder="def execute(input_data):&#10;    return {'result': '处理完成'}"></textarea>
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
        
        const executor = document.getElementById('skill-new-executor').value;
        const promptTemplate = document.getElementById('skill-new-prompt').value.trim();
        
        if (executor === 'llm' && !promptTemplate) {
            alert('选择"AI模型"执行器时必须填写提示模板');
            return;
        }
        
        if (executor === 'script' && !document.getElementById('skill-new-script').value.trim()) {
            alert('选择"脚本"执行器时必须填写脚本内容');
            return;
        }
        
        const skillData = {
            name: name,
            description: document.getElementById('skill-new-description').value,
            skill_type: document.getElementById('skill-new-type').value,
            executor: executor,
            enabled: document.getElementById('skill-new-enabled').checked,
            icon: document.getElementById('skill-new-icon').value || 'fas fa-cog',
            prompt_template: promptTemplate,
            script: document.getElementById('skill-new-script').value || '',
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
                alert('创建失败: ' + (data.errors ? data.errors.join('\n') : data.message));
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
        document.getElementById('form-model-type').value = model?.model_type || 'text';
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
            data.model_type = document.getElementById('form-model-type').value;
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
                const result = await response.json();
                const groups = result.groups || [];
                let agent = null;
                groups.forEach(group => {
                    if (group.agents) {
                        const found = group.agents.find(a => a.id === agentId);
                        if (found) agent = found;
                    }
                });
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
                resolve({ selected: [] });
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
                    row.style.display = '';
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

    async logout() {
        try {
            const response = await fetch(`${this.baseUrl}/api/logout`, {
                method: 'POST'
            });
            
            const result = await response.json();
            if (result.status === 'success') {
                window.location.href = '/login';
            } else {
                alert(result.message || '退出失败');
            }
        } catch (error) {
            alert(`退出失败: ${error.message}`);
        }
    }

    startStatusPolling() {
        this.stopStatusPolling();
        this.statusIntervalTime = 3000;

        const poll = async () => {
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

                // 更新文档内容（只在处理中时更新，避免完成后重复刷新）
                if (status.status === 'processing' && status.current_document) {
                    document.getElementById('input-content').value = status.current_document;
                    this.updatePreview(status.current_document, false); // 使用非流式更新
                    
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

                    // 更新当前运行的Agent状态（只在处理中时更新）
                    if (status.status === 'processing' && status.state.current_agent_id) {
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

            // 根据运行状态动态调整轮询频率
            let targetInterval = 3000;
            if (status && status.status === 'processing') {
                targetInterval = 800;
            }
            if (this.statusIntervalTime !== targetInterval) {
                this.statusIntervalTime = targetInterval;
                clearInterval(this.statusInterval);
                this.statusInterval = setInterval(poll, targetInterval);
            }
        };

        this.statusInterval = setInterval(poll, this.statusIntervalTime);
    }

    stopStatusPolling() {
        if (this.statusInterval) {
            clearInterval(this.statusInterval);
            this.statusInterval = null;
        }
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
        // 默认切换到"预览"视图
        const previewBtn = document.querySelector('[data-view="preview"]');
        if (previewBtn && !previewBtn.classList.contains('active')) {
            previewBtn.classList.add('active');
            document.querySelector('[data-view="markdown"]').classList.remove('active');
        }
        
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

            // 停止状态轮询，使用WebSocket更新
            if (this.statusInterval) {
                clearInterval(this.statusInterval);
                this.statusInterval = null;
            }

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
                
                const agentTableBody = document.getElementById('agent-status-body');
                const agentRows = Array.from(document.querySelectorAll('#agent-status-body tr'));
                
                if (self.processingAgentIds.length > 0 && agentTableBody) {
                    agentRows.sort((a, b) => {
                        const idA = a.dataset.id;
                        const idB = b.dataset.id;
                        const idxA = self.processingAgentIds.indexOf(idA);
                        const idxB = self.processingAgentIds.indexOf(idB);
                        return idxA - idxB;
                    });
                    
                    agentRows.forEach(row => {
                        agentTableBody.appendChild(row);
                    });
                }
                
                agentRows.forEach(row => {
                    const agentId = row.dataset.id;
                    const shouldShow = !self.processingAgentIds.length || self.processingAgentIds.includes(agentId);
                    row.style.display = shouldShow ? '' : 'none';
                    
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
                    enable_search: enableSearch,
                    agent_ids: self.processingAgentIds
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
                        
                        // 处理完成后更新进度条到100%
                        const progressFill = document.getElementById('progress-fill');
                        const progressText = document.getElementById('progress-text');
                        if (progressFill) {
                            progressFill.style.width = '100%';
                        }
                        if (progressText) {
                            progressText.textContent = '100%';
                        }
                        
                        // 处理完成后确保滚动到预览底部
                        const previewContent = document.getElementById('preview-content');
                        if (previewContent) {
                            previewContent.scrollTop = previewContent.scrollHeight;
                        }
                        
                        // 将所有Agent状态更新为"完成"（确保最后一个Agent也被更新）
                        const agentRows = document.querySelectorAll('#agent-status-body tr');
                        agentRows.forEach(row => {
                            const statusBadge = row.querySelector('.status-badge');
                            if (statusBadge) {
                                const currentStatus = statusBadge.textContent;
                                if (currentStatus === '运行中' || currentStatus === '就绪') {
                                    statusBadge.textContent = '完成';
                                    statusBadge.className = 'status-badge badge-completed';
                                }
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
                // 清除可能存在的streamTimer
                if (self.streamTimer) {
                    clearInterval(self.streamTimer);
                    self.streamTimer = null;
                }
                // 重新启动状态轮询
                self.startStatusPolling();
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
        const headers = headerLine.split('|').filter(h => h.trim()).map(h => this._escapeInline(h.trim()));

        const separatorLine = lines[1];
        const separators = separatorLine.split('|').filter(s => s.trim());
        const alignments = separators.map(s => {
            if (s.startsWith(':') && s.endsWith(':')) return 'center';
            if (s.endsWith(':')) return 'right';
            return 'left';
        });

        const dataLines = lines.slice(2);
        const rows = dataLines.map(line => {
            return line.split('|').filter(c => c.trim()).map(c => this._escapeInline(c.trim()));
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
        html = html.replace(/&lt;br&gt;/g, '<br>');
        html = html.replace(/&lt;br\/&gt;/g, '<br>');
        html = html.replace(/&lt;p&gt;/g, '');
        html = html.replace(/&lt;\/p&gt;/g, '<br>');
        html = html.replace(/&lt;b&gt;/g, '<strong>');
        html = html.replace(/&lt;\/b&gt;/g, '</strong>');
        html = html.replace(/&lt;i&gt;/g, '<em>');
        html = html.replace(/&lt;\/i&gt;/g, '</em>');
        html = html.replace(/&lt;strong&gt;/g, '<strong>');
        html = html.replace(/&lt;\/strong&gt;/g, '</strong>');
        html = html.replace(/&lt;em&gt;/g, '<em>');
        html = html.replace(/&lt;\/em&gt;/g, '</em>');
        html = html.replace(/&lt;ul&gt;/g, '<ul>');
        html = html.replace(/&lt;\/ul&gt;/g, '</ul>');
        html = html.replace(/&lt;ol&gt;/g, '<ol>');
        html = html.replace(/&lt;\/ol&gt;/g, '</ol>');
        html = html.replace(/&lt;li&gt;/g, '<li>');
        html = html.replace(/&lt;\/li&gt;/g, '</li>');
        html = html.replace(/&lt;span&gt;/g, '<span>');
        html = html.replace(/&lt;\/span&gt;/g, '</span>');
        html = html.replace(/&lt;div&gt;/g, '<div>');
        html = html.replace(/&lt;\/div&gt;/g, '</div>');
        html = html.replace(/&lt;hr&gt;/g, '<hr>');
        html = html.replace(/&lt;br\s*\/&gt;/g, '<br>');
        return html;
    }

    _escapeInline(text) {
        let html = text;
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
        html = html.replace(/&lt;br&gt;/g, '<br>');
        html = html.replace(/&lt;br\/&gt;/g, '<br>');
        html = html.replace(/&lt;p&gt;/g, '');
        html = html.replace(/&lt;\/p&gt;/g, '<br>');
        return html;
    }

    openSearchLogModal() {
        const modal = document.getElementById('search-log-modal');
        modal.style.display = 'block';
        this.loadSearchLogs();
    }

    closeSearchLogModal() {
        const modal = document.getElementById('search-log-modal');
        modal.style.display = 'none';
    }

    async loadSearchLogs() {
        try {
            const response = await fetch(`${this.baseUrl}/api/status`);
            const data = await response.json();
            
            const searchLogs = data.state?.search_logs || [];
            const container = document.getElementById('search-log-list');
            
            if (searchLogs.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-search"></i>
                        <p>暂无搜索记录</p>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = searchLogs.map((log, index) => `
                <div class="search-log-item">
                    <div class="search-log-header">
                        <span class="search-log-iteration">#${log.iteration}</span>
                        <span class="search-log-time">${log.timestamp}</span>
                        <span class="search-log-count">${log.result_count} 条结果</span>
                        <span class="search-log-duration">${log.elapsed_time}s</span>
                    </div>
                    <div class="search-log-query">
                        <i class="fas fa-search"></i>
                        <span>${log.query}</span>
                    </div>
                    ${log.error ? `
                        <div class="search-log-error">
                            <i class="fas fa-exclamation-circle"></i>
                            <span>${log.error}</span>
                        </div>
                    ` : ''}
                    <div class="search-log-results">
                        ${log.results.map((result, idx) => `
                            <div class="search-log-result">
                                <div class="result-title">
                                    <span class="result-number">${idx + 1}</span>
                                    <a href="${result.url}" target="_blank" class="result-link">${result.title}</a>
                                </div>
                                ${result.snippet ? `<p class="result-snippet">${result.snippet}</p>` : ''}
                            </div>
                        `).join('')}
                    </div>
                </div>
            `).join('');
        } catch (error) {
            console.error('加载搜索日志失败:', error);
        }
    }

    async startDivination() {
        const startBtn = document.getElementById('start-divination-btn');
        const resetBtn = document.getElementById('reset-divination-btn');
        const divinationContent = document.getElementById('divination-content');
        const coinsContainer = document.getElementById('coins-container');
        const hexagramContainer = document.getElementById('hexagram-container');
        const solutionContainer = document.getElementById('solution-container');

        startBtn.disabled = true;
        startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 摇卦中...';

        coinsContainer.innerHTML = '';
        hexagramContainer.innerHTML = '';
        solutionContainer.innerHTML = '';

        const content = divinationContent.value.trim();

        try {
            const url = content 
                ? `${this.baseUrl}/api/yijing/shake?content=${encodeURIComponent(content)}`
                : `${this.baseUrl}/api/yijing/shake`;
            const response = await fetch(url);
            const result = await response.json();

            if (result.status !== 'success') {
                alert('摇卦失败: ' + result.message);
                return;
            }

            const data = result.data;

            for (let i = 0; i < data.yao_results.length; i++) {
                const yao = data.yao_results[i];
                await this.renderCoinResult(yao, i + 1, coinsContainer);
                await new Promise(r => setTimeout(r, 600));
            }

            await new Promise(r => setTimeout(r, 500));
            this.renderHexagramResult(data, hexagramContainer);
            this.renderSolution(data, solutionContainer);

            this.currentDivinationData = data;
            const aiExplainBtn = document.getElementById('ai-explain-btn');
            if (aiExplainBtn) {
                aiExplainBtn.disabled = false;
            }

            resetBtn.disabled = false;
            startBtn.innerHTML = '<i class="fas fa-play"></i> 开始摇卦';
        } catch (error) {
            console.error('摇卦失败:', error);
            alert('摇卦失败: ' + error.message);
            startBtn.innerHTML = '<i class="fas fa-play"></i> 开始摇卦';
            startBtn.disabled = false;
        }
    }

    renderCoinResult(yao, step, container) {
        return new Promise(resolve => {
            const coinItem = document.createElement('div');
            coinItem.className = 'coin-item';
            
            let coinHtml = '';
            if (yao.coin_result === '三背') {
                coinHtml = '<div class="coin"><div class="coin-back"></div></div><div class="coin"><div class="coin-back"></div></div><div class="coin"><div class="coin-back"></div></div>';
            } else if (yao.coin_result === '两背一字') {
                coinHtml = '<div class="coin"><div class="coin-back"></div></div><div class="coin"><div class="coin-back"></div></div><div class="coin"><div class="coin-face"></div></div>';
            } else if (yao.coin_result === '两字一背') {
                coinHtml = '<div class="coin"><div class="coin-back"></div></div><div class="coin"><div class="coin-face"></div></div><div class="coin"><div class="coin-face"></div></div>';
            } else if (yao.coin_result === '三字') {
                coinHtml = '<div class="coin"><div class="coin-face"></div></div><div class="coin"><div class="coin-face"></div></div><div class="coin"><div class="coin-face"></div></div>';
            }
            
            coinItem.innerHTML = `
                <div class="coin-step">第${step}次</div>
                <div class="coin-icons">${coinHtml}</div>
                <div class="coin-result">${yao.coin_result}</div>
                <div class="coin-value">${yao.value} · ${yao.type}</div>
                <div class="yao-display ${yao.is_yang ? 'yang' : 'yin'} ${yao.is_change ? 'change' : ''}">
                    ${yao.is_yang ? '—' : '--'}
                    ${yao.is_change ? '<span class="change-mark">变</span>' : ''}
                </div>
            `;
            
            coinItem.style.opacity = '0';
            coinItem.style.transform = 'translateY(20px)';
            container.appendChild(coinItem);
            
            requestAnimationFrame(() => {
                coinItem.style.transition = 'all 0.5s ease';
                coinItem.style.opacity = '1';
                coinItem.style.transform = 'translateY(0)';
            });
            
            setTimeout(resolve, 500);
        });
    }

    renderHexagramResult(data, container) {
        const original = data.original_hexagram;
        const changed = data.changed_hexagram;
        const yaoResults = data.yao_results;

        const renderHexagramYao = (yaoList, isChanged) => {
            let yaoHtml = '';
            for (let i = 5; i >= 0; i--) {
                const yao = yaoList[i];
                const yaoClass = yao.is_yang ? 'yang' : 'yin';
                const changeClass = isChanged && yao.is_change ? 'change' : '';
                const symbol = yao.is_yang ? '—' : '--';
                yaoHtml += `
                    <div class="hex-yao-row ${yaoClass} ${changeClass}">
                        <span class="hex-yao-symbol">${symbol}</span>
                    </div>
                `;
            }
            return yaoHtml;
        };

        let html = `
            <div class="hexagram-layout">
                <div class="hexagram-left">
                    <div class="hexagram-yao-list">
                        <div class="yao-list-title">六爻排列（自下而上）</div>
                        <div class="yao-list-items">
        `;

        yaoResults.forEach(yao => {
            const yaoClass = yao.is_yang ? 'yang' : 'yin';
            const changeClass = yao.is_change ? 'change' : '';
            html += `
                <div class="yao-item ${yaoClass} ${changeClass}">
                    <span class="yao-name">${yao.name}</span>
                    <span class="yao-symbol">${yao.is_yang ? '—' : '--'}</span>
                    <span class="yao-type">${yao.type}(${yao.value})</span>
                    ${yao.is_change ? '<span class="yao-change">变</span>' : ''}
                </div>
            `;
        });

        html += `
                        </div>
                    </div>
                </div>
                <div class="hexagram-right">
                    <div class="hexagram-card hexagram-original-card">
                        <div class="hexagram-title">本卦 · ${original.full_name}</div>
                        <div class="hexagram-yao-display">
                            <div class="hex-upper-label">上卦</div>
                            <div class="hex-yao-stack">
                                ${renderHexagramYao(yaoResults, false)}
                            </div>
                            <div class="hex-lower-label">下卦</div>
                        </div>
                        <div class="hexagram-name">第${original.number}卦</div>
                        <div class="hexagram-desc">${original.description}</div>
                    </div>
        `;

        if (changed) {
            html += `
                <div class="hexagram-change-arrow-horizontal">
                    <span>变</span>
                    <i class="fas fa-arrow-right"></i>
                </div>
                <div class="hexagram-card hexagram-changed-card">
                    <div class="hexagram-title">之卦 · ${changed.full_name}</div>
                    <div class="hexagram-yao-display">
                        <div class="hex-upper-label">上卦</div>
                        <div class="hex-yao-stack">
                            ${renderHexagramYao(yaoResults.map((y, i) => {
                                return { is_yang: y.is_change ? !y.is_yang : y.is_yang, is_change: y.is_change };
                            }), true)}
                        </div>
                        <div class="hex-lower-label">下卦</div>
                    </div>
                    <div class="hexagram-name">第${changed.number}卦</div>
                    <div class="hexagram-desc">${changed.description}</div>
                </div>
            `;
        }

        html += `
                </div>
            </div>
        `;

        container.innerHTML = html;
    }

    renderSolution(data, container) {
        const lines = data.solution_text.split('\n');
        let html = '<div class="solution-content">';
        
        if (data.content) {
            html += `<div class="solution-content-item"><span class="solution-label">占卜内容：</span><span class="solution-value">${data.content}</span></div>`;
            html += '<div class="solution-line">&nbsp;</div>';
        }
        
        lines.forEach(line => {
            if (line.startsWith('【')) {
                html += `<div class="solution-section">${line}</div>`;
            } else if (line.trim()) {
                html += `<div class="solution-line">${line}</div>`;
            } else {
                html += '<div class="solution-line">&nbsp;</div>';
            }
        });
        
        html += '</div>';
        container.innerHTML = html;
    }

    resetDivination() {
        const startBtn = document.getElementById('start-divination-btn');
        const resetBtn = document.getElementById('reset-divination-btn');
        const aiExplainBtn = document.getElementById('ai-explain-btn');
        const divinationContent = document.getElementById('divination-content');
        const coinsContainer = document.getElementById('coins-container');
        const hexagramContainer = document.getElementById('hexagram-container');
        const solutionContainer = document.getElementById('solution-container');
        const aiSolutionContainer = document.getElementById('ai-solution-container');

        if (this.aiExplainEventSource) {
            this.aiExplainEventSource.close();
            this.aiExplainEventSource = null;
        }

        startBtn.disabled = false;
        aiExplainBtn.disabled = true;

        divinationContent.value = '';

        coinsContainer.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-coins" style="font-size: 48px; margin-bottom: 15px;"></i>
                <p>点击上方按钮开始摇卦</p>
                <p style="font-size: 12px; color: #94a3b8;">将依次进行六次铜钱投掷</p>
            </div>
        `;
        
        hexagramContainer.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-book-open" style="font-size: 48px; margin-bottom: 15px;"></i>
                <p>摇卦后显示卦象结果</p>
            </div>
        `;
        
        solutionContainer.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-scroll" style="font-size: 48px; margin-bottom: 15px;"></i>
                <p>摇卦后显示解卦内容</p>
            </div>
        `;

        aiSolutionContainer.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-robot" style="font-size: 48px; margin-bottom: 15px;"></i>
                <p>点击"AI深度解卦"获取AI解卦</p>
            </div>
        `;

        this.currentDivinationData = null;
    }

    async saveDivinationResult(data) {
        try {
            const aiSolutionContainer = document.getElementById('ai-solution-container');
            const aiSolution = aiSolutionContainer ? aiSolutionContainer.innerHTML : '';
            
            await fetch(`${this.baseUrl}/api/yijing/save`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    content: data.content || '',
                    original_hexagram: data.original_hexagram,
                    changed_hexagram: data.changed_hexagram,
                    yao_results: data.yao_results,
                    change_count: data.change_count,
                    change_yao_positions: data.change_yao_positions,
                    solution_text: data.solution_text,
                    ai_solution: aiSolution
                })
            });
        } catch (error) {
            console.error('保存卜卦结果失败:', error);
        }
    }

    openYijingHistory() {
        document.getElementById('yijing-history-modal').style.display = 'flex';
        this.loadYijingHistory();
    }

    async loadYijingHistory() {
        const listEl = document.getElementById('yijing-history-list');
        try {
            const response = await fetch(`${this.baseUrl}/api/yijing/history`);
            const result = await response.json();
            
            if (result.status === 'success') {
                const history = result.data;
                
                if (history.length === 0) {
                    listEl.innerHTML = `
                        <div class="empty-state">
                            <i class="fas fa-inbox" style="font-size: 48px; margin-bottom: 15px; color: #94a3b8;"></i>
                            <p>暂无卜卦记录</p>
                        </div>
                    `;
                    return;
                }
                
                listEl.innerHTML = history.map(item => `
                    <div class="history-item" style="
                        padding: 12px;
                        margin-bottom: 8px;
                        background: white;
                        border-radius: 6px;
                        border: 1px solid #e2e8f0;
                        transition: all 0.2s;
                    " onmouseover="this.style.borderColor='#c0392b';this.style.boxShadow='0 2px 8px rgba(192,57,43,0.1)'" 
                       onmouseout="this.style.borderColor='#e2e8f0';this.style.boxShadow='none'">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div style="flex: 1; min-width: 0; cursor: pointer;" onclick="window.app.restoreYijingRecord('${item.session_id}')">
                                <div style="font-weight: 600; color: #1e293b; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                                    ${this.escapeHtml(item.content || '无占卜内容')}
                                </div>
                                <div style="font-size: 12px; color: #64748b;">
                                    ${item.date} · ${item.original_name} · 变爻: ${item.change_count}
                                </div>
                            </div>
                            <div style="display: flex; align-items: center; margin-left: 10px;">
                                <button onclick="event.stopPropagation(); window.app.deleteYijingRecord('${item.session_id}')" 
                                        style="border: none; background: none; color: #94a3b8; cursor: pointer; padding: 4px 8px; border-radius: 4px;"
                                        onmouseover="this.style.color='#ef4444';this.style.background='#fee2e2'"
                                        onmouseout="this.style.color='#94a3b8';this.style.background='none'">
                                    <i class="fas fa-trash"></i>
                                </button>
                                <i class="fas fa-chevron-right" style="color: #94a3b8; margin-left: 8px; cursor: pointer;" 
                                   onclick="window.app.restoreYijingRecord('${item.session_id}')"></i>
                            </div>
                        </div>
                    </div>
                `).join('');
            }
        } catch (error) {
            console.error('加载卜卦历史失败:', error);
            listEl.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-exclamation-circle" style="font-size: 48px; margin-bottom: 15px; color: #ef4444;"></i>
                    <p>加载失败: ${error.message}</p>
                </div>
            `;
        }
    }

    async restoreYijingRecord(sessionId) {
        try {
            const response = await fetch(`${this.baseUrl}/api/yijing/history/${sessionId}`);
            const result = await response.json();
            
            if (result.status === 'success') {
                const data = result.data;
                
                document.getElementById('yijing-history-modal').style.display = 'none';
                document.getElementById('divination-content').value = data.content || '';
                
                const coinsContainer = document.getElementById('coins-container');
                const hexagramContainer = document.getElementById('hexagram-container');
                const solutionContainer = document.getElementById('solution-container');
                const aiSolutionContainer = document.getElementById('ai-solution-container');
                
                coinsContainer.innerHTML = '';
                for (let i = 0; i < data.yao_results.length; i++) {
                    const yao = data.yao_results[i];
                    await this.renderCoinResult(yao, i + 1, coinsContainer);
                    await new Promise(r => setTimeout(r, 300));
                }
                
                await new Promise(r => setTimeout(r, 300));
                this.renderHexagramResult(data, hexagramContainer);
                this.renderSolution(data, solutionContainer);
                
                if (data.ai_solution) {
                    aiSolutionContainer.innerHTML = data.ai_solution;
                } else {
                    aiSolutionContainer.innerHTML = `
                        <div class="empty-state">
                            <i class="fas fa-robot" style="font-size: 48px; margin-bottom: 15px;"></i>
                            <p>点击"AI深度解卦"获取AI解卦</p>
                        </div>
                    `;
                }
                
                this.currentDivinationData = data;
                const aiExplainBtn = document.getElementById('ai-explain-btn');
                if (aiExplainBtn) {
                    aiExplainBtn.disabled = false;
                }
                
                const resetBtn = document.getElementById('reset-divination-btn');
                if (resetBtn) {
                    resetBtn.disabled = false;
                }
            } else {
                alert('加载记录失败: ' + result.message);
            }
        } catch (error) {
            console.error('还原卜卦记录失败:', error);
            alert('还原失败: ' + error.message);
        }
    }

    async deleteYijingRecord(sessionId) {
        if (!confirm('确定要删除这条卜卦记录吗？')) {
            return;
        }
        try {
            const response = await fetch(`${this.baseUrl}/api/yijing/history/${sessionId}`, {
                method: 'DELETE'
            });
            const result = await response.json();
            if (result.status === 'success') {
                this.loadYijingHistory();
            } else {
                alert('删除失败: ' + result.message);
            }
        } catch (error) {
            console.error('删除卜卦记录失败:', error);
            alert('删除失败: ' + error.message);
        }
    }

    startAiExplain() {
        const aiExplainBtn = document.getElementById('ai-explain-btn');
        const aiSolutionContainer = document.getElementById('ai-solution-container');

        if (!this.currentDivinationData) {
            alert('请先摇卦');
            return;
        }

        const data = this.currentDivinationData;
        const content = document.getElementById('divination-content').value || '';

        aiExplainBtn.disabled = true;
        aiExplainBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> AI解卦中...';

        aiSolutionContainer.innerHTML = `
            <div class="ai-solution-loading">
                <div class="ai-solution-loading-header">
                    <i class="fas fa-robot"></i>
                    <span>AI正在解卦中，请稍候...</span>
                </div>
                <div class="ai-solution-content" id="ai-solution-content"></div>
            </div>
        `;

        const requestBody = {
            content: content,
            original: data.original_hexagram || {},
            changed: data.changed_hexagram || null,
            yao_results: data.yao_results,
            change_count: data.change_count,
            change_yao_positions: data.change_yao_positions || []
        };

        this.startAiExplainFetch(requestBody, aiExplainBtn, aiSolutionContainer);
    }

    async startAiExplainFetch(requestBody, aiExplainBtn, solutionContainer) {
        try {
            const response = await fetch(`${this.baseUrl}/api/yijing/ai-explain`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestBody)
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let fullContent = '';
            let modelName = '';
            let promptText = '';

            solutionContainer.innerHTML = `
                <div class="ai-solution-loading">
                    <div class="ai-solution-loading-header">
                        <i class="fas fa-robot"></i>
                        <span>AI正在解卦中，请稍候...</span>
                    </div>
                    <div class="ai-solution-content" id="ai-solution-content"></div>
                </div>
            `;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const jsonStr = line.slice(6);
                        try {
                            const result = JSON.parse(jsonStr);
                            if (result.status === 'started') {
                                modelName = result.model || '';
                                promptText = result.prompt || '';
                            } else if (result.status === 'stream') {
                                fullContent += result.chunk;
                                const contentEl = document.getElementById('ai-solution-content');
                                if (contentEl) {
                                    contentEl.innerHTML = this.markdownToHtml(fullContent);
                                    const rightContainer = solutionContainer.parentElement;
                                    if (rightContainer) {
                                        rightContainer.scrollTop = rightContainer.scrollHeight;
                                    }
                                }
                            } else if (result.status === 'completed') {
                                modelName = result.model || modelName;
                                promptText = result.prompt || promptText;
                                aiExplainBtn.disabled = false;
                                aiExplainBtn.innerHTML = '<i class="fas fa-robot"></i> AI 深度解卦';
                                
                                const loadingHeader = document.querySelector('.ai-solution-loading-header');
                                if (loadingHeader) {
                                    loadingHeader.style.display = 'none';
                                }
                                
                                const contentEl = document.getElementById('ai-solution-content');
                                if (contentEl) {
                                    const footer = `
                                        <div class="ai-solution-footer">
                                            <div class="ai-model-info">
                                                <i class="fas fa-cpu"></i>
                                                <span>模型：${modelName}</span>
                                            </div>
                                            <details class="ai-prompt-details">
                                                <summary><i class="fas fa-file-alt"></i> 查看提示词</summary>
                                                <pre class="ai-prompt-text">${this.escapeHtml(promptText)}</pre>
                                            </details>
                                        </div>
                                    `;
                                    contentEl.innerHTML = this.markdownToHtml(fullContent) + footer;
                                    const rightContainer = solutionContainer.parentElement;
                                    if (rightContainer) {
                                        rightContainer.scrollTop = rightContainer.scrollHeight;
                                    }
                                }
                                
                                this.saveDivinationResult(this.currentDivinationData);
                            } else if (result.status === 'error') {
                                alert('AI解卦失败: ' + result.message);
                                aiExplainBtn.disabled = false;
                                aiExplainBtn.innerHTML = '<i class="fas fa-robot"></i> AI 深度解卦';
                            }
                        } catch (e) {
                            console.warn('解析SSE数据失败:', e);
                        }
                    }
                }
            }
        } catch (error) {
            console.error('AI解卦失败:', error);
            alert('AI解卦失败: ' + error.message);
            aiExplainBtn.disabled = false;
            aiExplainBtn.innerHTML = '<i class="fas fa-robot"></i> AI 深度解卦';
        }
    }

    // ============ 龙虾Claw功能 ============
    clawTabs = {
        'main': { id: 'main', name: '主会话', type: 'default', sessionId: null, messages: [] },
        'feishu': { id: 'feishu', name: '飞书会话', type: 'default', sessionId: null, messages: [] }
    };
    currentClawTab = 'main';
    clawTabCounter = 1;
    
    getCurrentClawSessionId() {
        return this.clawTabs[this.currentClawTab]?.sessionId || null;
    }
    
    getCurrentClawMessages() {
        return this.clawTabs[this.currentClawTab]?.messages || [];
    }
    
    setCurrentClawSessionId(sessionId) {
        if (this.clawTabs[this.currentClawTab]) {
            this.clawTabs[this.currentClawTab].sessionId = sessionId;
        }
    }
    
    addCurrentClawMessage(msgData) {
        if (this.clawTabs[this.currentClawTab]) {
            this.clawTabs[this.currentClawTab].messages.push(msgData);
        }
    }
    
    setCurrentClawMessages(messages) {
        if (this.clawTabs[this.currentClawTab]) {
            this.clawTabs[this.currentClawTab].messages = messages;
        }
    }
    
    initClawChat() {
        const sendBtn = document.getElementById('claw-chat-send-btn');
        const input = document.getElementById('claw-chat-input');
        const clearBtn = document.getElementById('claw-chat-clear-btn');
        
        if (sendBtn) {
            sendBtn.onclick = () => this.sendClawChatMessage();
        }
        
        if (input) {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendClawChatMessage();
                }
            });
        }
        
        if (clearBtn) {
            clearBtn.onclick = () => this.clearClawChat();
        }
        
        this.loadClawChatModels();
    }
    
    async loadClawChatModels() {
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/chat/models`);
            const result = await response.json();
            if (result.success && result.models.length > 0) {
                const select = document.getElementById('claw-model-select');
                if (select) {
                    select.innerHTML = '<option value="">默认模型</option>';
                    result.models.forEach(model => {
                        const option = document.createElement('option');
                        option.value = model.name;
                        option.textContent = `${model.name} (${model.provider})`;
                        select.appendChild(option);
                    });
                }
            }
        } catch (error) {
            console.error('加载模型列表失败:', error);
        }
    }
    
    async sendClawChatMessage() {
        const input = document.getElementById('claw-chat-input');
        const sendBtn = document.getElementById('claw-chat-send-btn');
        const modelSelect = document.getElementById('claw-model-select');
        const messagesContainer = document.getElementById('claw-chat-messages');
        const message = input.value.trim();
        const modelName = modelSelect ? modelSelect.value : '';
        
        if (!message) {
            return;
        }
        
        this.clawChatAbortController = new AbortController();
        
        input.value = '';
        sendBtn.disabled = true;
        sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 发送中...';
        
        this.addClawChatMessage('user', message, false, new Date().toISOString());
        
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/chat/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    message: message, 
                    session_id: this.getCurrentClawSessionId(),
                    model_name: modelName || undefined
                }),
                keepalive: true,
                signal: this.clawChatAbortController?.signal
            });
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let assistantMessageId = null;
            let isDone = false;
            let modelInfo = null;
            let tokenStats = null;
            
            while (!isDone) {
                const { done, value } = await reader.read();
                if (done) break;
                
                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.substring(6));
                            
                            if (data.success) {
                                    this.setCurrentClawSessionId(data.session_id);
                                
                                if (data.model_name) {
                                    modelInfo = data.model_name;
                                }
                                if (data.token_stats) {
                                    tokenStats = data.token_stats;
                                }
                                
                                if (data.content) {
                                    if (!assistantMessageId) {
                                        assistantMessageId = this.addClawChatMessage('assistant', data.content, true);
                                    } else {
                                        this.updateClawChatMessage(assistantMessageId, data.content);
                                    }
                                }
                                
                                if (data.done) {
                                    isDone = true;
                                    if (assistantMessageId) {
                                        this.finishClawChatMessage(assistantMessageId, modelInfo, tokenStats);
                                    }
                                }
                            } else {
                                this.addClawChatMessage('system', `<span style="color: #ef4444;">错误: ${data.error}</span>`);
                            }
                        } catch (e) {
                            console.error('解析SSE数据失败:', e);
                        }
                    }
                }
            }
            
            if (assistantMessageId && !isDone) {
                this.finishClawChatMessage(assistantMessageId);
            }
        } catch (error) {
            this.addClawChatMessage('system', `<span style="color: #ef4444;">发送失败: ${error.message}</span>`);
        } finally {
            const indicators = document.querySelectorAll('.claw-typing-indicator');
            indicators.forEach(ind => ind.remove());
            sendBtn.disabled = false;
            sendBtn.innerHTML = '<i class="fas fa-send"></i> 发送';
        }
    }
    
    renderClawChatMessage(role, content, timestamp = null, modelName = null, tokenStats = null) {
        const messagesContainer = document.getElementById('claw-chat-messages');
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `claw-chat-message ${role}`;
        messageDiv.style.cssText = `
            display: flex; flex-direction: column; margin-bottom: 15px; align-items: ${role === 'user' ? 'flex-end' : 'flex-start'};
        `;
        
        const innerDiv = document.createElement('div');
        innerDiv.style.cssText = `
            display: flex;
        `;
        
        const avatar = document.createElement('div');
        avatar.style.cssText = `
            width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
            font-size: 18px; flex-shrink: 0; margin ${role === 'user' ? 'left' : 'right'}: 10px;
        `;
        
        if (role === 'user') {
            avatar.style.background = '#3b82f6';
            avatar.innerHTML = '<i class="fas fa-user" style="color: white;"></i>';
        } else if (role === 'assistant') {
            avatar.style.background = '#10b981';
            avatar.innerHTML = '<i class="fas fa-robot" style="color: white;"></i>';
        } else {
            avatar.style.background = '#64748b';
            avatar.innerHTML = '<i class="fas fa-info-circle" style="color: white;"></i>';
        }
        
        const contentDiv = document.createElement('div');
        contentDiv.style.cssText = `
            max-width: 90%; padding: 12px 15px; border-radius: 12px; font-size: 14px; line-height: 1.5;
            ${role === 'user' 
                ? 'background: #3b82f6; color: white; border-bottom-right-radius: 4px;' 
                : role === 'assistant' 
                    ? 'background: white; color: #1e293b; border-bottom-left-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);' 
                    : 'background: #f1f5f9; color: #64748b; border-radius: 8px;'}
        `;
        
        if (role === 'assistant') {
            contentDiv.innerHTML = `<span class="claw-streaming-text">${this.renderMarkdown(content)}</span>`;
        } else if (role === 'user') {
            contentDiv.textContent = content;
        } else {
            contentDiv.innerHTML = content.replace(/\n/g, '<br>');
        }
        
        innerDiv.appendChild(avatar);
        innerDiv.appendChild(contentDiv);
        messageDiv.appendChild(innerDiv);
        
        if (role === 'assistant' && (modelName || tokenStats || timestamp)) {
            const infoParts = [];
            if (modelName) {
                infoParts.push(`模型: ${modelName}`);
            }
            if (tokenStats) {
                const pt = tokenStats.prompt_tokens || 0;
                const ct = tokenStats.completion_tokens || 0;
                const tps = typeof tokenStats.tokens_per_second === 'number' && tokenStats.tokens_per_second >= 0
                    ? tokenStats.tokens_per_second.toFixed(1)
                    : '0.0';
                infoParts.push(`输入 ${pt} → 输出 ${ct} tokens (${tps}/s)`);
            }
            if (timestamp) {
                infoParts.push(this.formatTimestamp(timestamp));
            }
            if (infoParts.length > 0) {
                const infoDiv = document.createElement('div');
                infoDiv.style.cssText = `
                    font-size: 11px; color: #94a3b8; margin-top: 4px; text-align: left;
                `;
                infoDiv.textContent = infoParts.join(' | ');
                messageDiv.appendChild(infoDiv);
            }
        }
        
        messagesContainer.appendChild(messageDiv);
        
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
    
    addClawChatMessage(role, content, isStreaming = false, timestamp = null) {
        const messagesContainer = document.getElementById('claw-chat-messages');
        const isWelcome = messagesContainer.querySelector('.empty-state');
        if (isWelcome) {
            messagesContainer.innerHTML = '';
        }
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `claw-chat-message ${role}`;
        messageDiv.style.cssText = `
            display: flex; flex-direction: column; margin-bottom: 15px; align-items: ${role === 'user' ? 'flex-end' : 'flex-start'};
        `;
        
        const innerDiv = document.createElement('div');
        innerDiv.style.cssText = `
            display: flex;
        `;
        
        const avatar = document.createElement('div');
        avatar.style.cssText = `
            width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
            font-size: 18px; flex-shrink: 0; margin ${role === 'user' ? 'left' : 'right'}: 10px;
        `;
        
        if (role === 'user') {
            avatar.style.background = '#3b82f6';
            avatar.innerHTML = '<i class="fas fa-user" style="color: white;"></i>';
        } else if (role === 'assistant') {
            avatar.style.background = '#10b981';
            avatar.innerHTML = '<i class="fas fa-robot" style="color: white;"></i>';
        } else {
            avatar.style.background = '#64748b';
            avatar.innerHTML = '<i class="fas fa-info-circle" style="color: white;"></i>';
        }
        
        const contentDiv = document.createElement('div');
        contentDiv.style.cssText = `
            max-width: 90%; padding: 12px 15px; border-radius: 12px; font-size: 14px; line-height: 1.5;
            ${role === 'user' 
                ? 'background: #3b82f6; color: white; border-bottom-right-radius: 4px;' 
                : role === 'assistant' 
                    ? 'background: white; color: #1e293b; border-bottom-left-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);' 
                    : 'background: #f1f5f9; color: #64748b; border-radius: 8px;'}
        `;
        
        if (isStreaming) {
            contentDiv.id = `claw-assistant-${Date.now()}`;
            contentDiv.innerHTML = `<span class="claw-streaming-text">${content}</span><span class="claw-typing-indicator"><i class="fas fa-circle fa-xs"></i><i class="fas fa-circle fa-xs" style="animation-delay: 0.2s;"></i><i class="fas fa-circle fa-xs" style="animation-delay: 0.4s;"></i></span>`;
            contentDiv.dataset.rawText = content;
            contentDiv.dataset.timestamp = timestamp || new Date().toISOString();
            const indicatorStyle = document.createElement('style');
            indicatorStyle.textContent = `.claw-typing-indicator i { animation: bounce 1.4s infinite ease-in-out both; } @keyframes bounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }`;
            document.head.appendChild(indicatorStyle);
        } else {
            if (role === 'assistant') {
                contentDiv.innerHTML = `<span class="claw-streaming-text">${this.renderMarkdown(content)}</span>`;
            } else if (role === 'user') {
                contentDiv.textContent = content;
            } else {
                contentDiv.innerHTML = content.replace(/\n/g, '<br>');
            }
        }
        
        innerDiv.appendChild(avatar);
        innerDiv.appendChild(contentDiv);
        messageDiv.appendChild(innerDiv);
        messagesContainer.appendChild(messageDiv);
        
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        
        const msgData = { role, content, timestamp: timestamp || new Date().toISOString() };
        this.addCurrentClawMessage(msgData);
        
        return contentDiv.id;
    }
    
    updateClawChatMessage(elementId, content) {
        const element = document.getElementById(elementId);
        if (element) {
            const textSpan = element.querySelector('.claw-streaming-text');
            if (textSpan) {
                const currentText = element.dataset.rawText || '';
                const newText = currentText + content;
                element.dataset.rawText = newText;
                
                if (content.includes('<video') || content.includes('<img')) {
                    textSpan.innerHTML = newText;
                } else {
                    textSpan.innerHTML = this.renderMarkdown(newText);
                }
            } else {
                element.innerHTML += content.replace(/\n/g, '<br>');
            }
        }
        
        const messagesContainer = document.getElementById('claw-chat-messages');
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
    
    finishClawChatMessage(elementId, modelName = null, tokenStats = null) {
        const element = document.getElementById(elementId);
        if (element) {
            const indicator = element.querySelector('.claw-typing-indicator');
            
            if (indicator) {
                indicator.remove();
            }
            
            const rawText = element.dataset.rawText || '';
            if (rawText) {
                const currentTab = this.clawTabs[this.currentClawTab];
                if (currentTab && currentTab.messages.length > 0) {
                    const lastMsg = currentTab.messages[currentTab.messages.length - 1];
                    if (lastMsg.role === 'assistant') {
                        lastMsg.content = rawText;
                        lastMsg.modelName = modelName;
                        lastMsg.tokenStats = tokenStats;
                    }
                }
            }
            
            const messageDiv = element.parentElement.parentElement;
            
            const infoParts = [];
            
            if (modelName) {
                infoParts.push(`模型: ${modelName}`);
            }
            
            if (tokenStats) {
                const pt = tokenStats.prompt_tokens || 0;
                const ct = tokenStats.completion_tokens || 0;
                const tps = typeof tokenStats.tokens_per_second === 'number' && tokenStats.tokens_per_second >= 0
                    ? tokenStats.tokens_per_second.toFixed(1)
                    : '0.0';
                infoParts.push(`输入 ${pt} → 输出 ${ct} tokens (${tps}/s)`);
            }
            
            infoParts.push(this.formatTimestamp(new Date().toISOString()));
            
            if (infoParts.length > 0) {
                const infoDiv = document.createElement('div');
                infoDiv.style.cssText = `
                    font-size: 11px; color: #94a3b8; margin-top: 4px; text-align: left;
                `;
                infoDiv.textContent = infoParts.join(' | ');
                messageDiv.appendChild(infoDiv);
            }
        }
        
        const messagesContainer = document.getElementById('claw-chat-messages');
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
    
    renderMarkdown(text) {
        if (!text) return '';
        
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                breaks: true,
                gfm: true
            });
            return marked.parse(text);
        }
        
        let html = text;
        
        html = html.replace(/&/g, '&amp;');
        html = html.replace(/</g, '&lt;');
        html = html.replace(/>/g, '&gt;');
        
        html = html.replace(/^### (.*$)/gm, '<h3>$1</h3>');
        html = html.replace(/^## (.*$)/gm, '<h2>$1</h2>');
        html = html.replace(/^# (.*$)/gm, '<h1>$1</h1>');
        
        html = html.replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre class="claw-code-block"><code>$2</code></pre>');
        html = html.replace(/`([^`]+)`/g, '<code class="claw-inline-code">$1</code>');
        
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
        
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="claw-link">$1</a>');
        html = html.replace(/^> (.*$)/gm, '<blockquote>$1</blockquote>');
        
        html = html.replace(/^\s*\d+\.\s+/gm, '<li>$&</li>');
        html = html.replace(/^\s*[-*+]\s+/gm, '<li>$&</li>');
        html = html.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>');
        
        html = html.replace(/^\|(.*)\|$/gm, (match) => {
            const parts = match.split('|').map(p => p.trim()).filter(p => p);
            if (parts.length === 0) return match;
            if (match.includes('---')) return '';
            return '<tr>' + parts.map(p => `<td>${p}</td>`).join('') + '</tr>';
        });
        
        html = html.replace(/(<tr>[\s\S]*?<\/tr>[\s\S]*?<\/tr>)/g, '<table class="claw-table">$1</table>');
        
        html = html.replace(/\*\*\*\*/g, '<hr>');
        html = html.replace(/^---$/gm, '<hr>');
        
        html = html.replace(/\n/g, '<br>');
        html = html.replace(/<li>(\s*\d+\.\s+|\*\s+|-|\s*)\s*/g, '<li>');
        
        return html;
    }
    
    formatTimestamp(timestamp) {
        if (!timestamp) return '';
        
        let date;
        
        if (typeof timestamp === 'number') {
            if (timestamp.toString().length === 10) {
                date = new Date(timestamp * 1000);
            } else {
                date = new Date(timestamp);
            }
        } else if (typeof timestamp === 'string') {
            let trimmed = timestamp.trim();
            
            if (trimmed.includes('T')) {
                const parts = trimmed.split('.');
                if (parts.length > 1) {
                    trimmed = parts[0] + '.' + parts[1].substring(0, 3);
                }
            }
            
            date = new Date(trimmed);
            
            if (isNaN(date.getTime())) {
                const normalized = trimmed.replace(' ', 'T');
                date = new Date(normalized);
            }
        } else {
            date = new Date(timestamp);
        }
        
        if (isNaN(date.getTime())) {
            return '未知时间';
        }
        
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');
        
        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
    }
    
    clearClawChat() {
        const messagesContainer = document.getElementById('claw-chat-messages');
        messagesContainer.innerHTML = `
            <div style="text-align: center; color: #94a3b8; margin-top: 50px;">
                <i class="fas fa-robot" style="font-size: 48px; margin-bottom: 15px;"></i>
                <p>欢迎来到龙虾Claw！</p>
                <p style="font-size: 14px; margin-top: 5px;">我是你的AI助手，可以回答问题、执行命令、操作文件等。</p>
            </div>
        `;
        this.setCurrentClawSessionId(null);
        this.setCurrentClawMessages([]);
    }
    
    createNewClawSession() {
        this.addClawTab();
    }
    
    switchClawTab(tabId) {
        if (tabId === this.currentClawTab) return;
        
        this.currentClawTab = tabId;
        
        document.querySelectorAll('.claw-tab').forEach(t => t.classList.remove('active'));
        const activeTab = document.querySelector(`.claw-tab[data-tab-id="${tabId}"]`);
        if (activeTab) activeTab.classList.add('active');
        
        const tab = this.clawTabs[tabId];
        const messagesContainer = document.getElementById('claw-chat-messages');
        
        if (tab.messages && tab.messages.length > 0) {
            messagesContainer.innerHTML = '';
            tab.messages.forEach(msg => {
                this.renderClawChatMessage(msg.role, msg.content, msg.timestamp, msg.modelName, msg.tokenStats);
            });
        } else if (tabId === 'feishu') {
            this.loadFeishuChatMessages();
        } else {
            messagesContainer.innerHTML = `
                <div style="text-align: center; color: #94a3b8; margin-top: 50px;">
                    <i class="fas fa-robot" style="font-size: 48px; margin-bottom: 15px;"></i>
                    <p>欢迎来到龙虾Claw！</p>
                    <p style="font-size: 14px; margin-top: 5px;">我是你的AI助手，可以回答问题、执行命令、操作文件等。</p>
                </div>
            `;
        }
        
        if (tabId === 'feishu' && !this.feishuPollingInterval) {
            this.startFeishuPolling();
        }
    }
    
    addClawTab() {
        const tabId = `tab_${++this.clawTabCounter}_${Date.now()}`;
        const tabName = `会话 ${this.clawTabCounter}`;
        
        this.clawTabs[tabId] = {
            id: tabId,
            name: tabName,
            type: 'custom',
            sessionId: null,
            messages: []
        };
        
        const tabsContainer = document.getElementById('claw-tabs');
        const newTab = document.createElement('div');
        newTab.className = 'claw-tab';
        newTab.dataset.tabId = tabId;
        newTab.innerHTML = `
            <i class="fas fa-comment"></i> ${tabName}
            <i class="fas fa-times claw-tab-close" onclick="app.closeClawTab('${tabId}'); event.stopPropagation();"></i>
        `;
        newTab.onclick = () => this.switchClawTab(tabId);
        tabsContainer.appendChild(newTab);
        
        this.switchClawTab(tabId);
    }
    
    closeClawTab(tabId) {
        const tab = this.clawTabs[tabId];
        if (!tab || tab.type === 'default') return;
        
        delete this.clawTabs[tabId];
        
        const tabEl = document.querySelector(`.claw-tab[data-tab-id="${tabId}"]`);
        if (tabEl) tabEl.remove();
        
        if (this.currentClawTab === tabId) {
            const remainingTabs = Object.keys(this.clawTabs);
            if (remainingTabs.length > 0) {
                this.switchClawTab(remainingTabs[0]);
            }
        }
    }
    
    async loadFeishuChatMessages() {
        try {
            const response = await fetch('/api/lobster-claw/feishu/messages?limit=50');
            const data = await response.json();
            const messagesContainer = document.getElementById('claw-chat-messages');
            
            if (data.success && data.messages && data.messages.length > 0) {
                const feishuTab = this.clawTabs['feishu'];
                feishuTab.messages = [];
                
                messagesContainer.innerHTML = '';
                
                const reversedMessages = [...data.messages].reverse();
                
                reversedMessages.forEach(m => {
                    if (m.content) {
                        const msg = { role: 'user', content: m.content, timestamp: m.timestamp };
                        feishuTab.messages.push(msg);
                        this.renderClawChatMessage(msg.role, msg.content, msg.timestamp);
                    }
                    if (m.response && m.status === 'success') {
                        const msg = { role: 'assistant', content: m.response, timestamp: m.timestamp };
                        feishuTab.messages.push(msg);
                        this.renderClawChatMessage(msg.role, msg.content, msg.timestamp);
                    }
                });
            } else {
                messagesContainer.innerHTML = `
                    <div style="text-align: center; color: #94a3b8; margin-top: 50px;">
                        <i class="fas fa-paper-plane" style="font-size: 48px; margin-bottom: 15px;"></i>
                        <p>飞书会话</p>
                        <p style="font-size: 14px; margin-top: 5px;">飞书消息将在这里同步显示</p>
                    </div>
                `;
                if (this.clawTabs['feishu']) {
                    this.clawTabs['feishu'].messages = [];
                }
            }
        } catch (e) {
            console.error('加载飞书会话消息失败:', e);
        }
    }
    
    startFeishuPolling() {
        if (this.feishuPollingInterval) return;
        this.feishuPollingInterval = setInterval(() => {
            if (this.currentClawTab === 'feishu') {
                this.loadFeishuChatMessages();
            }
        }, 3000);
    }
    
    stopFeishuPolling() {
        if (this.feishuPollingInterval) {
            clearInterval(this.feishuPollingInterval);
            this.feishuPollingInterval = null;
        }
    }
    
    async loadClawChatSessions() {
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/chat/sessions`);
            const result = await response.json();
            
            const listContainer = document.getElementById('claw-sessions-list');
            
            if (result.success && result.sessions.length > 0) {
                const sortedSessions = result.sessions.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
                
                listContainer.innerHTML = sortedSessions.map(session => {
                    const createdAt = new Date(session.created_at);
                    const timeStr = createdAt.toLocaleString('zh-CN', {
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit'
                    });
                    
                    return `
                        <div style="padding: 12px; border-bottom: 1px solid #e2e8f0; cursor: pointer;" onclick="app.loadClawChatSession('${session.id}')">
                            <div style="font-weight: bold; color: #1e293b;">会话 ${session.id.split('_')[2] || session.id.substring(0, 10)}</div>
                            <div style="font-size: 12px; color: #64748b; margin-top: 4px;">消息数: ${session.message_count} | ${timeStr}</div>
                            <div style="font-size: 12px; color: #94a3b8; margin-top: 2px;">${session.preview || '无预览'}</div>
                        </div>
                    `;
                }).join('');
            } else {
                listContainer.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-inbox" style="font-size: 48px; margin-bottom: 15px; color: #94a3b8;"></i>
                        <p>暂无会话记录</p>
                    </div>
                `;
            }
            
            document.getElementById('claw-sessions-modal').style.display = 'flex';
        } catch (error) {
            alert('获取会话记录失败: ' + error.message);
        }
    }
    
    async loadClawChatSession(sessionId) {
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/chat/session/${sessionId}`);
            const result = await response.json();
            
            if (result.success) {
                this.clearClawChat();
                this.setCurrentClawSessionId(sessionId);
                
                const messagesContainer = document.getElementById('claw-chat-messages');
                messagesContainer.innerHTML = '';
                
                result.session.messages.forEach(msg => {
                    this.addClawChatMessage(msg.role, msg.content, false, msg.timestamp);
                });
                
                document.getElementById('claw-sessions-modal').style.display = 'none';
            }
        } catch (error) {
            alert('加载会话失败: ' + error.message);
        }
    }
    
    async loadClawMemory() {
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/memory/list`);
            const result = await response.json();
            this.renderClawMemoryList(result);
            document.getElementById('claw-memory-modal').style.display = 'flex';
        } catch (error) {
            alert('获取记忆列表失败: ' + error.message);
        }
    }
    
    async searchClawMemory() {
        try {
            const query = document.getElementById('claw-memory-search-input').value;
            const memoryType = document.getElementById('claw-memory-type-filter').value;
            
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/memory/search`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, memory_type: memoryType || undefined, limit: 50 })
            });
            const result = await response.json();
            this.renderClawMemoryList(result);
        } catch (error) {
            alert('搜索记忆失败: ' + error.message);
        }
    }
    
    renderClawMemoryList(result) {
        const listContainer = document.getElementById('claw-memory-list');
        
        if (result.success && result.memories.length > 0) {
            listContainer.innerHTML = result.memories.map(memory => {
                const timestamp = new Date(memory.timestamp);
                const timeStr = timestamp.toLocaleString('zh-CN', {
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit'
                });
                
                const typeLabel = memory.type === 'long_term' ? 
                    '<span style="background: #3b82f6; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">长期</span>' :
                    '<span style="background: #10b981; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">短期</span>';
                
                const keywords = memory.keywords && memory.keywords.length > 0 ? 
                    `<div style="font-size: 12px; color: #64748b; margin-top: 4px;">关键词: ${memory.keywords.join(', ')}</div>` : '';
                
                return `
                    <div style="padding: 12px; border-bottom: 1px solid #e2e8f0;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            ${typeLabel}
                            <button class="btn btn-outline-danger btn-sm" onclick="app.deleteClawMemory(${memory.id})">
                                <i class="fas fa-trash"></i> 删除
                            </button>
                        </div>
                        <div style="font-size: 14px; color: #1e293b; margin-top: 8px; line-height: 1.5;">${memory.content}</div>
                        ${keywords}
                        <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">${timeStr}</div>
                    </div>
                `;
            }).join('');
        } else {
            listContainer.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-inbox" style="font-size: 48px; margin-bottom: 15px; color: #94a3b8;"></i>
                    <p>暂无记忆记录</p>
                </div>
            `;
        }
    }
    
    async deleteClawMemory(memoryId) {
        if (!confirm('确定要删除这条记忆吗？')) return;
        
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/memory/${memoryId}`, {
                method: 'DELETE'
            });
            const result = await response.json();
            
            if (result.success) {
                this.loadClawMemory();
            } else {
                alert('删除失败: ' + result.error);
            }
        } catch (error) {
            alert('删除记忆失败: ' + error.message);
        }
    }

    toggleMemoryMaximize() {
        const content = document.getElementById('claw-memory-modal-content');
        const body = document.getElementById('claw-memory-modal-body');
        const maxBtn = document.querySelector('#claw-memory-modal button[onclick="app.toggleMemoryMaximize()"] i');
        
        if (!content || !body || !maxBtn) return;
        
        if (this._memoryMaximized) {
            content.style.width = '85%';
            content.style.maxWidth = '900px';
            content.style.maxHeight = '80vh';
            content.style.borderRadius = '16px';
            body.style.maxHeight = 'calc(80vh - 80px)';
            maxBtn.className = 'fas fa-expand';
            this._memoryMaximized = false;
        } else {
            content.style.width = '98%';
            content.style.maxWidth = 'none';
            content.style.maxHeight = '95vh';
            content.style.borderRadius = '8px';
            body.style.maxHeight = 'calc(95vh - 80px)';
            maxBtn.className = 'fas fa-compress';
            this._memoryMaximized = true;
        }
    }

    // ============ 定时任务管理 ============
    async loadCronTasks() {
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/cron/list`);
            const result = await response.json();
            this.renderCronTaskList(result);
            document.getElementById('claw-cron-modal').style.display = 'flex';
        } catch (error) {
            alert('获取任务列表失败: ' + error.message);
        }
    }

    renderCronTaskList(result) {
        const listContainer = document.getElementById('claw-cron-task-list');
        
        if (result.success && result.tasks.length > 0) {
            listContainer.innerHTML = result.tasks.map(task => {
                const typeLabel = task.task_type === 'ai' ?
                    '<span style="background: #3b82f6; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">AI对话</span>' :
                    '<span style="background: #f59e0b; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">Shell命令</span>';
                
                const enabledLabel = task.enabled ?
                    '<span style="background: #10b981; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">已启用</span>' :
                    '<span style="background: #64748b; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">已禁用</span>';
                
                const schedule = task.schedule || task.run_at || '无';
                const nextRun = task.next_run_at ? new Date(task.next_run_at).toLocaleString('zh-CN') : '未知';
                
                return `
                    <div style="padding: 12px; border-bottom: 1px solid #e2e8f0;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div style="display: flex; gap: 8px;">
                                ${typeLabel}
                                ${enabledLabel}
                            </div>
                            <div style="display: flex; gap: 5px;">
                                <button class="btn btn-outline-secondary btn-sm" onclick="app.runCronTask(${task.id})" title="立即执行">
                                    <i class="fas fa-play"></i>
                                </button>
                                <button class="btn btn-outline-secondary btn-sm" onclick="app.toggleCronTask(${task.id})" title="${task.enabled ? '禁用' : '启用'}">
                                    <i class="fas ${task.enabled ? 'fa-pause' : 'fa-play'}"></i>
                                </button>
                                <button class="btn btn-outline-secondary btn-sm" onclick="app.viewCronRuns(${task.id})" title="查看运行历史">
                                    <i class="fas fa-history"></i>
                                </button>
                                <button class="btn btn-outline-danger btn-sm" onclick="app.deleteCronTask(${task.id})">
                                    <i class="fas fa-trash"></i> 删除
                                </button>
                            </div>
                        </div>
                        <div style="font-size: 16px; font-weight: 600; color: #1e293b; margin-top: 8px;">${task.name}</div>
                        <div style="font-size: 14px; color: #64748b; margin-top: 4px; line-height: 1.5;">${task.content}</div>
                        <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">
                            调度: ${schedule} | 下次执行: ${nextRun} | 超时: ${task.timeout}秒
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            listContainer.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-clock" style="font-size: 48px; margin-bottom: 15px; color: #94a3b8;"></i>
                    <p>暂无定时任务</p>
                </div>
            `;
        }
    }

    showAddCronTask() {
        document.getElementById('claw-cron-task-list').style.display = 'none';
        document.getElementById('claw-cron-add-form').style.display = 'block';
    }

    hideAddCronTask() {
        document.getElementById('claw-cron-task-list').style.display = 'block';
        document.getElementById('claw-cron-add-form').style.display = 'none';
        document.getElementById('cron-name').value = '';
        document.getElementById('cron-task-type').value = 'ai';
        document.getElementById('cron-schedule').value = '';
        document.getElementById('cron-run-at').value = '';
        document.getElementById('cron-content').value = '';
        document.getElementById('cron-timeout').value = '300';
        document.getElementById('cron-enabled').value = 'true';
    }

    async addCronTask() {
        const name = document.getElementById('cron-name').value.trim();
        const taskType = document.getElementById('cron-task-type').value;
        const schedule = document.getElementById('cron-schedule').value.trim();
        const runAt = document.getElementById('cron-run-at').value;
        const content = document.getElementById('cron-content').value.trim();
        const timeout = parseInt(document.getElementById('cron-timeout').value) || 300;
        const enabled = document.getElementById('cron-enabled').value === 'true';
        
        if (!name) {
            alert('请输入任务名称');
            return;
        }
        if (!content) {
            alert('请输入任务内容');
            return;
        }
        if (!schedule && !runAt) {
            alert('请指定cron表达式或一次性执行时间');
            return;
        }
        
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/cron/add`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, task_type: taskType, content, schedule, run_at: runAt, timeout, enabled })
            });
            const result = await response.json();
            
            if (result.success) {
                alert('任务添加成功');
                this.hideAddCronTask();
                this.loadCronTasks();
            } else {
                alert('添加失败: ' + result.error);
            }
        } catch (error) {
            alert('添加任务失败: ' + error.message);
        }
    }

    async deleteCronTask(taskId) {
        if (!confirm('确定要删除这个任务吗？')) return;
        
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/cron/${taskId}`, {
                method: 'DELETE'
            });
            const result = await response.json();
            
            if (result.success) {
                this.loadCronTasks();
            } else {
                alert('删除失败: ' + result.error);
            }
        } catch (error) {
            alert('删除任务失败: ' + error.message);
        }
    }

    async toggleCronTask(taskId) {
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/cron/toggle/${taskId}`, {
                method: 'POST'
            });
            const result = await response.json();
            
            if (result.success) {
                this.loadCronTasks();
            } else {
                alert('操作失败: ' + result.error);
            }
        } catch (error) {
            alert('操作失败: ' + error.message);
        }
    }

    async runCronTask(taskId) {
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/cron/${taskId}/run-now`, {
                method: 'POST'
            });
            const result = await response.json();
            
            if (result.success) {
                alert('任务已触发执行');
            } else {
                alert('触发失败: ' + result.error);
            }
        } catch (error) {
            alert('触发任务失败: ' + error.message);
        }
    }

    async viewCronRuns(taskId) {
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/cron/${taskId}/runs`);
            const result = await response.json();
            
            if (result.success && result.runs.length > 0) {
                const runs = result.runs.map(run => {
                    const status = run.status === 'completed' ? '成功' : run.status === 'failed' ? '失败' : run.status;
                    return `<div style="padding: 8px; border-bottom: 1px solid #e2e8f0;">
                        <div style="font-size: 12px; color: #64748b;">${new Date(run.started_at).toLocaleString('zh-CN')}</div>
                        <div style="font-size: 14px; color: ${run.status === 'completed' ? '#10b981' : '#ef4444'};">状态: ${status}</div>
                        ${run.output ? `<div style="font-size: 13px; color: #1e293b; margin-top: 4px; white-space: pre-wrap; max-height: 100px; overflow-y: auto;">${run.output}</div>` : ''}
                        ${run.error ? `<div style="font-size: 13px; color: #ef4444; margin-top: 4px;">错误: ${run.error}</div>` : ''}
                        <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">耗时: ${run.duration ? run.duration.toFixed(2) : '0'}秒</div>
                    </div>`;
                }).join('');
                
                alert(`运行历史:\n\n${runs}`);
            } else {
                alert('暂无运行历史');
            }
        } catch (error) {
            alert('获取运行历史失败: ' + error.message);
        }
    }

    toggleCronMaximize() {
        const content = document.getElementById('claw-cron-modal-content');
        const body = document.getElementById('claw-cron-modal-body');
        const maxBtn = document.querySelector('#claw-cron-modal button[onclick="app.toggleCronMaximize()"] i');
        
        if (!content || !body || !maxBtn) return;
        
        if (this._cronMaximized) {
            content.style.width = '85%';
            content.style.maxWidth = '900px';
            content.style.maxHeight = '80vh';
            content.style.borderRadius = '16px';
            body.style.maxHeight = 'calc(80vh - 80px)';
            maxBtn.className = 'fas fa-expand';
            this._cronMaximized = false;
        } else {
            content.style.width = '98%';
            content.style.maxWidth = 'none';
            content.style.maxHeight = '95vh';
            content.style.borderRadius = '8px';
            body.style.maxHeight = 'calc(95vh - 80px)';
            maxBtn.className = 'fas fa-compress';
            this._cronMaximized = true;
        }
    }

    // ============ 脚本管理 ============
    async showScriptModal() {
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/script/list`);
            const result = await response.json();
            this.renderScriptList(result);
            document.getElementById('claw-script-modal').style.display = 'flex';
        } catch (error) {
            alert('获取脚本列表失败: ' + error.message);
        }
    }

    renderScriptList(result) {
        const listContainer = document.getElementById('claw-script-list');
        
        if (result.success && result.scripts.length > 0) {
            listContainer.innerHTML = result.scripts.map(script => {
                const codePreview = script.code.length > 100 ? script.code.substring(0, 100) + '...' : script.code;
                const createdAt = new Date(script.created_at).toLocaleString('zh-CN');
                const desc = script.description || '';
                
                return `
                    <div style="padding: 12px; border-bottom: 1px solid #e2e8f0;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                                <strong style="font-size: 15px; font-family: monospace;">${script.name}</strong>
                                ${desc ? `<span style="font-size: 13px; color: #0369a1; background: #e0f2fe; padding: 2px 8px; border-radius: 4px;">${desc}</span>` : ''}
                                <span style="font-size: 12px; color: #64748b;">ID: ${script.id}</span>
                            </div>
                            <div style="display: flex; gap: 5px;">
                                <button class="btn btn-outline-secondary btn-sm" onclick="app.executeScript(${script.id})" title="执行脚本">
                                    <i class="fas fa-play"></i>
                                </button>
                                <button class="btn btn-outline-secondary btn-sm" onclick="app.deleteScript(${script.id})" title="删除脚本">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                        </div>
                        <div style="font-size: 12px; color: #94a3b8;">创建时间: ${createdAt}</div>
                        <div style="font-size: 13px; color: #1e293b; margin-top: 6px; padding: 6px; background: #f1f5f9; border-radius: 4px; font-family: monospace; white-space: pre-wrap; max-height: 60px; overflow-y: auto;">${codePreview}</div>
                    </div>
                `;
            }).join('');
        } else {
            listContainer.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-code" style="font-size: 48px; margin-bottom: 15px; color: #94a3b8;"></i>
                    <p>暂无脚本</p>
                    <p style="font-size: 14px; margin-top: 5px;">点击上方按钮创建新脚本</p>
                </div>
            `;
        }
    }

    showAddScript() {
        document.getElementById('claw-script-add-form').style.display = 'block';
        document.getElementById('script-name').value = '';
        document.getElementById('script-description').value = '';
        document.getElementById('script-code').value = '';
    }

    hideAddScript() {
        document.getElementById('claw-script-add-form').style.display = 'none';
    }

    async addScript() {
        const name = document.getElementById('script-name').value.trim();
        const description = document.getElementById('script-description').value.trim();
        const code = document.getElementById('script-code').value.trim();
        
        if (!name) {
            alert('请输入脚本名称');
            return;
        }
        if (!code) {
            alert('请输入脚本代码');
            return;
        }
        
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/script/create`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, description, code })
            });
            const result = await response.json();
            
            if (result.success) {
                alert('脚本创建成功！');
                this.hideAddScript();
                this.showScriptModal();
            } else {
                alert('创建失败: ' + result.error);
            }
        } catch (error) {
            alert('创建脚本失败: ' + error.message);
        }
    }

    async executeScript(scriptId) {
        try {
            const scriptList = await fetch(`${this.baseUrl}/api/lobster-claw/script/list`).then(r => r.json());
            const script = scriptList.scripts.find(s => s.id === scriptId);
            const scriptName = script ? script.name : `脚本#${scriptId}`;

            const response = await fetch(`${this.baseUrl}/api/lobster-claw/script/execute`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ script_id: scriptId })
            });
            const result = await response.json();
            
            if (result.success) {
                // 关闭脚本管理弹窗
                document.getElementById('claw-script-modal').style.display = 'none';

                // 将结果传给大模型美化输出
                const sendBtn = document.getElementById('claw-chat-send-btn');
                const modelSelect = document.getElementById('claw-model-select');
                const modelName = modelSelect ? modelSelect.value : '';

                this.clawChatAbortController = new AbortController();
                sendBtn.disabled = true;
                sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 分析中...';

                const beautifyPrompt = `我执行了一个名为"${scriptName}"的Python脚本，以下是脚本的原始执行结果。请帮我分析解读这个执行结果，用简洁美观的Markdown格式总结关键信息，指出需要注意的异常或问题。如果结果本身已经清晰，直接整理排版即可，不要编造不存在的信息。\n\n执行结果：\n\`\`\`\n${result.result}\n\`\`\``;

                try {
                    const chatResponse = await fetch(`${this.baseUrl}/api/lobster-claw/chat/stream`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            message: beautifyPrompt, 
                            session_id: this.getCurrentClawSessionId(),
                            model_name: modelName || undefined
                        }),
                        keepalive: true,
                        signal: this.clawChatAbortController?.signal
                    });
                    
                    const reader = chatResponse.body.getReader();
                    const decoder = new TextDecoder();
                    let assistantMessageId = null;
                    let isDone = false;
                    let modelInfo = null;
                    let tokenStats = null;
                    
                    while (!isDone) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        
                        const chunk = decoder.decode(value);
                        const lines = chunk.split('\n');
                        
                        for (const line of lines) {
                            if (line.startsWith('data: ')) {
                                try {
                                    const data = JSON.parse(line.substring(6));
                                    
                                    if (data.success) {
                                        if (data.session_id) {
                                            this.setCurrentClawSessionId(data.session_id);
                                        }
                                        if (data.model_name) {
                                            modelInfo = data.model_name;
                                        }
                                        if (data.token_stats) {
                                            tokenStats = data.token_stats;
                                        }
                                        
                                        if (data.content) {
                                            if (!assistantMessageId) {
                                                assistantMessageId = this.addClawChatMessage('assistant', data.content, true);
                                            } else {
                                                this.updateClawChatMessage(assistantMessageId, data.content);
                                            }
                                        }
                                        
                                        if (data.done) {
                                            isDone = true;
                                            if (assistantMessageId) {
                                                this.finishClawChatMessage(assistantMessageId, modelInfo, tokenStats);
                                            }
                                        }
                                    } else {
                                        this.addClawChatMessage('system', `<span style="color: #ef4444;">分析失败: ${data.error}</span>`);
                                    }
                                } catch (e) {
                                    console.error('解析SSE数据失败:', e);
                                }
                            }
                        }
                    }
                    
                    if (assistantMessageId && !isDone) {
                        this.finishClawChatMessage(assistantMessageId);
                    }
                } catch (error) {
                    this.addClawChatMessage('system', `<span style="color: #ef4444;">大模型分析失败: ${error.message}</span>`);
                } finally {
                    const indicators = document.querySelectorAll('.claw-typing-indicator');
                    indicators.forEach(ind => ind.remove());
                    sendBtn.disabled = false;
                    sendBtn.innerHTML = '<i class="fas fa-send"></i> 发送';
                }
            } else {
                alert('执行失败: ' + result.error);
            }
        } catch (error) {
            console.error('Execute script error:', error);
            alert('执行脚本失败: ' + error.message);
        }
    }

    async deleteScript(scriptId) {
        if (!confirm('确定要删除这个脚本吗？')) {
            return;
        }
        
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/script/${scriptId}`, {
                method: 'DELETE'
            });
            const result = await response.json();
            
            if (result.success) {
                alert('脚本删除成功');
                this.showScriptModal();
            } else {
                alert('删除失败: ' + result.error);
            }
        } catch (error) {
            alert('删除脚本失败: ' + error.message);
        }
    }

    async approveScript(scriptId) {
        if (!confirm('确定要审批此脚本吗？审批后脚本将允许执行包含危险操作的代码（如文件操作、系统命令等）。请确保您信任此脚本的内容。')) {
            return;
        }
        
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/script/${scriptId}/approve`, {
                method: 'POST'
            });
            const result = await response.json();
            
            if (result.success) {
                alert('脚本审批成功！');
                this.showScriptModal();
            } else {
                alert('审批失败: ' + result.error);
            }
        } catch (error) {
            alert('审批脚本失败: ' + error.message);
        }
    }

    async revokeScript(scriptId) {
        if (!confirm('确定要撤销此脚本的审批吗？撤销后脚本将不再允许执行危险操作。')) {
            return;
        }
        
        try {
            const response = await fetch(`${this.baseUrl}/api/lobster-claw/script/${scriptId}/revoke`, {
                method: 'POST'
            });
            const result = await response.json();
            
            if (result.success) {
                alert('脚本审批已撤销');
                this.showScriptModal();
            } else {
                alert('撤销失败: ' + result.error);
            }
        } catch (error) {
            alert('撤销审批失败: ' + error.message);
        }
    }

    // ============ AI聊天功能 ============
    aiChatRoles = [];
    aiChatMessages = [];
    aiChatEventSource = null;
    
    // ============ 文档处理功能 ============
    processingAgentIds = [];
    
    aiChatRoleAvatars = {
        "编辑": "✏️",
        "审核": "🔍",
        "扩展": "📚",
        "润色": "✨"
    };
    aiChatAvatarColors = [
        "#ef4444", "#f97316", "#f59e0b", "#eab308",
        "#84cc16", "#22c55e", "#10b981", "#14b8a6",
        "#06b6d4", "#0ea5e9", "#3b82f6", "#6366f1",
        "#8b5cf6", "#a855f7", "#d946ef", "#ec4899"
    ];

    initAIChat() {
        const selectBtn = document.getElementById('ai-chat-select-agents-btn');
        const startBtn = document.getElementById('ai-chat-start-btn');
        const historyBtn = document.getElementById('ai-chat-history-btn');
        
        if (selectBtn) {
            selectBtn.addEventListener('click', () => this.openAgentSelectDialog());
        }
        
        if (startBtn) {
            startBtn.addEventListener('click', () => this.toggleAIChat());
        }
        
        if (historyBtn) {
            historyBtn.addEventListener('click', () => this.openHistoryModal());
        }
        
        this.loadAIChatRoles();
    }
    
    // ========== AI聊天历史记录功能 ==========
    
    openHistoryModal() {
        document.getElementById('ai-chat-history-modal').style.display = 'flex';
        this.currentHistorySessionId = null;
        this.showHistoryList();
    }
    
    showHistoryList() {
        document.getElementById('history-list-view').style.display = 'block';
        document.getElementById('history-detail-view').style.display = 'none';
        this.loadHistoryList();
    }
    
    async loadHistoryList() {
        const searchInput = document.getElementById('history-search');
        const keyword = searchInput ? searchInput.value.trim().toLowerCase() : '';
        
        try {
            const response = await fetch(`${this.baseUrl}/api/ai-chat/history?limit=100`);
            const result = await response.json();
            
            if (result.status === 'success') {
                let history = result.data;
                
                // 过滤
                if (keyword) {
                    history = history.filter(h => h.theme.toLowerCase().includes(keyword));
                }
                
                const listEl = document.getElementById('history-list');
                
                if (history.length === 0) {
                    listEl.innerHTML = `
                        <div class="empty-state">
                            <i class="fas fa-inbox" style="font-size: 48px; margin-bottom: 15px; color: #94a3b8;"></i>
                            <p>${keyword ? '没有找到匹配的聊天记录' : '暂无聊天记录'}</p>
                        </div>
                    `;
                    return;
                }
                
                listEl.innerHTML = history.map(item => `
                    <div class="history-item" onclick="window.app.showHistoryDetail('${item.session_id}')" style="
                        padding: 12px;
                        margin-bottom: 8px;
                        background: white;
                        border-radius: 6px;
                        border: 1px solid #e2e8f0;
                        cursor: pointer;
                        transition: all 0.2s;
                    " onmouseover="this.style.borderColor='#3b82f6';this.style.boxShadow='0 2px 8px rgba(59,130,246,0.1)'" 
                       onmouseout="this.style.borderColor='#e2e8f0';this.style.boxShadow='none'">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div style="flex: 1; min-width: 0;">
                                <div style="font-weight: 600; color: #1e293b; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                                    ${this.escapeHtml(item.theme)}
                                </div>
                                <div style="font-size: 12px; color: #64748b;">
                                    ${item.date} · ${item.message_count} 条消息 · ${item.role_names.join(', ')}
                                </div>
                                <div style="font-size: 12px; color: #3b82f6; margin-top: 4px;">
                                    <i class="fas fa-link"></i> <a href="/chat-history/${item.session_id}" target="_blank" style="text-decoration: underline;">独立访问</a>
                                </div>
                            </div>
                            <div style="margin-left: 10px;">
                                <i class="fas fa-chevron-right" style="color: #94a3b8;"></i>
                            </div>
                        </div>
                    </div>
                `).join('');
            }
        } catch (error) {
            console.error('加载历史记录失败:', error);
        }
    }
    
    async showHistoryDetail(sessionId) {
        this.currentHistorySessionId = sessionId;
        
        try {
            const response = await fetch(`${this.baseUrl}/api/ai-chat/history/${sessionId}`);
            const result = await response.json();
            
            if (result.status === 'success') {
                const detail = result.data;
                document.getElementById('history-list-view').style.display = 'none';
                document.getElementById('history-detail-view').style.display = 'block';
                
                const contentEl = document.getElementById('history-detail-content');
                contentEl.innerHTML = `
                    <div style="margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #e2e8f0;">
                        <h4 style="margin: 0 0 8px 0; color: #1e293b;">${this.escapeHtml(detail.theme)}</h4>
                        <div style="font-size: 13px; color: #64748b;">
                            ${detail.date} · ${detail.message_count} 条消息
                        </div>
                    </div>
                    ${detail.messages.map(msg => {
                        const time = msg.timestamp ? new Date(msg.timestamp * 1000).toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit'}) : '';
                        const isImage = msg.is_image;
                        const isVideo = msg.is_video;
                        const imgHtml = isImage && msg.image_url ? `<img src="${msg.image_url}" style="max-width: 100%; max-height: 300px; border-radius: 6px; margin-top: 5px; cursor: pointer;" onclick="window.aiChatOpenImage('${msg.image_url.replace(/'/g, "\\'")}')">` : '';
                        const videoHtml = isVideo && msg.video_url ? `<video src="${msg.video_url}" controls style="max-width: 100%; max-height: 300px; border-radius: 6px; margin-top: 5px;">您的浏览器不支持视频播放</video>` : '';
                        return `
                            <div style="margin-bottom: 12px; padding: 10px; background: white; border-radius: 6px;">
                                <div style="font-weight: 600; color: #3b82f6; margin-bottom: 4px;">
                                    ${this.escapeHtml(msg.role_name)} <span style="font-weight: normal; color: #94a3b8; font-size: 12px;">${time}</span>
                                </div>
                                <div style="color: #334155; line-height: 1.6; word-wrap: break-word;">${this.escapeHtml(this.sanitizeThinkingContent(msg.content))}</div>
                                ${imgHtml}
                                ${videoHtml}
                            </div>
                        `;
                    }).join('')}
                `;
            }
        } catch (error) {
            console.error('加载历史记录详情失败:', error);
            alert('加载失败: ' + error.message);
        }
    }
    
    async deleteCurrentHistory() {
        if (!this.currentHistorySessionId) return;
        
        if (!confirm('确定要删除这条聊天记录吗？')) return;
        
        try {
            const response = await fetch(`${this.baseUrl}/api/ai-chat/history/delete`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: this.currentHistorySessionId })
            });
            const result = await response.json();
            
            if (result.status === 'success') {
                alert('删除成功');
                this.showHistoryList();
            } else {
                alert('删除失败: ' + result.message);
            }
        } catch (error) {
            console.error('删除历史记录失败:', error);
            alert('删除失败: ' + error.message);
        }
    }

    toggleHistoryMaximize() {
        const modalContent = document.getElementById('ai-chat-history-modal-content');
        const historyDetail = document.getElementById('history-detail-content');
        
        if (modalContent.classList.contains('maximized')) {
            modalContent.classList.remove('maximized');
            modalContent.style.width = '';
            modalContent.style.maxWidth = '';
            modalContent.style.maxHeight = '';
            modalContent.style.height = '';
            if (historyDetail) {
                historyDetail.style.maxHeight = '600px';
            }
        } else {
            modalContent.classList.add('maximized');
            if (historyDetail) {
                historyDetail.style.maxHeight = 'calc(95vh - 180px)';
            }
        }
    }

    async loadAIChatRoles() {
        try {
            const response = await fetch(`${this.baseUrl}/api/ai-chat/roles`);
            const result = await response.json();
            if (result.status === 'success') {
                this.aiChatRoles = result.data;
                this.renderAIChatRoles();
            }
        } catch (error) {
            console.error('加载角色失败:', error);
        }
    }

    async openAgentSelectDialog() {
        try {
            const response = await fetch(`${this.baseUrl}/api/ai-chat/agents?refresh=true`);
            const result = await response.json();
            if (result.status !== 'success') {
                alert('获取agent列表失败');
                return;
            }

            const agents = result.data;
            const existingIds = this.aiChatRoles.map(r => r.agent_id);
            
            let html = '<div style="max-height: 400px; overflow-y: auto;">';
            agents.forEach(agent => {
                const isSelected = existingIds.includes(agent.id);
                html += `
                    <label style="display: flex; align-items: center; padding: 10px; border-bottom: 1px solid #eee; cursor: pointer;">
                        <input type="checkbox" ${isSelected ? 'checked' : ''} value="${agent.id}">
                        <div style="margin-left: 10px;">
                            <div style="font-weight: 600;">${agent.name}</div>
                            <div style="font-size: 12px; color: #666;">${agent.role_description.substring(0, 50)}...</div>
                        </div>
                    </label>
                `;
            });
            html += '</div>';

            const dialog = document.createElement('div');
            dialog.className = 'modal';
            dialog.style.display = 'block';
            dialog.innerHTML = `
                <div class="modal-content" style="width: 500px;">
                    <div class="modal-header">
                        <h3><i class="fas fa-users"></i> 选择角色</h3>
                        <button class="modal-close" onclick="this.closest('.modal').remove()">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="modal-body">
                        ${html}
                        <div style="margin-top: 15px;">
                            <button id="ai-chat-confirm-select" class="btn btn-primary" style="width: 100%;">
                                <i class="fas fa-check"></i> 确认选择
                            </button>
                        </div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(dialog);
            
            dialog.querySelector('#ai-chat-confirm-select').addEventListener('click', async () => {
                const checkboxes = dialog.querySelectorAll('input[type="checkbox"]');
                const selectedIds = Array.from(checkboxes).filter(c => c.checked).map(c => c.value);
                
                // Remove roles that are unchecked
                for (const role of this.aiChatRoles) {
                    if (!selectedIds.includes(role.agent_id)) {
                        await this.removeAIChatRole(role.agent_id);
                    }
                }
                
                // Add roles that are newly checked
                for (const agentId of selectedIds) {
                    if (!existingIds.includes(agentId)) {
                        await this.addAIChatRole(agentId);
                    }
                }
                
                dialog.remove();
            });
            
            dialog.querySelector('.modal-close').addEventListener('click', () => dialog.remove());
        } catch (error) {
            console.error('打开角色选择对话框失败:', error);
        }
    }
    
    async openProcessingAgentSelectDialog() {
        try {
            const response = await fetch(`${this.baseUrl}/api/ai-chat/agents?refresh=true`);
            const result = await response.json();
            if (result.status !== 'success') {
                alert('获取agent列表失败');
                return;
            }

            const agents = result.data;
            const existingIds = [...this.processingAgentIds];
            
            let html = '<div style="max-height: 400px; overflow-y: auto;">';
            agents.forEach(agent => {
                const isSelected = existingIds.includes(agent.id);
                html += `
                    <label style="display: flex; align-items: center; padding: 10px; border-bottom: 1px solid #eee; cursor: pointer;">
                        <input type="checkbox" ${isSelected ? 'checked' : ''} value="${agent.id}" data-name="${agent.name}">
                        <div style="margin-left: 10px;">
                            <div style="font-weight: 600;">${agent.name}</div>
                            <div style="font-size: 12px; color: #666;">${agent.role_description.substring(0, 50)}...</div>
                        </div>
                    </label>
                `;
            });
            html += '</div>';

            const dialog = document.createElement('div');
            dialog.className = 'modal';
            dialog.style.display = 'block';
            dialog.innerHTML = `
                <div class="modal-content" style="width: 500px;">
                    <div class="modal-header">
                        <h3><i class="fas fa-users"></i> 选择处理角色</h3>
                        <button class="modal-close" onclick="this.closest('.modal').remove()">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="modal-body">
                        <p style="color: #666; margin-bottom: 15px; font-size: 13px;">选择用于文档处理的Agent（可多选），未选择时使用所有已启用的Agent。</p>
                        ${html}
                        <div style="margin-top: 15px;">
                            <button id="processing-confirm-select" class="btn btn-primary" style="width: 100%;">
                                <i class="fas fa-check"></i> 确认选择
                            </button>
                        </div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(dialog);
            
            const selectionOrder = [...existingIds];
            
            dialog.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
                checkbox.addEventListener('change', () => {
                    const agentId = checkbox.value;
                    if (checkbox.checked) {
                        if (!selectionOrder.includes(agentId)) {
                            selectionOrder.push(agentId);
                        }
                    } else {
                        const index = selectionOrder.indexOf(agentId);
                        if (index > -1) {
                            selectionOrder.splice(index, 1);
                        }
                    }
                });
            });
            
            dialog.querySelector('#processing-confirm-select').addEventListener('click', () => {
                this.processingAgentIds = selectionOrder;
                
                const selectBtn = document.getElementById('processing-select-agents-btn');
                if (selectBtn && selectionOrder.length > 0) {
                    const selectedNames = selectionOrder.map(id => {
                        const agent = agents.find(a => a.id === id);
                        return agent ? agent.name : id;
                    }).join('、');
                    selectBtn.innerHTML = `<i class="fas fa-users"></i> 角色选择 (${selectedNames})`;
                } else if (selectBtn) {
                    selectBtn.innerHTML = '<i class="fas fa-users"></i> 角色选择';
                }
                
                dialog.remove();
            });
            
            dialog.querySelector('.modal-close').addEventListener('click', () => dialog.remove());
        } catch (error) {
            console.error('打开处理角色选择对话框失败:', error);
        }
    }

    async addAIChatRole(agentId) {
        try {
            const response = await fetch(`${this.baseUrl}/api/ai-chat/add-role`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ agent_id: agentId })
            });
            const result = await response.json();
            if (result.status === 'success') {
                this.aiChatRoles.push(result.data);
                this.renderAIChatRoles();
            } else {
                alert(result.message);
            }
        } catch (error) {
            console.error('添加角色失败:', error);
        }
    }

    async removeAIChatRole(agentId) {
        try {
            const response = await fetch(`${this.baseUrl}/api/ai-chat/remove-role`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ agent_id: agentId })
            });
            const result = await response.json();
            if (result.status === 'success') {
                this.aiChatRoles = this.aiChatRoles.filter(r => r.agent_id !== agentId);
                this.renderAIChatRoles();
            }
        } catch (error) {
            console.error('移除角色失败:', error);
        }
    }

    renderAIChatRoles() {
        const roleList = document.getElementById('ai-chat-role-list');
        if (!roleList) return;

        if (this.aiChatRoles.length === 0) {
            roleList.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-users" style="font-size: 32px; margin-bottom: 10px;"></i>
                    <p>点击"角色选择"添加角色</p>
                </div>
            `;
            return;
        }

        let html = '';
        this.aiChatRoles.forEach((role, index) => {
            const avatar = this.aiChatRoleAvatars[role.name] || this.getRandomAvatar();
            const color = this.aiChatAvatarColors[index % this.aiChatAvatarColors.length];
            html += `
                <div class="ai-chat-role-card">
                    <button class="remove-btn" onclick="window.app.removeAIChatRole('${role.agent_id}')">
                        <i class="fas fa-times"></i>
                    </button>
                    <div class="ai-chat-role-header">
                        <div class="ai-chat-role-avatar" style="background: ${color};">${avatar}</div>
                        <div class="ai-chat-role-info">
                            <div class="ai-chat-role-name">${role.name}</div>
                            <div class="ai-chat-role-model">${role.model_name}</div>
                        </div>
                    </div>
                </div>
            `;
        });

        roleList.innerHTML = html;
    }

    getRandomAvatar() {
        const avatars = ['👤', '🧑', '👨', '👩', '🧔', '👩‍🦰', '👨‍🦱', '🧑‍🦳'];
        return avatars[Math.floor(Math.random() * avatars.length)];
    }

    async toggleAIChat() {
        const startBtn = document.getElementById('ai-chat-start-btn');
        
        if (startBtn.innerHTML.includes('启动聊天')) {
            await this.startAIChat();
        } else {
            await this.stopAIChat();
        }
    }

    async startAIChat() {
        if (this.aiChatRoles.length < 2) {
            alert('请至少添加2个角色才能开始聊天');
            return;
        }

        const dialog = document.createElement('div');
        dialog.className = 'modal';
        dialog.style.display = 'block';
        dialog.innerHTML = `
            <div class="modal-content" style="width: 450px;">
                <div class="modal-header">
                    <h3><i class="fas fa-comments"></i> 开始聊天</h3>
                    <button class="modal-close" onclick="this.closest('.modal').remove()">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="modal-body">
                    <div style="margin-bottom: 15px;">
                        <label style="display: block; margin-bottom: 8px; font-weight: 600;">聊天主题</label>
                        <input type="text" id="ai-chat-theme-input" 
                               placeholder="请输入聊天主题，或留空由AI自动生成"
                               style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px;">
                    </div>
                    <div style="display: flex; gap: 10px; margin-top: 20px;">
                        <button id="ai-chat-generate-theme-btn" class="btn btn-secondary" style="flex: 1;">
                            <i class="fas fa-magic"></i> AI生成主题
                        </button>
                        <button id="ai-chat-confirm-start-btn" class="btn btn-primary" style="flex: 1;">
                            <i class="fas fa-play"></i> 开始聊天
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(dialog);
        
        const themeInput = dialog.querySelector('#ai-chat-theme-input');
        themeInput.focus();
        
        dialog.querySelector('#ai-chat-generate-theme-btn').addEventListener('click', async () => {
            const btn = dialog.querySelector('#ai-chat-generate-theme-btn');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 生成中...';
            
            try {
                const response = await fetch(`${this.baseUrl}/api/ai-chat/generate-theme`);
                const result = await response.json();
                if (result.status === 'success') {
                    themeInput.value = result.data.theme;
                }
            } catch (error) {
                console.error('生成主题失败:', error);
                themeInput.value = '讨论人工智能对未来的影响';
            }
            
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-magic"></i> AI生成主题';
        });
        
        dialog.querySelector('#ai-chat-confirm-start-btn').addEventListener('click', async () => {
            let theme = themeInput.value.trim();
            
            if (!theme) {
                try {
                    const response = await fetch(`${this.baseUrl}/api/ai-chat/generate-theme`);
                    const result = await response.json();
                    if (result.status === 'success') {
                        theme = result.data.theme;
                    }
                } catch (error) {
                    console.error('生成主题失败:', error);
                    theme = '讨论人工智能对未来的影响';
                }
            }
            
            dialog.remove();
            await this._startAIChatWithTheme(theme);
        });
        
        dialog.querySelector('.modal-close').addEventListener('click', () => dialog.remove());
    }
    
    async _startAIChatWithTheme(theme) {
        try {
            if (this.isAIChatting) {
                alert('聊天正在进行中，请先停止当前聊天');
                return;
            }
            
            this.isAIChatting = true;
            this.aiChatMessages = [];
            this.renderAIChatMessages();
            this.updateAIChatStats();
            
            const startBtn = document.getElementById('ai-chat-start-btn');
            startBtn.innerHTML = '<i class="fas fa-stop"></i> 停止聊天';
            startBtn.classList.remove('btn-success');
            startBtn.classList.add('btn-danger');
            
            this.connectAIChatEvents(theme);
        } catch (error) {
            console.error('启动聊天失败:', error);
            alert('启动聊天失败: ' + error.message);
            this.isAIChatting = false;
        }
    }

    async stopAIChat() {
        try {
            this.isAIChatting = false;
            this.sendAIChatAction('stop');
            
            const startBtn = document.getElementById('ai-chat-start-btn');
            startBtn.innerHTML = '<i class="fas fa-play"></i> 启动聊天';
            startBtn.classList.remove('btn-danger');
            startBtn.classList.add('btn-success');
            
            if (this.aiChatWebSocket) {
                this.aiChatWebSocket.close();
                this.aiChatWebSocket = null;
            }
            
            this.removeTypingIndicator();
        } catch (error) {
            console.error('停止聊天失败:', error);
        }
    }

    connectAIChatEvents(theme = null) {
        if (this.aiChatWebSocket) {
            this.aiChatWebSocket.close();
        }

        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.aiChatWebSocket = new WebSocket(`${wsProtocol}//${window.location.host}/ws/ai-chat`);
        
        this.aiChatWebSocket.onopen = () => {
            console.log('AI Chat WebSocket connected');
            if (theme) {
                this.sendAIChatAction('start', { theme: theme });
            }
        };
        
        this.aiChatWebSocket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                if (data.status === 'connected') {
                    console.log('WebSocket connected:', data.message);
                } else if (data.status === 'started') {
                    this.renderAIChatTheme(data.theme);
                } else if (data.status === 'stopped') {
                    this.stopAIChat();
                } else if (data.status === 'error') {
                    alert(data.message);
                } else if (data.event === 'theme') {
                    this.renderAIChatTheme(data.data.theme);
                } else if (data.event === 'typing') {
                    this.showTypingIndicator(data.data.role_name);
                } else if (data.event === 'message_chunk') {
                    this.removeTypingIndicator();
                    this.updateStreamingMessage(data.data.role_name, data.data.chunk, data.data.full_content);
                } else if (data.event === 'message') {
                    this.finalizeStreamingMessage(data.data);
                } else if (data.event === 'stopped') {
                    this.stopAIChat();
                } else if (data.event === 'chat_ended') {
                    this.isAIChatting = false;
                    const startBtn = document.getElementById('ai-chat-start-btn');
                    if (startBtn) {
                        startBtn.innerHTML = '<i class="fas fa-play"></i> 启动聊天';
                        startBtn.classList.remove('btn-danger');
                        startBtn.classList.add('btn-success');
                    }
                    this.removeTypingIndicator();
                }
            } catch (e) {
                console.error('解析AI聊天事件失败:', e);
            }
        };

        this.aiChatWebSocket.onerror = (error) => {
            console.error('AI Chat WebSocket error:', error);
            if (this.aiChatWebSocket) {
                this.aiChatWebSocket.close();
                this.aiChatWebSocket = null;
            }
        };

        this.aiChatWebSocket.onclose = () => {
            console.log('AI Chat WebSocket disconnected');
            this.aiChatWebSocket = null;
        };
    }

    sendAIChatAction(action, data = {}) {
        if (this.aiChatWebSocket && this.aiChatWebSocket.readyState === WebSocket.OPEN) {
            this.aiChatWebSocket.send(JSON.stringify({ action, ...data }));
        }
    }

    renderAIChatTheme(theme) {
        const messagesContainer = document.getElementById('ai-chat-messages');
        if (!messagesContainer) return;
        
        messagesContainer.innerHTML = `
            <div class="ai-chat-theme-info">
                <i class="fas fa-lightbulb"></i> 聊天主题：${theme}
            </div>
        `;
    }

    showTypingIndicator(roleName) {
        const messagesContainer = document.getElementById('ai-chat-messages');
        if (!messagesContainer) return;
        
        this.removeTypingIndicator();
        
        const role = this.aiChatRoles.find(r => r.name === roleName);
        const avatar = role ? this.aiChatRoleAvatars[role.name] || this.getRandomAvatar() : '👤';
        const colorIndex = this.aiChatRoles.findIndex(r => r.name === roleName);
        const color = this.aiChatAvatarColors[colorIndex % this.aiChatAvatarColors.length];
        
        const typingDiv = document.createElement('div');
        typingDiv.className = 'ai-chat-message ai-chat-typing-indicator';
        typingDiv.innerHTML = `
            <div class="ai-chat-message-avatar" style="background: ${color};">${avatar}</div>
            <div class="ai-chat-message-content">
                <div class="ai-chat-message-name">${roleName}</div>
                <div class="ai-chat-typing">
                    <span>正在输入</span>
                    <div class="ai-chat-typing-dot"></div>
                    <div class="ai-chat-typing-dot"></div>
                    <div class="ai-chat-typing-dot"></div>
                </div>
            </div>
        `;
        
        messagesContainer.appendChild(typingDiv);
        this.scrollAIChatToBottom();
    }

    removeTypingIndicator() {
        const indicator = document.querySelector('.ai-chat-typing-indicator');
        if (indicator) {
            indicator.remove();
        }
    }

    updateStreamingMessage(roleName, chunk, fullContent) {
        const messagesContainer = document.getElementById('ai-chat-messages');
        if (!messagesContainer) return;

        let streamingMsg = messagesContainer.querySelector('.ai-chat-message.streaming');
        
        if (!streamingMsg) {
            const role = this.aiChatRoles.find(r => r.name === roleName);
            const avatar = role ? this.aiChatRoleAvatars[role.name] || this.getRandomAvatar() : '👤';
            const colorIndex = this.aiChatRoles.findIndex(r => r.name === roleName);
            const color = this.aiChatAvatarColors[colorIndex % this.aiChatAvatarColors.length];
            
            streamingMsg = document.createElement('div');
            streamingMsg.className = 'ai-chat-message streaming';
            streamingMsg.innerHTML = `
                <div class="ai-chat-message-avatar" style="background: ${color};">${avatar}</div>
                <div class="ai-chat-message-content">
                    <div class="ai-chat-message-name">${roleName}</div>
                    <div class="ai-chat-message-text">${this.escapeHtml(this.sanitizeThinkingContent(fullContent))}</div>
                </div>
            `;
            
            messagesContainer.appendChild(streamingMsg);
        } else {
            const textElement = streamingMsg.querySelector('.ai-chat-message-text');
            if (textElement) {
                textElement.innerHTML = this.escapeHtml(this.sanitizeThinkingContent(fullContent));
            }
        }
        
        this.scrollAIChatToBottom();
    }

    finalizeStreamingMessage(messageData) {
        const messagesContainer = document.getElementById('ai-chat-messages');
        if (!messagesContainer) return;

        const streamingMsg = messagesContainer.querySelector('.ai-chat-message.streaming');
        if (streamingMsg) {
            streamingMsg.classList.remove('streaming');
            
            const nameElement = streamingMsg.querySelector('.ai-chat-message-name');
            if (nameElement && messageData.timestamp) {
                const timestamp = this.formatTimestamp(messageData.timestamp);
                if (!nameElement.querySelector('.ai-chat-message-time')) {
                    nameElement.innerHTML = `${messageData.role_name}<span class="ai-chat-message-time">${timestamp}</span>`;
                }
            }
            
            const textElement = streamingMsg.querySelector('.ai-chat-message-text');
            if (textElement) {
                const content = messageData.content;
                const charCount = messageData.char_count;
                const messageIndex = messageData.message_index || (this.aiChatMessages.length + 1);
                
                if (messageData.is_video && messageData.video_url) {
                    const videoSrc = messageData.video_url;
                    const prompt = messageData.video_prompt || content;
                    
                    textElement.innerHTML = `
                        <div class="ai-chat-video-container">
                            <video src="${videoSrc}" controls class="ai-chat-video" loading="lazy">
                                您的浏览器不支持视频播放
                            </video>
                            <div class="ai-chat-video-prompt">提示词: ${this.escapeHtml(prompt)}</div>
                        </div>
                        <span class="ai-chat-char-count" style="color: #94a3b8; font-size: 11px; margin-left: 8px;">(${messageIndex}号/${charCount}字)</span>
                    `;
                } else if (messageData.is_image && (messageData.image_url || messageData.image_data)) {
                    const imageSrc = messageData.image_url || `data:image/png;base64,${messageData.image_data}`;
                    const prompt = messageData.image_prompt || content;
                    
                    textElement.innerHTML = `
                        <div class="ai-chat-image-container">
                            <img src="${imageSrc}" alt="生成的图片" class="ai-chat-image" loading="lazy" onclick="window.aiChatOpenImage('${imageSrc.replace(/'/g, "\\'")}')">
                            <div class="ai-chat-image-prompt">提示词: ${this.escapeHtml(prompt)}</div>
                        </div>
                        <span class="ai-chat-char-count" style="color: #94a3b8; font-size: 11px; margin-left: 8px;">(${messageIndex}号/${charCount}字)</span>
                    `;
                } else {
                    const formattedContent = this.formatAIChatContent(content);
                    textElement.innerHTML = formattedContent + 
                        `<span class="ai-chat-char-count" style="color: #94a3b8; font-size: 11px; margin-left: 8px;">(${messageIndex}号/${charCount}字)</span>`;
                }
            }
        } else if (messageData.is_video && messageData.video_url) {
            const role = this.aiChatRoles.find(r => r.name === messageData.role_name);
            const avatar = role ? this.aiChatRoleAvatars[role.name] || this.getRandomAvatar() : '👤';
            const colorIndex = this.aiChatRoles.findIndex(r => r.name === messageData.role_name);
            const color = this.aiChatAvatarColors[colorIndex % this.aiChatAvatarColors.length];
            
            const videoSrc = messageData.video_url;
            const prompt = messageData.video_prompt || messageData.content;
            const charCount = messageData.char_count;
            const messageIndex = messageData.message_index || (this.aiChatMessages.length + 1);
            const timestamp = messageData.timestamp ? this.formatTimestamp(messageData.timestamp) : '';
            
            const videoMsg = document.createElement('div');
            videoMsg.className = 'ai-chat-message';
            videoMsg.innerHTML = `
                <div class="ai-chat-message-avatar" style="background: ${color};">${avatar}</div>
                <div class="ai-chat-message-content">
                    <div class="ai-chat-message-name">${messageData.role_name}${timestamp ? `<span class="ai-chat-message-time">${timestamp}</span>` : ''}</div>
                    <div class="ai-chat-message-text">
                        <div class="ai-chat-video-container">
                            <video src="${videoSrc}" controls class="ai-chat-video" loading="lazy">
                                您的浏览器不支持视频播放
                            </video>
                            <div class="ai-chat-video-prompt">提示词: ${this.escapeHtml(prompt)}</div>
                        </div>
                        <span class="ai-chat-char-count" style="color: #94a3b8; font-size: 11px; margin-left: 8px;">(${messageIndex}号/${charCount}字)</span>
                    </div>
                </div>
            `;
            messagesContainer.appendChild(videoMsg);
            this.scrollAIChatToBottom();
        } else if (messageData.is_image && (messageData.image_url || messageData.image_data)) {
            const role = this.aiChatRoles.find(r => r.name === messageData.role_name);
            const avatar = role ? this.aiChatRoleAvatars[role.name] || this.getRandomAvatar() : '👤';
            const colorIndex = this.aiChatRoles.findIndex(r => r.name === messageData.role_name);
            const color = this.aiChatAvatarColors[colorIndex % this.aiChatAvatarColors.length];
            
            const imageSrc = messageData.image_url || `data:image/png;base64,${messageData.image_data}`;
            const prompt = messageData.image_prompt || messageData.content;
            const charCount = messageData.char_count;
            const messageIndex = messageData.message_index || (this.aiChatMessages.length + 1);
            const timestamp = messageData.timestamp ? this.formatTimestamp(messageData.timestamp) : '';
            
            const imageMsg = document.createElement('div');
            imageMsg.className = 'ai-chat-message';
            imageMsg.innerHTML = `
                <div class="ai-chat-message-avatar" style="background: ${color};">${avatar}</div>
                <div class="ai-chat-message-content">
                    <div class="ai-chat-message-name">${messageData.role_name}${timestamp ? `<span class="ai-chat-message-time">${timestamp}</span>` : ''}</div>
                    <div class="ai-chat-message-text">
                        <div class="ai-chat-image-container">
                            <img src="${imageSrc}" alt="生成的图片" class="ai-chat-image" loading="lazy" onclick="window.aiChatOpenImage('${imageSrc.replace(/'/g, "\\'")}')">
                            <div class="ai-chat-image-prompt">提示词: ${this.escapeHtml(prompt)}</div>
                        </div>
                        <span class="ai-chat-char-count" style="color: #94a3b8; font-size: 11px; margin-left: 8px;">(${messageIndex}号/${charCount}字)</span>
                    </div>
                </div>
            `;
            messagesContainer.appendChild(imageMsg);
            this.scrollAIChatToBottom();
        }
        
        const existingIndex = this.aiChatMessages.findIndex(m => m.role_name === messageData.role_name && m.content === messageData.content);
        if (existingIndex === -1) {
            this.aiChatMessages.push(messageData);
        }
        
        // 更新总统计
        this.updateAIChatStats();
    }
    
    updateAIChatStats() {
        const totalMessagesEl = document.getElementById('ai-chat-total-messages');
        const totalCharsEl = document.getElementById('ai-chat-total-chars');
        
        if (totalMessagesEl) {
            totalMessagesEl.textContent = this.aiChatMessages.length;
        }
        
        if (totalCharsEl) {
            const totalChars = this.aiChatMessages.reduce((sum, msg) => {
                return sum + (msg.char_count || msg.content.length);
            }, 0);
            totalCharsEl.textContent = totalChars;
        }
    }
    
    sanitizeThinkingContent(text) {
        return window.Utils.sanitizeThinkingContent(text);
    }

    formatAIChatContent(content) {
        return window.Utils.formatAIChatContent(content);
    }

    renderAIChatMessages() {
        const messagesContainer = document.getElementById('ai-chat-messages');
        if (!messagesContainer) return;

        if (this.aiChatMessages.length === 0) {
            messagesContainer.innerHTML = '';
            return;
        }

        const existingMessages = messagesContainer.querySelectorAll('.ai-chat-message');
        const startIndex = existingMessages.length;

        if (startIndex === 0) {
            let html = '';
            this.aiChatMessages.forEach((msg, index) => {
                const role = this.aiChatRoles.find(r => r.name === msg.role_name);
                const avatar = role ? this.aiChatRoleAvatars[role.name] || this.getRandomAvatar() : '👤';
                const colorIndex = this.aiChatRoles.findIndex(r => r.name === msg.role_name);
                const color = this.aiChatAvatarColors[colorIndex % this.aiChatAvatarColors.length];
                
                const colorClass = this.getIntelligentColorClass(msg.content);
                
                // 添加字数标注和序号
                const charCount = msg.char_count || msg.content.length;
                const messageIndex = msg.message_index || (index + 1);
                const charCountHtml = `<span class="ai-chat-char-count" style="color: #94a3b8; font-size: 11px; margin-left: 8px;">(${messageIndex}号/${charCount}字)</span>`;
                
                // 添加时间
                const timestamp = msg.timestamp ? this.formatTimestamp(msg.timestamp) : '';
                
                // 处理强调文字
                const formattedContent = this.formatAIChatContent(msg.content);
                
                let messageContent = `<div class="ai-chat-message-text ${colorClass}">${formattedContent}${charCountHtml}</div>`;
                
                if (msg.is_video && msg.video_url) {
                    const videoPrompt = msg.video_prompt || msg.content;
                    messageContent = `
                        <div class="ai-chat-message-text">
                            <div class="ai-chat-video-container">
                                <video src="${msg.video_url}" controls class="ai-chat-video" loading="lazy">
                                    您的浏览器不支持视频播放
                                </video>
                                <div class="ai-chat-video-prompt">提示词: ${this.escapeHtml(videoPrompt)}</div>
                            </div>
                            ${charCountHtml}
                        </div>
                    `;
                } else if (msg.is_image && (msg.image_url || msg.image_data)) {
                    const imageSrc = msg.image_url || `data:image/png;base64,${msg.image_data}`;
                    const imagePrompt = msg.image_prompt || msg.content;
                    messageContent = `
                        <div class="ai-chat-message-text">
                            <div class="ai-chat-image-container">
                                <img src="${imageSrc}" alt="生成的图片" class="ai-chat-image" loading="lazy" onclick="window.aiChatOpenImage('${imageSrc.replace(/'/g, "\\'")}')">
                                <div class="ai-chat-image-prompt">提示词: ${this.escapeHtml(imagePrompt)}</div>
                            </div>
                            ${charCountHtml}
                        </div>
                    `;
                }
                
                html += `
                    <div class="ai-chat-message">
                        <div class="ai-chat-message-avatar" style="background: ${color};">${avatar}</div>
                        <div class="ai-chat-message-content">
                            <div class="ai-chat-message-name">${msg.role_name}${timestamp ? `<span class="ai-chat-message-time">${timestamp}</span>` : ''}</div>
                            ${messageContent}
                        </div>
                    </div>
                `;
            });

            const themeInfo = messagesContainer.querySelector('.ai-chat-theme-info');
            if (themeInfo) {
                messagesContainer.innerHTML = themeInfo.outerHTML + html;
            } else {
                messagesContainer.innerHTML = html;
            }
        } else {
            const fragment = document.createDocumentFragment();
            
            for (let i = startIndex; i < this.aiChatMessages.length; i++) {
                const msg = this.aiChatMessages[i];
                const role = this.aiChatRoles.find(r => r.name === msg.role_name);
                const avatar = role ? this.aiChatRoleAvatars[role.name] || this.getRandomAvatar() : '👤';
                const colorIndex = this.aiChatRoles.findIndex(r => r.name === msg.role_name);
                const color = this.aiChatAvatarColors[colorIndex % this.aiChatAvatarColors.length];
                
                const colorClass = this.getIntelligentColorClass(msg.content);
                
                // 添加字数标注和序号
                const charCount = msg.char_count || msg.content.length;
                const messageIndex = msg.message_index || (i + 1);
                const charCountHtml = `<span class="ai-chat-char-count" style="color: #94a3b8; font-size: 11px; margin-left: 8px;">(${messageIndex}号/${charCount}字)</span>`;
                
                // 添加时间
                const timestamp = msg.timestamp ? this.formatTimestamp(msg.timestamp) : '';
                
                // 处理强调文字
                const formattedContent = this.formatAIChatContent(msg.content);
                
                let messageContent = `<div class="ai-chat-message-text ${colorClass}">${formattedContent}${charCountHtml}</div>`;
                
                if (msg.is_video && msg.video_url) {
                    const videoPrompt = msg.video_prompt || msg.content;
                    messageContent = `
                        <div class="ai-chat-message-text">
                            <div class="ai-chat-video-container">
                                <video src="${msg.video_url}" controls class="ai-chat-video" loading="lazy">
                                    您的浏览器不支持视频播放
                                </video>
                                <div class="ai-chat-video-prompt">提示词: ${this.escapeHtml(videoPrompt)}</div>
                            </div>
                            ${charCountHtml}
                        </div>
                    `;
                } else if (msg.is_image && (msg.image_url || msg.image_data)) {
                    const imageSrc = msg.image_url || `data:image/png;base64,${msg.image_data}`;
                    const imagePrompt = msg.image_prompt || msg.content;
                    messageContent = `
                        <div class="ai-chat-message-text">
                            <div class="ai-chat-image-container">
                                <img src="${imageSrc}" alt="生成的图片" class="ai-chat-image" loading="lazy" onclick="window.aiChatOpenImage('${imageSrc.replace(/'/g, "\\'")}')">
                                <div class="ai-chat-image-prompt">提示词: ${this.escapeHtml(imagePrompt)}</div>
                            </div>
                            ${charCountHtml}
                        </div>
                    `;
                }
                
                const msgDiv = document.createElement('div');
                msgDiv.className = 'ai-chat-message';
                msgDiv.innerHTML = `
                    <div class="ai-chat-message-avatar" style="background: ${color};">${avatar}</div>
                    <div class="ai-chat-message-content">
                        <div class="ai-chat-message-name">${msg.role_name}${timestamp ? `<span class="ai-chat-message-time">${timestamp}</span>` : ''}</div>
                        ${messageContent}
                    </div>
                `;
                
                fragment.appendChild(msgDiv);
            }
            
            messagesContainer.appendChild(fragment);
        }
        
        this.scrollAIChatToBottom();
    }

    getIntelligentColorClass(content) {
        if (content.includes('错误') || content.includes('失败') || content.includes('问题')) {
            return 'intelligent-color danger';
        } else if (content.includes('成功') || content.includes('完成') || content.includes('好的')) {
            return 'intelligent-color success';
        } else if (content.includes('注意') || content.includes('警告') || content.includes('提醒')) {
            return 'intelligent-color warning';
        }
        return '';
    }

    scrollAIChatToBottom() {
        const messagesContainer = document.getElementById('ai-chat-messages');
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }

    escapeHtml(text) {
        return window.Utils.escapeHtml(text);
    }

    formatTimestamp(timestamp) {
        return window.Utils.formatTimestamp(timestamp);
    }

    // ========== 统计分析功能 ==========
    
    async loadStatistics() {
        try {
            const startDate = document.getElementById('stat-start-date')?.value;
            const endDate = document.getElementById('stat-end-date')?.value;
            
            let statsUrl = `${this.baseUrl}/api/model_calls/statistics`;
            if (startDate || endDate) {
                const params = [];
                if (startDate) params.push(`start_date=${startDate}`);
                if (endDate) params.push(`end_date=${endDate}`);
                statsUrl += '?' + params.join('&');
            }
            
            const [statsResponse, logsResponse] = await Promise.all([
                fetch(statsUrl),
                fetch(`${this.baseUrl}/api/model_calls?limit=10`)
            ]);
            
            const stats = await statsResponse.json();
            const logs = await logsResponse.json();
            
            this.renderStatistics(stats);
            this.renderRecentCalls(logs);
        } catch (error) {
            console.error('加载统计数据失败:', error);
        }
    }
    
    renderStatistics(stats) {
        document.getElementById('stat-total-calls').textContent = stats.total_calls || 0;
        document.getElementById('stat-total-tokens').textContent = (stats.total_tokens || 0).toLocaleString();
        document.getElementById('stat-prompt-tokens').textContent = (stats.total_prompt_tokens || 0).toLocaleString();
        document.getElementById('stat-completion-tokens').textContent = (stats.total_completion_tokens || 0).toLocaleString();
        
        const modelsList = document.getElementById('stat-models-list');
        if (stats.models && Object.keys(stats.models).length > 0) {
            modelsList.innerHTML = Object.entries(stats.models).map(([modelName, modelStats]) => {
                return `
                    <div style="padding: 10px; border-bottom: 1px solid #e2e8f0;">
                        <div style="font-size: 13px; font-weight: 500; color: #1e293b;">${modelName}</div>
                        <div style="font-size: 12px; color: #64748b; margin-top: 4px;">
                            调用 ${modelStats.calls} 次 | Token ${modelStats.total_tokens.toLocaleString()} | 
                            输入 ${modelStats.prompt_tokens.toLocaleString()} | 输出 ${modelStats.completion_tokens.toLocaleString()}
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            modelsList.innerHTML = '<div class="empty-state">暂无数据</div>';
        }
        
        const dailyList = document.getElementById('stat-daily-list');
        if (stats.daily_stats && stats.daily_stats.length > 0) {
            dailyList.innerHTML = stats.daily_stats.map(day => {
                return `
                    <div style="padding: 10px; border-bottom: 1px solid #e2e8f0;">
                        <div style="font-size: 13px; font-weight: 500; color: #1e293b;">${day.date}</div>
                        <div style="font-size: 12px; color: #64748b; margin-top: 4px;">
                            调用 ${day.calls} 次 | Token ${day.total_tokens.toLocaleString()}
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            dailyList.innerHTML = '<div class="empty-state">暂无数据</div>';
        }
    }
    
    renderRecentCalls(logs) {
        const recentList = document.getElementById('stat-recent-calls');
        if (logs.logs && logs.logs.length > 0) {
            recentList.innerHTML = logs.logs.map(log => {
                const timestamp = new Date(log.timestamp);
                const timeStr = timestamp.toLocaleString('zh-CN', {
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit'
                });
                
                const userMsg = log.messages && log.messages.length > 0 ? 
                    log.messages[log.messages.length - 1].content.slice(0, 50) + (log.messages[log.messages.length - 1].content.length > 50 ? '...' : '') : '';
                
                return `
                    <div style="padding: 12px; border-bottom: 1px solid #e2e8f0; display: flex; justify-content: space-between; cursor: pointer;" 
                         onclick="app.showLogDetail('${log.id}')" 
                         onmouseenter="this.style.background='#f8fafc'" 
                         onmouseleave="this.style.background='transparent'">
                        <div style="flex: 1;">
                            <div style="font-size: 13px; font-weight: 500; color: #3b82f6;">${log.model_name}</div>
                            <div style="font-size: 12px; color: #64748b; margin-top: 4px;">${userMsg}</div>
                        </div>
                        <div style="text-align: right; margin-left: 20px;">
                            <div style="font-size: 12px; color: #64748b;">${timeStr}</div>
                            <div style="font-size: 12px; color: #10b981; margin-top: 4px;">
                                ${log.prompt_tokens} → ${log.completion_tokens} tokens
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            recentList.innerHTML = '<div class="empty-state">暂无数据</div>';
        }
    }

    async showLogDetail(logId) {
        try {
            const response = await fetch(`${this.baseUrl}/api/model_calls/${logId}`);
            const result = await response.json();
            if (result.log) {
                const log = result.log;
                document.getElementById('detail-model-name').textContent = log.model_name;
                document.getElementById('detail-total-tokens').textContent = log.total_tokens.toLocaleString();
                document.getElementById('detail-prompt-tokens').textContent = log.prompt_tokens.toLocaleString();
                document.getElementById('detail-completion-tokens').textContent = log.completion_tokens.toLocaleString();
                document.getElementById('detail-duration').textContent = log.duration ? log.duration.toFixed(2) + 's' : '0s';
                
                const timestamp = new Date(log.timestamp);
                document.getElementById('detail-timestamp').textContent = timestamp.toLocaleString('zh-CN');
                
                if (log.messages && log.messages.length > 0) {
                    const messagesStr = log.messages.map(m => `[${m.role}] ${m.content}`).join('\n\n');
                    document.getElementById('detail-messages').textContent = messagesStr;
                } else {
                    document.getElementById('detail-messages').textContent = '-';
                }
                
                document.getElementById('detail-response').textContent = log.response || '-';
                
                document.getElementById('log-detail-modal').style.display = 'flex';
                this._logDetailMaximized = false;
            }
        } catch (error) {
            console.error('获取日志详情失败:', error);
        }
    }

    toggleLogDetailMaximize() {
        const modal = document.getElementById('log-detail-modal');
        const content = document.getElementById('log-detail-modal-content');
        const body = document.getElementById('log-detail-body');
        const maxBtn = document.querySelector('#log-detail-modal button[onclick="app.toggleLogDetailMaximize()"] i');
        
        if (!modal || !content || !body || !maxBtn) return;
        
        if (this._logDetailMaximized) {
            content.style.width = '90%';
            content.style.maxWidth = '900px';
            content.style.maxHeight = '80vh';
            content.style.borderRadius = '12px';
            body.style.padding = '20px';
            maxBtn.className = 'fas fa-expand';
            this._logDetailMaximized = false;
        } else {
            content.style.width = '100%';
            content.style.maxWidth = 'none';
            content.style.maxHeight = 'none';
            content.style.borderRadius = '0';
            body.style.padding = '30px';
            maxBtn.className = 'fas fa-compress';
            this._logDetailMaximized = true;
        }
    }

    // ========== 视频模型功能 ==========
    
    async loadVideoModels() {
        try {
            const response = await fetch('/api/video-models');
            const models = await response.json();
            
            const select = document.getElementById('video-model-select');
            if (!select) return;
            
            if (models.length === 0) {
                select.innerHTML = '<option value="">-- 请先在模型配置中添加视频模型 --</option>';
                return;
            }
            
            select.innerHTML = models.map(m => 
                `<option value="${m.id}">${m.name} (${m.model_name})</option>`
            ).join('');
        } catch (error) {
            console.error('加载视频模型失败:', error);
        }
    }
    
    async generateVideo() {
        const prompt = document.getElementById('video-prompt').value.trim();
        if (!prompt) {
            alert('请输入视频提示词');
            return;
        }
        
        const modelId = document.getElementById('video-model-select').value;
        if (!modelId) {
            alert('请先选择视频模型');
            return;
        }
        
        const width = parseInt(document.getElementById('video-width').value) || 1152;
        const height = parseInt(document.getElementById('video-height').value) || 768;
        const numFrames = parseInt(document.getElementById('video-frames').value) || 121;
        const frameRate = parseInt(document.getElementById('video-fps').value) || 24;
        const imageUrl = document.getElementById('video-image-url').value.trim();
        const negativePrompt = document.getElementById('video-negative-prompt').value.trim();
        
        // 显示结果区域和进度条
        document.getElementById('video-result').style.display = 'block';
        document.getElementById('video-progress').style.display = 'block';
        document.getElementById('video-result-content').style.display = 'none';
        document.getElementById('video-error').style.display = 'none';
        document.getElementById('video-progress-text').textContent = '正在创建任务...';
        
        // 进度条使用动画效果
        const progressBar = document.getElementById('video-progress-bar');
        progressBar.style.width = '0%';
        progressBar.style.transition = 'width 0.5s ease';
        let progress = 0;
        const animateProgress = () => {
            if (progress < 90) {
                progress += Math.random() * 10;
                progressBar.style.width = `${progress}%`;
            }
        };
        const progressInterval = setInterval(animateProgress, 2000);
        
        // 禁用按钮
        const btn = document.getElementById('generate-video-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 生成中...';
        
        try {
            const response = await fetch('/api/video-generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prompt: prompt,
                    model_id: modelId,
                    width: width,
                    height: height,
                    num_frames: numFrames,
                    frame_rate: frameRate,
                    image_url: imageUrl || null,
                    negative_prompt: negativePrompt
                })
            });
            
            const result = await response.json();
            
            if (result.status === 'success') {
                const videoId = result.video_id;
                document.getElementById('video-progress-text').textContent = `任务已创建 (ID: ${videoId.substring(0, 8)}...)，等待生成...`;
                
                // 开始轮询状态
                clearInterval(progressInterval);
                progressBar.style.width = '0%';
                this.pollVideoStatus(videoId);
            } else {
                throw new Error(result.message || '创建任务失败');
            }
        } catch (error) {
            console.error('视频生成失败:', error);
            document.getElementById('video-error').style.display = 'block';
            document.getElementById('video-error-text').textContent = error.message;
            document.getElementById('video-progress').style.display = 'none';
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-play-circle"></i> 生成视频';
        }
    }
    
    async pollVideoStatus(videoId) {
        let consecutiveFailures = 0;
        const progressBar = document.getElementById('video-progress-bar');
        
        const pollVideo = async () => {
            try {
                const response = await fetch(`/api/video-status/${videoId}`);
                const result = await response.json();
                
                // API返回格式: {code: "success"/"error", task_status: "completed"/"in_progress"/...}
                if (result.code === 'error') {
                    throw new Error(result.message || '请求失败');
                }
                
                const taskStatus = result.task_status || 'unknown';
                const progress = result.progress || 0;
                
                // 更新进度条
                if (progressBar) {
                    progressBar.style.width = `${progress}%`;
                }
                
                // 更新进度状态文本
                const statusTexts = {
                    'queued': '排队等待中...',
                    'in_progress': '生成中...',
                    'completed': '生成完成！',
                    'failed': '生成失败'
                };
                document.getElementById('video-progress-text').textContent = 
                    `${statusTexts[taskStatus] || '处理中...'} ${progress}%`;
                
                if (taskStatus === 'completed') {
                    clearInterval(pollInterval);
                    if (progressBar) {
                        progressBar.style.width = '100%';
                    }
                    
                    const videoUrl = result.video_url || '';
                    if (videoUrl) {
                        document.getElementById('video-progress').style.display = 'none';
                        document.getElementById('video-preview-area').style.display = 'none';
                        document.getElementById('video-result-content').style.display = 'block';
                        
                        const player = document.getElementById('video-result-player');
                        player.src = videoUrl;
                        
                        // 显示视频信息
                        const sizeInfo = result.size || '未知大小';
                        const seconds = result.seconds || '未知时长';
                        document.getElementById('video-result-info').textContent = 
                            `视频已保存到本地 | 时长: ${seconds} | 大小: ${sizeInfo}`;
                        
                        // 自动播放
                        player.play().catch(e => console.log('自动播放被阻止:', e));
                    } else {
                        throw new Error('视频生成完成，但未获取到视频URL');
                    }
                } else if (taskStatus === 'failed') {
                    clearInterval(pollInterval);
                    document.getElementById('video-progress').style.display = 'none';
                    document.getElementById('video-error').style.display = 'block';
                    const errorMsg = result.error || '视频生成失败';
                    document.getElementById('video-error-text').textContent = 
                        typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg);
                } else {
                    // 仍在进行中，重置失败计数
                    consecutiveFailures = 0;
                    pollTimeout = setTimeout(pollVideo, 1000);
                }
            } catch (error) {
                consecutiveFailures++;
                // 如果连续失败多次，停止轮询
                if (consecutiveFailures >= 3) {
                    clearInterval(pollInterval);
                    clearTimeout(pollTimeout);
                    document.getElementById('video-progress').style.display = 'none';
                    document.getElementById('video-error').style.display = 'block';
                    document.getElementById('video-error-text').textContent = error.message || '轮询失败';
                    return;
                }
                // 临时错误，继续重试
                pollTimeout = setTimeout(pollVideo, 1000);
            }
        };
        
        // 每1秒轮询一次（更快的响应速度）
        const pollInterval = setInterval(() => {}, 600000); // 10分钟后清理
        let pollTimeout = setTimeout(pollVideo, 1000);
    }
    
    clearVideoForm() {
        document.getElementById('video-prompt').value = '';
        document.getElementById('video-width').value = 1152;
        document.getElementById('video-height').value = 768;
        document.getElementById('video-frames').value = 121;
        document.getElementById('video-fps').value = 24;
        document.getElementById('video-image-url').value = '';
        document.getElementById('video-negative-prompt').value = '';
        document.getElementById('video-result').style.display = 'none';
        document.getElementById('video-progress-bar').style.width = '0%';
    }
    
    async optimizePrompt() {
        const prompt = document.getElementById('video-prompt').value.trim();
        
        if (!prompt) {
            alert('请先输入视频提示词');
            return;
        }
        
        const btn = document.getElementById('optimize-prompt-btn');
        const originalText = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 优化中...';
        btn.disabled = true;
        
        try {
            const response = await fetch('/api/optimize-prompt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: prompt })
            });
            
            const result = await response.json();
            
            if (result.code === 'success') {
                document.getElementById('video-prompt').value = result.optimized_prompt;
            } else {
                alert('优化失败: ' + result.message);
            }
        } catch (error) {
            console.error('优化提示词失败:', error);
            alert('优化提示词失败: ' + error.message);
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    }
}

// 图片放大查看
App.prototype.openImage = function(imageSrc) {
    // 检查是否已存在lightbox，存在则移除
    let overlay = document.getElementById('image-lightbox');
    if (overlay) {
        overlay.remove();
        return;
    }
    
    // 创建遮罩层
    overlay = document.createElement('div');
    overlay.id = 'image-lightbox';
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.9);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        cursor: pointer;
    `;
    
    // 创建图片
    const img = document.createElement('img');
    img.src = imageSrc;
    img.style.cssText = `
        max-width: 90%;
        max-height: 90%;
        object-fit: contain;
        border-radius: 8px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
    `;
    
    overlay.appendChild(img);
    document.body.appendChild(overlay);
    
    // 点击关闭
    overlay.addEventListener('click', () => {
        overlay.remove();
    });
};

// 将openImage挂载到window对象
window.aiChatOpenImage = function(imageSrc) {
    window.app.openImage(imageSrc);
};

// ============ 飞书接入管理 ============

App.prototype.showFeishuModal = async function() {
    document.getElementById('claw-feishu-modal').style.display = 'block';
    await this.loadFeishuStatus();
    await this.loadFeishuConfig();
    this.switchFeishuTab('config');
};

App.prototype.toggleFeishuMaximize = function() {
    const content = document.getElementById('claw-feishu-modal-content');
    content.classList.toggle('modal-maximized');
    const icon = event.currentTarget.querySelector('i');
    if (content.classList.contains('modal-maximized')) {
        icon.className = 'fas fa-compress';
    } else {
        icon.className = 'fas fa-expand';
    }
};

App.prototype.switchFeishuTab = function(tabName) {
    // 隐藏所有面板
    document.querySelectorAll('.feishu-tab-panel').forEach(p => p.style.display = 'none');
    // 移除所有按钮的active
    document.querySelectorAll('.feishu-tab-btn').forEach(b => b.classList.remove('active'));
    // 显示当前面板
    const panel = document.getElementById('feishu-' + tabName + '-panel');
    if (panel) panel.style.display = 'block';
    const btn = document.querySelector(`.feishu-tab-btn[data-tab="${tabName}"]`);
    if (btn) btn.classList.add('active');
    // 切换到消息日志时加载
    if (tabName === 'messages') {
        this.loadFeishuMessages();
    }
    // 切换到会话时加载
    if (tabName === 'sessions') {
        this.loadFeishuSessions();
    }
};

App.prototype.loadFeishuStatus = async function() {
    try {
        const response = await fetch('/api/lobster-claw/feishu/status');
        const data = await response.json();
        if (data.success) {
            const statusSection = document.getElementById('feishu-status-section');
            const enabledBadge = data.enabled
                ? '<span class="status-badge success">已启用</span>'
                : '<span class="status-badge warning">未启用</span>';
            const configBadge = data.is_configured
                ? '<span class="status-badge success">已配置</span>'
                : '<span class="status-badge error">未配置</span>';
            statusSection.innerHTML = `
                <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
                    <strong>状态：</strong> ${enabledBadge} ${configBadge}
                    <span style="color: #666;">机器人: ${data.bot_name || '-'}</span>
                    <span style="color: #666;">域名: ${data.domain || '-'}</span>
                </div>
                <div style="margin-top: 8px; padding: 8px; background: #f5f5f5; border-radius: 4px;">
                    <strong>Webhook URL:</strong>
                    <code id="feishu-webhook-url-display">${data.webhook_url}</code>
                    <button class="btn btn-secondary btn-sm" onclick="app.copyFeishuWebhookUrl()" style="margin-left: 8px;">
                        <i class="fas fa-copy"></i> 复制
                    </button>
                </div>
            `;
            // 更新帮助页面的 webhook url
            const helpUrl = document.getElementById('feishu-webhook-url-help');
            if (helpUrl) helpUrl.textContent = data.webhook_url;
        }
    } catch (e) {
        console.error('加载飞书状态失败:', e);
    }
};

App.prototype.loadFeishuConfig = async function() {
    try {
        const response = await fetch('/api/lobster-claw/feishu/config');
        const data = await response.json();
        if (data.success && data.config) {
            const c = data.config;
            document.getElementById('feishu-app-id').value = c.app_id || '';
            // 密码字段：脱敏显示为***时不填充，保持空让用户重新输入
            if (c.app_secret && c.app_secret !== '***') {
                document.getElementById('feishu-app-secret').value = c.app_secret;
            } else {
                document.getElementById('feishu-app-secret').value = '';
                document.getElementById('feishu-app-secret').placeholder = c.app_secret === '***' ? '已配置 (重新输入可修改)' : '应用密钥';
            }
            if (c.encrypt_key && c.encrypt_key !== '***') {
                document.getElementById('feishu-encrypt-key').value = c.encrypt_key;
            } else {
                document.getElementById('feishu-encrypt-key').value = '';
                document.getElementById('feishu-encrypt-key').placeholder = c.encrypt_key === '***' ? '已配置 (重新输入可修改)' : '事件加密密钥';
            }
            document.getElementById('feishu-verification-token').value = c.verification_token || '';
            document.getElementById('feishu-bot-name').value = c.bot_name || '';
            document.getElementById('feishu-domain').value = c.domain || 'feishu';
            document.getElementById('feishu-event-mode').value = c.event_mode || 'long_connection';
            document.getElementById('feishu-enabled').checked = !!c.enabled;
            document.getElementById('feishu-dm-policy').value = c.dm_policy || 'open';
            document.getElementById('feishu-allow-list').value = (c.allow_list || []).join('\n');
            document.getElementById('feishu-block-list').value = (c.block_list || []).join('\n');
            document.getElementById('feishu-handle-groups').checked = c.handle_groups !== false;
            document.getElementById('feishu-handle-dms').checked = c.handle_dms !== false;
            document.getElementById('feishu-trigger-on-mention').checked = c.trigger_on_mention !== false;
        }
    } catch (e) {
        console.error('加载飞书配置失败:', e);
    }
};

App.prototype.saveFeishuConfig = async function() {
    const allowList = document.getElementById('feishu-allow-list').value
        .split('\n').map(s => s.trim()).filter(s => s);
    const blockList = document.getElementById('feishu-block-list').value
        .split('\n').map(s => s.trim()).filter(s => s);

    const config = {
        app_id: document.getElementById('feishu-app-id').value.trim(),
        app_secret: document.getElementById('feishu-app-secret').value,
        encrypt_key: document.getElementById('feishu-encrypt-key').value,
        verification_token: document.getElementById('feishu-verification-token').value,
        bot_name: document.getElementById('feishu-bot-name').value.trim(),
        domain: document.getElementById('feishu-domain').value,
        event_mode: document.getElementById('feishu-event-mode').value,
        enabled: document.getElementById('feishu-enabled').checked,
        dm_policy: document.getElementById('feishu-dm-policy').value,
        allow_list: allowList,
        block_list: blockList,
        handle_groups: document.getElementById('feishu-handle-groups').checked,
        handle_dms: document.getElementById('feishu-handle-dms').checked,
        trigger_on_mention: document.getElementById('feishu-trigger-on-mention').checked
    };

    // 移除空字符串的密码字段（不修改）
    if (!config.app_secret) delete config.app_secret;
    if (!config.encrypt_key) delete config.encrypt_key;

    const msgDiv = document.getElementById('feishu-config-message');
    msgDiv.className = 'config-message-info';
    msgDiv.textContent = '正在保存...';

    try {
        const response = await fetch('/api/lobster-claw/feishu/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(config)
        });
        const data = await response.json();
        if (data.success) {
            msgDiv.className = 'config-message-success';
            msgDiv.textContent = '配置已保存';
            await this.loadFeishuStatus();
            setTimeout(() => { msgDiv.textContent = ''; }, 3000);
        } else {
            msgDiv.className = 'config-message-error';
            msgDiv.textContent = '保存失败: ' + (data.error || '未知错误');
        }
    } catch (e) {
        msgDiv.className = 'config-message-error';
        msgDiv.textContent = '保存失败: ' + e.message;
    }
};

App.prototype.testFeishuConnection = async function() {
    const msgDiv = document.getElementById('feishu-config-message');
    msgDiv.className = 'config-message-info';
    msgDiv.textContent = '正在测试连接...';

    try {
        const response = await fetch('/api/lobster-claw/feishu/test-connection', {
            method: 'POST'
        });
        const data = await response.json();
        if (data.success) {
            msgDiv.className = 'config-message-success';
            msgDiv.textContent = '连接成功! Token: ' + (data.token_preview || '') + '...';
        } else {
            msgDiv.className = 'config-message-error';
            msgDiv.textContent = '连接失败: ' + (data.error || '未知错误');
        }
    } catch (e) {
        msgDiv.className = 'config-message-error';
        msgDiv.textContent = '连接失败: ' + e.message;
    }
};

App.prototype.loadFeishuMessages = async function() {
    try {
        const response = await fetch('/api/lobster-claw/feishu/messages?limit=50');
        const data = await response.json();
        const tbody = document.getElementById('feishu-messages-tbody');
        if (data.success && data.messages && data.messages.length > 0) {
            tbody.innerHTML = data.messages.map(m => `
                <tr>
                    <td>${this.formatTime(m.timestamp)}</td>
                    <td title="${m.sender}">${(m.sender || '').substring(0, 12)}...</td>
                    <td>${m.message_type}</td>
                    <td title="${this.escapeHtml(m.content)}">${this.escapeHtml((m.content || '').substring(0, 50))}</td>
                    <td title="${this.escapeHtml(m.response)}">${this.escapeHtml((m.response || '').substring(0, 50))}</td>
                    <td><span class="status-badge ${m.status === 'success' ? 'success' : 'error'}">${m.status}</span></td>
                    <td>${(m.duration || 0).toFixed(2)}s</td>
                </tr>
            `).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #999;">暂无消息</td></tr>';
        }
    } catch (e) {
        console.error('加载飞书消息失败:', e);
    }
};

App.prototype.clearFeishuMessages = async function() {
    if (!confirm('确定清空所有飞书消息日志?')) return;
    try {
        const response = await fetch('/api/lobster-claw/feishu/messages', {method: 'DELETE'});
        const data = await response.json();
        if (data.success) {
            this.loadFeishuMessages();
        }
    } catch (e) {
        console.error('清空飞书消息失败:', e);
    }
};

App.prototype.copyFeishuWebhookUrl = function() {
    const urlEl = document.getElementById('feishu-webhook-url-display');
    if (urlEl) {
        // 构造完整URL
        const fullUrl = window.location.origin + urlEl.textContent;
        navigator.clipboard.writeText(fullUrl).then(() => {
            const btn = event.currentTarget;
            const origHtml = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-check"></i> 已复制';
            setTimeout(() => { btn.innerHTML = origHtml; }, 2000);
        });
    }
};

App.prototype.loadFeishuSessions = async function() {
    try {
        const response = await fetch('/api/lobster-claw/feishu/sessions');
        const data = await response.json();
        const listEl = document.getElementById('feishu-sessions-list');
        if (data.success && data.sessions && data.sessions.length > 0) {
            listEl.innerHTML = `
                <div style="display: grid; gap: 8px;">
                    ${data.sessions.map(s => `
                        <div class="feishu-session-item" onclick="app.loadFeishuSessionDetail('${s.session_id}')" style="padding: 12px; border: 1px solid #e0e0e0; border-radius: 8px; cursor: pointer; transition: all 0.2s;">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <i class="fas ${s.is_group ? 'fa-users' : 'fa-user'}" style="color: ${s.is_group ? '#2196F3' : '#4CAF50'};"></i>
                                    <span style="font-weight: 500;">${s.is_group ? '群聊' : '私聊'} - ${s.chat_id.substring(0, 16)}${s.chat_id.length > 16 ? '...' : ''}</span>
                                </div>
                                <span style="color: #999; font-size: 12px;">${s.message_count} 条消息</span>
                            </div>
                            <div style="margin-top: 4px; color: #999; font-size: 12px;">
                                ${s.last_used ? '最后活跃: ' + this.formatTime(s.last_used) : '暂无活跃时间'}
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        } else {
            listEl.innerHTML = '<div style="text-align: center; color: #999; padding: 40px;">暂无飞书会话</div>';
        }
    } catch (e) {
        console.error('加载飞书会话失败:', e);
    }
};

App.prototype.loadFeishuSessionDetail = async function(sessionId) {
    try {
        const response = await fetch(`/api/lobster-claw/feishu/sessions/${sessionId}`);
        const data = await response.json();
        if (data.success) {
            const detailEl = document.getElementById('feishu-session-detail');
            const messagesEl = document.getElementById('feishu-session-messages');
            
            messagesEl.innerHTML = `
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    ${data.messages.map(m => {
                        const isUser = m.role === 'user';
                        return `
                            <div style="display: flex; gap: 8px;">
                                <div style="width: 32px; height: 32px; border-radius: 50%; background: ${isUser ? '#2196F3' : '#4CAF50'}; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                                    <i class="fas ${isUser ? 'fa-user' : 'fa-robot'}" style="color: white; font-size: 14px;"></i>
                                </div>
                                <div style="flex: 1;">
                                    <div style="font-weight: 500; font-size: 13px; margin-bottom: 4px;">${isUser ? '用户' : '火锅大侠'}</div>
                                    <div style="background: ${isUser ? '#e3f2fd' : '#f1f8e9'}; padding: 8px 12px; border-radius: 8px; word-break: break-word;">${this.escapeHtml(m.content || '')}</div>
                                    <div style="color: #999; font-size: 11px; margin-top: 4px;">${m.timestamp ? this.formatTime(m.timestamp) : ''}</div>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            `;
            
            detailEl.style.display = 'block';
            messagesEl.scrollTop = messagesEl.scrollHeight;
        }
    } catch (e) {
        console.error('加载飞书会话详情失败:', e);
    }
};

App.prototype.closeFeishuSessionDetail = function() {
    document.getElementById('feishu-session-detail').style.display = 'none';
};

App.prototype.formatTime = function(isoStr) {
    if (!isoStr) return '-';
    try {
        const d = new Date(isoStr);
        return d.toLocaleString('zh-CN');
    } catch {
        return isoStr;
    }
};

App.prototype.toggleCollapseAll = function() {
    const header = document.querySelector('.header');
    const toolbar = document.querySelector('#lobster-claw-panel .toolbar');
    const leftNav = document.querySelector('.left-nav');
    const collapseBtn = document.getElementById('collapse-all-btn');
    const expandBtn = document.getElementById('expand-all-btn');
    
    const isCollapsed = header.classList.contains('collapsed');
    
    if (isCollapsed) {
        header.classList.remove('collapsed');
        toolbar.classList.remove('collapsed');
        leftNav.classList.remove('collapsed');
        if (collapseBtn) {
            const icon = collapseBtn.querySelector('i');
            icon.classList.remove('fa-expand');
            icon.classList.add('fa-compress');
            collapseBtn.title = '收缩所有菜单';
        }
        if (expandBtn) {
            expandBtn.classList.remove('show');
        }
    } else {
        header.classList.add('collapsed');
        toolbar.classList.add('collapsed');
        leftNav.classList.add('collapsed');
        if (collapseBtn) {
            const icon = collapseBtn.querySelector('i');
            icon.classList.remove('fa-compress');
            icon.classList.add('fa-expand');
            collapseBtn.title = '展开所有菜单';
        }
        if (expandBtn) {
            expandBtn.classList.add('show');
        }
    }
};

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    window.app = new App();
});