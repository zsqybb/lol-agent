// ==================== 游戏助手 ====================

let gamePollTimer = null;
let autoAcceptEnabled = localStorage.getItem('lol_autoAccept') === 'true';
let autoBanEnabled = localStorage.getItem('lol_autoBan') === 'true';
let autoBanChampionKey = parseInt(localStorage.getItem('lol_autoBanKey') || '0') || null;
let autoBanChampionName = localStorage.getItem('lol_autoBanName') || '';
let lastGamePhase = '';
let _championDataCache = {};  // champion id -> name/image map
let _currentSelectPosition = localStorage.getItem('lol_selectPosition') || 'TOP';
let _lastReadyCheckNotified = false;
let _autoBanExecuted = false;

// 恢复自动禁用 UI 状态
if (autoBanEnabled && autoBanChampionName) {
    setTimeout(() => {
        const targetEl = document.getElementById('autoBanTarget');
        if (targetEl) targetEl.textContent = autoBanChampionName;
        const toggleEl = document.getElementById('toggleAutoBan');
        if (toggleEl) toggleEl.checked = true;
        const configEl = document.getElementById('autoBanConfig');
        if (configEl) configEl.classList.add('auto-ban-config-visible');
    }, 500);
}
if (autoAcceptEnabled) {
    setTimeout(() => {
        const toggleEl = document.getElementById('toggleAutoAccept');
        if (toggleEl) toggleEl.checked = true;
    }, 500);
}

const POSITION_CN = {'TOP':'上单','JUNGLE':'打野','MIDDLE':'中单','BOTTOM':'ADC','UTILITY':'辅助','FILL':'补位'};
const LANE_COLORS = {
    'TOP':     { css: 'lane-top',    cn: '上单' },
    'JUNGLE':  { css: 'lane-jungle', cn: '打野' },
    'MIDDLE':  { css: 'lane-mid',    cn: '中单' },
    'BOTTOM':  { css: 'lane-bot',    cn: 'ADC' },
    'UTILITY': { css: 'lane-sup',    cn: '辅助' },
};

// 骨架屏
function buildSkeleton() {
    let h = '<div class="champ-select-skeleton">';
    h += '<div class="skeleton-row"><div class="skeleton-block lg" style="flex:1"></div></div>';
    for (let i = 0; i < 5; i++) {
        h += `<div class="skeleton-row">
            <div class="skeleton-block sm"></div>
            <div class="skeleton-block md"></div>
            <div class="skeleton-block sm" style="margin-left:auto"></div>
            <div class="skeleton-block md"></div>
        </div>`;
    }
    h += '</div>';
    return h;
}

async function _loadChampionCache() {
    if (Object.keys(_championDataCache).length > 0) return;
    try {
        const resp = await fetch('/api/champions');
        const data = await resp.json();
        if (data.success && data.champions) {
            data.champions.forEach(c => {
                _championDataCache[c.key] = c;
            });
        }
    } catch (e) { console.warn('英雄缓存加载失败:', e); }
}

function _championName(champId) {
    const c = _championDataCache[champId];
    return c ? c.name : '未知';
}

function _championImg(champId) {
    const c = _championDataCache[champId];
    return c ? `/static/img/champion/${c.image}` : '/static/img/champion/Akali.png';
}

function _showCardsForPhase(phase) {
    const cards = {
        readyCheckCard: phase === 'ReadyCheck',
        champSelectCard: phase === 'ChampSelect',
        banSuggestCard: phase === 'ChampSelect',
        inGameCard: phase === 'InProgress',
        eogCard: phase === 'EndOfGame',
    };
    // 自动禁用配置: 根据开关状态显示
    const autoBanConfig = document.getElementById('autoBanConfig');
    if (autoBanConfig) {
        autoBanConfig.classList.toggle('auto-ban-config-visible', autoBanEnabled);
    }

    for (const [id, visible] of Object.entries(cards)) {
        const el = document.getElementById(id);
        if (el) el.style.display = visible ? 'block' : 'none';
    }
}

