"""
游戏流程管理器 — 基于LCU API实现游戏自动化
参照 LeagueAkari：自动接受、选人助手、符文应用、对局统计
"""
import logging
from lcu_connect import lcu_get, lcu_post, find_lcu, is_connected

logger = logging.getLogger(__name__)

# 游戏阶段映射
PHASE_NAMES = {
    'None': '未运行',
    'Lobby': '大厅',
    'Matchmaking': '匹配中',
    'ReadyCheck': '等待接受',
    'ChampSelect': '选人中',
    'InProgress': '游戏中',
    'WaitingForStats': '等待结算',
    'EndOfGame': '结算中',
    'Reconnect': '重新连接',
}

# 位置名称映射
POSITION_NAMES = {
    'TOP': '上单', 'JUNGLE': '打野', 'MIDDLE': '中单',
    'BOTTOM': 'ADC', 'UTILITY': '辅助', 'FILL': '补位',
}


def get_gameflow_phase():
    """获取当前游戏阶段，返回 {phase, phase_cn, data}"""
    result = lcu_get('/lol-gameflow/v1/session')
    if not result.get('success'):
        return {'phase': 'Unknown', 'phase_cn': '未连接', 'data': None}

    data = result['data']
    phase = data.get('phase', 'None')
    return {
        'phase': phase,
        'phase_cn': PHASE_NAMES.get(phase, phase),
        'data': data,
    }


def accept_ready_check():
    """接受对局就绪检查"""
    return lcu_post('/lol-matchmaking/v1/ready-check/accept', json_data={})


def decline_ready_check():
    """拒绝对局就绪检查"""
    return lcu_post('/lol-matchmaking/v1/ready-check/decline', json_data={})


def get_champ_select_session():
    """获取当前选人阶段的完整数据"""
    result = lcu_get('/lol-champ-select/v1/session')
    if not result.get('success'):
        return {'success': False, 'error': '不在选人阶段'}

    data = result['data']
    actions = data.get('actions', [])
    my_team = data.get('myTeam', [])
    their_team = data.get('theirTeam', [])
    timer = data.get('timer', {})
    local_cell_id = data.get('localPlayerCellId', 0)

    # 我的操作列表
    local_actions = []
    for action_group in actions:
        for a in action_group:
            if a.get('actorCellId') == local_cell_id:
                local_actions.append({
                    'id': a.get('id'),
                    'type': a.get('type', ''),  # pick/ban
                    'completed': a.get('completed', False),
                    'champion_id': a.get('championId', 0),
                })

    # 我方信息
    my_team_info = []
    for p in my_team:
        my_team_info.append({
            'cell_id': p.get('cellId'),
            'summoner_id': p.get('summonerId', 0),
            'champion_id': p.get('championId', 0),
            'champion_pick_intent': p.get('championPickIntent', 0),
            'spell1_id': p.get('spell1Id', 0),
            'spell2_id': p.get('spell2Id', 0),
            'assigned_position': p.get('assignedPosition', ''),
            'summoner_name': p.get('summonerName', ''),
        })

    # 敌方信息（只显示已选的）
    their_team_info = []
    for p in their_team:
        their_team_info.append({
            'cell_id': p.get('cellId'),
            'champion_id': p.get('championId', 0),
            'champion_pick_intent': p.get('championPickIntent', 0),
            'spell1_id': p.get('spell1Id', 0),
            'spell2_id': p.get('spell2Id', 0),
            'assigned_position': p.get('assignedPosition', ''),
            'summoner_name': p.get('summonerName', ''),
        })

    # 双方 ban 位
    bans = data.get('bans', {})
    my_bans = bans.get('myTeamBans', [])
    their_bans = bans.get('theirTeamBans', [])

    # LCU returns timer values in milliseconds; normalize to seconds
    raw_timer = timer.get('adjustedTimeLeftInPhase', 0)
    raw_total = timer.get('totalTimeInPhase', 0)
    if raw_timer > 1000:
        raw_timer = int(raw_timer / 1000)
    if raw_total > 1000:
        raw_total = int(raw_total / 1000)

    return {
        'success': True,
        'phase': timer.get('phase', ''),
        'timer': raw_timer,
        'total_timer': raw_total,
        'local_cell_id': local_cell_id,
        'my_actions': local_actions,
        'my_team': my_team_info,
        'their_team': their_team_info,
        'my_bans': my_bans,
        'their_bans': their_bans,
    }


def perform_action(action_id, champion_id, completed=False, action_type='pick'):
    """
    在选人阶段执行操作（选人、ban人、预选）
    action_id: 从 get_champ_select_session 获取的 action id
    champion_id: 英雄数字ID
    completed: True=锁定, False=预选
    """
    payload = {
        'championId': champion_id,
        'completed': completed,
    }
    if action_type == 'ban':
        payload['type'] = 'ban'

    return lcu_post(
        f'/lol-champ-select/v1/session/actions/{action_id}',
        json_data=payload
    )


