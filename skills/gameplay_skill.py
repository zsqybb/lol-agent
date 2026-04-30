"""
玩法检索Skill - 查询英雄出装、符文、技能、攻略等
触发关键词：出装、符文、天赋、技能、加点、胜率、怎么玩、对线、counter、连招等
数据源：champion_builds.json + Data Dragon champion.json
"""
import json
import os
import logging
from .base_skill import BaseSkill

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
BUILDS_FILE = os.path.join(BASE_DIR, 'static', 'champion_builds.json')
CHAMPIONS_FILE = os.path.join(BASE_DIR, 'static', 'data', 'zh_CN', 'champion.json')


class GameplaySkill(BaseSkill):
    name = "gameplay"
    description = "英雄玩法检索：出装、符文、技能加点、攻略、胜率等"
    priority = 60

    keywords = [
        '出装', '符文', '天赋', '技能', '加点', '胜率', 'ban率', '选率',
        '怎么玩', '怎么打', '攻略', '对线', 'counter', '克制', '连招',
        '主升', '副升', '核心装', '出门装', '鞋子', '装备',
        '玩法', 'tier', '强度',
        'kda',
    ]

    _builds = None
    _champions = None

    def _load_builds(self):
        if GameplaySkill._builds is None:
            try:
                with open(BUILDS_FILE, 'r', encoding='utf-8') as f:
                    GameplaySkill._builds = json.load(f)
            except Exception:
                GameplaySkill._builds = {}
        return GameplaySkill._builds

    def _load_champions(self):
        if GameplaySkill._champions is None:
            try:
                with open(CHAMPIONS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    GameplaySkill._champions = {}
                    for key, champ in data.get('data', {}).items():
                        GameplaySkill._champions[champ.get('name', '')] = champ
                        GameplaySkill._champions[key] = champ
                        title = champ.get('title', '')
                        if title and title not in GameplaySkill._champions:
                            GameplaySkill._champions[title] = champ
            except Exception:
                GameplaySkill._champions = {}
        return GameplaySkill._champions

    def should_trigger(self, message: str) -> bool:
        msg_lower = message.lower()
        for kw in self.keywords:
            if kw in msg_lower:
                return True
        return False

    def _find_hero(self, message: str):
        builds = self._load_builds()
        champions = self._load_champions()

        champ_data = None
        champ_id = None

        for name, champ in champions.items():
            if isinstance(champ.get('name'), str) and champ['name'] in message:
                champ_data = champ
                champ_id = champ.get('id', '')
                break
            if isinstance(champ.get('title'), str) and champ['title'] in message:
                champ_data = champ
                champ_id = champ.get('id', '')
                break

        if not champ_data:
            from fuzzywuzzy import fuzz, process
            all_titles = []
            title_to_id = {}
            for cid, c in champions.items():
                if isinstance(c, dict) and c.get('id'):
                    t = c.get('title', '')
                    n = c.get('name', '')
                    if t:
                        all_titles.append(t)
                        title_to_id[t] = c['id']
                    if n:
                        all_titles.append(n)
                        title_to_id[n] = c['id']
            if all_titles:
                match = process.extractOne(message, all_titles, scorer=fuzz.token_set_ratio)
                if match and match[1] > 75:
                    matched_name = match[0]
                    champ_id = title_to_id.get(matched_name, '')
                    if champ_id:
                        champ_data = champions.get(champ_id, champions.get(matched_name, {}))

        build_data = None
        if champ_id and champ_id in builds:
            build_data = builds[champ_id]

        return champ_id, champ_data, build_data

    def execute(self, message: str, context: dict = None) -> dict:
        champ_id, champ_data, build_data = self._find_hero(message)

        if not champ_id and context:
            gameplay_kw = ['出装', '符文', '天赋', '技能', '加点', '怎么玩', '攻略', '连招', '装备', '玩法', '胜率', 'ban率', '选率', 'kda']
            has_gameplay_kw = any(kw in message for kw in gameplay_kw)
            if has_gameplay_kw:
                last_champ_id = context.get('last_champ_id', '')
                last_champ_name = context.get('last_champ_name', '')
                if last_champ_id:
                    builds = self._load_builds()
                    champions = self._load_champions()
                    for name, champ in champions.items():
                        if champ.get('id', '') == last_champ_id:
                            champ_data = champ
                            champ_id = last_champ_id
                            build_data = builds.get(last_champ_id)
                            break

        if not champ_id:
            gameplay_kw = ['出装', '符文', '天赋', '技能', '加点', '怎么玩', '攻略', '连招', '装备', '玩法']
            has_gameplay_kw = any(kw in message for kw in gameplay_kw)
            if has_gameplay_kw:
                hint = f'⚠️ 未找到"{message}"中的英雄名称\n💡 请输入英雄名+玩法关键词，如"亚索出装"、"盖伦符文"、"盲僧怎么玩"'
            else:
                hint = f'⚔️ 这里是英雄问答\n💡 请输入英雄名称查询玩法攻略，如"亚索怎么玩"、"盲僧出装"、"阿狸符文"'
            return {
                'skill': self.name,
                'success': False,
                'error': hint,
                'data': None,
            }

        result_data = {
            'champ_id': champ_id,
        }

        if champ_data:
            result_data['name'] = champ_data.get('name', '')
            result_data['title'] = champ_data.get('title', '')
            result_data['tags'] = champ_data.get('tags', [])
            result_data['info'] = champ_data.get('info', {})
            passive = champ_data.get('passive', {})
            if passive:
                result_data['passive'] = {
                    'name': passive.get('name', ''),
                    'description': passive.get('description', ''),
                }
            spells = champ_data.get('spells', [])
            if spells:
                result_data['spells'] = []
                for sp in spells:
                    result_data['spells'].append({
                        'id': sp.get('id', ''),
                        'name': sp.get('name', ''),
                        'description': sp.get('description', ''),
                        'cooldownBurn': sp.get('cooldownBurn', ''),
                        'costBurn': sp.get('costBurn', ''),
                    })

        if build_data:
            result_data['build'] = build_data

        counter_kw = ['克制', 'counter', '怎么打', '对线', '打不过', '被克']
        need_counter = any(kw in message for kw in counter_kw)
        if need_counter:
            result_data['need_counter'] = True

        return {
            'skill': self.name,
            'success': True,
            'hero': result_data.get('name', champ_id),
            'data': result_data,
        }

    def format_result(self, result: dict) -> str:
        if not result.get('success'):
            return result.get('error', '未找到相关英雄信息')

        data = result.get('data', {})
        name = data.get('name', data.get('champ_id', ''))
        title = data.get('title', '')
        parts = [f"⚔️ **{title}({name})** 玩法攻略\n"]

        tags = data.get('tags', [])
        if tags:
            tag_cn = {'Fighter': '战士', 'Tank': '坦克', 'Mage': '法师', 'Assassin': '刺客', 'Marksman': '射手', 'Support': '辅助'}
            tag_emoji = {'Fighter': '⚔️', 'Tank': '🛡️', 'Mage': '🔮', 'Assassin': '🗡️', 'Marksman': '🏹', 'Support': '💚'}
            tag_strs = [f"{tag_emoji.get(t, '')}{tag_cn.get(t, t)}" for t in tags]
            parts.append(f"📍定位：{' '.join(tag_strs)}")



        passive = data.get('passive', {})
        if passive:
            parts.append(f"\n🎯 **被动 - {passive.get('name', '')}**")
            parts.append(f"  {passive.get('description', '')}")

        spells = data.get('spells', [])
        if spells:
            parts.append("\n🎮 **技能**")
            key_map = {'Q': 0, 'W': 1, 'E': 2, 'R': 3}
            key_emoji = {'Q': '🔵', 'W': '🟢', 'E': '🟡', 'R': '🔴'}
            for key, idx in key_map.items():
                if idx < len(spells):
                    sp = spells[idx]
                    cd = sp.get('cooldownBurn', '')
                    cd_str = f" (CD: {cd})" if cd else ""
                    parts.append(f"  {key_emoji.get(key, '')} **{key}** - {sp.get('name', '')}{cd_str}")
                    parts.append(f"    {sp.get('description', '')[:100]}")

        build = data.get('build', {})
        if build:
            tier = build.get('tier', 0)
            tier_label = build.get('tier_label', 'N/A')
            tier_emoji = {1: '🟢', 2: '🔵', 3: '🟡', 4: '🔴', 5: '🔴'}
            parts.append(f"\n📈 **强度评级**：{tier_emoji.get(tier, '⚪')} {tier_label} (Tier {tier})")

            wr = build.get('win_rate', 0)
            pr = build.get('pick_rate', 0)
            br = build.get('ban_rate', 0)
            wr_emoji = '🔥' if wr > 52 else '👍' if wr > 50 else '⚠️'
            parts.append(f"  {wr_emoji}胜率：{wr:.1f}% | 选率：{pr:.1f}% | Ban率：{br:.1f}%")

            kda = build.get('kda', 0)
            kda_emoji = '💪' if kda > 3 else '👍' if kda > 2 else '⚠️'
            main_pos = build.get('main_position', '')
            parts.append(f"  {kda_emoji}KDA：{kda:.2f} | 主位置：{main_pos}")

            roles_cn = build.get('roles_cn', [])
            if roles_cn:
                parts.append(f"  🗺️位置：{', '.join(roles_cn)}")

            runes = build.get('runes', {})
            if runes:
                parts.append("\n✨ **符文配置**")
                primary = runes.get('primary', '')
                primary_runes = runes.get('primary_runes', [])
                secondary = runes.get('secondary', '')
                secondary_runes = runes.get('secondary_runes', [])
                if primary:
                    parts.append(f"  🔹主系：**{primary}** — {', '.join(primary_runes) if primary_runes else ''}")
                if secondary:
                    parts.append(f"  🔸副系：**{secondary}** — {', '.join(secondary_runes) if secondary_runes else ''}")

            skills_str = build.get('skills', '')
            if skills_str:
                parts.append(f"\n🎯 **技能加点**：{skills_str}")

            builds_info = build.get('builds', {})
            if builds_info:
                parts.append("\n🎒 **出装推荐**")
                starts = builds_info.get('starts', [])
                core = builds_info.get('core', [])
                boots = builds_info.get('boots', [])
                situational = builds_info.get('situational', [])
                if starts:
                    parts.append(f"  🏠出门装：{', '.join(starts)}")
                if core:
                    parts.append(f"  ⭐核心装：{', '.join(core)}")
                if boots:
                    parts.append(f"  👢鞋子：{', '.join(boots)}")
                if situational:
                    parts.append(f"  🔧可选装：{', '.join(situational)}")

            skill_seq = build.get('skill_sequence', [])
            if skill_seq:
                parts.append(f"\n📝 **加点顺序**：{' → '.join(skill_seq)}")

        counter_info = data.get('counter_info', '')
        if counter_info:
            parts.append(f"\n\n🛡️ **克制攻略**\n{counter_info}")

        return '\n'.join(parts)