function renderGameState(state) {
    const container = document.getElementById('gameStateDisplay');
    if (!container) return;

    const phase = state.phase;
    const phaseCn = state.phase_cn;

    // 切换阶段时更新卡片显示
    if (phase !== lastGamePhase) {
        _showCardsForPhase(phase);
        _lastReadyCheckNotified = false;
        _autoBanExecuted = false;
    }

    if (!state.connected) {
        container.innerHTML = `
        <div class="game-state-placeholder">
            <i class="fas fa-plug" style="font-size:48px;color:var(--text-muted)"></i>
            <p>请先启动英雄联盟客户端，然后点击"从客户端读取"连接</p>
            <button class="btn btn-primary" onclick="connectLcu()" style="margin-top:12px">
                <i class="fas fa-link"></i> 连接客户端
            </button>
        </div>`;
        _showCardsForPhase('Unknown');
        lastGamePhase = phase;
        return;
    }

    const phaseColors = {
        'Lobby': 'var(--info)', 'Matchmaking': 'var(--accent)',
        'ReadyCheck': 'var(--gold)', 'ChampSelect': 'var(--win)',
        'InProgress': 'var(--loss)', 'EndOfGame': 'var(--text-muted)',
    };
    const phaseIcons = {
        'Lobby': 'fa-home', 'Matchmaking': 'fa-search', 'ReadyCheck': 'fa-bell',
        'ChampSelect': 'fa-users', 'InProgress': 'fa-swords', 'EndOfGame': 'fa-trophy',
    };
    const color = phaseColors[phase] || 'var(--text-muted)';
    const icon = phaseIcons[phase] || 'fa-circle';

    let html = `
    <div class="game-state-header" style="text-align:center;padding:20px 0">
        <div style="font-size:48px;color:${color};margin-bottom:8px">
            <i class="fas ${icon}"></i>
        </div>
        <div style="font-size:24px;font-weight:700;color:var(--text-primary)">${phaseCn}</div>
    </div>`;

    // 就绪检查
    if (phase === 'ReadyCheck') {
        html += `
        <div style="text-align:center;padding:12px;background:rgba(200,155,60,0.1);border-radius:8px;margin:0 20px">
            <p style="color:var(--gold);font-weight:600"><i class="fas fa-exclamation-triangle"></i> 对局已找到！</p>
            ${autoAcceptEnabled ? '<p style="color:var(--win)">自动接受已开启，正在自动接受...</p>' : '<p>请点击"立即接受"按钮接受对局</p>'}
        </div>`;
        // 浏览器通知
        if (!_lastReadyCheckNotified) {
            _lastReadyCheckNotified = true;
            _sendBrowserNotification('对局已找到！', '请立即接受对局');
        }
    }

    // 选人阶段信息
    if (phase === 'ChampSelect' && state.champ_select) {
        const cs = state.champ_select;
        const pct = cs.total_timer > 0 ? Math.round((cs.timer / cs.total_timer) * 100) : 0;
        html += `
        <div style="padding:8px 20px;text-align:center">
            <div style="display:flex;align-items:center;gap:8px;justify-content:center;margin-bottom:8px">
                <span>⏱ 剩余时间:</span>
                <span style="font-weight:700;font-size:18px;color:${cs.timer < 10 ? 'var(--loss)' : 'var(--text-primary)'}">${cs.timer}s</span>
            </div>
            <div style="background:var(--bg-secondary);border-radius:4px;height:6px;overflow:hidden">
                <div style="height:100%;width:${100-pct}%;background:${cs.timer < 10 ? 'var(--loss)' : 'var(--win)'};border-radius:4px;transition:width 1s linear"></div>
            </div>
            <div style="margin-top:8px;display:flex;gap:24px;justify-content:center;font-size:12px;color:var(--text-muted)">
                <span>我方 Ban: ${cs.my_bans_count}/5</span>
                <span>敌方 Ban: ${cs.their_bans_count}/5</span>
            </div>
        </div>`;
    }

    // 游戏中
    if (phase === 'InProgress' && state.in_game) {
        html += `
        <div style="text-align:center;padding:12px;color:var(--loss)">
            <i class="fas fa-swords"></i> 正在游戏中 — ${state.in_game.summoner_name}
        </div>`;
    }

    // 结算
    if (phase === 'EndOfGame' && state.end_of_game) {
        const eog = state.end_of_game;
        const resultEmoji = eog.win ? '🏆' : '💔';
        const resultText = eog.win ? '胜利' : '失败';
        const resultColor = eog.win ? 'var(--win)' : 'var(--loss)';
        const kdaRatio = eog.deaths === 0 ? (eog.kills + eog.assists).toFixed(1) : ((eog.kills + eog.assists) / eog.deaths).toFixed(2);
        html += `
        <div class="eog-summary" style="text-align:center;padding:20px">
            <div style="font-size:56px">${resultEmoji}</div>
            <div style="font-size:28px;font-weight:700;color:${resultColor};margin:8px 0">${resultText}</div>
            <div style="font-size:22px;color:var(--text-primary)">
                <span style="color:var(--win)">${eog.kills}</span> /
                <span style="color:var(--loss)">${eog.deaths}</span> /
                <span style="color:var(--info)">${eog.assists}</span>
                <span style="font-size:14px;color:var(--text-muted)"> (KDA ${kdaRatio})</span>
            </div>
            <button class="btn btn-outline btn-sm" style="margin-top:12px" onclick="loadEogDetail()">
                <i class="fas fa-chart-bar"></i> 查看详细数据
            </button>
        </div>`;
    }

    container.innerHTML = html;

    // 同步选人计时器到champSelectCard (由轮询驱动，避免双倒计时漂移)
    if (phase === 'ChampSelect' && state.champ_select) {
        const cs = state.champ_select;
        const timerEl = document.getElementById('champSelectTimer');
        if (timerEl) {
            timerEl.textContent = cs.timer + 's';
            timerEl.style.color = cs.timer < 10 ? 'var(--loss)' : 'var(--text-primary)';
            timerEl.style.animation = cs.timer < 10 ? 'pulse 0.6s ease-in-out infinite' : 'none';
        }
    }

    // 选人阶段自动加载详情和禁用推荐
    if (phase === 'ChampSelect' && phase !== lastGamePhase) {
        loadChampSelectData();
        loadBanSuggestions();
    }

    // 游戏中加载实时信息
    if (phase === 'InProgress' && phase !== lastGamePhase) {
        loadInGameInfo();
    }

    // 结算阶段自动加载详情和可点赞列表
    if (phase === 'EndOfGame' && phase !== lastGamePhase) {
        loadEogDetail();
        loadHonorEligible();
    }

    lastGamePhase = phase;
}

function _sendBrowserNotification(title, body) {
    if (!('Notification' in window)) return;
    if (Notification.permission === 'granted') {
        new Notification(title, { body, icon: '/static/img/champion/Akali.png' });
    } else if (Notification.permission !== 'denied') {
        Notification.requestPermission().then(p => {
            if (p === 'granted') new Notification(title, { body });
        });
    }
}

