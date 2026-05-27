// ==================== 英雄图鉴 ====================

let allChampions = [];
let currentRoleFilter = 'ALL';
let currentSort = 'key';
let _refreshing = false;

async function updateDataFreshness() {
    try {
        const resp = await fetch('/api/champions/refresh-status');
        const data = await resp.json();
        if (data.success) {
            const el = document.getElementById('dataFreshness');
            if (!el) return;
            const days = data.age_days;
            let cls = 'fresh';
            let text = '';
            if (days < 0) {
                text = '未更新';
                cls = 'stale';
            } else if (days === 0) {
                text = '今天更新';
                cls = 'fresh';
            } else if (days <= 7) {
                text = `${days}天前更新`;
                cls = days <= 3 ? 'fresh' : 'warn';
            } else {
                text = `${days}天前更新`;
                cls = 'stale';
            }
            el.textContent = text;
            el.className = 'data-freshness ' + cls;
            el.title = `补丁: ${data.patch} | 来源: ${data.source} | 英雄: ${data.champions_count}`;
        }
    } catch (e) { /* 静默处理 */ }
}

document.getElementById('btnRefreshData')?.addEventListener('click', async function() {
    if (_refreshing) return;
    if (!confirm('将从Riot Data Dragon和OP.GG获取最新英雄数据，可能需要几秒到十几秒。\n\n确定刷新？')) return;

    _refreshing = true;
    const btn = this;
    const icon = btn.querySelector('i');
    btn.disabled = true;
    if (icon) icon.classList.add('fa-spin');
    notify('正在获取最新数据...', 'info');

    try {
        const resp = await fetch('/api/champions/refresh', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({force: false}),
        });
        const data = await resp.json();
        if (data.success) {
            const meta = data.meta || {};
            let msg = '数据刷新完成！';
            if (meta.tier_updated) msg += ` 梯队数据已更新(${meta.champions_count}英雄)`;
            if (meta.ddragon_updated) msg += ` 基础数据已更新至${meta.patch}`;
            notify(msg, 'success');

            // 清除所有缓存，重新加载
            _championDataCache = {};
            _championDetailCache = {};
            window._championsLoaded = false;
            allChampions = [];
            loadChampions();
            updateDataFreshness();
            updateDdragonVersion();
            // 让游戏助手也重新加载缓存
            _loadChampionCache();
        } else {
            notify(data.message || data.error || '刷新失败', 'error');
        }
    } catch (e) {
        notify('刷新失败: ' + e.message, 'error');
    } finally {
        _refreshing = false;
        btn.disabled = false;
        if (icon) icon.classList.remove('fa-spin');
    }
});

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

// 英雄详情缓存
let _currentChampBuild = null;
let _currentChampPositions = [];
let _currentPositionName = '';
let _currentChampId = '';
let _championDetailCache = {};  // champId -> {champ, build}

async function openChampionDetail(champId) {
    const modal = document.getElementById('championModal');
    const detail = document.getElementById('championDetail');

    detail.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i> 加载中...</div>';
    modal.style.display = 'flex';
    _currentChampBuild = null;
    _currentChampId = champId;

    await loadIconMaps();

    // 使用缓存
    const cached = _championDetailCache[champId];
    let champ, build;

    if (cached) {
        champ = cached.champ;
        build = cached.build;
    } else {
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
            champ = champData[champId] || Object.values(champData)[0];
            if (!champ) {
                detail.innerHTML = '<div class="error-state"><p>数据格式错误</p></div>';
                return;
            }

            build = null;
            if (respBuild.ok) {
                try {
                    const buildData = await respBuild.json();
                    if (buildData.success) build = buildData.build;
                } catch (e) {
                    console.warn('Build数据解析失败:', e);
                }
            }

            // 缓存（最多缓存20个英雄）
            if (Object.keys(_championDetailCache).length < 20) {
                _championDetailCache[champId] = { champ, build };
            }
        } catch (e) {
            console.error('英雄详情加载失败:', e);
            detail.innerHTML = `<div class="error-state"><p>加载失败: ${e.message}</p></div>`;
            return;
        }
    }

    if (build) {
        _currentChampBuild = build;
        _currentChampPositions = build.positions || [];
        _currentPositionName = build.main_position || '';
        if (_currentChampPositions.length > 0 && !_currentPositionName) {
            _currentPositionName = _currentChampPositions[0].name || '';
        }
    }

    renderChampionDetailContent(champ, champId, build);
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

