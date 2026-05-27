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

let _apiKeySetTime = null;

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
            _apiKeySetTime = Date.now();
            localStorage.setItem('lol_api_key_set_time', _apiKeySetTime.toString());
            resultEl.innerHTML = `<span style="color:var(--win)">✅ ${data.message} 当前密钥: ${data.currentKey}</span>`;
            updateApiKeyExpiryIndicator();
            notify('API密钥更新成功！', 'success');
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
    // 恢复保存的设置时间
    const saved = localStorage.getItem('lol_api_key_set_time');
    if (saved) _apiKeySetTime = parseInt(saved);
    updateApiKeyExpiryIndicator();
}
loadCurrentApiKey();

function updateApiKeyExpiryIndicator() {
    const indicator = document.getElementById('apiKeyExpiryIndicator');
    if (!indicator) return;

    if (!_apiKeySetTime) {
        indicator.innerHTML = '<span style="color:var(--text-muted);font-size:12px">尚未设置API密钥或未记录设置时间</span>';
        indicator.className = 'api-key-expiry';
        return;
    }

    const elapsed = Date.now() - _apiKeySetTime;
    const hoursElapsed = elapsed / (1000 * 60 * 60);
    const hoursRemaining = 24 - hoursElapsed;

    if (hoursRemaining <= 0) {
        indicator.innerHTML = '<i class="fas fa-exclamation-triangle"></i> API密钥可能已过期（超过24小时），请更新密钥';
        indicator.className = 'api-key-expiry expired';
    } else if (hoursRemaining <= 4) {
        indicator.innerHTML = `<i class="fas fa-clock"></i> API密钥将在约 ${Math.round(hoursRemaining)} 小时后过期，建议提前更新`;
        indicator.className = 'api-key-expiry warning';
    } else {
        indicator.innerHTML = `<i class="fas fa-check-circle"></i> API密钥有效（剩余约 ${Math.round(hoursRemaining)} 小时）`;
        indicator.className = 'api-key-expiry valid';
    }
}