// ==================== 禁用推荐 ====================

async function loadBanSuggestions() {
    try {
        const resp = await fetch('/api/game/ban-suggestions');
        const data = await resp.json();
        if (!data.success) return;

        const container = document.getElementById('banSuggestContent');
        if (!container) return;

        const tierColors = {1: '#ff6464', 2: '#c89b3c', 3: '#4a9eff'};
        const tierBorders = {1: 'tier-1', 2: 'tier-2', 3: 'tier-3'};

        let html = '<div class="ban-suggest-grid">';
        data.suggestions.forEach((s, i) => {
            const name = s.name || s.id;
            const img = `/static/img/champion/${s.id}.png`;
            const borderCls = tierBorders[s.tier] || '';
            const k = s.key || 0;
            html += `
            <div class="ban-suggest-item ${borderCls}" onclick="quickBanChampion(${k}, '${name.replace(/'/g, "\\'")}')"
                 title="禁用率: ${s.ban_rate.toFixed(1)}% | 胜率: ${s.win_rate.toFixed(1)}%">
                <div class="ban-suggest-rank">${i + 1}</div>
                <img src="${img}" onerror="this.src='/static/img/champion/Akali.png'" class="champ-thumb" style="width:38px;height:38px;border:none">
                <div class="ban-suggest-info">
                    <div style="font-size:12px;font-weight:600;color:var(--text-primary)">${name}</div>
                    <div class="ban-rate-bar"><div class="ban-rate-bar-fill" style="width:${Math.min(s.ban_rate, 100)}%"></div></div>
                    <div style="display:flex;align-items:center;gap:6px;margin-top:2px">
                        <span class="tier-badge ${borderCls}">${s.tier_label}</span>
                        <span style="font-size:10px;color:var(--text-muted)">${s.ban_rate.toFixed(1)}% ban</span>
                    </div>
                </div>
            </div>`;
        });
        html += '</div>';
        container.innerHTML = html;
    } catch (e) {
        console.error('加载禁用推荐失败:', e);
    }
}

function quickBanChampion(champKey, champName) {
    const pendingAction = (window._csActions || []).find(a => !a.completed && a.type === 'ban');
    if (pendingAction) {
        executeChampAction(pendingAction.id, 'ban', champKey);
        notify(`正在禁用: ${champName}`, 'info');
    } else {
        // 尝试找到选择英雄的action（如果当前轮到Pick，ban已经过了）
        const pickAction = (window._csActions || []).find(a => !a.completed && a.type === 'pick');
        if (pickAction) {
            notify('当前是你的选人回合，无法禁用', 'error');
        } else {
            notify('当前没有待执行的禁用操作', 'error');
        }
    }
}

// ==================== 游戏中实时监控 ====================

async function loadInGameInfo() {
    try {
        const resp = await fetch('/api/game/in-game-info');
        const data = await resp.json();
        const container = document.getElementById('inGameContent');
        if (!container) return;

        if (!data.success) {
            container.innerHTML = '<div style="text-align:center;color:var(--text-muted)">无法获取游戏内信息</div>';
            return;
        }

        let html = `
        <div style="text-align:center;padding:8px 0">
            <div style="font-size:14px;color:var(--text-primary);font-weight:600">
                <i class="fas fa-user"></i> ${data.summoner_name || '玩家'}
            </div>`;
        if (data.game_data) {
            html += `
            <div style="font-size:12px;color:var(--text-muted);margin-top:4px">
                游戏模式: ${data.game_data.game_mode || '--'}
            </div>`;
        }
        html += `
            <div style="margin-top:8px;color:var(--accent)">
                <i class="fas fa-circle" style="animation:pulse 1.5s infinite"></i> 游戏进行中...
            </div>
        </div>`;
        container.innerHTML = html;
    } catch (e) {
        console.error('加载游戏信息失败:', e);
    }
}

// ==================== 赛后点赞 ====================

async function loadHonorEligible() {
    try {
        await _loadChampionCache();
        const resp = await fetch('/api/game/honor-eligible');
        const data = await resp.json();
        if (!data.success || !data.players || data.players.length === 0) return;

        const honorPanel = document.getElementById('honorPanel');
        const honorContent = document.getElementById('honorContent');
        if (!honorPanel || !honorContent) return;

        honorPanel.style.display = 'block';

        const honorTypes = [
            { type: 'HEART', icon: 'fa-heart', color: '#ff6b8a', label: '团队合作' },
            { type: 'SHOTSHOT', icon: 'fa-star', color: '#ffb347', label: '神级操作' },
            { type: 'GREATSHOT', icon: 'fa-crown', color: '#9b59b6', label: '稳如泰山' },
        ];

        let html = '<div style="display:flex;flex-direction:column;gap:8px">';
        data.players.forEach(p => {
            const champName = _championName(p.champion_id);
            html += `
            <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;background:var(--bg-secondary);border-radius:8px">
                <img src="${_championImg(p.champion_id)}" onerror="this.src='/static/img/champion/Akali.png'" style="width:36px;height:36px;border-radius:6px">
                <span style="flex:1;font-size:13px;color:var(--text-primary)">${p.summoner_name || champName}</span>
                <div style="display:flex;gap:4px">`;
            honorTypes.forEach(ht => {
                html += `<button class="btn btn-sm" style="padding:4px 8px;font-size:10px;background:${ht.color};color:#fff;border:none;border-radius:4px;cursor:pointer"
                    onclick="sendHonor(${p.summoner_id}, '${ht.type}')" title="${ht.label}">
                    <i class="fas ${ht.icon}"></i>
                </button>`;
            });
            html += '</div></div>';
        });
        html += '</div>';
        honorContent.innerHTML = html;
    } catch (e) {
        console.error('加载点赞列表失败:', e);
    }
}

