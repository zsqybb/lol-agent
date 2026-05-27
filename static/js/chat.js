// ==================== 统一智能问答 ====================

const chatModeConfig = {
    ai: {
        icon: 'fa-robot',
        title: 'AI 问答助手',
        desc: '问什么答什么，检测到英雄/装备/故事等关键词时自动调用知识库',
        placeholder: '随便问，检测到关键词会自动调用知识库',
        suggestions: [
            { query: '当前版本哪些英雄最强？推荐上分英雄', label: 'T1英雄推荐' },
            { query: '亚索怎么出装？符文怎么带？', label: '亚索攻略详解' },
            { query: '中单法师和刺客哪个版本更强势？', label: '中单版本分析' },
            { query: '英雄联盟排位赛机制是怎样的？', label: '排位赛机制' },
            { query: '德玛西亚的背景故事是什么？', label: '德玛西亚故事' },
            { query: '你好，你是谁？', label: '打个招呼' },
        ],
    },
    hero: {
        icon: 'fa-crown',
        title: '英雄问答',
        desc: '查询英雄的玩法攻略、出装推荐、符文配置、技能介绍等',
        placeholder: '输入英雄名+玩法/出装/符文，如：亚索怎么出装',
        suggestions: [
            { query: '亚索怎么玩？出装符文推荐', label: '亚索攻略' },
            { query: '盖伦的技能和出装', label: '盖伦攻略' },
            { query: '盲僧打野怎么出装？', label: '盲僧出装' },
            { query: '当前版本T1上单英雄推荐', label: 'T1上单推荐' },
            { query: '阿狸中单符文怎么带？', label: '阿狸符文' },
            { query: '金克丝ADC出装推荐', label: '金克丝出装' },
        ],
    },
    lore: {
        icon: 'fa-book-open',
        title: '故事问答',
        desc: '探索英雄的背景故事、阵营传说、符文之地的历史',
        placeholder: '输入英雄名+故事/背景，如：亚索的背景故事',
        suggestions: [
            { query: '亚索的背景故事', label: '亚索的故事' },
            { query: '阿狸的身世来历', label: '阿狸的身世' },
            { query: '德玛西亚的历史', label: '德玛西亚历史' },
            { query: '诺克萨斯阵营介绍', label: '诺克萨斯介绍' },
            { query: '艾欧尼亚的故事', label: '艾欧尼亚传说' },
            { query: '金克丝的背景故事', label: '金克丝的故事' },
        ],
    },
};

const chatState = {
    mode: 'ai',
    histories: { ai: [], hero: [], lore: [] },
    sessionIds: { ai: '', hero: '', lore: '' },
    loading: false,
};

