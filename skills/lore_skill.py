import json
import os
import re
import logging
from .base_skill import BaseSkill

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
LORE_DIR = os.path.join(BASE_DIR, 'lore')
CHAMPIONS_DIR = os.path.join(LORE_DIR, 'champions')
FACTIONS_DIR = os.path.join(LORE_DIR, 'factions')
INDEX_FILE = os.path.join(LORE_DIR, 'index.json')


class LoreSkill(BaseSkill):
    name = "lore"
    description = "英雄/地区背景故事检索"
    priority = 55

    keywords = [
        '故事', '背景', '来历', '身世', '阵营', '关系', '传说', '宇宙',
        '符文之地', '符文大陆', '历史', '过去', '经历',
        '介绍', '什么人', '什么来头', '来自',
        '德玛西亚', '诺克萨斯', '弗雷尔卓德', '艾欧尼亚', '恕瑞玛',
        '祖安', '皮尔特沃夫', '皮城', '比尔吉沃特', '暗影岛',
        '巨神峰', '班德尔城', '以绪塔尔', '虚空',
    ]

    _faction_cn_to_slug = {
        '德玛西亚': 'demacia', '诺克萨斯': 'noxus', '弗雷尔卓德': 'freljord',
        '艾欧尼亚': 'ionia', '恕瑞玛': 'shurima', '祖安': 'zaun',
        '皮尔特沃夫': 'piltover', '皮城': 'piltover', '比尔吉沃特': 'bilgewater',
        '暗影岛': 'shadow-isles', '巨神峰': 'mount-targon', '班德尔城': 'bandle-city',
        '以绪塔尔': 'ixtal', '虚空之地': 'void', '虚空': 'void',
    }

    _index_data = None

    MAX_TOTAL_CHARS = 3000

    def _load_lore_index(self):
        if LoreSkill._index_data is None:
            try:
                with open(INDEX_FILE, 'r', encoding='utf-8') as f:
                    LoreSkill._index_data = json.load(f)
            except Exception:
                LoreSkill._index_data = {}
        return LoreSkill._index_data

    def _load_champion_lore(self, champ_id):
        filepath = os.path.join(CHAMPIONS_DIR, f'{champ_id}.json')
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def _load_faction_lore(self, slug):
        filepath = os.path.join(FACTIONS_DIR, f'{slug}.json')
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def _clean_html(self, text):
        if not text:
            return ''
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\[https?://[^\]]+\]', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def should_trigger(self, message: str) -> bool:
        msg_lower = message.lower()
        for kw in self.keywords:
            if kw in msg_lower:
                return True

        index_data = self._load_lore_index()
        for champ_id, info in index_data.items():
            if champ_id.startswith('faction_'):
                continue
            cn_name = info.get('name', '')
            cn_title = info.get('title', '')
            if (cn_name and cn_name in message) or (cn_title and cn_title in message):
                lore_kw = ['故事', '背景', '来历', '身世', '传说', '介绍', '什么人', '来自', '关系']
                for lk in lore_kw:
                    if lk in message:
                        return True
                break

        return False

    def _detect_target(self, message: str):
        index_data = self._load_lore_index()
        if not index_data:
            return None, None, None

        for cn_name, slug in self._faction_cn_to_slug.items():
            if cn_name in message:
                key = f'faction_{slug}'
                if key in index_data:
                    return 'faction', slug, index_data[key]

        faction_result = self._find_faction(message, index_data)
        if faction_result:
            return 'faction', faction_result[0], faction_result[1]

        champ_result = self._find_champion(message, index_data)
        if champ_result:
            return 'champion', champ_result[0], champ_result[1]

        return None, None, None

    def _find_champion(self, message, index_data):
        for champ_id, info in index_data.items():
            if champ_id.startswith('faction_'):
                continue
            cn_name = info.get('name', '')
            cn_title = info.get('title', '')
            if (cn_name and cn_name in message) or (cn_title and cn_title in message):
                return champ_id, info
        try:
            from fuzzywuzzy import fuzz, process
            all_names = []
            name_to_id = {}
            for champ_id, info in index_data.items():
                if champ_id.startswith('faction_'):
                    continue
                n = info.get('name', '')
                t = info.get('title', '')
                if n:
                    all_names.append(n)
                    name_to_id[n] = champ_id
                if t:
                    all_names.append(t)
                    name_to_id[t] = champ_id
            if all_names:
                match = process.extractOne(message, all_names, scorer=fuzz.token_set_ratio)
                if match and match[1] > 75:
                    champ_id = name_to_id[match[0]]
                    return champ_id, index_data[champ_id]
        except Exception:
            pass
        return None

    def _find_faction(self, message, index_data):
        for key, info in index_data.items():
            if not key.startswith('faction_'):
                continue
            cn_name = info.get('name', '')
            if cn_name and cn_name in message:
                slug = info.get('slug', key.replace('faction_', ''))
                return slug, info
        return None

    def execute(self, message: str, context: dict = None) -> dict:
        gameplay_kw = ['出装', '符文', '天赋', '技能', '加点', '怎么玩', '攻略', '连招', '装备', '玩法', '胜率']
        if any(kw in message for kw in gameplay_kw):
            return {
                'skill': self.name,
                'success': False,
                'error': f'⚠️ 您当前在故事问答模式\n💡 查询出装/符文/玩法请切换到「英雄问答」模式\n📖 如需查询背景故事，请输入如"亚索的背景故事"',
                'data': None,
            }

        target_type, target_id, index_info = self._detect_target(message)

        if not target_type:
            lore_kw = ['故事', '背景', '来历', '身世', '传说', '历史', '阵营', '介绍']
            has_lore_kw = any(kw in message for kw in lore_kw)
            if has_lore_kw:
                hint = f'⚠️ 未找到"{message}"中的英雄或地区名称\n💡 请输入名称+故事关键词，如"亚索的背景故事"、"德玛西亚的历史"'
            else:
                hint = f'📖 这里是故事问答\n💡 请输入英雄或地区名称查询背景故事，如"亚索的背景故事"、"德玛西亚的历史"、"阿狸的身世"'
            return {
                'skill': self.name,
                'success': False,
                'error': hint,
                'data': None,
            }

        if target_type == 'champion':
            return self._execute_champion(message, target_id, index_info)
        elif target_type == 'faction':
            return self._execute_faction(message, target_id, index_info)

    def _execute_champion(self, message, champ_id, index_info):
        lore_data = self._load_champion_lore(champ_id)
        if not lore_data:
            return {
                'skill': self.name,
                'success': False,
                'error': f'未找到{index_info.get("name", "")}的背景故事',
                'data': None,
            }

        cn_desc = lore_data.get('cn_description', '')
        if cn_desc:
            cn_desc = self._clean_html(cn_desc)
            if len(cn_desc) > self.MAX_TOTAL_CHARS:
                cn_desc = cn_desc[:self.MAX_TOTAL_CHARS] + '...'
            sections = {'背景故事': cn_desc}
        else:
            relevant = self._select_relevant_sections(message, lore_data.get('sections', {}))
            sections = {}
            total = 0
            for title, content in relevant.items():
                title = self._clean_html(title)
                content = self._clean_html(content)
                remaining = self.MAX_TOTAL_CHARS - total
                if remaining <= 0:
                    break
                if len(content) > remaining:
                    content = content[:remaining] + '...'
                sections[title] = content
                total += len(content)

        faction_cn = lore_data.get('faction_cn', '')

        return {
            'skill': self.name,
            'success': True,
            'target_type': 'champion',
            'hero': lore_data.get('name', ''),
            'hero_title': lore_data.get('title', ''),
            'faction': faction_cn,
            'data': {
                'name': lore_data.get('name', ''),
                'title': lore_data.get('title', ''),
                'faction': faction_cn,
                'sections': sections,
                'total_chars': sum(len(v) for v in sections.values()),
            },
        }

    def _execute_faction(self, message, faction_slug, index_info):
        lore_data = self._load_faction_lore(faction_slug)
        if not lore_data:
            return {
                'skill': self.name,
                'success': False,
                'error': f'未找到{index_info.get("name", "")}的历史',
                'data': None,
            }

        cn_desc = lore_data.get('cn_description', '')
        if cn_desc:
            cn_desc = self._clean_html(cn_desc)
            if len(cn_desc) > self.MAX_TOTAL_CHARS:
                cn_desc = cn_desc[:self.MAX_TOTAL_CHARS] + '...'
            sections = {'地区简介': cn_desc}
        else:
            relevant = self._select_relevant_sections(message, lore_data.get('sections', {}))
            sections = {}
            total = 0
            for title, content in relevant.items():
                title = self._clean_html(title)
                content = self._clean_html(content)
                remaining = self.MAX_TOTAL_CHARS - total
                if remaining <= 0:
                    break
                if len(content) > remaining:
                    content = content[:remaining] + '...'
                sections[title] = content
                total += len(content)

        champ_names = index_info.get('champions', [])

        return {
            'skill': self.name,
            'success': True,
            'target_type': 'faction',
            'faction': index_info.get('name', ''),
            'data': {
                'name': index_info.get('name', ''),
                'champions': champ_names,
                'sections': sections,
                'total_chars': sum(len(v) for v in sections.values()),
            },
        }

    def _select_relevant_sections(self, message: str, sections: dict) -> dict:
        if not sections:
            return {}

        query_hints = {
            '关系': ['relation', '关系', '人物'],
            '能力': ['abilit', '能力', '技能'],
            '外貌': ['appear', '外貌', '外观'],
            '性格': ['person', '性格', '个性'],
            '历史': ['histor', '历史', '过去', '经历'],
            '早期': ['early', '早期', '幼年', '童年'],
            '背景': ['background', '背景', '来历', '身世'],
            '传说': ['lore', '传说', '故事'],
            '介绍': ['background', 'biography', '介绍', '概述'],
        }

        relevant_keys = set()
        for hint, patterns in query_hints.items():
            if hint in message:
                for key in sections:
                    key_lower = key.lower()
                    if any(p in key_lower for p in patterns):
                        relevant_keys.add(key)

        if relevant_keys:
            return {k: v for k, v in sections.items() if k in relevant_keys}

        if len(sections) <= 3:
            return sections

        priority_patterns = ['background', 'biography', 'history', 'lore']
        result = {}
        for pp in priority_patterns:
            for key in sections:
                if pp in key.lower() and key not in result:
                    result[key] = sections[key]

        if not result:
            first_key = list(sections.keys())[0]
            result[first_key] = sections[first_key]

        return result

    def format_result(self, result: dict) -> str:
        if not result.get('success'):
            return result.get('error', '未找到相关背景故事')

        data = result.get('data', {})
        target_type = result.get('target_type', '')

        if target_type == 'champion':
            parts = [f"📖 **{data.get('title', '')}({data.get('name', '')})** 背景故事"]
            faction = data.get('faction', '')
            if faction:
                parts.append(f"🏰 所属阵营：{faction}")
            parts.append("")
            for section_title, content in data.get('sections', {}).items():
                parts.append(f"--- {section_title} ---")
                parts.append(content)
                parts.append("")
            parts.append("💡 想了解更多？可以问「XX的关系网」「XX的阵营介绍」")

        elif target_type == 'faction':
            parts = [f"🏰 **{data.get('name', '')}** 地区历史"]
            champs = [c for c in data.get('champions', []) if c and c.strip()]
            if champs:
                parts.append(f"⚔️ 关联英雄：{', '.join(champs[:15])}")
            parts.append("")
            for section_title, content in data.get('sections', {}).items():
                parts.append(f"--- {section_title} ---")
                parts.append(content)
                parts.append("")
            if champs:
                parts.append(f"💡 想了解某位英雄的故事？输入「{champs[0]}的背景故事」试试")

        return '\n'.join(parts)