async function sendHonor(summonerId, honorType) {
    try {
        const resp = await fetch('/api/game/honor', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ summoner_id: summonerId, honor_type: honorType }),
        });
        const data = await resp.json();
        if (data.success) {
            notify('点赞成功！', 'success');
            document.getElementById('honorPanel').style.display = 'none';
        } else {
            notify(data.error || '点赞失败', 'error');
        }
    } catch (e) {
        notify('点赞失败: ' + e.message, 'error');
    }
}

// ==================== 英雄选择详情 ====================

async function loadEogDetail() {
    try {
        await _loadChampionCache();
        const resp = await fetch('/api/game/eog-detail');
        const data = await resp.json();
        if (!data.success) return;

        const container = document.getElementById('eogContent');
        if (!container) return;

        const lp = data.local_player || {};
        const kdaRatio = lp.deaths === 0 ? (lp.kills + lp.assists).toFixed(1) : ((lp.kills + lp.assists) / lp.deaths).toFixed(2);
        const goldFormatted = lp.gold_earned ? (lp.gold_earned / 1000).toFixed(1) + 'k' : '0';
        const dmgFormatted = lp.total_damage ? (lp.total_damage / 1000).toFixed(0) + 'k' : '0';
        const resultColor = data.win ? 'var(--win)' : 'var(--loss)';
        const resultText = data.win ? '胜利' : '失败';

        let html = `
        <div style="text-align:center;padding:12px 0">
            <div style="font-size:20px;font-weight:700;color:${resultColor}">${resultText}</div>
        </div>
        <div class="eog-stats-grid">
            <div class="eog-stat-item">
                <div class="eog-stat-value">${lp.kills}/${lp.deaths}/${lp.assists}</div>
                <div class="eog-stat-label">KDA (${kdaRatio})</div>
            </div>
            <div class="eog-stat-item">
                <div class="eog-stat-value">${lp.champion_level || '--'}</div>
                <div class="eog-stat-label">英雄等级</div>
            </div>
            <div class="eog-stat-item">
                <div class="eog-stat-value">${goldFormatted}</div>
                <div class="eog-stat-label">获得金币</div>
            </div>
            <div class="eog-stat-item">
                <div class="eog-stat-value">${dmgFormatted}</div>
                <div class="eog-stat-label">英雄伤害</div>
            </div>
            <div class="eog-stat-item">
                <div class="eog-stat-value">${lp.cs_score || 0}</div>
                <div class="eog-stat-label">补刀数</div>
            </div>
            <div class="eog-stat-item">
                <div class="eog-stat-value">${lp.vision_score || 0}</div>
                <div class="eog-stat-label">视野得分</div>
            </div>
            ${lp.largest_multi_kill ? `
            <div class="eog-stat-item">
                <div class="eog-stat-value" style="color:var(--accent)">${lp.largest_multi_kill >= 5 ? '五杀!' : lp.largest_multi_kill >= 4 ? '四杀' : lp.largest_multi_kill >= 3 ? '三杀' : '双杀'}</div>
                <div class="eog-stat-label">最大连杀</div>
            </div>` : ''}
        </div>`;

        // 装备
        const items = lp.items || [];
        if (items.some(i => i > 0)) {
            html += '<div class="section-title"><i class="fas fa-shopping-bag"></i> 装备</div>';
            html += '<div style="display:flex;gap:4px;flex-wrap:wrap">';
            items.forEach(i => {
                if (i > 0) {
                    html += `<img src="/static/img/item/${i}.png" style="width:36px;height:36px;border-radius:4px" onerror="this.style.display='none'" title="物品${i}">`;
                }
            });
            html += '</div>';
        }

        // 双方对比
        html += '<div class="section-title" style="margin-top:16px"><i class="fas fa-users"></i> 双方阵容</div>';
        html += '<div class="pick-teams">';

        // 我方
        html += '<div class="pick-team"><h4 style="color:var(--win)">我方</h4>';
        (data.my_team || []).forEach(p => {
            const kda = `${p.kills}/${p.deaths}/${p.assists}`;
            html += `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;padding:4px 8px;background:var(--bg-secondary);border-radius:6px;${p.is_me ? 'border-left:3px solid var(--accent)' : ''}">
                <img src="${_championImg(p.champion_id)}" style="width:28px;height:28px;border-radius:4px" onerror="this.src='/static/img/champion/Akali.png'">
                <span style="font-size:12px;flex:1;${p.is_me ? 'color:var(--accent);font-weight:600' : ''}">${p.summoner_name || _championName(p.champion_id)}</span>
                <span style="font-size:11px;color:var(--text-muted)">${kda}</span>
            </div>`;
        });
        html += '</div>';

        // 敌方
        html += '<div class="pick-team"><h4 style="color:var(--loss)">敌方</h4>';
        (data.enemy_team || []).forEach(p => {
            const kda = `${p.kills}/${p.deaths}/${p.assists}`;
            html += `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;padding:4px 8px;background:var(--bg-secondary);border-radius:6px">
                <img src="${_championImg(p.champion_id)}" style="width:28px;height:28px;border-radius:4px" onerror="this.src='/static/img/champion/Akali.png'">
                <span style="font-size:12px;flex:1">${p.summoner_name || _championName(p.champion_id)}</span>
                <span style="font-size:11px;color:var(--text-muted)">${kda}</span>
            </div>`;
        });
        html += '</div></div>';

        container.innerHTML = html;
    } catch (e) {
        console.error('加载对局详情失败:', e);
    }
}

