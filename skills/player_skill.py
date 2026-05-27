"""
玩家查询Skill - 查询玩家段位、战绩、比赛记录等
触发关键词：查询玩家、段位、战绩、比赛、KDA、胜率等
数据源：Riot API 实时查询
"""
import logging
from .base_skill import BaseSkill

logger = logging.getLogger(__name__)

try:
    from riot_api_client import get_player_full_info, get_api_key
    HAS_RIOT_API = True
except ImportError:
    HAS_RIOT_API = False


class PlayerSkill(BaseSkill):
    name = "player"
    description = "玩家数据查询：段位、战绩、比赛记录、KDA等"
    priority = 70

    strong_keywords = [
        '查询玩家', '玩家信息', '战绩', '比赛记录',
        '最近比赛', '对局', 'mastery', '熟练度',
        '召唤师',
    ]

    weak_keywords = [
        '段位', '排位', '胜率', 'kda', '分数', 'lp', '晋级', '段位赛',
    ]

    keywords = strong_keywords + weak_keywords

    def should_trigger(self, message: str) -> bool:
        if not HAS_RIOT_API:
            return False

        msg_lower = message.lower()

        for kw in self.strong_keywords:
            if kw in msg_lower:
                return True

        import re
        if re.search(r'\S+#\S+', message):
            return True

        if re.search(r'(\S+)的[段位战绩比赛]', message):
            return True

        for kw in self.weak_keywords:
            if kw in msg_lower:
                if re.search(r'\S+#\S+', message):
                    return True
                for sk in ['查询', '查看', '帮我查', '查一下', '我想查']:
                    if sk in msg_lower:
                        return True
                return False

        return False

    def _parse_player_query(self, message: str):
        import re

        match = re.search(r'(\S+?)#(\S+)', message)
        if match:
            return match.group(1), match.group(2)

        patterns = [
            r'查询[玩家召唤师]?\s*[:：]?\s*(\S+)',
            r'(\S+)的[段位战绩比赛]',
        ]
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return match.group(1), ''

        return None, None

    def execute(self, message: str, context: dict = None) -> dict:
        if not HAS_RIOT_API:
            return {
                'skill': self.name,
                'success': False,
                'error': 'Riot API模块未加载，无法查询玩家数据',
                'data': None,
            }

        game_name, tag_line = self._parse_player_query(message)

        if not game_name:
            return {
                'skill': self.name,
                'success': False,
                'error': '请提供玩家名称，格式：玩家名#标签（如 Selfless#KR11）',
                'data': None,
            }

        platform = context.get('platform', 'kr') if context else 'kr'
        region = context.get('region', 'asia') if context else 'asia'

        result = get_player_full_info(game_name, tag_line, platform, region)

        if not result.get('success'):
            return {
                'skill': self.name,
                'success': False,
                'error': result.get('error', '查询玩家数据失败'),
                'data': None,
            }

        return {
            'skill': self.name,
            'success': True,
            'target_type': 'player',
            'data': result,
        }

    def format_result(self, result: dict) -> str:
        if not result.get('success'):
            return result.get('error', '查询玩家数据失败')

        data = result.get('data', {})
        account = data.get('account', {})
        summoner = data.get('summoner', {})
        rank_data = data.get('rank', {})
        parts = []
        name = account.get('gameName', '') or summoner.get('name', '')
        parts.append(f"👤 **玩家：{name}**\n")

        if rank_data:
            rank_order = [
                ('solo', '单双排'),
                ('flex', '灵活排位'),
            ]
            tier_emoji = {'IRON': '🔩', 'BRONZE': '🥉', 'SILVER': '🥈', 'GOLD': '🥇', 'PLATINUM': '💎', 'EMERALD': '💚', 'DIAMOND': '💠', 'MASTER': '🔴', 'GRANDMASTER': '🔥', 'CHALLENGER': '👑'}
            for key, name_cn in rank_order:
                entry = rank_data.get(key, {})
                if entry and entry.get('tier'):
                    tier = entry.get('tier', '')
                    division = entry.get('division', '')
                    lp = entry.get('leaguePoints', 0)
                    wins = entry.get('wins', 0)
                    losses = entry.get('losses', 0)
                    total = wins + losses
                    wr = (wins / total * 100) if total > 0 else 0
                    t_emoji = tier_emoji.get(tier.upper(), '🎮')
                    wr_emoji = '🔥' if wr > 55 else '👍' if wr > 50 else '⚠️'
                    parts.append(f"{t_emoji} **{name_cn}**：{tier} {division} ({lp}LP)")
                    parts.append(f"  {wr_emoji} 战绩：{wins}胜 {losses}负 (胜率{wr:.1f}%)")
        else:
            parts.append("📋 暂无排位数据")

        matches = data.get('matches', [])
        if matches:
            parts.append(f"\n🎮 **最近{len(matches)}场比赛**")
            for m in matches[:5]:
                win = m.get('win', False)
                champ = m.get('champion_name_cn', '')
                kda = f"{m.get('kills', 0)}/{m.get('deaths', 0)}/{m.get('assists', 0)}"
                mode = m.get('game_mode', '')
                result_str = '✅胜' if win else '❌负'
                parts.append(f"  {result_str} | {champ} | KDA: {kda} | {mode}")

        return '\n'.join(parts)
