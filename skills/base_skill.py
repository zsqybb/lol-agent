"""
Skill基类 - 定义统一接口
所有具体Skill必须继承此类并实现抽象方法
"""
import json
import os
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

LORE_BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lore')
LORE_INDEX_FILE = os.path.join(LORE_BASE_DIR, 'index.json')


class BaseSkill(ABC):
    name = ""
    description = ""
    keywords = []
    priority = 50

    @abstractmethod
    def should_trigger(self, message: str) -> bool:
        pass

    @abstractmethod
    def execute(self, message: str, context: dict = None) -> dict:
        pass

    @abstractmethod
    def format_result(self, result: dict) -> str:
        pass

    def _load_lore_index(self):
        try:
            with open(LORE_INDEX_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _load_champion_lore(self, champ_id: str) -> dict:
        filepath = os.path.join(LORE_BASE_DIR, 'champions', f'{champ_id}.json')
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _load_faction_lore(self, faction_slug: str) -> dict:
        filepath = os.path.join(LORE_BASE_DIR, 'factions', f'{faction_slug}.json')
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _find_champion(self, query: str, index_data: dict = None):
        if not index_data:
            index_data = self._load_lore_index()

        best_match = None
        best_score = 0

        for champ_id, info in index_data.items():
            if champ_id.startswith('faction_'):
                continue
            cn_name = info.get('name', '')
            cn_title = info.get('title', '')

            if query.lower() == cn_name.lower() or query.lower() == cn_title.lower() or query.lower() == champ_id.lower():
                return champ_id, info, 100

            name_score = self._simple_similarity(query, cn_name)
            title_score = self._simple_similarity(query, cn_title)
            id_score = self._simple_similarity(query.lower(), champ_id.lower())
            score = max(name_score, title_score, id_score)

            if score > best_score:
                best_score = score
                best_match = (champ_id, info, score)

        if best_match and best_score >= 60:
            return best_match
        return None

    def _find_faction(self, query: str, index_data: dict = None):
        if not index_data:
            index_data = self._load_lore_index()

        faction_cn_map = {
            '德玛西亚': 'demacia', '诺克萨斯': 'noxus', '弗雷尔卓德': 'freljord',
            '艾欧尼亚': 'ionia', '恕瑞玛': 'shurima', '祖安': 'zaun',
            '皮尔特沃夫': 'piltover', '皮城': 'piltover', '比尔吉沃特': 'bilgewater',
            '暗影岛': 'shadow-isles', '巨神峰': 'mount-targon', '班德尔城': 'bandle-city',
            '以绪塔尔': 'ixtal', '虚空之地': 'void', '虚空': 'void',
        }

        for cn_name, slug in faction_cn_map.items():
            if cn_name in query or slug in query.lower():
                key = f'faction_{slug}'
                if key in index_data:
                    return slug, index_data[key]

        return None

    @staticmethod
    def _simple_similarity(s1: str, s2: str) -> float:
        if not s1 or not s2:
            return 0
        s1, s2 = s1.lower(), s2.lower()
        if s1 == s2:
            return 100
        if s1 in s2 or s2 in s1:
            return 85
        common = sum(1 for c in s1 if c in s2)
        return (common / max(len(s1), len(s2))) * 100