async function loadChampSelectData() {
    try {
        // 先显示骨架屏
        const content = document.getElementById('champSelectContent');
        if (content) content.innerHTML = buildSkeleton();

        await _loadChampionCache();
        const [csResp, recoResp] = await Promise.all([
            fetch('/api/game/champ-select'),
            fetch('/api/game/recommendations?position=' + (_currentSelectPosition || 'TOP'))
        ]);

        const data = await csResp.json();
        if (!data.success) return;

        // 保存当前操作
        window._csActions = data.my_actions || [];
        window._csMyTeam = data.my_team || [];

        // 确定我的位置
        const mySlot = data.my_team.find(p => p.cell_id === data.local_cell_id);
        if (mySlot && mySlot.assigned_position && mySlot.assigned_position !== 'FILL') {
            _currentSelectPosition = mySlot.assigned_position;
            localStorage.setItem('lol_selectPosition', _currentSelectPosition);
        }
        // 如果位置仍未确定（盲选等），保留上次选择的或手动设置的

        // 自动禁用
        if (autoBanEnabled && !_autoBanExecuted) {
            const banAction = (data.my_actions || []).find(a => !a.completed && a.type === 'ban');
            if (banAction && autoBanChampionKey) {
                _autoBanExecuted = true;
                executeChampAction(banAction.id, 'ban', autoBanChampionKey);
            }
        }

        const timerEl = document.getElementById('champSelectTimer');
        if (timerEl) timerEl.textContent = data.timer + 's';

        let html = '<div class="champ-pick-panel">';

        // 英雄搜索
        html += `
        <div class="champ-pick-search">
            <input type="text" id="champSearchInput" placeholder="搜索英雄名称（选人/禁用）..." autocomplete="off">
            <div id="champSearchResults" class="search-results-dropdown"></div>
        </div>`;

        // "轮到你了" 提示
        const pendingAction = (data.my_actions || []).find(a => !a.completed);
        if (pendingAction) {
            const verb = pendingAction.type === 'ban' ? '禁用' : '选择';
            html += `<div class="your-turn-banner">
                <i class="fas fa-exclamation-circle"></i> 轮到你了 — <span class="action-type">${verb}英雄</span>
            </div>`;
        }

        // 禁用行
        html += '<div class="pick-bans-row">';
        html += '<div class="ban-group"><span class="ban-group-label">我方禁用</span><div class="ban-slots">';
        for (const b of (data.my_bans || [])) {
            if (b) {
                html += `<div class="ban-slot filled"><img src="${_championImg(b)}" title="${_championName(b)}"></div>`;
            } else {
                html += '<div class="ban-slot empty"></div>';
            }
        }
        html += '</div></div>';
        html += '<div class="ban-group"><span class="ban-group-label">敌方禁用</span><div class="ban-slots">';
        for (const b of (data.their_bans || [])) {
            if (b) {
                html += `<div class="ban-slot filled"><img src="${_championImg(b)}" title="${_championName(b)}"></div>`;
            } else {
                html += '<div class="ban-slot empty"></div>';
            }
        }
        html += '</div></div></div>';

        // 分路选择器 (当检测不到位置时显示)
        const posMap = {'TOP':'上单', 'JUNGLE':'打野', 'MIDDLE':'中单', 'BOTTOM':'ADC', 'UTILITY':'辅助'};
        const showPosSelector = !mySlot || !mySlot.assigned_position || mySlot.assigned_position === 'FILL';
        if (showPosSelector) {
            html += '<div class="position-selector" style="display:flex;align-items:center;gap:8px;margin-bottom:12px;padding:8px 12px;background:rgba(200,155,60,0.1);border-radius:8px">';
            html += '<span style="font-size:12px;color:var(--accent)"><i class="fas fa-map-marker-alt"></i> 我的分路：</span>';
            Object.entries(posMap).forEach(([key, label]) => {
                const isActive = _currentSelectPosition === key;
                html += `<button class="pos-select-btn ${isActive ? 'active' : ''}"
                    style="padding:4px 10px;border-radius:4px;font-size:11px;cursor:pointer;border:1px solid ${isActive ? 'var(--accent)' : 'var(--border)'};background:${isActive ? 'var(--accent)' : 'transparent'};color:${isActive ? '#0a0e1a' : 'var(--text-secondary)'}"
                    onclick="selectLanePosition('${key}')">${label}</button>`;
            });
            html += '</div>';
        }

        // 分路对阵
        const Lanes = ['TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY'];
        html += '<div class="pick-lane-grid">';
        for (const lane of Lanes) {
            const ally = data.my_team.find(p => p.assigned_position === lane);
            const enemy = (data.their_team || []).find(p => p.assigned_position === lane);
            const isMyLane = lane === _currentSelectPosition;
            const laneCss = LANE_COLORS[lane] || { css: '', cn: lane };

            html += `<div class="pick-lane-row ${laneCss.css}${isMyLane ? ' is-my-lane' : ''}">`;
            html += `<div class="lane-label ${laneCss.css}">${laneCss.cn}</div>`;

            // 我方
            html += '<div class="lane-slot">';
            if (ally) {
                const allyName = ally.champion_id ? _championName(ally.champion_id) : (ally.summoner_name || '');
                const isMe = ally.cell_id === data.local_cell_id;
                if (ally.champion_id) {
                    html += `<div class="champ-thumb${isMe ? ' is-active' : ' is-teammate'}">
                        <img src="${_championImg(ally.champion_id)}" onerror="this.src='/static/img/champion/Akali.png'">
                    </div>`;
                } else {
                    html += '<div class="champ-thumb is-empty"></div>';
                }
                html += `<span class="summoner-name" style="${isMe ? 'color:var(--accent);font-weight:600' : ''}">${allyName}${isMe ? ' (你)' : ''}</span>`;
            } else {
                html += '<div class="champ-thumb is-empty"></div>';
                html += '<span class="champ-name-text">等待加入</span>';
            }
            html += '</div>';

            // VS
            html += '<div class="lane-vs">VS</div>';

            // 敌方
            html += '<div class="lane-slot" style="justify-content:flex-end">';
            if (enemy && enemy.champion_id) {
                const isNew = lastGamePhase !== 'ChampSelect'; // 首次渲染时触发reveal动画
                html += `<span class="champ-name-text" style="color:var(--loss)">${_championName(enemy.champion_id)}</span>`;
                html += `<div class="champ-thumb is-enemy${isNew ? ' is-reveal' : ''}">
                    <img src="${_championImg(enemy.champion_id)}" onerror="this.src='/static/img/champion/Akali.png'">
                </div>`;
            } else {
                html += '<span class="champ-name-text" style="color:var(--text-muted)">未知</span>';
                html += '<div class="champ-thumb is-empty"></div>';
            }
            html += '</div>';

            html += '</div>'; // pick-lane-row
        }
        html += '</div>'; // pick-lane-grid

        // 我的操作按钮
        if (data.my_actions && data.my_actions.length > 0) {
            html += '<div class="pick-actions">';
            data.my_actions.forEach(a => {
                const actionLabel = a.type === 'ban' ? '禁用' : '选择';
                const actionColor = a.type === 'ban' ? 'var(--loss)' : 'var(--win)';
                html += `<button class="btn btn-sm" style="background:${actionColor};color:#fff;margin-right:8px" onclick="executeChampAction(${a.id}, '${a.type}')" ${a.completed ? 'disabled' : ''}>
                    <i class="fas fa-${a.type === 'ban' ? 'ban' : 'check'}"></i> ${a.completed ? '已完成' : actionLabel}
                </button>`;
            });
            html += '</div>';
        }

        html += '</div>'; // close champ-pick-panel

        document.getElementById('champSelectContent').innerHTML = html;

        // 初始化英雄搜索
        initChampSearch();

        // 加载推荐英雄
        if (recoResp.ok) {
            const recoData = await recoResp.json();
            if (recoData.success && recoData.recommendations) {
                renderChampRecommendations(recoData.recommendations, data.my_actions);
            }
        }

        // Timer展示由renderGameState每2秒轮询同步更新，此处仅设初始值
    } catch (e) {
        console.error('加载选人数据失败:', e);
    }
}

