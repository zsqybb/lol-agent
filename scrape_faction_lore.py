"""
爬取符文之地13个阵营/地区的完整历史
- 按地区分文件存储到 lore/factions/{faction_slug}.json
- 每个文件包含：地区名、描述、关联英雄、完整历史
- RAG检索时只加载目标地区的文件

数据源: 
  1. LOL宇宙官网 (yz.lol.qq.com) - 地区概述
  2. Fandom Wiki - 地区完整历史
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
FACTIONS_DIR = os.path.join(BASE_DIR, 'lore', 'factions')
LORE_INDEX_FILE = os.path.join(BASE_DIR, 'lore', 'index.json')

FANDOM_API = 'https://leagueoflegends.fandom.com/api.php'
UNIVERSE_SEARCH_URL = 'https://yz.lol.qq.com/v1/zh_cn/search/index.json'
FACTION_DETAIL_URL = 'https://yz.lol.qq.com/v1/zh_cn/factions/{slug}/index.json'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
}

FACTION_FANDOM_PAGES = {
    'demacia': 'Demacia',
    'noxus': 'Noxus',
    'freljord': 'Freljord',
    'ionia': 'Ionia',
    'shurima': 'Shurima',
    'zaun': 'Zaun',
    'piltover': 'Piltover',
    'bilgewater': 'Bilgewater',
    'shadow-isles': 'Shadow Isles',
    'mount-targon': 'Mount Targon',
    'bandle-city': 'Bandle City',
    'ixtal': 'Ixtal',
    'void': 'The Void',
}

FACTION_CN = {
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
}

REQUEST_DELAY = 1.5


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


def strip_html(html_str):
    if not html_str:
        return ''
    from html.parser import HTMLParser
    class _S(HTMLParser):
        def __init__(self):
            super().__init__()
            self.t = []
            self._skip = False
        def handle_starttag(self, tag, attrs):
            if tag in ('script', 'style'): self._skip = True
        def handle_endtag(self, tag):
            if tag in ('script', 'style'): self._skip = False
            if tag in ('p', 'br', 'div', 'li'): self.t.append('\n')
        def handle_data(self, d):
            if not self._skip: self.t.append(d)
    p = _S()
    p.feed(html_str)
    return ''.join(p.t).strip()


def fetch_json(url, params=None, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"Retry {attempt+1}: {e}")
                time.sleep(2)
            else:
                logger.error(f"Failed: {e}")
                return None


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


def extract_lore_sections(sections):
    lore_indices = []
    lore_keywords = ['lore', 'history', 'culture', 'government', 'military',
                     'relations', 'geography', 'economy', 'demographics',
                     'architecture', 'wildlife', 'trivia']
    skip_keywords = ['trivia', 'change log', 'references', 'see also', 'skins',
                     'gallery', 'development', 'patch']

    for s in sections:
        line = s.get('line', '').lower()
        index = s.get('index', '')
        if not index or not str(index).isdigit():
            continue
        if any(sk in line for sk in skip_keywords):
            continue
        lore_indices.append({
            'index': int(index),
            'title': s.get('line', ''),
        })

    return lore_indices


def scrape_faction_from_universe(slug):
    url = FACTION_DETAIL_URL.format(slug=slug)
    data = fetch_json(url)
    if not data:
        return None
    faction = data.get('faction', {})
    overview = faction.get('overview', {})
    desc_html = overview.get('short', '') if isinstance(overview, dict) else ''
    desc = strip_html(desc_html)
    return {
        'name': faction.get('name', FACTION_CN.get(slug, slug)),
        'overview': desc,
    }


def scrape_faction_from_fandom(slug, page_title):
    sections = get_fandom_sections(page_title)
    if not sections:
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

    return {
        'sections': lore_parts,
        'total_chars': total_chars,
    }


def get_faction_champions(slug):
    data = fetch_json(UNIVERSE_SEARCH_URL)
    if not data:
        return []
    champs = []
    for c in data.get('champions', []):
        if c.get('associated-faction-slug') == slug:
            champs.append({
                'name': c.get('name', ''),
                'slug': c.get('slug', ''),
            })
    return champs


def main():
    logger.info("=" * 60)
    logger.info("符文之地阵营历史爬虫")
    logger.info("=" * 60)

    os.makedirs(FACTIONS_DIR, exist_ok=True)

    index_data = {}
    if os.path.exists(LORE_INDEX_FILE):
        with open(LORE_INDEX_FILE, 'r', encoding='utf-8') as f:
            index_data = json.load(f)

    factions = list(FACTION_FANDOM_PAGES.items())
    total = len(factions)
    success = 0

    for i, (slug, fandom_page) in enumerate(factions):
        cn_name = FACTION_CN.get(slug, slug)
        logger.info(f"[{i+1}/{total}] {cn_name} ({slug})")

        universe_data = scrape_faction_from_universe(slug)
        fandom_data = scrape_faction_from_fandom(slug, fandom_page)
        champions = get_faction_champions(slug)

        result = {
            'slug': slug,
            'name': cn_name,
            'fandom_page': fandom_page,
            'champions': champions,
            'champion_count': len(champions),
        }

        if universe_data:
            result['overview'] = universe_data.get('overview', '')

        if fandom_data:
            result['sections'] = fandom_data.get('sections', {})
            result['total_chars'] = fandom_data.get('total_chars', 0)
            result['source'] = 'fandom_wiki'
        elif universe_data:
            result['sections'] = {'Overview': result.get('overview', '')}
            result['total_chars'] = len(result.get('overview', ''))
            result['source'] = 'lol_universe'
        else:
            result['sections'] = {}
            result['total_chars'] = 0
            result['source'] = 'none'

        filepath = os.path.join(FACTIONS_DIR, f'{slug}.json')
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        index_data[f'faction_{slug}'] = {
            'name': cn_name,
            'faction': slug,
            'faction_cn': cn_name,
            'total_chars': result.get('total_chars', 0),
            'sections': list(result.get('sections', {}).keys()),
            'champion_count': len(champions),
            'file': f'factions/{slug}.json',
        }

        success += 1
        logger.info(f"  OK - {result.get('total_chars', 0)} chars, {len(champions)} champions, {len(result.get('sections', {}))} sections")

        time.sleep(REQUEST_DELAY)

    with open(LORE_INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    logger.info("\n" + "=" * 60)
    logger.info(f"Done! Success: {success}/{total}")
    logger.info(f"Output: {FACTIONS_DIR}")

    total_chars = sum(v.get('total_chars', 0) for k, v in index_data.items() if k.startswith('faction_'))
    logger.info(f"Total faction lore: {total_chars} chars ({total_chars // 1000}KB)")


if __name__ == '__main__':
    main()
