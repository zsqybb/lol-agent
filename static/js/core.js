/**
 * LOL数据助手 - 前端交互
 * 对接后端API，显示真实数据
 */

// ==================== 图标映射 ====================
let _iconMaps = null;
const DDRAGON_BASE = 'https://ddragon.leagueoflegends.com/cdn';
let DDRAGON_VERSION = '14.10.1'; // 动态更新版本号

async function updateDdragonVersion() {
    try {
        const resp = await fetch('/api/champions/refresh-status');
        const data = await resp.json();
        if (data.success && data.patch) {
            DDRAGON_VERSION = data.patch;
            console.log('DataDragon version updated to:', DDRAGON_VERSION);
        }
    } catch (e) { /* 静默失败，使用默认版本 */ }
}

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
        return `/static/img/item/${itemId}.png`;
    }
    if (!_iconMaps) return '';
    const id = _fuzzyLookup(_iconMaps.items, itemName);
    if (id) {
        return `/static/img/item/${id}.png`;
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

async function switchTab(tabId) {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    const navItem = document.querySelector(`.nav-item[data-tab="${tabId}"]`);
    if (navItem) navItem.classList.add('active');
    const tabEl = document.getElementById(tabId);
    if (tabEl) tabEl.classList.add('active');

    const titles = {
        'self-info': '个人信息',
        'search-player': '查询他人',
        'champion-list': '英雄图鉴',
        'settings': '设置',
        'game-assist': '游戏助手',
        'smart-chat': '智能问答',
    };
    document.getElementById('pageTitle').textContent = titles[tabId] || tabId;

    // 停止之前的轮询
    stopGamePolling();

    if (tabId === 'champion-list') {
        if (!window._championsLoaded) loadChampions();
        updateDataFreshness();
    }

    if (tabId === 'game-assist') {
        // 先连接LCU，再启动轮询
        const result = await connectLcu();
        if (result && result.success) {
            await checkLcuStatus();
        }
        startGamePolling();
    }
}

document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', function() {
    switchTab(this.dataset.tab);
  });
});