let _champSearchDocHandler = null;

function initChampSearch() {
    const input = document.getElementById('champSearchInput');
    const dropdown = document.getElementById('champSearchResults');
    if (!input || !dropdown) return;

    // 防止重复绑定同一个input
    if (input.dataset.searchInitialized === '1') return;
    input.dataset.searchInitialized = '1';

    input.addEventListener('input', function() {
        const q = this.value.trim().toLowerCase();
        const dd = document.getElementById('champSearchResults');
        if (!dd) return;
        if (!q) { dd.classList.remove('show'); return; }

        const results = allChampions.filter(c =>
            c.name.toLowerCase().includes(q) || c.id.toLowerCase().includes(q)
        ).slice(0, 8);

        if (results.length === 0) {
            dd.innerHTML = '<div style="padding:8px 14px;color:var(--text-muted);font-size:12px">无匹配英雄</div>';
        } else {
            dd.innerHTML = results.map(c => `
                <div class="search-result-item" data-champ-id="${c.id}" data-champ-key="${c.key}">
                    <img src="/static/img/champion/${c.image}" onerror="this.src='/static/img/champion/Akali.png'">
                    <span class="name">${c.name}</span>
                    ${c.tier_label ? `<span class="reco-badge ${c.tier <= 2 ? 's-tier' : c.tier <= 3 ? 'a-tier' : 'b-tier'}">${c.tier_label}</span>` : ''}
                </div>
            `).join('');

            dd.querySelectorAll('.search-result-item').forEach(item => {
                item.addEventListener('click', () => {
                    const champKey = parseInt(item.dataset.champKey);
                    const inp = document.getElementById('champSearchInput');
                    if (inp) inp.value = item.querySelector('.name').textContent;
                    dd.classList.remove('show');
                    const pendingAction = (window._csActions || []).find(a => !a.completed);
                    if (pendingAction) {
                        executeChampAction(pendingAction.id, pendingAction.type, champKey);
                    }
                });
            });
        }
        dd.classList.add('show');
    });

    // 使用全局单一document handler避免重复绑定
    if (!_champSearchDocHandler) {
        _champSearchDocHandler = function(e) {
            const inp = document.getElementById('champSearchInput');
            const dd = document.getElementById('champSearchResults');
            if (inp && dd && !inp.contains(e.target) && !dd.contains(e.target)) {
                dd.classList.remove('show');
            }
        };
        document.addEventListener('click', _champSearchDocHandler);
    }
}

