/**
 * LOL数据助手 - 前端交互
 * 对接后端API，显示真实数据
 */

// ==================== 图标映射 ====================
let _iconMaps = null;
const DDRAGON_BASE = 'https://ddragon.leagueoflegends.com/cdn';
const DDRAGON_VERSION = '14.10.1'; // DataDragon CDN版本

async function loadIconMaps() {
    if (_iconMaps) return _iconMaps;
    try {
        const resp = await fetch('/static/icon_maps.json');
        _iconMaps = await resp.json();
    } catch (e) {
        console.warn('图标映射加载失败:', e);
        _iconMaps = { items: {}, runes: {}, rune_trees: {} };
    }
    return _iconMaps;
}

function _fuzzyLookup(map, name) {
    if (map[name]) return map[name];
    for (const key of Object.keys(map)) {
        if (key.includes(name) || name.includes(key)) return map[key];
    }
    return null;
}

function getItemIcon(itemName, itemId) {
    if (itemId) {
        return `${DDRAGON_BASE}/${DDRAGON_VERSION}/img/item/${itemId}.png`;
    }
    if (!_iconMaps) return '';
    const id = _fuzzyLookup(_iconMaps.items, itemName);
    if (id) {
        return `${DDRAGON_BASE}/${DDRAGON_VERSION}/img/item/${id}.png`;
    }
    return '';
}

function getRuneIcon(runeName) {
    if (!_iconMaps) return '';
    const icon = _fuzzyLookup(_iconMaps.runes, runeName);
    return icon ? `${DDRAGON_BASE}/img/${icon}` : '';
}

function getRuneTreeIcon(treeName) {
    if (!_iconMaps) return '';
    const icon = _iconMaps.rune_trees[treeName];
    return icon ? `${DDRAGON_BASE}/img/${icon}` : '';
}

// ==================== 工具函数 ====================

function notify(message, type = 'info') {
    const container = document.getElementById('notifications');
    const el = document.createElement('div');
    el.className = `notification ${type}`;
    el.innerHTML = `<i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>${message}`;
    container.appendChild(el);
    setTimeout(() => {
        el.classList.add('removing');
        setTimeout(() => el.remove(), 300);
    }, 3500);
}

function showLoading(text = '加载中...') {
    document.getElementById('loadingText').textContent = text;
    document.getElementById('loadingOverlay').style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
}

function formatNumber(num) {
    if (num >= 10000) return (num / 10000).toFixed(1) + '万';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'k';
    return num.toString();
}

