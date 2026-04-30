"""
英雄联盟英雄背景故事爬虫
数据源：
1. LOL宇宙官网 yz.lol.qq.com - 详细传记、名言、短简介
2. Riot Data Dragon API - 基础lore(备用补充)、英雄英文名映射

输出文件: champion_lore.json
结构: { 英雄中文名: { name, title, slug, lore, short_bio, quote, quote_author, full_bio, faction, release_date } }
"""
import json
import os
import re
import time
import logging
import requests
from html import unescape
from html.parser import HTMLParser

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), 'champion_lore.json')

LOL_UNIVERSE_LIST_URL = 'https://yz.lol.qq.com/v1/zh_cn/search/index.json'
LOL_UNIVERSE_CHAMP_URL = 'https://yz.lol.qq.com/v1/zh_cn/champions/{slug}/index.json'
DDAGON_VERSIONS_URL = 'https://ddragon.leagueoflegends.com/api/versions.json'
DDAGON_CHAMP_URL = 'https://ddragon.leagueoflegends.com/cdn/{version}/data/zh_CN/champion/{id}.json'
DDAGON_LIST_URL = 'https://ddragon.leagueoflegends.com/cdn/{version}/data/zh_CN/champion.json'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}

REQUEST_TIMEOUT = 30
REQUEST_DELAY = 0.8


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._texts = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self._skip = False
        if tag in ('p', 'br', 'div', 'li'):
            self._texts.append('\n')

    def handle_data(self, data):
        if not self._skip:
            self._texts.append(data)

    def get_text(self):
        return ''.join(self._texts).strip()


def strip_html(html_str):
    if not html_str:
        return ''
    html_str = unescape(html_str)
    html_str = html_str.replace('\r\n', '\n').replace('\r', '\n')
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(html_str)
        result = extractor.get_text()
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result
    except Exception:
        html_str = re.sub(r'<br\s*/?>', '\n', html_str)
        html_str = re.sub(r'</p>', '\n', html_str)
        html_str = re.sub(r'<[^>]+>', '', html_str)
        return html_str.strip()


def fetch_json(url, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"Retry {attempt+1}/{retries} for {url}: {e}")
                time.sleep(2)
            else:
                logger.error(f"Failed after {retries} retries: {url} - {e}")
                return None


def get_ddragon_version():
    data = fetch_json(DDAGON_VERSIONS_URL)
    if data and len(data) > 0:
        version = data[0]
        logger.info(f"Data Dragon latest version: {version}")
        return version
    return '16.9.1'


def get_ddragon_champion_map(version):
    url = DDAGON_LIST_URL.format(version=version)
    data = fetch_json(url)
    if not data:
        return {}, {}

    name_to_id = {}
    id_to_data = {}
    for champ_id, champ in data.get('data', {}).items():
        cn_name = champ.get('name', '')
        name_to_id[cn_name] = champ_id
        id_to_data[champ_id] = {
            'id': champ_id,
            'name': cn_name,
            'title': champ.get('title', ''),
            'key': champ.get('key', ''),
        }

    logger.info(f"Data Dragon: {len(name_to_id)} champions")
    return name_to_id, id_to_data


def get_ddragon_lore(version, champ_id):
    url = DDAGON_CHAMP_URL.format(version=version, id=champ_id)
    data = fetch_json(url)
    if not data:
        return None

    champ = data.get('data', {}).get(champ_id, {})
    return {
        'lore': champ.get('lore', ''),
        'blurb': champ.get('blurb', ''),
        'tags': champ.get('tags', []),
        'partype': champ.get('partype', ''),
        'info': champ.get('info', {}),
    }


def scrape_lol_universe_list():
    data = fetch_json(LOL_UNIVERSE_LIST_URL)
    if not data:
        return []

    champions = data.get('champions', [])
    logger.info(f"LOL Universe: {len(champions)} champions in list")
    return champions


def scrape_lol_universe_champion(slug):
    url = LOL_UNIVERSE_CHAMP_URL.format(slug=slug)
    data = fetch_json(url)
    if not data:
        return None

    champ = data.get('champion', {})
    bio = champ.get('biography', {})

    full_bio_html = bio.get('full', '')
    full_bio = strip_html(full_bio_html)

    short_bio_html = bio.get('short', '')
    short_bio = strip_html(short_bio_html)

    quote = bio.get('quote', '')
    quote_author = bio.get('quote-author', '')

    related_stories = []
    for story in champ.get('related-stories', []):
        related_stories.append({
            'title': story.get('title', ''),
            'slug': story.get('slug', ''),
            'url': f"https://universe.leagueoflegends.com/zh_CN/story/{story.get('slug', '')}/"
        })

    return {
        'name': champ.get('name', ''),
        'title': champ.get('title', ''),
        'slug': slug,
        'full_bio': full_bio,
        'short_bio': short_bio,
        'quote': quote,
        'quote_author': quote_author,
        'faction': champ.get('associated-faction-slug', ''),
        'release_date': champ.get('release-date', ''),
        'related_stories': related_stories,
    }