function updateChatWelcome() {
    const cfg = chatModeConfig[chatState.mode];
    const iconEl = document.querySelector('.chat-welcome-icon');
    const titleEl = document.getElementById('chatWelcomeTitle');
    const descEl = document.getElementById('chatWelcomeDesc');
    const suggestionsEl = document.getElementById('chatSuggestions');
    const inputEl = document.getElementById('chatInput');

    if (iconEl) {
        iconEl.className = `fas ${cfg.icon} fa-2x chat-welcome-icon`;
        const colorMap = { ai: 'var(--info)', hero: 'var(--accent)', lore: 'var(--lore-color)' };
        iconEl.style.color = colorMap[chatState.mode];
    }
    if (titleEl) titleEl.textContent = cfg.title;
    if (descEl) descEl.textContent = cfg.desc;
    if (inputEl) inputEl.placeholder = cfg.placeholder;

    if (suggestionsEl) {
        suggestionsEl.innerHTML = cfg.suggestions.map(s =>
            `<button class="suggestion-btn" data-query="${s.query}">${s.label}</button>`
        ).join('');
        suggestionsEl.querySelectorAll('.suggestion-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                sendChatMessage(btn.dataset.query);
            });
        });
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatAiReply(text) {
    if (!text) return '';
    let html = escapeHtml(text);
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/^(##\s+.+)$/gm, '<div style="font-size:14px;font-weight:700;color:var(--accent);margin:10px 0 4px">$1</div>');
    html = html.replace(/^(#\s+.+)$/gm, '<div style="font-size:15px;font-weight:700;color:var(--accent);margin:10px 0 4px">$1</div>');
    html = html.replace(/^(\d+[.]\s+.+)$/gm, '<div style="padding-left:16px;margin:2px 0"><span style="color:var(--accent);font-weight:600">$1</span></div>');
    html = html.replace(/^([-*]\s+.+)$/gm, '<div style="padding-left:16px;margin:2px 0">• $1</div>');
    html = html.replace(/\n\n/g, '<div style="height:8px"></div>');
    html = html.replace(/\n/g, '<br>');
    return html;
}

function renderChatMessages() {
    const el = document.getElementById('chatHistory');
    if (!el) return;

    const history = chatState.histories[chatState.mode] || [];

    if (history.length === 0) {
        const welcomeEl = document.getElementById('chatWelcome');
        if (welcomeEl) welcomeEl.style.display = '';
        el.querySelectorAll('.chat-message').forEach(m => m.remove());
        return;
    }

    const welcomeEl = document.getElementById('chatWelcome');
    if (welcomeEl) welcomeEl.style.display = 'none';

    let html = '';
    history.forEach(msg => {
        const isUser = msg.role === 'user';
        const avatarIcon = isUser ? 'fa-user' : 'fa-robot';
        const avatarBg = isUser ? 'var(--accent)' : 'var(--info)';
        const avatarColor = isUser ? 'var(--bg-primary)' : '#fff';
        const msgClass = isUser ? 'user' : 'assistant';
        const content = isUser ? escapeHtml(msg.content) : formatAiReply(msg.content);
        const timeStr = msg.time ? `<span style="display:block;font-size:10px;color:var(--text-muted);margin-top:4px;text-align:right">${msg.time}</span>` : '';
        html += `
        <div class="chat-message ${msgClass}">
            <div class="chat-avatar" style="background:${avatarBg};color:${avatarColor}">
                <i class="fas ${avatarIcon}"></i>
            </div>
            <div class="chat-bubble">${content}${timeStr}</div>
        </div>`;
    });

    el.querySelectorAll('.chat-message').forEach(m => m.remove());
    el.insertAdjacentHTML('beforeend', html);
    el.scrollTop = el.scrollHeight;
}

async function ensureSessionId() {
    const mode = chatState.mode;
    if (chatState.sessionIds[mode]) return chatState.sessionIds[mode];
    try {
        const resp = await fetch('/api/chat/session', { method: 'POST' });
        const data = await resp.json();
        if (data.success) {
            chatState.sessionIds[mode] = data.session_id;
            return chatState.sessionIds[mode];
        }
    } catch (e) {
        console.error('创建会话失败:', e);
    }
    chatState.sessionIds[mode] = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    return chatState.sessionIds[mode];
}

async function sendChatMessage(message) {
    if (!message || chatState.loading) return;

    const inputEl = document.getElementById('chatInput');
    const statusEl = document.getElementById('chatStatus');
    const mode = chatState.mode;

    if (inputEl) inputEl.value = '';

    const now = new Date();
    const timeStr = `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}`;

    chatState.histories[mode].push({ role: 'user', content: message, time: timeStr });
    renderChatMessages();

    chatState.loading = true;
    if (statusEl) {
        statusEl.innerHTML = '<div class="chat-typing"><div class="chat-typing-dot"></div><div class="chat-typing-dot"></div><div class="chat-typing-dot"></div></div> <span style="color:var(--info)">正在思考中...</span>';
    }

    const sessionId = await ensureSessionId();

    try {
        const resp = await fetch('/api/ai-chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                history: chatState.histories[mode].slice(0, -1),
                mode: mode,
                champ_id: _currentChampId || '',
                session_id: sessionId,
            })
        });

        const data = await resp.json();

        if (data.success) {
            const replyTime = new Date();
            const replyTimeStr = `${replyTime.getHours().toString().padStart(2,'0')}:${replyTime.getMinutes().toString().padStart(2,'0')}`;
            chatState.histories[mode].push({ role: 'assistant', content: data.reply, time: replyTimeStr });
            renderChatMessages();

            if (statusEl) {
                statusEl.innerHTML = '<span style="color:var(--win)">✓ 回答完成</span> <span class="chat-hint">按 Enter 发送</span>';
                setTimeout(() => {
                    statusEl.innerHTML = '<span class="chat-hint">按 Enter 发送</span>';
                }, 3000);
            }
        } else {
            throw new Error(data.error || '请求失败');
        }
    } catch (e) {
        console.error('聊天请求失败:', e);
        if (statusEl) {
            statusEl.innerHTML = `<span style="color:var(--loss)">✗ ${e.message}</span>`;
        }
        chatState.histories[mode].pop();
        renderChatMessages();
    } finally {
        chatState.loading = false;
    }
}