function renderChampRecommendations(recs, actions) {
    const content = document.getElementById('champSelectContent');
    if (!content || recs.length === 0) return;

    const existing = content.querySelector('.champ-reco-section');
    if (existing) existing.remove();

    const tierColors = {1: '#ff6464', 2: '#c89b3c', 3: '#4a9eff'};
    let html = '<div class="champ-reco-section"><div class="section-title"><i class="fas fa-lightbulb"></i> 推荐英雄 (点击快速选择)</div>';
    html += '<div style="display:flex;gap:4px;flex-wrap:wrap">';

    recs.forEach(r => {
        const img = `/static/img/champion/${r.id}.png`;
        const color = tierColors[r.tier] || 'var(--text-muted)';
        html += `
        <div class="pick-champ-item" style="text-align:center;width:68px;padding:4px;cursor:pointer;border-radius:8px;transition:background 0.2s"
             onclick="quickPickChampion(${allChampions.find(c => c.id === r.id)?.key || 0}, '${r.name}')"
             onmouseover="this.style.background='var(--bg-card-hover)'" onmouseout="this.style.background=''">
            <img src="${img}" onerror="this.src='/static/img/champion/Akali.png'" style="width:44px;height:44px;border-radius:8px">
            <div class="name" style="font-size:10px;color:var(--text-primary);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${r.name}</div>
            <div style="font-size:9px;color:${color};font-weight:600">${r.tier_label} · ${r.win_rate.toFixed(1)}%</div>
        </div>`;
    });

    html += '</div></div>';
    content.insertAdjacentHTML('beforeend', html);
}

function quickPickChampion(champKey, champName) {
    const pendingAction = (window._csActions || []).find(a => !a.completed);
    if (pendingAction) {
        executeChampAction(pendingAction.id, pendingAction.type, champKey);
        notify(`正在${pendingAction.type === 'ban' ? '禁用' : '选择'}: ${champName}`, 'info');
    } else {
        notify('当前没有待执行的操作', 'error');
    }
}

async function executeChampAction(actionId, actionType, championId) {
    if (!championId) {
        notify('请先搜索并选择一个英雄', 'error');
        return;
    }
    try {
        const resp = await fetch('/api/game/champ-select/action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                action_id: actionId,
                champion_id: championId,
                type: actionType,
                completed: true,
            })
        });
        const data = await resp.json();
        if (data.success || data.status === 204) {
            notify(`${actionType === 'ban' ? '禁用' : '选择'}成功！`, 'success');
            setTimeout(() => loadChampSelectData(), 500);
        } else {
            notify(data.error || '操作失败', 'error');
        }
    } catch (e) {
        notify('操作失败: ' + e.message, 'error');
    }
}

// ==================== 自动禁用配置 ====================

function initAutoBanSearch() {
    const input = document.getElementById('autoBanSearch');
    if (!input || input._initialized) return;
    input._initialized = true;

    // 创建下拉容器
    let dropdown = document.getElementById('autoBanDropdown');
    if (!dropdown) {
        dropdown = document.createElement('div');
        dropdown.id = 'autoBanDropdown';
        dropdown.className = 'search-results-dropdown';
        dropdown.style.cssText = 'position:absolute;z-index:100;max-height:200px;overflow-y:auto';
        input.parentNode.style.position = 'relative';
        input.parentNode.appendChild(dropdown);
    }

    input.addEventListener('input', function() {
        const q = this.value.trim().toLowerCase();
        if (!q) { dropdown.classList.remove('show'); return; }

        const results = allChampions.filter(c =>
            c.name.toLowerCase().includes(q) || c.id.toLowerCase().includes(q)
        ).slice(0, 8);

        if (results.length === 0) {
            dropdown.innerHTML = '<div style="padding:8px 14px;color:var(--text-muted);font-size:12px">无匹配英雄</div>';
        } else {
            dropdown.innerHTML = results.map(c => `
                <div class="search-result-item" data-champ-key="${c.key}" data-champ-name="${c.name}">
                    <img src="/static/img/champion/${c.image}" onerror="this.src='/static/img/champion/Akali.png'">
                    <span class="name">${c.name}</span>
                </div>
            `).join('');
            dropdown.querySelectorAll('.search-result-item').forEach(item => {
                item.addEventListener('click', () => {
                    autoBanChampionKey = parseInt(item.dataset.champKey);
                    autoBanChampionName = item.dataset.champName;
                    localStorage.setItem('lol_autoBanKey', autoBanChampionKey);
                    localStorage.setItem('lol_autoBanName', autoBanChampionName);
                    input.value = autoBanChampionName;
                    document.getElementById('autoBanTarget').textContent = autoBanChampionName;
                    dropdown.classList.remove('show');
                });
            });
        }
        dropdown.classList.add('show');
    });

    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.classList.remove('show');
        }
    });
}

