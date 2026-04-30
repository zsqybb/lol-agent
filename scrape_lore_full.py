"""
从Fandom Wiki爬取英雄完整背景故事
- 按英雄分文件存储到 lore/champions/{hero_id}.json
- 每个文件包含：英雄名、地区标注、完整故事、人物关系
- RAG检索时只加载目标英雄的文件，节省token

数据源: leagueoflegends.fandom.com MediaWiki API
"""
import json
import os
import re
import time
import logging
import requests
from html.parser import HTMLParser

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(__file__)
CHAMPIONS_DIR = os.path.join(BASE_DIR, 'lore', 'champions')
FACTIONS_DIR = os.path.join(BASE_DIR, 'lore', 'factions')
LORE_INDEX_FILE = os.path.join(BASE_DIR, 'lore', 'index.json')

FANDOM_API = 'https://leagueoflegends.fandom.com/api.php'
LOL_UNIVERSE_LIST_URL = 'https://yz.lol.qq.com/v1/zh_cn/search/index.json'
DDAGON_LIST_URL = 'https://ddragon.leagueoflegends.com/cdn/{version}/data/zh_CN/champion.json'
DDAGON_VERSIONS_URL = 'https://ddragon.leagueoflegends.com/api/versions.json'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
}

FACTION_MAP = {
    'demacia': '德玛西亚',
    'noxus': '诺克萨斯',
    'freljord': '弗雷尔卓德',
    'ionia': '艾欧尼亚',
    'shurima': '恕瑞玛',
    'zaun': '祖安',
    'piltover': '皮尔特沃夫',
    'bilgewater': '比尔吉沃特',
    'shadow-isles': '暗影岛',
    'mount-targon': '巨神峰',
    'bandle-city': '班德尔城',
    'ixtal': '以绪塔尔',
    'void': '虚空之地',
    'unaffiliated': '无阵营',
}

REQUEST_DELAY = 1.2

FANDOM_PAGE_MAP = {
    'AurelionSol': 'Aurelion Sol',
    'Belveth': "Bel'Veth",
    'Chogath': "Cho'Gath",
    'DrMundo': 'Dr. Mundo',
    'JarvanIV': 'Jarvan IV',
    'Kaisa': "Kai'Sa",
    'Khazix': "Kha'Zix",
    'KogMaw': "Kog'Maw",
    'KSante': "K'Sante",
    'Leblanc': 'LeBlanc',
    'LeeSin': 'Lee Sin',
    'MasterYi': 'Master Yi',
    'MissFortune': 'Miss Fortune',
    'MonkeyKing': 'Wukong',
    'Nidalee': 'Nidalee',
    'RekSai': "Rek'Sai",
    'Renata': 'Renata Glasc',
    'TahmKench': 'Tahm Kench',
    'TwistedFate': 'Twisted Fate',
    'VelKoz': "Vel'Koz",
    'XinZhao': 'Xin Zhao',
}


class _WikiTextCleaner(HTMLParser):
    def __init__(self):
        super().__init__()
        self._texts = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'ref'):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'ref'):
            self._skip = False
        if tag in ('p', 'br', 'div', 'li', 'h2', 'h3'):
            self._texts.append('\n')

    def handle_data(self, data):
        if not self._skip:
            self._texts.append(data)

    def get_text(self):
        return ''.join(self._texts).strip()