function formatDuration(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}分${s}秒`;
}

function formatDate(timestamp) {
    if (!timestamp) return '未知时间';
    const d = new Date(timestamp);
    const month = d.getMonth() + 1;
    const day = d.getDate();
    const hours = d.getHours().toString().padStart(2, '0');
    const minutes = d.getMinutes().toString().padStart(2, '0');
    return `${month}月${day}日 ${hours}:${minutes}`;
}

// ==================== 标签切换 ====================

document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', function() {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    this.classList.add('active');
    const tabId = this.dataset.tab;
    document.getElementById(tabId).classList.add('active');

    const titles = {
        'self-info': '个人信息',
        'search-player': '查询他人',
        'champion-list': '英雄图鉴',
        'settings': '设置',
        'smart-chat': '智能问答',
    };
    document.getElementById('pageTitle').textContent = titles[tabId];

    if (tabId === 'champion-list' && !window._championsLoaded) {
        loadChampions();
    }
  });
});

// ==================== LCU 连接 ====================

async function checkLcuStatus() {
    try {
        const resp = await fetch('/api/lcu/status');
        const data = await resp.json();
        const el = document.getElementById('lcuStatus');
        if (data.connected) {
            el.innerHTML = '<span class="status-dot online"></span><span>客户端已连接</span>';
        } else {
            el.innerHTML = '<span class="status-dot offline"></span><span>客户端未连接</span>';
        }
        return data.connected;
    } catch (e) {
        return false;
    }
}

async function connectLcu() {
    try {
        const resp = await fetch('/api/lcu/connect');
        const data = await resp.json();
        if (data.success) {
            notify('LCU客户端连接成功！', 'success');
            await checkLcuStatus();
        } else {
            notify(data.error || '连接失败', 'error');
        }
        return data;
    } catch (e) {
        notify('连接失败: ' + e.message, 'error');
        return { success: false };
    }
}

// 浏览器环境才执行，Node.js 自动跳过
if (typeof document !== 'undefined') {
  document.getElementById('btnLcuConnect').addEventListener('click', connectLcu);
  document.getElementById('btnSettingsLcu').addEventListener('click', connectLcu);
}
document.getElementById('btnLcuRead').addEventListener('click', async () => {
    showLoading('正在从客户端读取数据...');
    try {
        const conn = await connectLcu();
        if (!conn.success) {
            hideLoading();
            notify('请先启动英雄联盟客户端', 'error');
            return;
        }

        await new Promise(r => setTimeout(r, 500));

        const resp = await fetch('/api/lcu/current-summoner');
        const data = await resp.json();

        if (data.success && data.summoner) {
            const summoner = data.summoner;
            notify('读取成功！', 'success');

            let rankInfo = {};
            try {
                const rankResp = await fetch('/api/lcu/rank');
                const rankData = await rankResp.json();
                if (rankData.success && rankData.rank) {
                    rankInfo = parseLcuRank(rankData.rank);
                }
            } catch (e) {
                console.warn('获取排位信息失败:', e);
            }

            renderPlayerResult('selfResult', {
                account: {
                    puuid: summoner.puuid,
                    game_name: summoner.name,
                    tag_line: ''
                },
                summoner: {
                    name: summoner.name,
                    summoner_level: summoner.level,
                    profile_icon_id: summoner.profile_icon_id,
                    profile_icon_path: summoner.profile_icon_path,
                    puuid: summoner.puuid,
                },
                masteries: [],
                matches: [],
                rank: rankInfo,
            });
        } else {
            const errorMsg = data.error || '读取失败';
            if (errorMsg.includes('401') || errorMsg.includes('认证')) {
                notify('认证失败：请尝试重启英雄联盟客户端后重试', 'error');
            } else if (errorMsg.includes('404') || errorMsg.includes('不可用') || errorMsg.includes('未登录')) {
                notify('客户端未登录：请在英雄联盟客户端中登录账号', 'error');
            } else if (errorMsg.includes('403') || errorMsg.includes('权限')) {
                notify('权限不足：请以管理员身份运行本程序', 'error');
            } else if (errorMsg.includes('超时')) {
                notify('请求超时：客户端可能未响应，请稍后重试', 'error');
            } else {
                notify(errorMsg, 'error');
            }
        }
    } catch (e) {
        notify('读取失败: ' + e.message, 'error');
    }
    hideLoading();
});

function parseLcuRank(rd) {
    let rankInfo = {};
    if (rd.highestRankedEntry) {
        const hre = rd.highestRankedEntry;
        rankInfo.solo = {
            tier: hre.tier || '',
            division: hre.division || '',
            leaguePoints: hre.leaguePoints || 0,
            wins: hre.wins || 0,
            losses: hre.losses || 0,
        };
    }
    if (rd.queues && rd.queues.length) {
        const soloQueue = rd.queues.find(q => q.queueType === 'RANKED_SOLO_5x5');
        const flexQueue = rd.queues.find(q => q.queueType === 'RANKED_FLEX_SR');
        if (soloQueue) {
            rankInfo.solo = {
                tier: soloQueue.tier || '',
                division: soloQueue.division || '',
                leaguePoints: soloQueue.leaguePoints || 0,
                wins: soloQueue.wins || 0,
                losses: soloQueue.losses || 0,
            };
        }
        if (flexQueue) {
            rankInfo.flex = {
                tier: flexQueue.tier || '',
                division: flexQueue.division || '',
                leaguePoints: flexQueue.leaguePoints || 0,
                wins: flexQueue.wins || 0,
                losses: flexQueue.losses || 0,
            };
        }
    }
    return rankInfo;
}

// ==================== Riot API 查询 ====================

async function searchPlayer(gameName, tagLine, platform, region = 'asia') {
    showLoading('正在查询玩家数据...');
    try {
        const params = new URLSearchParams({
            name: gameName,
            tag_line: tagLine,
            platform: platform,
            region: region
        });
        const resp = await fetch(`/api/player?${params}`);
        const data = await resp.json();

        if (data.success) {
            notify('查询成功！', 'success');
            return data;
        } else {
            notify(data.error || '查询失败', 'error');
            return null;
        }
    } catch (e) {
        notify('查询失败: ' + e.message, 'error');
        return null;
    } finally {
        hideLoading();
    }
}

document.getElementById('btnSelfSearch').addEventListener('click', async () => {
    const name = document.getElementById('selfGameName').value.trim();
    const tag = document.getElementById('selfTagLine').value.trim();
    const platform = document.getElementById('selfPlatform').value;
    const region = document.getElementById('selfRegion') ? document.getElementById('selfRegion').value : 'asia';

    if (!name) { notify('请输入游戏名', 'error'); return; }

    const result = await searchPlayer(name, tag, platform, region);
    if (result) {
        if (result.players) {
            renderPlayerSearchResults('selfResult', result.players, platform);
            document.getElementById('btnRefreshSelf').style.display = 'none';
            document.getElementById('selfFetchTime').style.display = 'none';
        } else {
            renderPlayerResult('selfResult', result);
            document.getElementById('btnRefreshSelf').style.display = 'inline-flex';
            window.lastSelfSearchParams = { name, tag, platform, region };
            if (result.fetch_time) {
                document.getElementById('selfFetchTime').style.display = 'block';
                document.getElementById('selfFetchTime').innerHTML = '数据获取时间: ' + result.fetch_time + ' (区域: ' + (result.fetch_region || region) + ')';
            }
        }
    }
});

document.getElementById('btnRefreshSelf').addEventListener('click', async () => {
    if (window.lastSelfSearchParams) {
        const { name, tag, platform, region } = window.lastSelfSearchParams;
        const result = await searchPlayer(name, tag, platform, region);
        if (result && !result.players) {
            renderPlayerResult('selfResult', result);
            if (result.fetch_time) {
                document.getElementById('selfFetchTime').innerHTML = '数据获取时间: ' + result.fetch_time + ' (区域: ' + (result.fetch_region || region) + ')';
            }
        }
    }
});

document.getElementById('btnSearchPlayer').addEventListener('click', async () => {
    const name = document.getElementById('searchGameName').value.trim();
    const tag = document.getElementById('searchTagLine').value.trim();
    const platform = document.getElementById('searchPlatform').value;
    const region = document.getElementById('searchRegion').value;

    if (!name) { notify('请输入游戏名', 'error'); return; }

    const result = await searchPlayer(name, tag, platform, region);
    if (result) {
        // 保存搜索参数用于刷新
        window.lastSearchParams = { name, tag, platform, region };
        
        if (result.players) {
            renderPlayerSearchResults('searchResult', result.players, platform);
            document.getElementById('btnRefreshPlayer').style.display = 'none';
            document.getElementById('searchFetchTime').style.display = 'none';
        } else {
            renderPlayerResult('searchResult', result);
            document.getElementById('btnRefreshPlayer').style.display = 'inline-flex';
            // 显示获取时间
            if (result.fetch_time) {
                document.getElementById('searchFetchTime').style.display = 'block';
                document.getElementById('searchFetchTime').innerHTML = `数据获取时间: ${result.fetch_time} (区域: ${result.fetch_region || region})`;
            }
        }
    }
});

// 刷新按钮事件
document.getElementById('btnRefreshPlayer').addEventListener('click', async () => {
    if (window.lastSearchParams) {
        const { name, tag, platform, region } = window.lastSearchParams;
        const result = await searchPlayer(name, tag, platform, region);
        if (result && !result.players) {
            renderPlayerResult('searchResult', result);
            if (result.fetch_time) {
                document.getElementById('searchFetchTime').innerHTML = `数据获取时间: ${result.fetch_time} (区域: ${result.fetch_region || region})`;
            }
        }
    }
});

// ==================== 渲染玩家搜索结果（多玩家列表）====================

function renderPlayerSearchResults(containerId, players, platform) {
    const container = document.getElementById(containerId);
    container.style.display = 'block';

    if (players.length === 0) {
        container.innerHTML = `<div class="error-state" style="padding:20px"><i class="fas fa-user-slash" style="color:var(--text-muted)"></i><p>未找到匹配的玩家，请输入标签以精确查找</p></div>`;
        return;
    }

    let html = `<div class="section-title"><i class="fas fa-users"></i> 找到 ${players.length} 个同名玩家</div>`;
    html += `<div class="player-search-grid">`;

    for (const player of players) {
        // 兼容两种数据结构：优化后的扁平化结构 和 旧的嵌套结构
        const account = player.account || player;
        const summoner = player.summoner || {};
        const iconSrc = player.profile_icon_path || (summoner.profile_icon_id ? `/static/img/profileicon/${summoner.profile_icon_id}.png` : '/static/img/profileicon/29.png');
        const name = account.game_name || summoner.name || player.name || '未知';
        const tag = account.tag_line || player.tag_line || '';
        const level = summoner.summoner_level || 0;
        const puuid = account.puuid || summoner.puuid || player.puuid || '';

        html += `
        <div class="player-search-card" data-puuid="${puuid}" data-tag="${tag}" data-platform="${platform}" data-name="${name}" onclick="loadPlayerByPuuid(this)">
            <img class="player-search-icon" src="${iconSrc}" onerror="this.src='/static/img/profileicon/29.png'" alt="${name}">
            <div class="player-search-info">
                <div class="player-search-name">${name}</div>
                ${tag ? `<div class="player-search-tag">#${tag}</div>` : ''}
                ${level ? `<div class="player-search-level">Lv.${level}</div>` : ''}
            </div>
        </div>`;
    }

    html += `</div>`;
    container.innerHTML = html;
}

async function loadPlayerByPuuid(el) {
    const name = el.dataset.name;
    const tag = el.dataset.tag;
    const platform = el.dataset.platform;
    const region = document.getElementById('searchRegion') ? document.getElementById('searchRegion').value : 'asia';

    showLoading('正在加载玩家详细信息...');
    try {
        const params = new URLSearchParams({ name: name, tag_line: tag, platform: platform, region: region });
        const resp = await fetch(`/api/player?${params}`);
        const data = await resp.json();

        if (data.success && !data.players) {
            const container = el.closest('.result-area');
            const containerId = container ? container.id : 'searchResult';
            renderPlayerResult(containerId, data);
            notify('查询成功！', 'success');
            
            document.getElementById('btnRefreshPlayer').style.display = 'inline-flex';
            window.lastSearchParams = { name, tag, platform, region };
            if (data.fetch_time) {
                document.getElementById('searchFetchTime').style.display = 'block';
                document.getElementById('searchFetchTime').innerHTML = '数据获取时间: ' + data.fetch_time + ' (区域: ' + (data.fetch_region || region) + ')';
            }
        } else {
            notify('无法获取玩家详细信息', 'error');
        }
    } catch (e) {
        notify('查询失败: ' + e.message, 'error');
    } finally {
        hideLoading();
    }
}

// ==================== 渲染玩家结果 ====================

function renderPlayerResult(containerId, data) {
    const container = document.getElementById(containerId);
    container.style.display = 'block';

    const account = data.account || {};
    const summoner = data.summoner || {};
    const masteries = data.masteries || [];
    const matches = data.matches || [];

    const currentPuuid = summoner.puuid || account.puuid || '';
    window.currentQueryPuuid = currentPuuid;

    const iconSrc = summoner.profile_icon_path || '/static/img/profileicon/29.png';
    const summonerName = summoner.name || account.game_name || '未知';
    const level = summoner.summoner_level || 0;
    const tagLine = account.tag_line || '';

    let html = '';

    html += `
    <div class="summoner-card">
        <img class="summoner-icon" src="${iconSrc}" onerror="this.src='/static/img/profileicon/29.png'" alt="头像">
        <div class="summoner-info">
            <div class="summoner-name">${summonerName}</div>
            <div class="summoner-level">Lv.${level}</div>
            ${tagLine ? `<div class="summoner-tag">#${tagLine}</div>` : ''}
        </div>
    </div>`;

    const rank = data.rank || {};
    if (rank.solo || rank.flex) {
        html += `<div class="section-title"><i class="fas fa-trophy"></i> 排位信息</div>`;
        html += `<div style="display:flex;gap:16px;flex-wrap:wrap">`;
        if (rank.solo && rank.solo.tier) {
            const tierMap = {'IRON':'坚韧黑铁','BRONZE':'英勇黄铜','SILVER':'不屈白银','GOLD':'荣耀黄金','PLATINUM':'华贵铂金','EMERALD':'流光翡翠','DIAMOND':'璀璨钻石','MASTER':'超凡大师','GRANDMASTER':'傲世宗师','CHALLENGER':'最强王者'};
            const tierCn = tierMap[rank.solo.tier] || rank.solo.tier;
            const wr = rank.solo.wins + rank.solo.losses > 0 ? ((rank.solo.wins / (rank.solo.wins + rank.solo.losses)) * 100).toFixed(1) : '0';
            html += `
            <div class="ranking-card" style="flex:1;min-width:200px">
                <div class="ranking-value" style="font-size:16px;color:var(--gold)">${tierCn} ${rank.solo.division}</div>
                <div class="ranking-label">单/双排 · ${rank.solo.leaguePoints}LP</div>
                <div style="font-size:12px;color:var(--text-muted);margin-top:4px">${rank.solo.wins}胜 ${rank.solo.losses}负 · 胜率${wr}%</div>
            </div>`;
        }
        if (rank.flex && rank.flex.tier) {
            const tierMap = {'IRON':'坚韧黑铁','BRONZE':'英勇黄铜','SILVER':'不屈白银','GOLD':'荣耀黄金','PLATINUM':'华贵铂金','EMERALD':'流光翡翠','DIAMOND':'璀璨钻石','MASTER':'超凡大师','GRANDMASTER':'傲世宗师','CHALLENGER':'最强王者'};
            const tierCn = tierMap[rank.flex.tier] || rank.flex.tier;
            const wr = rank.flex.wins + rank.flex.losses > 0 ? ((rank.flex.wins / (rank.flex.wins + rank.flex.losses)) * 100).toFixed(1) : '0';
            html += `
            <div class="ranking-card" style="flex:1;min-width:200px">
                <div class="ranking-value" style="font-size:16px;color:var(--info)">${tierCn} ${rank.flex.division}</div>
                <div class="ranking-label">灵活组排 · ${rank.flex.leaguePoints}LP</div>
                <div style="font-size:12px;color:var(--text-muted);margin-top:4px">${rank.flex.wins}胜 ${rank.flex.losses}负 · 胜率${wr}%</div>
            </div>`;
        }
        html += `</div>`;
    }

    if (masteries.length > 0) {
        html += `<div class="section-title"><i class="fas fa-star"></i> 英雄熟练度</div>`;
        html += `<div class="mastery-grid">`;
        for (const m of masteries) {
            const imgSrc = m.champion_image ? `/static/img/champion/${m.champion_image}` : '/static/img/champion/Akali.png';
            const levelClass = m.champion_level >= 7 ? 'level-7' : m.champion_level >= 6 ? 'level-6' : m.champion_level >= 5 ? 'level-5' : 'level-other';
            html += `
            <div class="mastery-item">
                <img class="mastery-champ-icon" src="${imgSrc}" onerror="this.src='/static/img/champion/Akali.png'" alt="${m.champion_name || ''}">
                <div class="mastery-info">
                    <div class="mastery-champ-name">${m.champion_name || '未知'}</div>
                    <div class="mastery-points">${formatNumber(m.champion_points)} 点</div>
                </div>
                <span class="mastery-level ${levelClass}">Lv.${m.champion_level}</span>
            </div>`;
        }
        html += `</div>`;
    }

    if (matches.length > 0) {
        html += `<div class="section-title"><i class="fas fa-swords"></i> 最近 ${matches.length} 场比赛</div>`;
        html += `<div class="match-list">`;
        for (const match of matches) {
            const myPuuid = summoner.puuid || account.puuid || '';
            const me = match.participants.find(p => p.puuid === myPuuid);
            
            if (!me) {
                console.warn('[Match Debug] Player not found in match:', match.match_id, 'myPuuid:', myPuuid.substring(0, 15) + '...', 'participants:', match.participants.map(p => p.puuid ? p.puuid.substring(0, 15) + '...' : 'null'));
                continue;
            }
            
            console.log('[Match Debug] Match:', match.match_id, 'Player:', me.riot_id_game_name + '#' + me.riot_id_tag_line, 'Champion:', me.champion_name, 'KDA:', me.kills + '/' + me.deaths + '/' + me.assists);
            
            const isWin = me.win;
            const kda = `${me.kills}/${me.deaths}/${me.assists}`;
            const kdaRatio = me.deaths === 0 ? (me.kills + me.assists) : ((me.kills + me.assists) / me.deaths).toFixed(1);
            const champImg = me.champion_image ? `/static/img/champion/${me.champion_image}` : '/static/img/champion/Akali.png';
            const champName = me.champion_name_cn || me.champion_name || '未知';
            const gameMode = match.game_mode || '';
            const gameDuration = match.game_duration || 0;
            const gameCreation = match.game_creation || 0;

            html += `
            <div class="match-item ${isWin ? 'win' : 'loss'}" onclick="openMatchDetail('${match.match_id}')" style="cursor:pointer">
                <img class="match-champ-icon" src="${champImg}" onerror="this.src='/static/img/champion/Akali.png'" alt="${champName}">
                <div class="match-info">
                    <div class="match-champ-name">${champName}</div>
                    <div class="match-mode">${gameMode} · ${formatDuration(gameDuration)}</div>
                    <div class="match-time">${formatDate(gameCreation)}</div>
                </div>
                <div class="match-kda">
                    <div class="match-kda-value ${parseFloat(kdaRatio) >= 3 ? 'good' : parseFloat(kdaRatio) < 1.5 ? 'bad' : ''}">${kda}</div>
                    <div style="font-size:11px;color:var(--text-muted)">KDA ${kdaRatio}</div>
                </div>
                <div class="match-result ${isWin ? 'win' : 'loss'}">${isWin ? '胜利' : '失败'}</div>
                <div style="margin-left:8px;color:var(--text-muted)"><i class="fas fa-chevron-right" style="font-size:10px"></i></div>
            </div>`;
        }
        html += `</div>`;
    }

    if (masteries.length === 0 && matches.length === 0 && summoner) {
        html += `<div class="error-state" style="padding:20px"><i class="fas fa-info-circle" style="color:var(--info)"></i><p>召唤师信息已获取，但暂无熟练度和比赛数据</p></div>`;
    }

    container.innerHTML = html;
}

// ==================== 对局详情弹窗 ====================

async function openMatchDetail(matchId) {
    const modal = document.getElementById('matchDetailModal');
    const detail = document.getElementById('matchDetailContent');

    detail.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i> 加载中...</div>';
    modal.style.display = 'flex';

    try {
        const resp = await fetch(`/api/match/${matchId}`);
        const data = await resp.json();

        if (!data.success) {
            detail.innerHTML = `<div class="error-state"><p>${data.error || '加载失败'}</p></div>`;
            return;
        }

        const blueTeam = data.blue_team || [];
        const redTeam = data.red_team || [];
        const blueWin = data.blue_win;
        const gameMode = data.game_mode || '';
        const gameDuration = data.game_duration || 0;
        const gameCreation = data.game_creation || 0;
        const teamObj = data.team_objectives || {};

        const objLabels = { champion: '击杀', tower: '推塔', dragon: '小龙', baron: '大龙', inhibitor: '水晶', riftHerald: '先锋' };

        let html = `
        <div class="match-detail-header">
            <div class="match-detail-mode">${gameMode}</div>
            <div class="match-detail-time">${formatDate(gameCreation)} · ${formatDuration(gameDuration)}</div>
        </div>`;

        const blueObj = teamObj[100] || {};
        const redObj = teamObj[200] || {};
        html += `<div class="team-objectives">`;
        for (const [key, label] of Object.entries(objLabels)) {
            const bv = blueObj[key] || 0;
            const rv = redObj[key] || 0;
            html += `<div class="obj-item">
                <span class="obj-blue ${bv > rv ? 'leading' : ''}">${bv}</span>
                <span class="obj-label">${label}</span>
                <span class="obj-red ${rv > bv ? 'leading' : ''}">${rv}</span>
            </div>`;
        }
        html += `</div>`;

        html += renderTeamTable(blueTeam, '蓝方', blueWin, 100);
        html += renderTeamTable(redTeam, '红方', !blueWin, 200);

        detail.innerHTML = html;
    } catch (e) {
        detail.innerHTML = `<div class="error-state"><p>加载失败: ${e.message}</p></div>`;
    }
}

function renderTeamTable(team, teamName, isWin, teamId) {
    const winClass = isWin ? 'win' : 'loss';
    const winText = isWin ? '胜利' : '失败';
    const teamGold = team.reduce((s, p) => s + (p.gold_earned || 0), 0);
    const teamDmg = team.reduce((s, p) => s + (p.total_damage_dealt || 0), 0);

    let html = `
    <div class="match-team-section">
        <div class="match-team-header ${winClass}">
            <span>${teamName} - ${winText}</span>
            <span style="font-size:11px;margin-left:12px">金币 ${formatNumber(teamGold)} · 伤害 ${formatNumber(teamDmg)}</span>
        </div>
        <table class="match-team-table">
            <thead><tr>
                <th style="width:140px">英雄</th>
                <th style="width:90px">KDA</th>
                <th style="width:70px">补刀</th>
                <th style="width:70px">视野</th>
                <th>装备</th>
            </tr></thead>
            <tbody>`;

    for (const p of team) {
        const champImg = p.champion_image ? `/static/img/champion/${p.champion_image}` : '/static/img/champion/Akali.png';
        const champName = p.champion_name_cn || p.champion_name || '未知';
        const pName = p.summoner_name || p.riot_id_game_name || '未知';
        const kdaRatio = p.deaths === 0 ? (p.kills + p.assists).toFixed(1) : ((p.kills + p.assists) / p.deaths).toFixed(1);
        const items = p.items || [];
        const wardKill = p.wards_killed || 0;
        const wardPlace = p.wards_placed || 0;
        const isCurrentPlayer = window.currentQueryPuuid && p.puuid === window.currentQueryPuuid;
        const highlightStyle = isCurrentPlayer ? 'background:rgba(255,215,0,0.1);border-left:3px solid var(--gold);' : '';

        html += `<tr class="${p.win ? 'win-row' : 'loss-row'}" style="${highlightStyle}">
            <td>
                <div style="display:flex;align-items:center;gap:6px">
                    <img src="${champImg}" style="width:28px;height:28px;border-radius:4px" onerror="this.src='/static/img/champion/Akali.png'">
                    <div>
                        <div style="font-size:12px;font-weight:600">${champName}${isCurrentPlayer ? ' <span style="color:var(--gold);font-size:10px">&#9660; 你</span>' : ''}</div>
                        <div style="font-size:10px;color:${isCurrentPlayer ? 'var(--gold)' : 'var(--text-muted)'}">${pName}</div>
                    </div>
                </div>
            </td>
            <td>
                <div style="font-size:12px;font-weight:600">${p.kills}/${p.deaths}/${p.assists}</div>
                <div style="font-size:10px;color:${parseFloat(kdaRatio) >= 3 ? 'var(--win)' : parseFloat(kdaRatio) < 1.5 ? 'var(--loss)' : 'var(--text-muted)'}">KDA ${kdaRatio}</div>
            </td>
            <td style="font-size:12px">${p.total_minions_killed || 0}</td>
            <td style="font-size:12px">${wardPlace}/${wardKill}</td>
            <td>
                <div style="display:flex;gap:2px;flex-wrap:wrap">
                    ${items.filter(i => i > 0).map(i => `<img src="/static/img/item/${i}.png" style="width:24px;height:24px;border-radius:2px" onerror="this.style.display='none'" title="物品${i}">`).join('')}
                </div>
            </td>
        </tr>`;
    }

    html += `</tbody></table></div>`;
    return html;
}

document.getElementById('matchDetailClose').addEventListener('click', () => {
    document.getElementById('matchDetailModal').style.display = 'none';
});

document.getElementById('matchDetailModal').addEventListener('click', (e) => {
    if (e.target === document.getElementById('matchDetailModal')) {
        document.getElementById('matchDetailModal').style.display = 'none';
    }
});

// ==================== 英雄图鉴 ====================

let allChampions = [];
let currentRoleFilter = 'ALL';
let currentSort = 'key';

async function loadChampions() {
    try {
        const resp = await fetch('/api/champions/with-build');
        const data = await resp.json();
        if (data.success) {
            allChampions = data.champions;
            window._championsLoaded = true;
            renderChampions();
        }
    } catch (e) {
        document.getElementById('championGrid').innerHTML =
            `<div class="error-state"><i class="fas fa-exclamation-triangle"></i><p>加载英雄列表失败</p></div>`;
    }
}

function renderChampions() {
    const grid = document.getElementById('championGrid');
    const searchText = (document.getElementById('championSearch').value || '').toLowerCase();

    let filtered = allChampions;

    if (currentRoleFilter !== 'ALL') {
        filtered = filtered.filter(c => {
            const roles = (c.roles_cn || []);
            return roles.some(r => r.includes(currentRoleFilter) || r === currentRoleFilter);
        });
    }

    if (searchText) {
        filtered = filtered.filter(c =>
            c.name.toLowerCase().includes(searchText) ||
            c.id.toLowerCase().includes(searchText) ||
            (c.title || '').toLowerCase().includes(searchText)
        );
    }

    filtered.sort((a, b) => {
        if (currentSort === 'win_rate_desc') return (b.win_rate || 0) - (a.win_rate || 0);
        else if (currentSort === 'pick_rate_desc') return (b.pick_rate || 0) - (a.pick_rate || 0);
        else if (currentSort === 'ban_rate_desc') return (b.ban_rate || 0) - (a.ban_rate || 0);
        else if (currentSort === 'rank_asc') return (a.rank || 999) - (b.rank || 999);
        else if (currentSort === 'difficulty_asc') return (a.difficulty || 2) - (b.difficulty || 2);
        return (a.key || 0) - (b.key || 0);
    });

    const statsEl = document.getElementById('championStats');
    const countEl = document.getElementById('championCount');
    if (statsEl && countEl) {
        statsEl.style.display = 'flex';
        countEl.textContent = `共 ${filtered.length} 位英雄`;
    }

    if (filtered.length === 0) {
        grid.innerHTML = `<div class="error-state" style="padding:20px"><p>没有找到匹配的英雄</p></div>`;
        return;
    }

    const diffClass = {1: 'easy', 2: 'medium', 3: 'hard'};
    const tierColors = {0: '', 1: 'tier-1', 2: 'tier-2', 3: 'tier-3', 4: 'tier-4', 5: 'tier-5'};
    const tierLabels = {0: '', 1: 'T1', 2: 'T2', 3: 'T3', 4: 'T4', 5: 'T5'};

    grid.innerHTML = filtered.map(c => {
        const roles = (c.roles_cn || []).join('/');
        const tier = c.tier || 0;
        const tierLabel = c.tier_label || tierLabels[tier] || '';
        const winRate = c.win_rate ? c.win_rate.toFixed(1) + '%' : '';
        const pickRate = c.pick_rate ? c.pick_rate.toFixed(1) + '%' : '';
        const banRate = c.ban_rate ? c.ban_rate.toFixed(1) + '%' : '';
        const kda = c.kda ? c.kda.toFixed(2) : '';
        const rankNum = c.rank || 0;
        return `
        <div class="champion-tile ${tierColors[tier] || ''}" data-champ-id="${c.id}">
            ${tierLabel ? `<span class="champ-tier ${tierColors[tier]}">${tierLabel}</span>` : ''}
            <img src="/static/img/champion/${c.image}" onerror="this.src='/static/img/champion/Akali.png'" alt="${c.name}">
            <div class="champ-info">
                <span class="champ-name" title="${c.name}">${c.name}</span>
                ${roles ? `<span class="champ-roles">${roles}</span>` : ''}
            </div>
            <div class="champ-rates">
                ${rankNum ? `<span class="rate-rank" title="排名" style="color:var(--text-muted)">#${rankNum}</span>` : ''}
                ${winRate ? `<span class="rate-win" title="胜率">胜${winRate}</span>` : ''}
                ${pickRate ? `<span class="rate-pick" title="选取率">选${pickRate}</span>` : ''}
                ${banRate ? `<span class="rate-ban" title="禁用率">禁${banRate}</span>` : ''}
                ${kda ? `<span class="rate-kda" title="KDA" style="color:var(--accent)">KDA ${kda}</span>` : ''}
            </div>
        </div>`;
    }).join('');

    grid.querySelectorAll('.champion-tile').forEach(tile => {
        tile.addEventListener('click', () => openChampionDetail(tile.dataset.champId));
    });
}

document.getElementById('championSearch').addEventListener('input', renderChampions);

document.querySelectorAll('.btn-filter').forEach(btn => {
    btn.addEventListener('click', function() {
        document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        currentRoleFilter = this.dataset.role;
        renderChampions();
    });
});

const sortEl = document.getElementById('championSort');
if (sortEl) {
    sortEl.addEventListener('change', function() {
        currentSort = this.value;
        renderChampions();
    });
}

// 英雄详情
let _currentChampBuild = null;
let _currentChampPositions = [];
let _currentPositionName = '';
let _currentChampId = '';

async function openChampionDetail(champId) {
    const modal = document.getElementById('championModal');
    const detail = document.getElementById('championDetail');

    detail.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i> 加载中...</div>';
    modal.style.display = 'flex';
    _currentChampBuild = null;
    _currentChampId = champId;

    await loadIconMaps();

    try {
        const [respChamp, respBuild] = await Promise.all([
            fetch(`/api/champion/${champId}`),
            fetch(`/api/champion-build/${champId}`)
        ]);

        const data = await respChamp.json();
        if (!data.success) {
            detail.innerHTML = `<div class="error-state"><p>${data.error || '加载失败'}</p></div>`;
            return;
        }

        const champData = data.data || {};
        const champ = champData[champId] || Object.values(champData)[0];
        if (!champ) {
            detail.innerHTML = '<div class="error-state"><p>数据格式错误</p></div>';
            return;
        }

        let build = null;
        if (respBuild.ok) {
            try {
                const buildData = await respBuild.json();
                if (buildData.success) {
                    build = buildData.build;
                    _currentChampBuild = build;
                    _currentChampPositions = (build && build.positions) || [];
                    _currentPositionName = (build && build.main_position) || '';
                    if (_currentChampPositions.length > 0 && !_currentPositionName) {
                        _currentPositionName = _currentChampPositions[0].name || '';
                    }
                }
            } catch (e) {
                console.warn('Build数据解析失败:', e);
            }
        }

        renderChampionDetailContent(champ, champId, build);
    } catch (e) {
        console.error('英雄详情加载失败:', e);
        detail.innerHTML = `<div class="error-state"><p>加载失败: ${e.message}</p></div>`;
    }
}

function renderChampionDetailContent(champ, champId, build) {
    const detail = document.getElementById('championDetail');

    const imgSrc = `/static/img/champion/${(champ.image && champ.image.full) || champId + '.png'}`;
    const passiveData = champ.passive || {};
    const passiveImg = `/static/img/passive/${(passiveData.image && passiveData.image.full) || champId + '_Passive.png'}`;

    const diff = (build && build.difficulty) || (champ.info && champ.info.difficulty ? Math.ceil(champ.info.difficulty / 3) : 2);
    const clampedDiff = Math.max(1, Math.min(3, diff > 3 ? Math.ceil(diff / 3.34) : diff));
    const diffStars = '★'.repeat(clampedDiff) + '☆'.repeat(3 - clampedDiff);
    const diffLabel = ['', '简单', '中等', '困难'][clampedDiff] || '中等';

    const rolesCn = (build && build.roles_cn) ? build.roles_cn : [];
    const rolesStr = rolesCn.length > 0 ? rolesCn.join(' / ') : (champ.tags || []).join('/');

    const tierNum = (build && build.tier) || 0;
    const tierLabel = (build && build.tier_label) || '';
    const tierClass = tierNum ? `tier-${tierNum}` : '';
    const rankNum = (build && build.rank) || 0;

    let currentStats = {};
    if (_currentChampPositions.length > 0 && _currentPositionName) {
        const posData = _currentChampPositions.find(p => p.name === _currentPositionName);
        if (posData) currentStats = posData;
    }
    const winRate = (currentStats.win_rate != null) ? currentStats.win_rate.toFixed(1) : ((build && build.win_rate) ? build.win_rate.toFixed(1) : '');
    const pickRate = (currentStats.pick_rate != null) ? currentStats.pick_rate.toFixed(1) : ((build && build.pick_rate) ? build.pick_rate.toFixed(1) : '');
    const banRate = (currentStats.ban_rate != null) ? currentStats.ban_rate.toFixed(1) : ((build && build.ban_rate) ? build.ban_rate.toFixed(1) : '');
    const kda = (currentStats.kda != null) ? currentStats.kda.toFixed(2) : ((build && build.kda) ? build.kda.toFixed(2) : '');

    let html = `
    <div class="champion-detail-header">
        <img src="${imgSrc}" onerror="this.src='/static/img/champion/Akali.png'" alt="${champ.name || champId}">
        <div>
            <div class="name">${champ.name || champId}
                <span style="font-size:12px;color:var(--text-muted);font-weight:normal;margin-left:8px">${champ.title || ''}</span>
                ${tierLabel ? `<span class="tier-badge ${tierClass}">${tierLabel}</span>` : ''}
            </div>
            <div style="display:flex;gap:12px;align-items:center;margin-top:8px;flex-wrap:wrap">
                <span class="tag-badge" style="background:var(--gold);color:#1a1a2e"><i class="fas fa-road"></i> ${rolesStr}</span>
                ${rankNum ? `<span style="color:var(--text-muted);font-size:12px">排名 #${rankNum}</span>` : ''}
            </div>
        </div>
    </div>

    <p style="font-size:13px;color:var(--text-secondary);line-height:1.8;margin-bottom:16px">${champ.blurb || ''}</p>`;

    if (_currentChampPositions.length > 1) {
        const posMap = {'TOP':'上单', 'JUNGLE':'打野', 'MID':'中单', 'ADC':'ADC', 'SUPPORT':'辅助'};
        html += `<div class="position-tabs">`;
        _currentChampPositions.forEach(pos => {
            const isActive = pos.name === _currentPositionName ? 'active' : '';
            const posCn = posMap[pos.name] || pos.name;
            html += `<button class="position-tab ${isActive}" onclick="switchPosition('${pos.name}')">${posCn}</button>`;
        });
        html += `</div>`;
    }

    const posLabel = (_currentChampPositions.length > 1 && _currentPositionName) ? ` (${_currentPositionName})` : '';
    if (winRate || pickRate || banRate) {
        html += `
    <div class="section-title"><i class="fas fa-chart-bar"></i> 韩服排位数据${posLabel}</div>
    <div class="ranking-cards" id="rankingCards">
        ${winRate ? `<div class="ranking-card"><div class="ranking-value ${parseFloat(winRate) >= 52 ? 'good' : parseFloat(winRate) < 48 ? 'bad' : ''}">${winRate}%</div><div class="ranking-label">胜率</div></div>` : ''}
        ${pickRate ? `<div class="ranking-card"><div class="ranking-value">${pickRate}%</div><div class="ranking-label">选取率</div></div>` : ''}
        ${banRate ? `<div class="ranking-card"><div class="ranking-value ${parseFloat(banRate) >= 10 ? 'hot' : ''}">${banRate}%</div><div class="ranking-label">禁用率</div></div>` : ''}
        ${kda ? `<div class="ranking-card"><div class="ranking-value">${kda}</div><div class="ranking-label">KDA</div></div>` : ''}
    </div>`;
    }

    const info = champ.info || {};
    const attackVal = info.attack || 0;
    const defenseVal = info.defense || 0;
    const magicVal = info.magic || 0;
    const diffVal = info.difficulty || diff * 33;
    const statColors = {
        attack: '#e84057',
        defense: '#4a9eff',
        magic: '#c764e8',
        difficulty: '#c89b3c'
    };


    if (build && build.builds) {
        html += renderBuildSection(build.builds, 'buildSection');
    }

    if (build && build.runes) {
        html += renderRunesSection(build.runes, 'runesSection');
    }

    const skillSequence = build && build.skill_sequence ? build.skill_sequence : [];
    const skillsStr = build && build.skills ? build.skills : '';
    html += renderSkillsSection(skillSequence, skillsStr, champ, 'skillsSection');

    html += `<div class="section-title"><i class="fas fa-magic"></i> 技能详情</div>`;
    html += `<div class="ability-list">`;

    if (passiveData && passiveData.name) {
        html += `
        <div class="ability-item">
            <img src="${passiveImg}" onerror="this.src='/static/img/passive/Akali_P.png'" alt="被动">
            <div>
                <div class="ability-name">${passiveData.name} <span style="color:var(--gold)">[被动]</span></div>
                <div style="font-size:11px;color:var(--text-muted)">${passiveData.description || ''}</div>
            </div>
        </div>`;
    }

    const spellKeys = ['Q', 'W', 'E', 'R'];
    const spells = champ.spells || [];
    spells.forEach((spell, i) => {
        const spellImg = `/static/img/spell/${(spell.image && spell.image.full) || ''}`;
        const cd = spell.cooldown ? spell.cooldown.join('/') + 's' : '';
        const cost = spell.cost ? spell.cost.join('/') : '';
        html += `
        <div class="ability-item">
            <img src="${spellImg}" onerror="this.src='/static/img/spell/AkaliQ.png'" alt="${spell.name || ''}">
            <div>
                <div class="ability-name">${spell.name || ''} <span style="color:var(--blue)">[${spellKeys[i] || i}]</span></div>
                <div style="font-size:11px;color:var(--text-muted)">${spell.description || spell.tooltip || ''}</div>
                <div style="font-size:10px;color:var(--text-muted);margin-top:4px">冷却: ${cd} | 消耗: ${cost}</div>
            </div>
        </div>`;
    });

    html += `</div>`;

    if (champ.allytips && champ.allytips.length > 0) {
        html += `<div class="section-title"><i class="fas fa-lightbulb"></i> 使用技巧</div>`;
        html += `<ul class="tips-list">`;
        champ.allytips.forEach(tip => { html += `<li>${tip}</li>`; });
        html += `</ul>`;
    }

    detail.innerHTML = html;
}

function renderBuildSection(b, containerId) {
    if (!b) return '';
    let html = `<div class="section-title"><i class="fas fa-shopping-bag"></i> 推荐装备</div>`;
    html += `<div class="build-section" id="${containerId}">`;

    if (b.starts) {
        html += `<div class="build-group"><div class="build-label">起始装备</div><div class="build-items">`;
        b.starts.forEach(item => {
            const icon = getItemIcon(item);
            html += `<span class="build-item" title="${item}">${icon ? `<img src="${icon}" class="item-icon" onerror="this.style.display='none'">` : '<span class="item-icon-placeholder"></span>'}<span class="item-name">${item}</span></span>`;
        });
        html += `</div></div>`;
    }

    if (b.boots) {
        html += `<div class="build-group"><div class="build-label">鞋子</div><div class="build-items">`;
        b.boots.forEach(item => {
            const icon = getItemIcon(item);
            html += `<span class="build-item" title="${item}">${icon ? `<img src="${icon}" class="item-icon" onerror="this.style.display='none'">` : '<span class="item-icon-placeholder"></span>'}<span class="item-name">${item}</span></span>`;
        });
        html += `</div></div>`;
    }

    if (b.core) {
        html += `<div class="build-group"><div class="build-label">核心装备</div><div class="build-items">`;
        b.core.forEach(item => {
            const icon = getItemIcon(item);
            html += `<span class="build-item core" title="${item}">${icon ? `<img src="${icon}" class="item-icon" onerror="this.style.display='none'">` : '<span class="item-icon-placeholder"></span>'}<span class="item-name">${item}</span></span>`;
        });
        html += `</div></div>`;
    }

    if (b.situational) {
        html += `<div class="build-group"><div class="build-label">可选装备</div><div class="build-items">`;
        b.situational.forEach(item => {
            const icon = getItemIcon(item);
            html += `<span class="build-item situational" title="${item}">${icon ? `<img src="${icon}" class="item-icon" onerror="this.style.display='none'">` : '<span class="item-icon-placeholder"></span>'}<span class="item-name">${item}</span></span>`;
        });
        html += `</div></div>`;
    }

    html += `</div>`;
    return html;
}

function renderRunesSection(r, containerId) {
    if (!r) return '';
    let html = `<div class="section-title"><i class="fas fa-gem"></i> 推荐符文</div>`;
    html += `<div class="runes-section" id="${containerId}">`;
    const primaryIcon = getRuneTreeIcon(r.primary || '精密');
    html += `<div class="rune-tree"><div class="rune-tree-name">${primaryIcon ? `<img src="${primaryIcon}" class="rune-tree-icon" onerror="this.style.display='none'">` : ''}${r.primary || '精密'}</div>`;
    (r.primary_runes || []).forEach(rune => {
        const icon = getRuneIcon(rune);
        html += `<span class="rune-name">${icon ? `<img src="${icon}" class="rune-icon" onerror="this.style.display='none'">` : ''}${rune}</span>`;
    });
    html += `</div>`;
    const secondaryIcon = getRuneTreeIcon(r.secondary || '坚决');
    html += `<div class="rune-tree"><div class="rune-tree-name">${secondaryIcon ? `<img src="${secondaryIcon}" class="rune-tree-icon" onerror="this.style.display='none'">` : ''}${r.secondary || '坚决'}</div>`;
    (r.secondary_runes || []).forEach(rune => {
        const icon = getRuneIcon(rune);
        html += `<span class="rune-name">${icon ? `<img src="${icon}" class="rune-icon" onerror="this.style.display='none'">` : ''}${rune}</span>`;
    });
    html += `</div>`;
    if (r.shards) {
        html += `<div class="rune-shards">属性碎片: ${(r.shards||[]).map(s => {
            const icon = getRuneIcon(s);
            return icon ? `<img src="${icon}" class="rune-icon" onerror="this.style.display='none'">${s}` : s;
        }).join(' | ')}</div>`;
    }
    html += `</div>`;
    return html;
}

function renderSkillsSection(skillSequence, skillsStr, champ, containerId) {
    let html = `<div class="section-title"><i class="fas fa-sort-numeric-up"></i> 技能加点</div>`;
    html += `<div class="skills-section" id="${containerId}">`;

    if (skillsStr) {
        html += `<div style="margin-bottom:12px">推荐加点优先级: <span class="skills-order-text">${skillsStr}</span></div>`;
    }

    if (skillSequence && skillSequence.length === 18) {
        const skillColors = { 'Q': 'var(--blue)', 'W': 'var(--win)', 'E': 'var(--accent)', 'R': 'var(--gold)' };
        const skillBg = { 'Q': '#1e3a5f', 'W': '#1e5f3a', 'E': '#5f3a1e', 'R': '#5f4a1e' };

        html += `<div class="skill-grid">`;
        html += `<div class="skill-grid-header">
            <div class="skill-grid-label">技能</div>`;
        for (let lv = 1; lv <= 18; lv++) {
            html += `<div class="skill-grid-lv">${lv}</div>`;
        }
        html += `</div>`;

        const skills = ['Q', 'W', 'E', 'R'];
        skills.forEach(skill => {
            html += `<div class="skill-grid-row">
                <div class="skill-grid-skill" style="color:${skillColors[skill]};font-weight:700">${skill}</div>`;
            for (let lv = 1; lv <= 18; lv++) {
                const isThisSkill = skillSequence[lv - 1] === skill;
                html += `<div class="skill-grid-cell ${isThisSkill ? 'active' : ''}" style="${isThisSkill ? `background:${skillBg[skill]};color:${skillColors[skill]};font-weight:700` : ''}">
                    ${isThisSkill ? '●' : ''}
                </div>`;
            }
            html += `</div>`;
        });

        html += `<div class="skill-grid-row skill-grid-result">
            <div class="skill-grid-skill" style="font-size:10px;color:var(--text-muted)">加点</div>`;
        skillSequence.forEach(skill => {
            html += `<div class="skill-grid-cell" style="font-size:10px;color:${skillColors[skill]};font-weight:600">${skill}</div>`;
        });
        html += `</div>`;

        html += `</div>`;
    } else if (skillsStr) {
        html += `<div class="skills-order">推荐加点顺序: <span class="skills-order-text">${skillsStr}</span></div>`;
    }

    html += `</div>`;
    return html;
}

// ==================== 分路切换 ====================

async function switchPosition(positionName) {
    _currentPositionName = positionName;

    document.querySelectorAll('.position-tab').forEach(tab => {
        const onClick = tab.getAttribute('onclick') || '';
        tab.classList.toggle('active', onClick.includes(positionName));
    });

    if (_currentChampId) {
        try {
            const resp = await fetch(`/api/champion-build/${_currentChampId}?position=${positionName}`);
            if (resp.ok) {
                const data = await resp.json();
                if (data.success && data.build) {
                    const build = data.build;
                    _currentChampBuild = build;
                    updateBuildSection(build);
                    updateRunesSection(build);
                    updateSkillsSection(build);
                }
            }
        } catch (e) {
            console.warn('分路数据获取失败:', e);
        }
    }

    const posData = _currentChampPositions.find(p => p.name === positionName);
    if (posData) updateRankingCards(posData);
}

function updateBuildSection(build) {
    const container = document.getElementById('buildSection');
    if (!container) return;
    const b = build && build.builds ? build.builds : null;
    if (!b || !Object.values(b).some(v => v && v.length > 0)) {
        container.innerHTML = '<div class="build-group"><div class="build-label" style="color:var(--text-muted)">该分路暂无出装数据</div></div>';
        return;
    }
    let html = '';
    if (b.starts && b.starts.length) {
        html += `<div class="build-group"><div class="build-label">起始装备</div><div class="build-items">`;
        b.starts.forEach(item => { const icon = getItemIcon(item); html += `<span class="build-item" title="${item}">${icon ? `<img src="${icon}" class="item-icon" onerror="this.style.display='none'">` : '<span class="item-icon-placeholder"></span>'}<span class="item-name">${item}</span></span>`; });
        html += `</div></div>`;
    }
    if (b.boots && b.boots.length) {
        html += `<div class="build-group"><div class="build-label">鞋子</div><div class="build-items">`;
        b.boots.forEach(item => { const icon = getItemIcon(item); html += `<span class="build-item" title="${item}">${icon ? `<img src="${icon}" class="item-icon" onerror="this.style.display='none'">` : '<span class="item-icon-placeholder"></span>'}<span class="item-name">${item}</span></span>`; });
        html += `</div></div>`;
    }
    if (b.core && b.core.length) {
        html += `<div class="build-group"><div class="build-label">核心装备</div><div class="build-items">`;
        const coreIds = b.core_ids || [];
        b.core.forEach((item, idx) => {
            const icon = getItemIcon(item, coreIds[idx]);
            html += `<span class="build-item core" title="${item}">${icon ? `<img src="${icon}" class="item-icon" onerror="this.style.display='none'">` : '<span class="item-icon-placeholder"></span>'}<span class="item-name">${item}</span></span>`;
        });
        html += `</div></div>`;
    }
    if (b.situational && b.situational.length) {
        html += `<div class="build-group"><div class="build-label">可选装备</div><div class="build-items">`;
        b.situational.forEach(item => { const icon = getItemIcon(item); html += `<span class="build-item" title="${item}">${icon ? `<img src="${icon}" class="item-icon" onerror="this.style.display='none'">` : '<span class="item-icon-placeholder"></span>'}<span class="item-name">${item}</span></span>`; });
        html += `</div></div>`;
    }
    if (build.builds_fallback) {
        html += `<div style="font-size:10px;color:var(--text-muted);margin-top:4px">* 该分路暂无专属出装，显示主位置推荐</div>`;
    }
    container.innerHTML = html;
}

function updateRunesSection(build) {
    const container = document.getElementById('runesSection');
    if (!container) return;
    const r = build && build.runes ? build.runes : null;
    if (!r || !r.primary) {
        container.innerHTML = '<div class="build-group"><div class="build-label" style="color:var(--text-muted)">该分路暂无符文数据</div></div>';
        return;
    }
    let html = '';
    const primaryIcon = getRuneTreeIcon(r.primary || '精密');
    html += `<div class="rune-tree"><div class="rune-tree-name">${primaryIcon ? `<img src="${primaryIcon}" class="rune-tree-icon" onerror="this.style.display='none'">` : ''}${r.primary || '精密'}</div>`;
    (r.primary_runes || []).forEach(rune => { const icon = getRuneIcon(rune); html += `<span class="rune-name">${icon ? `<img src="${icon}" class="rune-icon" onerror="this.style.display='none'">` : ''}${rune}</span>`; });
    html += `</div>`;
    const secondaryIcon = getRuneTreeIcon(r.secondary || '坚决');
    html += `<div class="rune-tree"><div class="rune-tree-name">${secondaryIcon ? `<img src="${secondaryIcon}" class="rune-tree-icon" onerror="this.style.display='none'">` : ''}${r.secondary || '坚决'}</div>`;
    (r.secondary_runes || []).forEach(rune => { const icon = getRuneIcon(rune); html += `<span class="rune-name">${icon ? `<img src="${icon}" class="rune-icon" onerror="this.style.display='none'">` : ''}${rune}</span>`; });
    html += `</div>`;
    if (r.shards) {
        html += `<div class="rune-shards">属性碎片: ${(r.shards||[]).map(s => { const icon = getRuneIcon(s); return icon ? `<img src="${icon}" class="rune-icon" onerror="this.style.display='none'">${s}` : s; }).join(' | ')}</div>`;
    }
    if (build.runes_fallback) {
        html += `<div style="font-size:10px;color:var(--text-muted);margin-top:4px">* 该分路暂无专属符文，显示主位置推荐</div>`;
    }
    container.innerHTML = html;
}

function updateSkillsSection(build) {
    const container = document.getElementById('skillsSection');
    if (!container) return;

    const skillsStr = build && build.skills ? build.skills : '';
    const skillSequence = build && build.skill_sequence ? build.skill_sequence : [];

    let html = '';
    if (skillsStr) {
        html += `<div style="margin-bottom:12px">推荐加点优先级: <span class="skills-order-text">${skillsStr}</span></div>`;
    }

    if (skillSequence && skillSequence.length === 18) {
        const skillColors = { 'Q': 'var(--blue)', 'W': 'var(--win)', 'E': 'var(--accent)', 'R': 'var(--gold)' };
        const skillBg = { 'Q': '#1e3a5f', 'W': '#1e5f3a', 'E': '#5f3a1e', 'R': '#5f4a1e' };

        html += `<div class="skill-grid">`;
        html += `<div class="skill-grid-header"><div class="skill-grid-label">技能</div>`;
        for (let lv = 1; lv <= 18; lv++) { html += `<div class="skill-grid-lv">${lv}</div>`; }
        html += `</div>`;

        ['Q', 'W', 'E', 'R'].forEach(skill => {
            html += `<div class="skill-grid-row"><div class="skill-grid-skill" style="color:${skillColors[skill]};font-weight:700">${skill}</div>`;
            for (let lv = 1; lv <= 18; lv++) {
                const isActive = skillSequence[lv - 1] === skill;
                html += `<div class="skill-grid-cell ${isActive ? 'active' : ''}" style="${isActive ? `background:${skillBg[skill]};color:${skillColors[skill]};font-weight:700` : ''}">${isActive ? '●' : ''}</div>`;
            }
            html += `</div>`;
        });

        html += `<div class="skill-grid-row skill-grid-result"><div class="skill-grid-skill" style="font-size:10px;color:var(--text-muted)">加点</div>`;
        skillSequence.forEach(skill => { html += `<div class="skill-grid-cell" style="font-size:10px;color:${skillColors[skill]};font-weight:600">${skill}</div>`; });
        html += `</div></div>`;
    } else if (skillsStr) {
        html += `<div class="skills-order">推荐加点顺序: <span class="skills-order-text">${skillsStr}</span></div>`;
    }

    container.innerHTML = html;
}

function updateRankingCards(posData) {
    const container = document.getElementById('rankingCards');
    if (!container) return;

    const winRate = (posData.win_rate != null) ? posData.win_rate.toFixed(1) : '';
    const pickRate = (posData.pick_rate != null) ? posData.pick_rate.toFixed(1) : '';
    const banRate = (posData.ban_rate != null) ? posData.ban_rate.toFixed(1) : '';
    const kda = (posData.kda != null) ? posData.kda.toFixed(2) : '';

    let html = '';
    if (winRate) html += `<div class="ranking-card"><div class="ranking-value ${parseFloat(winRate) >= 52 ? 'good' : parseFloat(winRate) < 48 ? 'bad' : ''}">${winRate}%</div><div class="ranking-label">胜率</div></div>`;
    if (pickRate) html += `<div class="ranking-card"><div class="ranking-value">${pickRate}%</div><div class="ranking-label">选取率</div></div>`;
    if (banRate) html += `<div class="ranking-card"><div class="ranking-value ${parseFloat(banRate) >= 10 ? 'hot' : ''}">${banRate}%</div><div class="ranking-label">禁用率</div></div>`;
    if (kda) html += `<div class="ranking-card"><div class="ranking-value">${kda}</div><div class="ranking-label">KDA</div></div>`;

    container.innerHTML = html;
}

document.getElementById('modalClose').addEventListener('click', () => {
    document.getElementById('championModal').style.display = 'none';
});

document.getElementById('championModal').addEventListener('click', (e) => {
    if (e.target === document.getElementById('championModal')) {
        document.getElementById('championModal').style.display = 'none';
    }
});

// ==================== API 测试 ====================

document.getElementById('btnTestApi').addEventListener('click', async () => {
    const resultEl = document.getElementById('apiTestResult');
    resultEl.textContent = '测试中...';

    try {
        const resp = await fetch('/api/player?name=Hide%20on%20bush&tag=KR1&platform=kr');
        const data = await resp.json();

        if (data.success && data.summoner) {
            resultEl.innerHTML = `<span style="color:var(--win)">✅ API可用！已获取到召唤师: ${data.summoner.name} (Lv.${data.summoner.summoner_level})</span>`;
        } else if (data.success) {
            resultEl.innerHTML = `<span style="color:var(--win)">✅ API可用！账号查询成功</span>`;
        } else {
            resultEl.innerHTML = `<span style="color:var(--loss)">❌ ${data.error || 'API测试失败'}</span>`;
        }
    } catch (e) {
        resultEl.innerHTML = `<span style="color:var(--loss)">❌ 请求失败: ${e.message}</span>`;
    }
});

// ==================== API 密钥更新 ====================

document.getElementById('btnUpdateApiKey').addEventListener('click', async () => {
    const apiKey = document.getElementById('apiKeyInput').value.trim();
    const resultEl = document.getElementById('apiTestResult');

    if (!apiKey) {
        resultEl.innerHTML = `<span style="color:var(--loss)">❌ 请输入API密钥</span>`;
        return;
    }

    if (!apiKey.startsWith('RGAPI-')) {
        resultEl.innerHTML = `<span style="color:var(--loss)">❌ 无效的API密钥格式，必须以 RGAPI- 开头</span>`;
        return;
    }

    resultEl.textContent = '更新中...';

    try {
        const resp = await fetch('/api/update-api-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ apiKey })
        });
        const data = await resp.json();

        if (data.success) {
            resultEl.innerHTML = `<span style="color:var(--win)">✅ ${data.message} 当前密钥: ${data.currentKey}</span>`;
            notify('API密钥更新成功！页面将自动刷新...', 'success');
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        } else {
            resultEl.innerHTML = `<span style="color:var(--loss)">❌ ${data.error}</span>`;
        }
    } catch (e) {
        resultEl.innerHTML = `<span style="color:var(--loss)">❌ 请求失败: ${e.message}</span>`;
    }
});

// 页面加载时获取当前密钥
async function loadCurrentApiKey() {
    try {
        const resp = await fetch('/api/get-api-key');
        const data = await resp.json();
        if (data.success) {
            document.getElementById('apiKeyInput').value = '';
        }
    } catch (e) {
        console.log('获取API密钥失败:', e);
    }
}
loadCurrentApiKey();

// ==================== 初始化 ====================

checkLcuStatus();

['selfGameName', 'searchGameName'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
        el.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const btnId = id === 'selfGameName' ? 'btnSelfSearch' : 'btnSearchPlayer';
                document.getElementById(btnId).click();
            }
        });
    }
});

console.log('%cLOL数据助手 v2.0 已加载', 'color: #c89b3c; font-size: 16px; font-weight: bold');

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