def main():
    logger.info("=" * 60)
    logger.info("英雄联盟英雄背景故事爬虫")
    logger.info("=" * 60)

    # 1. 获取Data Dragon版本和英雄映射
    version = get_ddragon_version()
    name_to_id, id_to_data = get_ddragon_champion_map(version)

    # 2. 获取LOL宇宙英雄列表
    universe_champs = scrape_lol_universe_list()
    if not universe_champs:
        logger.error("无法获取LOL宇宙英雄列表，退出")
        return

    # 3. 逐个爬取英雄背景故事
    lore_data = {}
    total = len(universe_champs)
    success = 0
    failed = 0

    for i, champ_info in enumerate(universe_champs):
        slug = champ_info.get('slug', '')
        cn_name = champ_info.get('name', '')

        logger.info(f"[{i+1}/{total}] {cn_name} (slug: {slug})")

        # 从LOL宇宙获取详细传记
        universe_data = scrape_lol_universe_champion(slug)

        if universe_data and universe_data.get('full_bio'):
            entry = {
                'name': universe_data.get('name', cn_name),
                'title': universe_data.get('title', ''),
                'slug': slug,
                'lore': universe_data.get('full_bio', ''),
                'short_bio': universe_data.get('short_bio', ''),
                'quote': universe_data.get('quote', ''),
                'quote_author': universe_data.get('quote_author', ''),
                'faction': universe_data.get('faction', ''),
                'release_date': universe_data.get('release_date', ''),
                'related_stories': universe_data.get('related_stories', []),
                'source': 'lol_universe',
            }
            lore_data[cn_name] = entry
            success += 1
            logger.info(f"  OK - lore length: {len(entry['lore'])} chars")
        else:
            # 尝试从Data Dragon获取基础lore
            champ_id = name_to_id.get(cn_name, '')
            if champ_id:
                dd_data = get_ddragon_lore(version, champ_id)
                if dd_data and dd_data.get('lore'):
                    entry = {
                        'name': cn_name,
                        'title': dd_data.get('title', champ_info.get('title', '')),
                        'slug': slug,
                        'lore': dd_data.get('lore', ''),
                        'short_bio': dd_data.get('blurb', ''),
                        'quote': '',
                        'quote_author': '',
                        'faction': champ_info.get('associated-faction-slug', ''),
                        'release_date': champ_info.get('release-date', ''),
                        'related_stories': [],
                        'tags': dd_data.get('tags', []),
                        'source': 'data_dragon',
                    }
                    lore_data[cn_name] = entry
                    success += 1
                    logger.info(f"  OK (Data Dragon fallback) - lore length: {len(entry['lore'])} chars")
                else:
                    failed += 1
                    logger.warning(f"  FAIL - no lore data from either source")
            else:
                failed += 1
                logger.warning(f"  FAIL - no Data Dragon mapping for {cn_name}")

        # 限速
        time.sleep(REQUEST_DELAY)

        # 每30个英雄自动保存
        if (i + 1) % 30 == 0:
            _save_lore(lore_data)
            logger.info(f"  [Auto-save] {i+1}/{total} champions saved")

    # 4. 最终保存
    _save_lore(lore_data)

    # 5. 统计
    logger.info("\n" + "=" * 60)
    logger.info(f"爬取完成!")
    logger.info(f"  成功: {success}")
    logger.info(f"  失败: {failed}")
    logger.info(f"  总计: {total}")
    logger.info(f"  输出: {OUTPUT_FILE}")

    # 按数据源统计
    universe_count = sum(1 for v in lore_data.values() if v.get('source') == 'lol_universe')
    ddragon_count = sum(1 for v in lore_data.values() if v.get('source') == 'data_dragon')
    logger.info(f"  LOL宇宙: {universe_count}")
    logger.info(f"  Data Dragon: {ddragon_count}")

    # 按阵营统计
    faction_counts = {}
    for v in lore_data.values():
        faction = v.get('faction', '未知')
        faction_counts[faction] = faction_counts.get(faction, 0) + 1
    logger.info("\n  阵营分布:")
    for faction, count in sorted(faction_counts.items(), key=lambda x: -x[1]):
        logger.info(f"    {faction or '未知'}: {count}")


def _save_lore(lore_data):
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(lore_data, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