def clean_wikitext(wikitext):
    if not wikitext:
        return ''
    text = wikitext
    text = re.sub(r'<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL)
    text = re.sub(r'<ref[^/]*/>', '', text)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'\[\[File:[^\]]*\]\]', '', text)
    text = re.sub(r'\[\[Image:[^\]]*\]\]', '', text)
    text = re.sub(r'\[\[([^|\]]*\|)?([^\]]*)\]\]', r'\2', text)
    text = re.sub(r"'''([^']*)'''", r'\1', text)
    text = re.sub(r"''([^']*)''", r'\1', text)
    text = re.sub(r'=====\s*(.*?)\s*=====', r'\n## \1\n', text)
    text = re.sub(r'====\s*(.*?)\s*====', r'\n## \1\n', text)
    text = re.sub(r'===\s*(.*?)\s*===', r'\n### \1\n', text)
    text = re.sub(r'==\s*(.*?)\s*==', r'\n## \1\n', text)
    text = re.sub(r'\{\{[^}]*\}\}', '', text)
    text = re.sub(r'\|[^|\n]*', '', text)
    text = re.sub(r'\{[^}]*\}', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def fetch_json(url, params=None, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"Retry {attempt+1}/{retries}: {e}")
                time.sleep(2)
            else:
                logger.error(f"Failed after {retries} retries: {e}")
                return None


def get_champion_name_map():
    version_data = fetch_json(DDAGON_VERSIONS_URL)
    version = version_data[0] if version_data else '16.9.1'
    data = fetch_json(DDAGON_LIST_URL.format(version=version))
    if not data:
        return {}, {}, {}
    name_to_id = {}
    id_to_name = {}
    id_to_title = {}
    for champ_id, champ in data.get('data', {}).items():
        cn_name = champ.get('name', '')
        cn_title = champ.get('title', '')
        name_to_id[cn_name] = champ_id
        id_to_name[champ_id] = cn_name
        id_to_title[champ_id] = cn_title
    logger.info(f"Data Dragon: {len(name_to_id)} champions")
    return name_to_id, id_to_name, id_to_title


def get_universe_faction_map():
    data = fetch_json(LOL_UNIVERSE_LIST_URL)
    if not data:
        return {}
    champ_faction = {}
    for champ in data.get('champions', []):
        slug = champ.get('slug', '')
        faction = champ.get('associated-faction-slug', '')
        cn_name = champ.get('name', '')
        champ_faction[cn_name] = faction
    return champ_faction


def get_fandom_sections(page_title):
    params = {
        'action': 'parse',
        'page': page_title,
        'prop': 'sections',
        'format': 'json',
    }
    data = fetch_json(FANDOM_API, params=params)
    if not data:
        return []
    return data.get('parse', {}).get('sections', [])


def get_fandom_section_text(page_title, section_index):
    params = {
        'action': 'parse',
        'page': page_title,
        'prop': 'wikitext',
        'format': 'json',
        'section': section_index,
    }
    data = fetch_json(FANDOM_API, params=params)
    if not data:
        return ''
    wikitext = data.get('parse', {}).get('wikitext', {}).get('*', '')
    return clean_wikitext(wikitext)


def get_fandom_full_page(page_title):
    params = {
        'action': 'parse',
        'page': page_title,
        'prop': 'wikitext',
        'format': 'json',
    }
    data = fetch_json(FANDOM_API, params=params)
    if not data:
        return ''
    wikitext = data.get('parse', {}).get('wikitext', {}).get('*', '')
    return clean_wikitext(wikitext)


def extract_lore_sections(sections):
    lore_section_indices = []
    lore_keywords = ['background', 'lore', 'biography', 'history', 'story', 'early life',
                     'relations', 'personality', 'appearance', 'abilities']
    skip_keywords = ['trivia', 'change log', 'references', 'see also', 'skins',
                     'chromas', 'development', 'patch', 'balance', 'bugs', 'gallery']

    for s in sections:
        line = s.get('line', '').lower()
        index = s.get('index', '')
        if not index or not str(index).isdigit():
            continue
        if any(sk in line for sk in skip_keywords):
            continue
        if any(lk in line for lk in lore_keywords):
            lore_section_indices.append({
                'index': int(index),
                'title': s.get('line', ''),
            })

    return lore_section_indices


def scrape_champion_lore(champ_id, cn_name, faction_slug):
    page_title = FANDOM_PAGE_MAP.get(champ_id, champ_id)
    sections = get_fandom_sections(page_title)

    if not sections:
        page_title_alt = page_title.replace('_', ' ')
        if page_title_alt != page_title:
            sections = get_fandom_sections(page_title_alt)
            if sections:
                page_title = page_title_alt

    if not sections:
        logger.warning(f"  No sections found for {champ_id}")
        return None

    lore_indices = extract_lore_sections(sections)

    lore_parts = {}
    total_chars = 0

    for sec in lore_indices:
        text = get_fandom_section_text(page_title, sec['index'])
        if text and len(text.strip()) > 20:
            cleaned = text.strip()
            lore_parts[sec['title']] = cleaned
            total_chars += len(cleaned)
        time.sleep(0.3)

    if not lore_parts:
        full_text = get_fandom_full_page(page_title)
        if full_text and len(full_text) > 100:
            lore_parts['Full Page'] = full_text
            total_chars = len(full_text)
        else:
            return None

    faction_cn = FACTION_MAP.get(faction_slug, faction_slug)

    result = {
        'id': champ_id,
        'name': cn_name,
        'faction': faction_slug,
        'faction_cn': faction_cn,
        'sections': lore_parts,
        'total_chars': total_chars,
        'source': 'fandom_wiki',
    }

    return result


def main():
    logger.info("=" * 60)
    logger.info("Fandom Wiki 英雄完整故事爬虫")
    logger.info("=" * 60)

    os.makedirs(CHAMPIONS_DIR, exist_ok=True)
    os.makedirs(FACTIONS_DIR, exist_ok=True)

    name_to_id, id_to_name, id_to_title = get_champion_name_map()
    champ_faction = get_universe_faction_map()

    universe_data = fetch_json(LOL_UNIVERSE_LIST_URL)
    universe_champs = {}
    if universe_data:
        for c in universe_data.get('champions', []):
            universe_champs[c.get('name', '')] = c

    champions = list(name_to_id.items())
    total = len(champions)
    success = 0
    failed = 0
    index_data = {}

    for i, (cn_name, champ_id) in enumerate(champions):
        faction_slug = champ_faction.get(cn_name, '')
        hero_title = id_to_title.get(champ_id, '')

        logger.info(f"[{i+1}/{total}] {cn_name}/{hero_title} ({champ_id}) - faction: {faction_slug}")

        result = scrape_champion_lore(champ_id, cn_name, faction_slug)

        if result:
            result['title'] = hero_title
            filepath = os.path.join(CHAMPIONS_DIR, f'{champ_id}.json')
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            faction_cn = FACTION_MAP.get(faction_slug, faction_slug)
            index_data[champ_id] = {
                'name': cn_name,
                'title': hero_title,
                'faction': faction_slug,
                'faction_cn': faction_cn,
                'total_chars': result['total_chars'],
                'sections': list(result['sections'].keys()),
                'file': f'champions/{champ_id}.json',
            }

            success += 1
            logger.info(f"  OK - {result['total_chars']} chars, {len(result['sections'])} sections")
        else:
            fallback = universe_champs.get(cn_name, {})
            bio = fallback.get('biography', {}) if isinstance(fallback, dict) else {}
            if bio:
                faction_cn = FACTION_MAP.get(faction_slug, faction_slug)
                fallback_result = {
                    'id': champ_id,
                    'name': cn_name,
                    'faction': faction_slug,
                    'faction_cn': faction_cn,
                    'sections': {'Biography': bio.get('full', '')},
                    'total_chars': len(bio.get('full', '')),
                    'source': 'lol_universe_fallback',
                }
                filepath = os.path.join(CHAMPIONS_DIR, f'{champ_id}.json')
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(fallback_result, f, ensure_ascii=False, indent=2)

                index_data[champ_id] = {
                    'name': cn_name,
                    'faction': faction_slug,
                    'faction_cn': faction_cn,
                    'total_chars': fallback_result['total_chars'],
                    'sections': list(fallback_result['sections'].keys()),
                    'file': f'champions/{champ_id}.json',
                }
                success += 1
                logger.info(f"  OK (universe fallback) - {fallback_result['total_chars']} chars")
            else:
                failed += 1
                logger.warning(f"  FAIL - no data")

        time.sleep(REQUEST_DELAY)

        if (i + 1) % 20 == 0:
            with open(LORE_INDEX_FILE, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
            logger.info(f"  [Auto-save] {i+1}/{total}")

    with open(LORE_INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    logger.info("\n" + "=" * 60)
    logger.info(f"Done! Success: {success}, Failed: {failed}, Total: {total}")
    logger.info(f"Output: {CHAMPIONS_DIR}")
    logger.info(f"Index: {LORE_INDEX_FILE}")

    total_chars = sum(v['total_chars'] for v in index_data.values())
    logger.info(f"Total lore text: {total_chars} chars ({total_chars // 1000}KB)")

    faction_counts = {}
    for v in index_data.values():
        fc = v.get('faction_cn', '未知')
        faction_counts[fc] = faction_counts.get(fc, 0) + 1
    logger.info("\nFaction distribution:")
    for fc, count in sorted(faction_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {fc}: {count}")


if __name__ == '__main__':
    main()
