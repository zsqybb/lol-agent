/**
 * LOL数据助手 - 主入口
 * 所有功能模块已拆分到 static/js/ 目录下
 * 本文件仅负责应用初始化
 */

// ==================== 初始化 ====================

checkLcuStatus();
// 后台预加载英雄数据
_loadChampionCache();
loadIconMaps();
updateDdragonVersion();

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
