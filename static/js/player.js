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

    const iconSrc = summoner.profile_icon_id ? `/static/img/profileicon/${summoner.profile_icon_id}.png` : (summoner.profile_icon_path || '/static/img/profileicon/29.png');
    const summonerName = summoner.name || account.game_name || '未知';
    const level = summoner.summoner_level || 0;
    const tagLine = account.tag_line || '';

    const TIER_MAP = {'IRON':'坚韧黑铁','BRONZE':'英勇黄铜','SILVER':'不屈白银','GOLD':'荣耀黄金','PLATINUM':'华贵铂金','EMERALD':'流光翡翠','DIAMOND':'璀璨钻石','MASTER':'超凡大师','GRANDMASTER':'傲世宗师','CHALLENGER':'最强王者'};

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
            const tierCn = TIER_MAP[rank.solo.tier] || rank.solo.tier;
            const wr = rank.solo.wins + rank.solo.losses > 0 ? ((rank.solo.wins / (rank.solo.wins + rank.solo.losses)) * 100).toFixed(1) : '0';
            html += `
            <div class="ranking-card" style="flex:1;min-width:200px">
                <div class="ranking-value" style="font-size:16px;color:var(--gold)">${tierCn} ${rank.solo.division}</div>
                <div class="ranking-label">单/双排 · ${rank.solo.leaguePoints}LP</div>
                <div style="font-size:12px;color:var(--text-muted);margin-top:4px">${rank.solo.wins}胜 ${rank.solo.losses}负 · 胜率${wr}%</div>
            </div>`;
        }
        if (rank.flex && rank.flex.tier) {
            const tierCn = TIER_MAP[rank.flex.tier] || rank.flex.tier;
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

function renderFullLcuInfo(containerId, data) {
    const container = document.getElementById(containerId);
    container.style.display = 'block';

    const s = data.summoner || {};
    const rank = data.rank || {};
    const wallet = data.wallet || {};
    const masteries = data.masteries || [];
    const matches = data.matches || [];
    const gameflow = data.gameflow || 'None';
    const totalMastery = data.total_mastery_score || 0;
    const totalChamps = data.total_champions_played || 0;
    const freeChamps = data.free_champion_ids || [];
    const challenges = data.challenges || {};
    const lootCount = data.loot_count || 0;
    const honor = data.honor || {};

    const TIER_MAP = {'IRON':'坚韧黑铁','BRONZE':'英勇黄铜','SILVER':'不屈白银','GOLD':'荣耀黄金','PLATINUM':'华贵铂金','EMERALD':'流光翡翠','DIAMOND':'璀璨钻石','MASTER':'超凡大师','GRANDMASTER':'傲世宗师','CHALLENGER':'最强王者'};
    const PHASE_NAMES = {'None':'未运行','Lobby':'大厅','Matchmaking':'匹配中','ReadyCheck':'等待接受','ChampSelect':'选人中','InProgress':'游戏中','WaitingForStats':'等待结算','EndOfGame':'结算中','Reconnect':'重新连接'};

    const iconId = s.profile_icon_id || 29;
    const iconSrc = `/static/img/profileicon/${iconId}.png`;

    let html = '';

    // 召唤师卡片
    html += `
    <div class="summoner-card">
        <img class="summoner-icon" src="${iconSrc}" onerror="this.src='/static/img/profileicon/29.png'" alt="头像">
        <div class="summoner-info">
            <div class="summoner-name">${s.name || '未知召唤师'}</div>
            <div class="summoner-level">Lv.${s.summoner_level || 0}</div>
            <div class="summoner-tag" style="margin-top:4px;display:flex;gap:16px;flex-wrap:wrap">
                <span style="color:${gameflow === 'InProgress' ? 'var(--loss)' : gameflow === 'ChampSelect' ? 'var(--win)' : 'var(--text-muted)'}">
                    <i class="fas fa-circle"></i> ${PHASE_NAMES[gameflow] || gameflow}
                </span>
                ${totalMastery ? `<span style="color:var(--accent)"><i class="fas fa-star"></i> ${formatNumber(totalMastery)} 总熟练度</span>` : ''}
                ${totalChamps ? `<span style="color:var(--info)"><i class="fas fa-users"></i> ${totalChamps} 位英雄</span>` : ''}
            </div>
        </div>
        <div style="text-align:right">
            ${wallet.rp ? `<div style="color:var(--info);font-weight:600">💎 ${wallet.rp.toLocaleString()} RP</div>` : ''}
            ${wallet.ip ? `<div style="color:var(--accent);font-weight:600">🪙 ${wallet.ip.toLocaleString()} BE</div>` : ''}
            ${lootCount ? `<div style="color:var(--text-muted);font-size:11px">📦 ${lootCount} 件战利品</div>` : ''}
        </div>
    </div>`;

    // 排位信息
    if (rank.solo || rank.flex) {
        html += `<div class="section-title"><i class="fas fa-trophy"></i> 排位段位</div>`;
        html += `<div class="ranking-cards">`;
        if (rank.solo && rank.solo.tier) {
            const tierCn = TIER_MAP[rank.solo.tier] || rank.solo.tier;
            const wr = (rank.solo.wins + rank.solo.losses) > 0 ? ((rank.solo.wins / (rank.solo.wins + rank.solo.losses)) * 100).toFixed(1) : '0';
            html += `
            <div class="ranking-card">
                <div class="ranking-value" style="font-size:15px;color:var(--gold)">${tierCn} ${rank.solo.division}</div>
                <div class="ranking-label">单/双排 · ${rank.solo.leaguePoints}LP</div>
                <div style="font-size:11px;color:var(--text-muted);margin-top:4px">${rank.solo.wins}胜 ${rank.solo.losses}负 · 胜率${wr}%</div>
            </div>`;
        }
        if (rank.flex && rank.flex.tier) {
            const tierCn = TIER_MAP[rank.flex.tier] || rank.flex.tier;
            const wr = (rank.flex.wins + rank.flex.losses) > 0 ? ((rank.flex.wins / (rank.flex.wins + rank.flex.losses)) * 100).toFixed(1) : '0';
            html += `
            <div class="ranking-card">
                <div class="ranking-value" style="font-size:15px;color:var(--info)">${tierCn} ${rank.flex.division}</div>
                <div class="ranking-label">灵活组排 · ${rank.flex.leaguePoints}LP</div>
                <div style="font-size:11px;color:var(--text-muted);margin-top:4px">${rank.flex.wins}胜 ${rank.flex.losses}负 · 胜率${wr}%</div>
            </div>`;
        }
        html += `</div>`;
    }

    // 本周免费英雄
    if (freeChamps.length > 0) {
        html += `<div class="section-title"><i class="fas fa-gift"></i> 本周免费英雄 (${freeChamps.length})</div>`;
        html += `<div class="free-champ-row">`;
        freeChamps.forEach(cid => {
            const name = _championName(cid);
            const img = _championImg(cid);
            html += `<div class="free-champ-item" title="${name}"><img src="${img}" onerror="this.src='/static/img/champion/Akali.png'"><span>${name}</span></div>`;
        });
        html += `</div>`;
    }

    // 英雄熟练度
    if (masteries.length > 0) {
        html += `<div class="section-title"><i class="fas fa-star"></i> 英雄熟练度</div>`;
        html += `<div class="mastery-grid">`;
        for (const m of masteries) {
            const name = _championName(m.champion_id);
            const img = _championImg(m.champion_id);
            const levelClass = m.champion_level >= 7 ? 'level-7' : m.champion_level >= 6 ? 'level-6' : m.champion_level >= 5 ? 'level-5' : 'level-other';
            const chestIcon = m.chest_granted ? '<span style="font-size:10px;color:var(--gold);margin-left:2px">🏆</span>' : '';
            html += `
            <div class="mastery-item">
                <img class="mastery-champ-icon" src="${img}" onerror="this.src='/static/img/champion/Akali.png'" alt="${name}">
                <div class="mastery-info">
                    <div class="mastery-champ-name">${name}${chestIcon}</div>
                    <div class="mastery-points">${formatNumber(m.champion_points)} 点</div>
                </div>
                <span class="mastery-level ${levelClass}">Lv.${m.champion_level}</span>
            </div>`;
        }
        html += `</div>`;
    }

    // LCU最近比赛
    if (matches.length > 0) {
        html += `<div class="section-title"><i class="fas fa-swords"></i> 最近 ${matches.length} 场比赛</div>`;
        html += `<div class="match-list">`;
        for (const m of matches) {
            const me = m.participants.find(p => p.summoner_name === (s.name || ''));
            if (!me) {
                const alt = m.participants[0];
                if (!alt) continue;
                const isWin = alt.win;
                const champImg = _championImg(alt.champion_id);
                const champName = _championName(alt.champion_id);
                html += `
                <div class="match-item ${isWin ? 'win' : 'loss'}">
                    <img class="match-champ-icon" src="${champImg}" onerror="this.src='/static/img/champion/Akali.png'" alt="${champName}">
                    <div class="match-info">
                        <div class="match-champ-name">${champName}</div>
                        <div class="match-mode">${m.game_mode || ''} · ${formatDuration(m.game_duration)}</div>
                        <div class="match-time">${formatDate(m.game_creation)}</div>
                    </div>
                    <div class="match-result ${isWin ? 'win' : 'loss'}">${isWin ? '胜利' : '失败'}</div>
                </div>`;
                continue;
            }
            const isWin = me.win;
            const kda = `${me.kills}/${me.deaths}/${me.assists}`;
            const kdaRatio = me.deaths === 0 ? (me.kills + me.assists) : ((me.kills + me.assists) / me.deaths).toFixed(1);
            const champImg = _championImg(me.champion_id);
            const champName = _championName(me.champion_id);
            html += `
            <div class="match-item ${isWin ? 'win' : 'loss'}">
                <img class="match-champ-icon" src="${champImg}" onerror="this.src='/static/img/champion/Akali.png'" alt="${champName}">
                <div class="match-info">
                    <div class="match-champ-name">${champName}</div>
                    <div class="match-mode">${m.game_mode || ''} · ${formatDuration(m.game_duration)}</div>
                    <div class="match-time">${formatDate(m.game_creation)}</div>
                </div>
                <div class="match-kda">
                    <div class="match-kda-value ${parseFloat(kdaRatio) >= 3 ? 'good' : parseFloat(kdaRatio) < 1.5 ? 'bad' : ''}">${kda}</div>
                    <div style="font-size:11px;color:var(--text-muted)">KDA ${kdaRatio}</div>
                </div>
                <div class="match-result ${isWin ? 'win' : 'loss'}">${isWin ? '胜利' : '失败'}</div>
            </div>`;
        }
        html += `</div>`;
    }

    // 挑战数据
    if (challenges.total_points) {
        html += `<div class="section-title"><i class="fas fa-medal"></i> 挑战数据</div>`;
        html += `<div class="ranking-cards">
            <div class="ranking-card">
                <div class="ranking-value" style="font-size:15px;color:var(--accent)">${challenges.total_points.toLocaleString()}</div>
                <div class="ranking-label">挑战点数</div>
            </div>
            ${challenges.title ? `
            <div class="ranking-card">
                <div class="ranking-value" style="font-size:15px;color:var(--purple, #a855f7)">${challenges.title}</div>
                <div class="ranking-label">称号</div>
            </div>` : ''}
            ${challenges.crystal_level ? `
            <div class="ranking-card">
                <div class="ranking-value" style="font-size:15px;color:var(--info)">${challenges.crystal_level}</div>
                <div class="ranking-label">水晶等级</div>
            </div>` : ''}
        </div>`;
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