document.getElementById('toggleAutoBan')?.addEventListener('change', function() {
    autoBanEnabled = this.checked;
    localStorage.setItem('lol_autoBan', autoBanEnabled.toString());
    const configEl = document.getElementById('autoBanConfig');
    if (configEl) configEl.classList.toggle('auto-ban-config-visible', autoBanEnabled);
    if (autoBanEnabled) {
        initAutoBanSearch();
        _autoBanExecuted = false;
        // 如果没设目标，自动选 ban 率最高的 T1 英雄作为默认
        if (!autoBanChampionKey) {
            fetch('/api/game/ban-suggestions')
                .then(r => r.json())
                .then(d => {
                    if (d.success && d.suggestions && d.suggestions.length > 0) {
                        const top = d.suggestions[0];
                        autoBanChampionKey = top.key;
                        autoBanChampionName = top.name;
                        localStorage.setItem('lol_autoBanKey', autoBanChampionKey);
                        localStorage.setItem('lol_autoBanName', autoBanChampionName);
                        const inputEl = document.getElementById('autoBanSearch');
                        if (inputEl) inputEl.value = autoBanChampionName;
                        const targetEl = document.getElementById('autoBanTarget');
                        if (targetEl) targetEl.textContent = autoBanChampionName;
                        notify(`自动禁用默认设置为: ${autoBanChampionName}`, 'info');
                    }
                }).catch(() => {});
        }
    }
    notify(autoBanEnabled ? '已开启自动禁用' : '已关闭自动禁用', autoBanEnabled ? 'success' : 'info');
});

document.getElementById('btnSetAutoBan')?.addEventListener('click', () => {
    if (!autoBanChampionKey) {
        notify('请先在搜索框中搜索并选择一个英雄', 'error');
        return;
    }
    localStorage.setItem('lol_autoBanKey', autoBanChampionKey);
    localStorage.setItem('lol_autoBanName', autoBanChampionName);
    document.getElementById('autoBanTarget').textContent = autoBanChampionName;
    notify(`自动禁用已设置为: ${autoBanChampionName}`, 'success');
});

// 页面加载时初始化自动禁用搜索（如果autoBanConfig可见的话）
if (document.getElementById('autoBanConfig')?.classList.contains('auto-ban-config-visible')) {
    initAutoBanSearch();
}

// ==================== 分路选择 ====================

function selectLanePosition(position) {
    _currentSelectPosition = position;
    localStorage.setItem('lol_selectPosition', position);
    // 刷新推荐英雄
    const recoUrl = '/api/game/recommendations?position=' + position;
    fetch(recoUrl)
        .then(r => r.json())
        .then(data => {
            if (data.success && data.recommendations) {
                renderChampRecommendations(data.recommendations, window._csActions || []);
            }
        }).catch(() => {});
    // 更新 UI 按钮状态
    document.querySelectorAll('.pos-select-btn').forEach(btn => {
        const isActive = btn.textContent.trim().includes(
            {'TOP':'上单','JUNGLE':'打野','MIDDLE':'中单','BOTTOM':'ADC','UTILITY':'辅助'}[position] || ''
        );
        btn.style.borderColor = isActive ? 'var(--accent)' : 'var(--border)';
        btn.style.background = isActive ? 'var(--accent)' : 'transparent';
        btn.style.color = isActive ? '#0a0e1a' : 'var(--text-secondary)';
    });
    notify('分路已切换为: ' + ({'TOP':'上单','JUNGLE':'打野','MIDDLE':'中单','BOTTOM':'ADC','UTILITY':'辅助'}[position] || position), 'info');
}

// ==================== 就绪检查 ====================

document.getElementById('btnQuickAccept')?.addEventListener('click', async () => {
    try {
        const resp = await fetch('/api/game/accept', { method: 'POST' });
        const data = await resp.json();
        if (data.success || data.status === 204) {
            notify('已接受对局！', 'success');
            document.getElementById('readyCheckCard').style.display = 'none';
        } else {
            notify(data.error || '接受失败', 'error');
        }
    } catch (e) {
        notify('请求失败: ' + e.message, 'error');
    }
});

// ==================== 轮询控制 ====================

function startGamePolling() {
    if (gamePollTimer) return;
    _loadChampionCache();
    _autoBanExecuted = false;
    _lastReadyCheckNotified = false;
    gamePollTimer = setInterval(async () => {
        try {
            const resp = await fetch('/api/game/status');
            const data = await resp.json();
            if (data.success) {
                renderGameState(data);
                // 自动接受
                if (autoAcceptEnabled && data.phase === 'ReadyCheck') {
                    await fetch('/api/game/accept', { method: 'POST' });
                }
            }
        } catch (e) { /* 忽略轮询错误 */ }
    }, 2000);
}

function stopGamePolling() {
    if (gamePollTimer) {
        clearInterval(gamePollTimer);
        gamePollTimer = null;
    }
}

// 自动接受开关
document.getElementById('toggleAutoAccept')?.addEventListener('change', function() {
    autoAcceptEnabled = this.checked;
    localStorage.setItem('lol_autoAccept', autoAcceptEnabled.toString());
    notify(autoAcceptEnabled ? '已开启自动接受对局' : '已关闭自动接受对局',
           autoAcceptEnabled ? 'success' : 'info');
});

// 手动接受对局按钮
document.getElementById('btnForceAccept')?.addEventListener('click', async () => {
    try {
        const resp = await fetch('/api/game/accept', { method: 'POST' });
        const data = await resp.json();
        if (data.success || data.status === 204) {
            notify('已接受对局！', 'success');
        } else {
            notify(data.error || '接受失败，可能不在等待阶段', 'error');
        }
    } catch (e) {
        notify('请求失败: ' + e.message, 'error');
    }
