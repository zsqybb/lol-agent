"""
数据刷新模块 — 从Riot Data Dragon和OP.GG获取最新英雄数据
支持: 英雄基础数据更新、梯队排行榜、出装推荐
"""
import os
import json
import logging
import time
from datetime import datetime

import requests
import urllib3

logger = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATA_DIR = os.path.join(os.path.dirname(__file__), 'static', 'data', 'zh_CN')
CHAMPION_DIR = os.path.join(DATA_DIR, 'champion')
BUILDS_FILE = os.path.join(os.path.dirname(__file__), 'static', 'champion_builds.json')
DDRAGON_VERSION_URL = 'https://ddragon.leagueoflegends.com/api/versions.json'
DDRAGON_CHAMPION_URL = 'https://ddragon.leagueoflegends.com/cdn/{version}/data/zh_CN/champion.json'
DDRAGON_CHAMPION_DETAIL_URL = 'https://ddragon.leagueoflegends.com/cdn/{version}/data/zh_CN/champion/{id}.json'


def fetch_latest_version():
    """从Data Dragon获取最新游戏版本号"""
    try:
        resp = requests.get(DDRAGON_VERSION_URL, timeout=15)
        versions = resp.json()
        return versions[0] if versions else None
    except Exception as e:
        logger.error(f"获取版本号失败: {e}")
        return None


def download_champion_data(version):
    """下载最新版本的英雄基础数据 (champion.json)"""
    url = DDRAGON_CHAMPION_URL.format(version=version)
    try:
        resp = requests.get(url, timeout=30)
        data = resp.json()
        logger.info(f"下载 champion.json 成功: {version}, {len(data.get('data', {}))} 个英雄")
        return data
    except Exception as e:
        logger.error(f"下载 champion.json 失败: {e}")
        return None


def save_champion_data(data):
    """保存 champion.json 到本地"""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, 'champion.json')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"champion.json 已保存: {path}")
        return True
    except Exception as e:
        logger.error(f"保存 champion.json 失败: {e}")
        return False