def hover_champion(action_id, champion_id):
    """预选/hover英雄（只在己方显示，不锁定）"""
    return perform_action(action_id, champion_id, completed=False)


def lock_champion(action_id, champion_id):
    """锁定英雄"""
    return perform_action(action_id, champion_id, completed=True)


def ban_champion(action_id, champion_id):
    """ban英雄"""
    return perform_action(action_id, champion_id, completed=True, action_type='ban')


def get_current_summoner():
    """获取当前召唤师信息"""
    result = lcu_get('/lol-summoner/v1/current-summoner')
    if result.get('success'):
        data = result['data']
        return {
            'success': True,
            'summoner_id': data.get('summonerId', 0),
            'name': data.get('displayName', ''),
            'level': data.get('summonerLevel', 0),
            'icon_id': data.get('profileIconId', 0),
        }
    return {'success': False}


def get_rune_pages():
    """获取所有符文页"""
    result = lcu_get('/lol-perks/v1/pages')
    if result.get('success'):
        return {'success': True, 'pages': result['data']}
    return {'success': False}


def set_current_rune_page(page_id):
    """激活指定符文页"""
    return lcu_post('/lol-perks/v1/currentpage', json_data={'id': page_id})


def create_rune_page(name, primary_style, sub_style, rune_ids, shard_ids):
    """
    创建符文页
    primary_style: 主系ID (如 8000=精密, 8100=主宰, 8200=巫术, etc.)
    sub_style: 副系ID
    rune_ids: [主系基石, 主系1, 主系2, 主系3, 副系1, 副系2]
    shard_ids: [进攻, 灵活, 防御] 如 [5008, 5008, 5001]
    """
    perk_ids = rune_ids + shard_ids
    payload = {
        'name': name,
        'primaryStyleId': primary_style,
        'subStyleId': sub_style,
        'selectedPerkIds': perk_ids,
        'current': True,
    }
    return lcu_post('/lol-perks/v1/pages', json_data=payload)


def delete_rune_page(page_id):
    """删除符文页"""
    return lcu_post('/lol-perks/v1/pages/' + str(page_id), json_data={})


def get_eog_stats():
    """获取对局结束统计"""
    result = lcu_get('/lol-end-of-game/v1/eog-stats-block')
    if result.get('success'):
        data = result['data']
        local_player = dict(data.get('localPlayer', {}))
        # try multiple possible locations for the 'won' field
        if 'won' not in local_player:
            lp_won = local_player.get('stats', {}).get('won', False)
            # fallback: check if the local player's team won
            if not lp_won:
                local_team_id = local_player.get('teamId')
                for team in data.get('teams', []):
                    if team.get('teamId') == local_team_id:
                        lp_won = team.get('won', False) or team.get('victory', False)
                        break
            local_player['won'] = lp_won
        return {
            'success': True,
            'game_id': data.get('gameId', 0),
            'game_mode': data.get('gameMode', ''),
            'game_duration': data.get('gameLength', 0),
            'teams': data.get('teams', []),
            'local_player': local_player,
        }
    return {'success': False, 'error': '暂无结算数据'}


def get_game_status_summary():
    """
    综合游戏状态摘要 — 前端轮询用
    返回简化的当前状态
    """
    if not is_connected():
        return {'connected': False, 'phase': 'Unknown', 'phase_cn': '未连接'}

    gameflow = get_gameflow_phase()
    summary = {
        'connected': True,
        'phase': gameflow['phase'],
        'phase_cn': gameflow['phase_cn'],
    }

    # 根据阶段补充信息
    if gameflow['phase'] == 'ReadyCheck':
        summary['ready_check'] = gameflow.get('data', {}).get('playerResponse', 'None')

    elif gameflow['phase'] == 'ChampSelect':
        cs = get_champ_select_session()
        if cs.get('success'):
            summary['champ_select'] = {
                'phase': cs['phase'],
                'timer': cs['timer'],
                'total_timer': cs['total_timer'],
                'has_action': len(cs.get('my_actions', [])) > 0,
                'my_team_size': len(cs.get('my_team', [])),
                'my_bans_count': len([b for b in cs.get('my_bans', []) if b]),
                'their_bans_count': len([b for b in cs.get('their_bans', []) if b]),
            }

    elif gameflow['phase'] == 'InProgress':
        # 获取游戏内信息
        chat_result = lcu_get('/lol-chat/v1/me')
        if chat_result.get('success'):
            summary['in_game'] = {
                'summoner_name': chat_result['data'].get('gameName', ''),
            }

    elif gameflow['phase'] == 'EndOfGame':
        eog = get_eog_stats()
        if eog.get('success'):
            local = eog.get('local_player', {})
            summary['end_of_game'] = {
                'game_id': eog.get('game_id'),
                'win': local.get('won', False),
                'kills': local.get('kills', 0),
                'deaths': local.get('deaths', 0),
                'assists': local.get('assists', 0),
            }

    return summary