function _renderBuildItem(item, itemId, extraClass) {
    const icon = getItemIcon(item, itemId);
    return `<span class="build-item ${extraClass || ''}" title="${item}">
        ${icon ? `<img src="${icon}" class="item-icon" onerror="this.style.display='none'">` : '<span class="item-icon-placeholder"></span>'}
        <span class="item-name">${item}</span>
    </span>`;
}

function _renderBuildGroup(label, items, extraClass, itemIds) {
    if (!items || !items.length) return '';
    let html = `<div class="build-group"><div class="build-label">${label}</div><div class="build-items">`;
    items.forEach((item, idx) => {
        html += _renderBuildItem(item, itemIds ? itemIds[idx] : null, extraClass);
    });
    html += `</div></div>`;
    return html;
}

function renderBuildSection(b, containerId) {
    if (!b) return '';
    let html = `<div class="section-title"><i class="fas fa-shopping-bag"></i> 推荐装备</div>`;
    html += `<div class="build-section" id="${containerId}">`;
    html += _renderBuildGroup('起始装备', b.starts);
    html += _renderBuildGroup('鞋子', b.boots);
    html += _renderBuildGroup('核心装备', b.core, 'core');
    html += _renderBuildGroup('可选装备', b.situational, 'situational');
    html += `</div>`;
    return html;
}

function _renderRuneName(rune) {
    const icon = getRuneIcon(rune);
    return `<span class="rune-name">${icon ? `<img src="${icon}" class="rune-icon" onerror="this.style.display='none'">` : ''}${rune}</span>`;
}

function _renderRuneTree(name, runes) {
    if (!name) return '';
    const icon = getRuneTreeIcon(name);
    let html = `<div class="rune-tree"><div class="rune-tree-name">${icon ? `<img src="${icon}" class="rune-tree-icon" onerror="this.style.display='none'">` : ''}${name}</div>`;
    (runes || []).forEach(rune => { html += _renderRuneName(rune); });
    html += `</div>`;
    return html;
}

function _renderRuneShards(shards) {
    if (!shards || !shards.length) return '';
    const parts = shards.map(s => {
        const icon = getRuneIcon(s);
        return icon ? `<img src="${icon}" class="rune-icon" onerror="this.style.display='none'">${s}` : s;
    });
    return `<div class="rune-shards">属性碎片: ${parts.join(' | ')}</div>`;
}

function renderRunesSection(r, containerId) {
    if (!r) return '';
    let html = `<div class="section-title"><i class="fas fa-gem"></i> 推荐符文</div>`;
    html += `<div class="runes-section" id="${containerId}">`;
    html += _renderRuneTree(r.primary || '精密', r.primary_runes);
    html += _renderRuneTree(r.secondary || '坚决', r.secondary_runes);
    html += _renderRuneShards(r.shards);
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
    html += _renderBuildGroup('起始装备', b.starts);
    html += _renderBuildGroup('鞋子', b.boots);
    html += _renderBuildGroup('核心装备', b.core, 'core', b.core_ids);
    html += _renderBuildGroup('可选装备', b.situational, 'situational');
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
    html += _renderRuneTree(r.primary || '精密', r.primary_runes);
    html += _renderRuneTree(r.secondary || '坚决', r.secondary_runes);
    html += _renderRuneShards(r.shards);
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

