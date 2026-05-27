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
            return data;
        }
        // 普通连接失败，尝试强制重连
        const retryResp = await fetch('/api/lcu/force-reconnect');
        const retryData = await retryResp.json();
        if (retryData.success) {
            notify('LCU重连成功！', 'success');
            await checkLcuStatus();
            return retryData;
        }
        notify(data.error || '连接失败，请确认LOL客户端已启动并登录', 'error');
        return { success: false };
    } catch (e) {
        notify('连接失败: ' + e.message, 'error');
        return { success: false };
    }
}

// 浏览器环境才执行，Node.js 自动跳过
if (typeof document !== 'undefined') {
  document.getElementById('btnLcuConnect').addEventListener('click', connectLcu);
  document.getElementById('btnSettingsLcu').addEventListener('click', connectLcu);
  // 页面加载时自动尝试连接LCU
  setTimeout(() => { connectLcu().then(() => checkLcuStatus()); }, 800);
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

        await new Promise(r => setTimeout(r, 800));

        // 使用一站式接口，并发获取全部数据
        const resp = await fetch('/api/lcu/full-info');
        const data = await resp.json();

        if (data.success && data.summoner) {
            const s = data.summoner;
            notify('读取成功！', 'success');

            // 加载英雄缓存以显示名字和图标
            await _loadChampionCache();

            const rank = data.rank || {};
            const wallet = data.wallet || {};
            const lcuMasteries = data.masteries || [];
            const lcuMatches = data.matches || [];
            const gameflowPhase = data.gameflow || 'None';

            renderFullLcuInfo('selfResult', {
                summoner: {
                    name: s.name,
                    summoner_level: s.level,
                    profile_icon_id: s.profile_icon_id,
                    puuid: s.puuid,
                },
                rank: rank,
                wallet: wallet,
                masteries: lcuMasteries,
                matches: lcuMatches,
                gameflow: gameflowPhase,
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