def extract_individual_champions(data):
    """为每个英雄提取单独的JSON文件"""
    os.makedirs(CHAMPION_DIR, exist_ok=True)
    champions = data.get('data', {})
    saved = 0
    for champ_id, champ in champions.items():
        try:
            path = os.path.join(CHAMPION_DIR, f'{champ_id}.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(champ, f, ensure_ascii=False, indent=2)
            saved += 1
        except Exception as e:
            logger.error(f"保存 {champ_id}.json 失败: {e}")
    logger.info(f"已提取 {saved} 个独立英雄文件到 {CHAMPION_DIR}")
    return saved


def cleanup_old_champion_files(current_champions):
    """清理不在当前英雄列表中的旧英雄文件"""
    if not os.path.exists(CHAMPION_DIR):
        return 0
    removed = 0
    current_ids = set(current_champions.keys())
    for fname in os.listdir(CHAMPION_DIR):
        if fname.endswith('.json'):
            champ_id = fname[:-5]  # 去掉 .json
            if champ_id not in current_ids:
                try:
                    os.remove(os.path.join(CHAMPION_DIR, fname))
                    removed += 1
                    logger.info(f"已删除旧英雄文件: {fname}")
                except Exception as e:
                    logger.error(f"删除 {fname} 失败: {e}")
    if removed:
        logger.info(f"共删除 {removed} 个旧英雄文件")
    return removed


def fetch_opgg_tier_list():
    """
    从OP.GG获取当前版本梯队排行数据
    尝试多种方式获取: API → 网页解析 → 备用源
    返回: list[{champion_id, tier, tier_label, rank, win_rate, pick_rate, ban_rate, kda, positions}] 或 None
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    # 方式1: OP.GG 内部API
    urls_to_try = [
        'https://op.gg/api/v1.0/internal/bypass/champions?region=kr',
        'https://lol-web-api.op.gg/api/v1.0/internal/bypass/champions?region=kr',
        'https://op.gg/api/v1.0/internal/bypass/champions?region=kr&language=zh_CN',
    ]
    for url in urls_to_try:
        try:
            resp = requests.get(url, timeout=15, headers=headers, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and 'data' in data:
                    champions = data['data']
                elif isinstance(data, list):
                    champions = data
                else:
                    continue
                result = _parse_opgg_response(champions)
                if result and len(result) > 50:
                    logger.info(f"OP.GG API成功: {url}, 获取到 {len(result)} 个英雄数据")
                    return result
        except Exception as e:
            logger.debug(f"OP.GG API {url} 失败: {e}")
            continue

    # 方式2: U.GG 备用
    try:
        resp = requests.get('https://u.gg/json/champion-tier-list.json', timeout=15,
                            headers=headers, verify=False)
        if resp.status_code == 200:
            data = resp.json()
            result = _parse_ugg_response(data)
            if result and len(result) > 50:
                logger.info(f"U.GG API成功, 获取到 {len(result)} 个英雄数据")
                return result
    except Exception as e:
        logger.debug(f"U.GG API 失败: {e}")

    # 方式3: Lolalytics 备用
    try:
        resp = requests.get('https://lolalytics.com/lol/api/v2/tierlist?lane=default&region=all&patch=current',
                            timeout=15, headers=headers, verify=False)
        if resp.status_code == 200:
            data = resp.json()
            result = _parse_lolalytics_response(data)
            if result and len(result) > 50:
                logger.info(f"Lolalytics API成功, 获取到 {len(result)} 个英雄数据")
                return result
    except Exception as e:
        logger.debug(f"Lolalytics API 失败: {e}")

    logger.warning("所有外部梯队数据源均不可用")
    return None


def _parse_opgg_response(champions):
    """解析OP.GG API返回的冠军数据"""
    result = []
    rank = 0
    for item in champions:
        try:
            if isinstance(item, dict):
                rank += 1
                entry = {
                    'champion_id': str(item.get('id', item.get('champion_id', ''))),
                    'name': item.get('name', item.get('champion_name', '')),
                    'tier': item.get('tier', item.get('tier_rank', 3)),
                    'tier_label': f"T{item.get('tier', item.get('tier_rank', 3))}",
                    'rank': rank,
                    'win_rate': float(item.get('win_rate', item.get('winRate', 50))),
                    'pick_rate': float(item.get('pick_rate', item.get('pickRate', 5))),
                    'ban_rate': float(item.get('ban_rate', item.get('banRate', 3))),
                    'kda': float(item.get('kda', 3.0)),
                    'positions': item.get('positions', item.get('lanes', [])),
                    'main_position': item.get('main_position', item.get('lane', '')),
                }
                result.append(entry)
        except Exception:
            continue
    return result if result else None


def _parse_ugg_response(data):
    """解析U.GG API响应"""
    result = []
    items = data if isinstance(data, list) else data.get('data', data.get('champions', []))
    rank = 0
    for item in items:
        try:
            rank += 1
            entry = {
                'champion_id': str(item.get('championId', item.get('id', ''))),
                'name': item.get('name', ''),
                'tier': item.get('tier', 3),
                'tier_label': f"T{item.get('tier', 3)}",
                'rank': rank,
                'win_rate': float(item.get('winRate', 50)),
                'pick_rate': float(item.get('pickRate', 5)),
                'ban_rate': float(item.get('banRate', 3)),
                'kda': float(item.get('kda', 3.0)),
                'positions': item.get('roles', item.get('positions', [])),
                'main_position': item.get('mainRole', item.get('role', '')),
            }
            result.append(entry)
        except Exception:
            continue
    return result if result else None


def _parse_lolalytics_response(data):
    """解析 Lolalytics API 响应"""
    result = []
    items = data if isinstance(data, list) else data.get('data', data.get('champions', []))
    rank = 0
    for item in items:
        try:
            rank += 1
            entry = {
                'champion_id': str(item.get('id', item.get('championId', ''))),
                'name': item.get('name', ''),
                'tier': item.get('tier', 3),
                'tier_label': f"T{item.get('tier', 3)}",
                'rank': rank,
                'win_rate': float(item.get('winRate', 50)),
                'pick_rate': float(item.get('pickRate', 5)),
                'ban_rate': float(item.get('banRate', 3)),
                'kda': float(item.get('kda', 3.0)),
                'positions': item.get('roles', item.get('positions', [])),
                'main_position': item.get('mainRole', item.get('role', '')),
            }
            result.append(entry)
        except Exception:
            continue
    return result if result else None


def _load_champion_key_map():
    """Build id->key lookup map from champion.json (avoids circular import from web_server)"""
    champ_file = os.path.join(DATA_DIR, 'champion.json')
    name_to_build_key = {}
    try:
        with open(champ_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for key, champ in data.get('data', {}).items():
            name_to_build_key[champ.get('id', '')] = champ.get('key', '')
            name_to_build_key[champ.get('key', '')] = champ.get('key', '')
    except Exception as e:
        logger.error(f"加载 champion.json 失败: {e}")
    return name_to_build_key


def merge_tier_data(tier_list, build_data):
    """
    将最新梯队数据合并到 build_data 中
    - 更新已存在英雄的 tier/win_rate/pick_rate/ban_rate/kda/rank
    - 添加新英雄的条目（基础build为空）
    - 不删除任何英雄（由cleanup负责）
    """
    name_to_build_key = _load_champion_key_map()

    updated = 0
    for entry in tier_list:
        champ_id = entry.get('champion_id', '')
        # 尝试匹配 build_data 中的键
        build_key = name_to_build_key.get(champ_id, champ_id)

        if build_key in build_data:
            existing = build_data[build_key]
        else:
            existing = {
                'roles': entry.get('positions', []),
                'roles_cn': [],
                'difficulty': 5,
                'builds': {},
                'runes': {},
                'skills': '',
                'skill_sequence': [],
            }
            build_data[build_key] = existing

        # 更新梯队数据
        existing['tier'] = entry['tier']
        existing['tier_label'] = entry['tier_label']
        existing['rank'] = entry['rank']
        existing['win_rate'] = entry['win_rate']
        existing['pick_rate'] = entry['pick_rate']
        existing['ban_rate'] = entry['ban_rate']
        existing['kda'] = entry['kda']
        existing['main_position'] = entry.get('main_position', existing.get('main_position', ''))
        if entry.get('positions'):
            existing['positions'] = entry['positions']
        updated += 1

    return updated


def rewrite_builds_json(build_data, meta):
    """重写 champion_builds.json，按rank排序，添加_meta字段"""
    # 分离 _meta 和英雄数据
    if '_meta' in build_data:
        del build_data['_meta']

    # 按 rank 重新排序
    sorted_data = {}
    sorted_items = sorted(build_data.items(), key=lambda x: x[1].get('rank', 999))
    for k, v in sorted_items:
        sorted_data[k] = v

    sorted_data['_meta'] = meta

    try:
        with open(BUILDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(sorted_data, f, ensure_ascii=False, indent=2)
        logger.info(f"champion_builds.json 已更新: {len(sorted_data)-1} 个英雄, meta={meta}")
        return True
    except Exception as e:
        logger.error(f"保存 champion_builds.json 失败: {e}")
        return False


def cleanup_stale_builds(build_data, current_champions):
    """
    清理 build_data 中不再存在于当前 champion.json 中的英雄
    返回被删除的数量
    """
    # 建立合法英雄ID集合 (数字key)
    valid_keys = set()
    for champ in current_champions.get('data', {}).values():
        valid_keys.add(champ.get('key', ''))
        valid_keys.add(champ.get('id', ''))

    removed = 0
    stale_keys = [k for k in build_data.keys() if k != '_meta' and k not in valid_keys]
    for k in stale_keys:
        logger.info(f"清理过期build数据: {k} ({build_data[k].get('name', build_data[k].get('id', '?'))})")
        del build_data[k]
        removed += 1

    return removed


def refresh_all(force_ddragon=False):
    """
    执行完整数据刷新流程
    返回: {success, message, meta: {updated, patch, champions_count, ddragon_updated, tier_updated}}
    """
    result = {
        'success': False,
        'message': '',
        'meta': {
            'updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'patch': '',
            'champions_count': 0,
            'ddragon_updated': False,
            'tier_updated': False,
        }
    }

    # 1. Data Dragon 更新
    current_version = fetch_latest_version()
    if current_version:
        result['meta']['patch'] = current_version

        # 检查本地已有版本
        local_file = os.path.join(DATA_DIR, 'champion.json')
        need_update = force_ddragon
        if not need_update and os.path.exists(local_file):
            try:
                with open(local_file, 'r', encoding='utf-8') as f:
                    local = json.load(f)
                if local.get('version') == current_version:
                    logger.info(f"本地 champion.json 已是最新版本 {current_version}")
                    result['meta']['champions_count'] = len(local.get('data', {}))
                else:
                    need_update = True
            except Exception:
                need_update = True

        if need_update:
            champion_data = download_champion_data(current_version)
            if champion_data:
                if save_champion_data(champion_data):
                    extract_individual_champions(champion_data)
                    cleanup_old_champion_files(champion_data.get('data', {}))
                    result['meta']['champions_count'] = len(champion_data.get('data', {}))
                    result['meta']['ddragon_updated'] = True
                    logger.info(f"Data Dragon 更新完成: {current_version}")
                else:
                    result['message'] += '保存 champion.json 失败; '
            else:
                result['message'] += '下载 champion.json 失败; '
        else:
            result['message'] += 'champion.json 已最新; '
    else:
        result['message'] += '获取最新版本号失败; '
        # 使用本地数据
        try:
            with open(os.path.join(DATA_DIR, 'champion.json'), 'r', encoding='utf-8') as f:
                local = json.load(f)
            result['meta']['patch'] = local.get('version', '?')
            result['meta']['champions_count'] = len(local.get('data', {}))
        except Exception:
            result['meta']['champions_count'] = 0

    # 2. OP.GG 梯队数据更新
    tier_list = fetch_opgg_tier_list()
    if tier_list:
        # 加载现有 builds
        try:
            with open(BUILDS_FILE, 'r', encoding='utf-8') as f:
                build_data = json.load(f)
            if '_meta' in build_data:
                del build_data['_meta']
        except Exception:
            build_data = {}

        updated = merge_tier_data(tier_list, build_data)
        result['meta']['tier_updated'] = True

        # 加载当前champion数据用于清理
        try:
            with open(os.path.join(DATA_DIR, 'champion.json'), 'r', encoding='utf-8') as f:
                current_champs = json.load(f)
        except Exception:
            current_champs = {'data': {}}

        stale_removed = cleanup_stale_builds(build_data, current_champs)

        meta = {
            'updated': result['meta']['updated'],
            'patch': result['meta']['patch'],
            'source': 'op.gg',
            'champions_count': len(build_data),
        }
        rewrite_builds_json(build_data, meta)

        msg = f'梯队数据已更新: {updated} 个英雄刷新'
        if stale_removed:
            msg += f', 清理 {stale_removed} 个过期条目'
        result['message'] += msg
    else:
        result['message'] += '梯队数据获取失败 (外部API不可用)，基础数据可能已更新'

    result['success'] = True
    return result


def get_data_status():
    """获取当前数据状态，供前端显示"""
    status = {
        'patch': '?',
        'updated': '未知',
        'source': '无',
        'champions_count': 0,
        'age_days': -1,
    }

    # 检查 champion.json
    champ_file = os.path.join(DATA_DIR, 'champion.json')
    if os.path.exists(champ_file):
        try:
            with open(champ_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            status['patch'] = data.get('version', '?')
            status['champions_count'] = len(data.get('data', {}))
        except Exception:
            pass

    # 检查 champion_builds.json 的 _meta
    if os.path.exists(BUILDS_FILE):
        try:
            with open(BUILDS_FILE, 'r', encoding='utf-8') as f:
                build_data = json.load(f)
            meta = build_data.get('_meta', {})
            status['updated'] = meta.get('updated', '未知')
            status['source'] = meta.get('source', '无')
            if 'champions_count' not in status or status['champions_count'] == 0:
                status['champions_count'] = len(build_data) - (1 if '_meta' in build_data else 0)

            # 计算天数
            if status['updated'] != '未知':
                try:
                    updated_date = datetime.strptime(status['updated'], '%Y-%m-%d %H:%M')
                    status['age_days'] = (datetime.now() - updated_date).days
                except ValueError:
                    try:
                        updated_date = datetime.strptime(status['updated'], '%Y-%m-%d')
                        status['age_days'] = (datetime.now() - updated_date).days
                    except ValueError:
                        pass
        except Exception:
            pass

    return status