function initUnifiedChat() {
    const inputEl = document.getElementById('chatInput');
    const sendBtn = document.getElementById('btnSendChat');
    const clearBtn = document.getElementById('btnClearChat');

    if (sendBtn) {
        sendBtn.addEventListener('click', () => {
            if (inputEl && inputEl.value.trim()) {
                sendChatMessage(inputEl.value.trim());
            }
        });
    }

    if (inputEl) {
        inputEl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (inputEl.value.trim()) {
                    sendChatMessage(inputEl.value.trim());
                }
            }
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', async () => {
            const mode = chatState.mode;
            const sid = chatState.sessionIds[mode];
            if (sid) {
                try {
                    await fetch('/api/chat/clear', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ session_id: sid, mode: mode })
                    });
                } catch (e) {
                    console.error('清除记忆失败:', e);
                }
            }
            chatState.histories[mode] = [];
            chatState.sessionIds[mode] = '';
            updateChatWelcome();
            renderChatMessages();
            const statusEl = document.getElementById('chatStatus');
            if (statusEl) {
                statusEl.innerHTML = '<span style="color:var(--win)">✓ 对话已清空</span> <span class="chat-hint">按 Enter 发送</span>';
                setTimeout(() => {
                    statusEl.innerHTML = '<span class="chat-hint">按 Enter 发送</span>';
                }, 3000);
            }
        });
    }

    document.querySelectorAll('.chat-mode-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const newMode = tab.dataset.mode;
            if (newMode === chatState.mode) return;

            document.querySelectorAll('.chat-mode-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            chatState.mode = newMode;
            updateChatWelcome();
            renderChatMessages();

            const inputEl = document.getElementById('chatInput');
            if (inputEl) {
                inputEl.placeholder = chatModeConfig[newMode].placeholder;
                inputEl.focus();
            }
        });
    });

    updateChatWelcome();
}

initUnifiedChat();

document.getElementById('btnSaveApiConfig')?.addEventListener('click', async () => {
    const aiApiKey = document.getElementById('aiApiKey')?.value || '';
    const xinghuoAppId = document.getElementById('xinghuoAppId')?.value || '';
    const xinghuoApiSecret = document.getElementById('xinghuoApiSecret')?.value || '';
    const apiConfigStatus = document.getElementById('apiConfigStatus');

    if (!aiApiKey || !xinghuoAppId || !xinghuoApiSecret) {
        if (apiConfigStatus) {
            apiConfigStatus.textContent = '请填写所有字段';
            apiConfigStatus.className = 'hint-text';
            apiConfigStatus.style.color = 'var(--loss)';
        }
        return;
    }

    try {
        const resp = await fetch('/api/save-ai-config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                aiApiKey,
                xinghuoAppId,
                xinghuoApiSecret
            })
        });

        const data = await resp.json();

        if (data.success) {
            if (apiConfigStatus) {
                apiConfigStatus.textContent = '配置保存成功！';
                apiConfigStatus.className = 'hint-text';
                apiConfigStatus.style.color = 'var(--win)';
            }
        } else {
            throw new Error(data.error || '保存失败');
        }
    } catch (e) {
        if (apiConfigStatus) {
            apiConfigStatus.textContent = `保存失败: ${e.message}`;
            apiConfigStatus.className = 'hint-text';
            apiConfigStatus.style.color = 'var(--loss)';
        }
    }
});

async function loadAiConfig() {
    try {
        const resp = await fetch('/api/get-ai-config');
        const data = await resp.json();

        if (data.success && data.config) {
            const config = data.config;
            if (document.getElementById('aiApiKey')) document.getElementById('aiApiKey').value = config.aiApiKey || '';
            if (document.getElementById('xinghuoAppId')) document.getElementById('xinghuoAppId').value = config.xinghuoAppId || '';
            if (document.getElementById('xinghuoApiSecret')) document.getElementById('xinghuoApiSecret').value = config.xinghuoApiSecret || '';
        }
    } catch (e) {
        console.warn('加载配置失败:', e);
    }
}

loadAiConfig();

document.getElementById('aiApiType')?.addEventListener('change', function() {
    const xinghuoConfig = document.getElementById('xinghuoConfig');
    if (xinghuoConfig) {
        xinghuoConfig.style.display = this.value === 'xinghuo' ? 'block' : 'none';
    }
});

const aiApiType = document.getElementById('aiApiType');
if (aiApiType) {
    const xinghuoConfig = document.getElementById('xinghuoConfig');
    if (xinghuoConfig) {
        xinghuoConfig.style.display = aiApiType.value === 'xinghuo' ? 'block' : 'none';
    }
}

