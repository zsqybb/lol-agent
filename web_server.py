"""
LOL数据助手 - Web服务器
Flask后端，提供API端点和静态资源
共享模块: shared.py (知识库、工具、RAG、AI配置)
"""
from flask import Flask, jsonify, request, send_from_directory
import json
import os
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='/static')

# ==================== 导入共享模块 ====================
from shared import (
    api_handler, logger as shared_logger,
    HAS_SKILL_SYSTEM, skill_dispatcher,
    HAS_CHAT_MEMORY, get_memory, delete_memory, new_session_id,
    HAS_LCU, find_lcu, is_connected, get_current_summoner, lcu_get, lcu_post, force_reconnect, get_lcu_status,
    HAS_RIOT_API, get_api_key, set_api_key,
    gameflow_manager_available, get_game_status_summary, accept_ready_check, get_champ_select_session,
    perform_action, get_rune_pages, set_current_rune_page, create_rune_page, delete_rune_page,
    get_gameflow_phase, get_eog_stats,
    call_spark_api, get_spark_config, RAG_MIN_SCORE,
    KNOWLEDGE_BASE, TOOLS,
    rag_search, format_rag_results,
    load_ai_config, SYSTEM_PROMPT,
    parse_tool_call_from_message, execute_tool_calls, generate_ai_response,
    _check_gfm,
)

# ==================== RAG & Skills API ====================

@app.route('/api/rag/search', methods=['GET'])
@api_handler
def api_rag_search():
    query = request.args.get('q', '')
    if not query:
        return jsonify({"success": False, "error": "请输入查询内容"})
    results = rag_search(query)
    return jsonify({
        "success": True,
        "query": query,
        "results": results,
        "formatted_results": format_rag_results(results)
    })

@app.route('/api/skills/list', methods=['GET'])
def api_skills_list():
    if not HAS_SKILL_SYSTEM:
        return jsonify({"success": False, "error": "Skill系统未加载"})
    return jsonify({"success": True, "skills": skill_dispatcher.get_skill_info()})

@app.route('/api/tools/list', methods=['GET'])
def api_tools_list():
    return jsonify({"success": True, "tools": TOOLS})


# ==================== Riot API 集成 ====================

@app.route('/api/player', methods=['GET'])
def api_player():
    if not HAS_RIOT_API:
        return jsonify({"success": False, "error": "Riot API模块未加载"})

    game_name = request.args.get('name', '').strip()
    tag_line = request.args.get('tag_line', '').strip()
    platform = request.args.get('platform', 'kr')
    region = request.args.get('region', 'asia')

    if not game_name:
        return jsonify({"success": False, "error": "请输入游戏名"})

    if not tag_line:
        return search_players_by_name(game_name, platform, region)

    from riot_api_client import get_player_full_info
    result = get_player_full_info(game_name, tag_line, platform, region)
    if result.get("success"):
        result["fetch_time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        result = enhance_player_data(result)
    return jsonify(result)


def search_players_by_name(game_name, platform, region):
    common_tags = ["KR1", "KR2", "KR3", "CN1", "CN2", "SG2", "NA1", "EUW1", "EUNE1",
                   "JP1", "TW1", "TW2", "VN1", "TH1", "PH1", "ID1"]

    accounts = []
    seen_puuids = set()

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from riot_api_client import get_account_by_riot_id, get_player_full_info

    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_tag = {executor.submit(get_account_by_riot_id, game_name, tag): tag for tag in common_tags}
        for future in as_completed(future_to_tag):
            tag = future_to_tag[future]
            result = future.result()
            if result.get("success"):
                puuid = result.get("puuid")
                if puuid and puuid not in seen_puuids:
                    seen_puuids.add(puuid)
                    accounts.append({
                        "puuid": puuid,
                        "game_name": result.get("game_name", game_name),
                        "tag_line": tag
                    })

    if not accounts:
        return jsonify({"success": False, "error": "未找到玩家"})

    if len(accounts) == 1:
        account = accounts[0]
        result = get_player_full_info(account["game_name"], account["tag_line"], platform, region)
        if result.get("success"):
            result["fetch_time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            result = enhance_player_data(result)
        return jsonify(result)

    return jsonify({
        "success": True,
        "players": accounts,
        "total": len(accounts),
        "message": f"找到 {len(accounts)} 个同名玩家，请补充标签后查询"
    })


@app.route('/api/match/<match_id>', methods=['GET'])
def api_match_detail(match_id):
    if not HAS_RIOT_API:
        return jsonify({"success": False, "error": "Riot API模块未加载"})
    from riot_api_client import get_match_detail
    result = get_match_detail(match_id)
    return jsonify(result)


# ==================== 英雄数据API ====================

CHAMPIONS_DATA = None
CHAMPIONS_FILE = os.path.join(os.path.dirname(__file__), 'static', 'data', 'zh_CN', 'champion.json')
_CHAMPION_DETAIL_CACHE = {}
_MAX_CHAMPION_CACHE = 30


def load_champions_data():
    """加载英雄数据，缓存到CHAMPIONS_DATA（key=数字ID的映射格式）"""
    global CHAMPIONS_DATA
    if CHAMPIONS_DATA is None:
        try:
            with open(CHAMPIONS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                CHAMPIONS_DATA = {}
                for key, champ in data.get("data", {}).items():
                    CHAMPIONS_DATA[str(champ.get("key", ""))] = {
                        "name": champ.get("name", ""),
                        "id": champ.get("id", ""),
                        "title": champ.get("title", ""),
                        "image": f"{key}.png",
                        "tags": champ.get("tags", []),
                        "info": champ.get("info", {})
                    }
        except Exception as e:
            logger.error(f"加载英雄数据失败: {e}")
            CHAMPIONS_DATA = {}
    return CHAMPIONS_DATA


def enhance_player_data(data):
    """为玩家数据添加英雄名称和图标"""
    champions = load_champions_data()
    if not champions:
        return data

    champ_key_to_id = {}
    for champ_id, champ in champions.items():
        key = str(champ.get('key', ''))
        if key:
            champ_key_to_id[key] = champ_id

    if data.get('masteries'):
        for m in data['masteries']:
            cid = str(m.get('champion_id', ''))
            if cid in champ_key_to_id:
                champ = champions.get(champ_key_to_id[cid], {})
                m['champion_name'] = champ.get('name', '')
                m['champion_image'] = champ.get('image', '')

    if data.get('matches'):
        for match in data['matches']:
            for p in match.get('participants', []):
                cid = str(p.get('champion_id', ''))
                if cid in champ_key_to_id:
                    champ = champions.get(champ_key_to_id[cid], {})
                    p['champion_name'] = champ.get('name', '')
                    p['champion_image'] = champ.get('image', '')

    return data


@app.route('/api/champions', methods=['GET'])
def api_champions():
    champions = load_champions_data()
    result = [{**v, "key": int(k)} for k, v in champions.items()]
    return jsonify({"success": True, "champions": result})


@app.route('/api/champion/<champ_id>', methods=['GET'])
def api_champion(champ_id):
    if '..' in champ_id or '/' in champ_id or '\\' in champ_id:
        return jsonify({"success": False, "error": "非法的英雄ID"})
    if champ_id in _CHAMPION_DETAIL_CACHE:
        return jsonify({"success": True, "data": {champ_id: _CHAMPION_DETAIL_CACHE[champ_id]}})
    try:
        champion_dir = os.path.join(os.path.dirname(__file__), 'static', 'data', 'zh_CN', 'champion')
        file_path = os.path.join(champion_dir, f'{champ_id}.json')
        real_path = os.path.realpath(file_path)
        if not real_path.startswith(os.path.realpath(champion_dir)):
            return jsonify({"success": False, "error": "非法的英雄ID"})
        with open(real_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if len(_CHAMPION_DETAIL_CACHE) >= _MAX_CHAMPION_CACHE:
            oldest = next(iter(_CHAMPION_DETAIL_CACHE))
            del _CHAMPION_DETAIL_CACHE[oldest]
        _CHAMPION_DETAIL_CACHE[champ_id] = data
        return jsonify({"success": True, "data": {champ_id: data}})
    except FileNotFoundError:
        return jsonify({"success": False, "error": "英雄数据未找到"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/champions/with-build', methods=['GET'])
@api_handler
def api_champions_with_build():
    try:
        build_file = os.path.join(os.path.dirname(__file__), 'static', 'champion_builds.json')
        with open(build_file, 'r', encoding='utf-8') as f:
            builds = json.load(f)

        champions = load_champions_data()
        result = []

        for key, champ in champions.items():
            build = builds.get(champ["id"], {})
            result.append({
                "key": int(key),
                "id": champ["id"],
                "name": champ["name"],
                "title": champ["title"],
                "image": champ["image"],
                "roles": champ["tags"],
                "roles_cn": build.get("roles_cn", champ["tags"]),
                "tier": build.get("tier", 0),
                "tier_label": build.get("tier_label", ""),
                "rank": build.get("rank", 0),
                "win_rate": build.get("win_rate", 0),
                "pick_rate": build.get("pick_rate", 0),
                "ban_rate": build.get("ban_rate", 0),
                "kda": build.get("kda", 0),
                "difficulty": build.get("difficulty", 2),
                "main_position": build.get("main_position", ""),
                "positions": build.get("positions", [])
            })

        return jsonify({"success": True, "champions": result})
    except Exception as e:
        logger.error(f"加载英雄数据失败: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/champion-build/<champ_id>', methods=['GET'])
@api_handler
def api_champion_build(champ_id):
    try:
        build_file = os.path.join(os.path.dirname(__file__), 'static', 'champion_builds.json')
        with open(build_file, 'r', encoding='utf-8') as f:
            builds = json.load(f)

        build = builds.get(champ_id, {})
        if build:
            return jsonify({"success": True, "build": build})
        else:
            return jsonify({"success": False, "error": "暂无该英雄的构建数据"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ==================== 数据刷新 ====================

@app.route('/api/champions/refresh', methods=['POST'])
def api_refresh_champions():
    global CHAMPIONS_DATA
    try:
        from data_refresher import refresh_all, get_data_status
    except ImportError as e:
        return jsonify({"success": False, "error": f"刷新模块加载失败: {e}"})

    params = request.get_json(silent=True) or {}
    force = params.get('force', False)

    result = refresh_all(force_ddragon=force)
    if result.get('success'):
        CHAMPIONS_DATA = None
        _CHAMPION_DETAIL_CACHE.clear()
    return jsonify(result)


@app.route('/api/champions/refresh-status', methods=['GET'])
def api_refresh_status():
    try:
        from data_refresher import get_data_status
    except ImportError as e:
        return jsonify({"success": False, "error": str(e)})
    status = get_data_status()
    return jsonify({"success": True, **status})


# ==================== LCU API ====================

@app.route('/api/lcu/status', methods=['GET'])
def api_lcu_status():
    if not HAS_LCU:
        return jsonify({"success": False, "error": "LCU模块未加载"})
    result = get_lcu_status()
    return jsonify(result)


@app.route('/api/lcu/connect', methods=['GET'])
def api_lcu_connect():
    if not HAS_LCU:
        return jsonify({"success": False, "error": "LCU模块未加载"})
    result = find_lcu()
    if result.get("success"):
        return jsonify({"success": True, "message": "已连接"})
    return jsonify({"success": False, "error": result.get("error", "未找到LOL客户端")})


@app.route('/api/lcu/force-reconnect', methods=['GET'])
def api_lcu_force_reconnect():
    if not HAS_LCU:
        return jsonify({"success": False, "error": "LCU模块未加载"})
    result = force_reconnect()
    return jsonify(result)


@app.route('/api/lcu/current-summoner', methods=['GET'])
def api_lcu_current_summoner():
    if not HAS_LCU:
        return jsonify({"success": False, "error": "LCU模块未加载"})
    result = get_current_summoner()
    if result.get("success"):
        return jsonify({"success": True, "summoner": result})
    return jsonify({"success": False, "error": result.get("error", "获取失败")})


@app.route('/api/lcu/rank', methods=['GET'])
def api_lcu_rank():
    if not HAS_LCU:
        return jsonify({"success": False, "error": "LCU模块未加载"})
    result = lcu_get("/lol-ranked/v1/current-ranked-stats")
    if result.get("success"):
        return jsonify({"success": True, "rank": result.get("data", {})})
    return jsonify({"success": False, "error": result.get("error", "获取排位失败")})


@app.route('/api/lcu/wallet', methods=['GET'])
def api_lcu_wallet():
    if not HAS_LCU:
        return jsonify({"success": False, "error": "LCU模块未加载"})
    result = lcu_get("/lol-store/v1/wallet")
    if result.get("success"):
        data = result["data"]
        return jsonify({"success": True, "wallet": {
            "ip": data.get("ip", 0),
            "rp": data.get("rp", 0),
        }})
    return jsonify({"success": False, "error": result.get("error", "获取失败")})


@app.route('/api/lcu/champion-masteries', methods=['GET'])
def api_lcu_champion_masteries():
    if not HAS_LCU:
        return jsonify({"success": False, "error": "LCU模块未加载"})
    result = lcu_get("/lol-collections/v1/inventories/chest-eligibility")
    mastery_result = lcu_get("/lol-champion-mastery/v1/local-player/champion-mastery")
    if mastery_result.get("success"):
        masteries = []
        for m in mastery_result["data"][:15]:
            masteries.append({
                "champion_id": m.get("championId", 0),
                "champion_level": m.get("championLevel", 0),
                "champion_points": m.get("championPoints", 0),
                "tokens_earned": m.get("tokensEarned", 0),
                "chest_granted": m.get("chestGranted", False),
            })
        return jsonify({"success": True, "masteries": masteries})
    return jsonify({"success": False, "error": mastery_result.get("error", "获取失败")})


@app.route('/api/lcu/match-history', methods=['GET'])
def api_lcu_match_history():
    if not HAS_LCU:
        return jsonify({"success": False, "error": "LCU模块未加载"})
    result = lcu_get("/lol-match-history/v1/products/lol/current-summoner/matches")
    if result.get("success"):
        matches = []
        for m in result["data"]["games"]["games"][:10]:
            participants = []
            for p in m.get("participants", []):
                participants.append({
                    "champion_id": p.get("championId", 0),
                    "summoner_name": p.get("summonerName", ""),
                    "team_id": p.get("teamId", 100),
                    "stats": p.get("stats", {}),
                })
            matches.append({
                "game_id": m.get("gameId", 0),
                "game_mode": m.get("gameMode", ""),
                "game_type": m.get("gameType", ""),
                "game_duration": m.get("gameDuration", 0),
                "game_creation": m.get("gameCreation", 0),
                "participants": participants,
            })
        return jsonify({"success": True, "matches": matches})
    return jsonify({"success": False, "error": result.get("error", "获取失败")})


@app.route('/api/lcu/full-info', methods=['GET'])
def api_lcu_full_info():
    if not HAS_LCU:
        return jsonify({"success": False, "error": "LCU模块未加载"})

    summoner_result = get_current_summoner()
    if not summoner_result.get("success"):
        return jsonify({"success": False, "error": summoner_result.get("error", "未登录")})

    from concurrent.futures import ThreadPoolExecutor, as_completed
    result = {"success": True, "summoner": summoner_result}

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            "rank": executor.submit(lcu_get, "/lol-ranked/v1/current-ranked-stats"),
            "mastery": executor.submit(lcu_get, "/lol-champion-mastery/v1/local-player/champion-mastery"),
            "wallet": executor.submit(lcu_get, "/lol-store/v1/wallet"),
            "matches": executor.submit(lcu_get, "/lol-match-history/v1/products/lol/current-summoner/matches"),
            "gameflow": executor.submit(lcu_get, "/lol-gameflow/v1/session"),
            "champion_rotation": executor.submit(lcu_get, "/lol-champion-rotation/v1/current-champion-rotation"),
            "loot": executor.submit(lcu_get, "/lol-loot/v1/player-loot"),
            "challenges": executor.submit(lcu_get, "/lol-challenges/v1/update-data"),
        }
        for key, future in futures.items():
            try:
                r = future.result(timeout=15)
                if r.get("success"):
                    data = r["data"]
                    if key == "mastery":
                        data = data[:8]
                    elif key == "matches":
                        data = data.get("games", {}).get("games", [])[:10]
                    result[key] = data
                else:
                    result[key] = None
            except Exception as e:
                logger.warning(f"LCU {key} 获取失败: {e}")
                result[key] = None

    # 注入游戏阶段中文名
    if result.get("gameflow"):
        phase = result["gameflow"].get("phase", "None")
        phase_map = {
            'None': '未运行', 'Lobby': '大厅', 'Matchmaking': '匹配中',
            'ReadyCheck': '等待接受', 'ChampSelect': '选人中', 'InProgress': '游戏中',
            'WaitingForStats': '等待结算', 'EndOfGame': '结算中', 'Reconnect': '重新连接',
        }
        result["gameflow"]["phase_cn"] = phase_map.get(phase, phase)

    # 增强数据：注入英雄名称和图标
    result = enhance_player_data(result)
    return jsonify(result)


# ==================== 游戏助手 API ====================

@app.route('/api/game/status', methods=['GET'])
def api_game_status():
    err = _check_gfm()
    if err: return err
    summary = get_game_status_summary()
    return jsonify({"success": True, **summary})


@app.route('/api/game/accept', methods=['POST'])
def api_game_accept():
    err = _check_gfm()
    if err: return err
    result = accept_ready_check()
    return jsonify(result)


@app.route('/api/game/champ-select', methods=['GET'])
def api_game_champ_select():
    err = _check_gfm()
    if err: return err
    result = get_champ_select_session()
    return jsonify(result)


@app.route('/api/game/champ-select/action', methods=['POST'])
def api_game_champ_action():
    err = _check_gfm()
    if err: return err
    data = request.get_json()
    action_id = data.get('action_id', 0)
    champion_id = data.get('champion_id', 0)
    action_type = data.get('type', 'pick')
    completed = data.get('completed', False)
    result = perform_action(action_id, champion_id, completed, action_type)
    return jsonify(result)


@app.route('/api/game/runes/apply', methods=['POST'])
def api_game_apply_runes():
    err = _check_gfm()
    if err: return err
    data = request.get_json()
    primary_style = data.get('primary_style', 8000)
    sub_style = data.get('sub_style', 8400)
    rune_ids = data.get('rune_ids', [])
    shard_ids = data.get('shard_ids', [5008, 5008, 5001])
    name = data.get('name', 'LOL助手推荐符文')

    result = create_rune_page(name, primary_style, sub_style, rune_ids, shard_ids)
    if result.get('success'):
        return jsonify({"success": True, "message": "符文页已应用"})
    return jsonify({"success": False, "error": result.get('error', '应用失败')})


@app.route('/api/game/recommendations', methods=['GET'])
def api_game_recommendations():
    position = request.args.get('position', '')
    if not position:
        return jsonify({"success": False, "error": "请指定位置"})

    pos_map = {'TOP': '上单', 'JUNGLE': '打野', 'MIDDLE': '中单', 'MID': '中单',
               'BOTTOM': 'ADC', 'ADC': 'ADC', 'UTILITY': '辅助', 'SUPPORT': '辅助'}
    role_cn = pos_map.get(position.upper(), position)

    try:
        build_file = os.path.join(os.path.dirname(__file__), 'static', 'champion_builds.json')
        with open(build_file, 'r', encoding='utf-8') as f:
            builds = json.load(f)
    except Exception:
        return jsonify({"success": False, "error": "加载英雄数据失败"})

    champions = load_champions_data()
    recommendations = []

    for champ_id, build in builds.items():
        positions = build.get('positions', [])
        matching = next((p for p in positions if p.get('name', '') == position.upper()), None)
        if not matching:
            continue
        tier = build.get('tier', 5)
        if tier > 3:
            continue
        champ_info = champions.get(str(build.get('key', '')), {})
        recommendations.append({
            "champion_id": build.get('key', 0),
            "champion_name": champ_info.get('name', champ_id),
            "champion_image": champ_info.get('image', ''),
            "tier": tier,
            "tier_label": build.get('tier_label', ''),
            "win_rate": matching.get('win_rate', 0),
            "pick_rate": matching.get('pick_rate', 0),
            "position": matching.get('name', ''),
            "position_cn": role_cn,
        })

    recommendations.sort(key=lambda x: (x['tier'], -x['win_rate']))
    return jsonify({"success": True, "recommendations": recommendations[:15], "position": position, "position_cn": role_cn})


@app.route('/api/game/eog-detail', methods=['GET'])
def api_game_eog_detail():
    err = _check_gfm()
    if err: return err
    try:
        stats = get_eog_stats()
        return jsonify({"success": True, "eog": stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/game/runes/pages', methods=['GET'])
def api_game_rune_pages():
    err = _check_gfm()
    if err: return err
    result = get_rune_pages()
    return jsonify(result)


@app.route('/api/game/ban-suggestions', methods=['GET'])
def api_game_ban_suggestions():
    position = request.args.get('position', '')
    try:
        build_file = os.path.join(os.path.dirname(__file__), 'static', 'champion_builds.json')
        with open(build_file, 'r', encoding='utf-8') as f:
            builds = json.load(f)
    except Exception:
        return jsonify({"success": False, "error": "加载数据失败"})

    champions = load_champions_data()
    suggestions = []

    for champ_id, build in builds.items():
        ban_rate = build.get('ban_rate', 0)
        if ban_rate <= 0:
            continue

        if position:
            positions = build.get('positions', [])
            matching = next((p for p in positions if p.get('name', '') == position.upper()), None)
            if not matching:
                continue

        champ_info = champions.get(str(build.get('key', '')), {})
        suggestions.append({
            "champion_id": build.get('key', 0),
            "champion_name": champ_info.get('name', champ_id),
            "champion_image": champ_info.get('image', ''),
            "ban_rate": ban_rate,
            "tier": build.get('tier', 5),
            "tier_label": build.get('tier_label', ''),
            "main_position": build.get('main_position', ''),
        })

    suggestions.sort(key=lambda x: -x['ban_rate'])
    return jsonify({"success": True, "suggestions": suggestions[:10]})


@app.route('/api/game/in-game-info', methods=['GET'])
def api_game_in_game_info():
    err = _check_gfm()
    if err: return err
    try:
        phase_data = get_gameflow_phase()
        if phase_data.get('phase') != 'InProgress':
            return jsonify({"success": False, "error": "当前不在游戏中"})

        game_data = phase_data.get('data', {})
        game_id = game_data.get('gameData', {}).get('gameId', 0)

        result = lcu_get(f"/lol-gameflow/v1/session")
        if not result.get("success"):
            return jsonify({"success": False, "error": "获取游戏数据失败"})

        game_session = result["data"].get("gameData", {})
        players = []
        for p in game_session.get("teamOne", []) + game_session.get("teamTwo", []):
            players.append({
                "summoner_name": p.get("summonerName", ""),
                "champion_id": p.get("championId", 0),
                "team": p.get("team", 0),
                "spell1_id": p.get("spell1Id", 0),
                "spell2_id": p.get("spell2Id", 0),
            })
        return jsonify({"success": True, "game_id": game_id, "players": players})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/game/honor', methods=['POST'])
def api_game_honor():
    err = _check_gfm()
    if err: return err
    data = request.get_json()
    summoner_id = data.get('summoner_id', '')
    honor_type = data.get('honor_type', 'HEART')

    if not summoner_id:
        return jsonify({"success": False, "error": "请指定要点赞的队友"})

    result = lcu_post("/lol-honor-v2/v1/honor-player", json_data={
        "summonerId": int(summoner_id),
        "honorType": honor_type,
    })
    if result.get("success") or result.get("status") == 204:
        return jsonify({"success": True, "message": "已点赞"})
    return jsonify({"success": False, "error": result.get("error", "点赞失败")})


@app.route('/api/game/honor-eligible', methods=['GET'])
def api_game_honor_eligible():
    err = _check_gfm()
    if err: return err
    result = lcu_get("/lol-honor-v2/v1/ballot")
    if result.get("success"):
        return jsonify({"success": True, "ballot": result.get("data", {})})
    return jsonify({"success": False, "error": result.get("error", "获取失败")})


# ==================== API密钥管理 ====================

@app.route('/api/api-key/test', methods=['POST'])
def api_key_test():
    if not HAS_RIOT_API:
        return jsonify({"success": False, "error": "Riot API模块未加载"})

    data = request.get_json()
    test_key = data.get('api_key', '').strip()

    if not test_key:
        return jsonify({"success": False, "error": "请输入要测试的API密钥"})

    old_key = get_api_key()
    set_api_key(test_key)

    try:
        from riot_api_client import get_account_by_riot_id
        result = get_account_by_riot_id("Test", "KR1")
        if result.get("success") or result.get("status") != 401:
            return jsonify({"success": True, "message": "API密钥有效"})
        else:
            return jsonify({"success": False, "error": result.get("error", "API密钥无效")})
    finally:
        set_api_key(old_key)


# ==================== AI对话 API ====================

@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.get_json()
    message = data.get('message', '')
    history = data.get('history', [])

    if not message:
        return jsonify({"success": False, "error": "请输入消息"})

    if HAS_SKILL_SYSTEM:
        rag_results = rag_search(message)
        rag_context = format_rag_results(rag_results)
        context = {'rag_context': rag_context}

        result = skill_dispatcher.dispatch(message, context)
        formatted = skill_dispatcher.format_result(result)

        return jsonify({
            "success": True,
            "response": formatted,
            "skill": result.get('skill_name', result.get('skill', '')),
            "skill_data": result,
            "rag_context": rag_context,
        })

    rag_results = rag_search(message)
    rag_context = format_rag_results(rag_results)
    tool_calls = parse_tool_call_from_message(message)
    tool_results = execute_tool_calls(tool_calls)
    ai_response = generate_ai_response(message, rag_context, tool_results)
    return jsonify({
        "success": True,
        "response": ai_response,
        "rag_context": rag_context,
        "tool_calls": tool_calls,
        "tool_results": tool_results
    })


@app.route('/api/ai-chat', methods=['POST'])
def api_ai_chat():
    data = request.get_json()
    message = data.get('message', '')
    history = data.get('history', [])
    mode = data.get('mode', 'ai')
    session_id = data.get('session_id', '')

    if not message or not message.strip():
        return jsonify({"success": False, "error": "请输入消息"})

    message = message.strip()

    memory_context = ''
    last_champ_id = ''
    last_champ_name = ''
    if HAS_CHAT_MEMORY and session_id:
        mem = get_memory(session_id, mode)
        memory_context = mem.get_context()
        last_champ_id, last_champ_name = mem.get_last_champ()

    if HAS_SKILL_SYSTEM:
        rag_results = rag_search(message)
        rag_context = format_rag_results(rag_results)
        context = {
            'rag_context': rag_context,
            'memory_context': memory_context,
            'last_champ_id': last_champ_id,
            'last_champ_name': last_champ_name,
            'mode': mode,
        }
        result = skill_dispatcher.dispatch(message, context)
        formatted = skill_dispatcher.format_result(result)

        if HAS_CHAT_MEMORY and session_id:
            mem.add_round(message, formatted,
                          champ_id=result.get('champion_id', ''),
                          champ_name=result.get('champion_name', ''))

        return jsonify({
            "success": True,
            "response": formatted,
            "skill": result.get('skill_name', result.get('skill', '')),
            "skill_data": result,
            "rag_context": rag_context,
            "memory_context": memory_context,
        })

    rag_results = rag_search(message)
    rag_context = format_rag_results(rag_results)
    tool_calls = parse_tool_call_from_message(message)
    tool_results = execute_tool_calls(tool_calls)
    ai_response = generate_ai_response(message, rag_context, tool_results)

    if HAS_CHAT_MEMORY and session_id:
        mem.add_round(message, ai_response)

    return jsonify({
        "success": True,
        "response": ai_response,
        "rag_context": rag_context,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "memory_context": memory_context,
    })


# ==================== 对话记忆管理 ====================

@app.route('/api/chat/session', methods=['POST'])
def api_chat_session():
    session_id = new_session_id() if HAS_CHAT_MEMORY else 'default'
    return jsonify({"success": True, "session_id": session_id})


@app.route('/api/chat/clear', methods=['POST'])
def api_chat_clear():
    data = request.get_json()
    session_id = data.get('session_id', '')
    mode = data.get('mode', 'ai')
    if HAS_CHAT_MEMORY and session_id:
        delete_memory(session_id, mode)
    return jsonify({"success": True, "message": "对话已清空"})


# ==================== AI配置管理 ====================

@app.route('/api/get-ai-config', methods=['GET'])
def api_get_ai_config():
    config = load_ai_config()
    return jsonify({"success": True, "config": config})


@app.route('/api/save-ai-config', methods=['POST'])
def api_save_ai_config():
    data = request.get_json()
    config = {
        'aiApiKey': data.get('aiApiKey', ''),
        'xinghuoApiSecret': data.get('xinghuoApiSecret', ''),
        'xinghuoAppId': data.get('xinghuoAppId', ''),
    }
    try:
        with open(os.path.join(os.path.dirname(__file__), 'ai_config.json'), 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return jsonify({"success": True, "message": "配置已保存"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/update-api-key', methods=['POST'])
def api_update_api_key():
    data = request.get_json()
    new_key = data.get('api_key', '').strip()
    if not new_key:
        return jsonify({"success": False, "error": "请输入API密钥"})
    set_api_key(new_key)
    return jsonify({"success": True, "message": "API密钥已更新"})


@app.route('/api/get-api-key', methods=['GET'])
def api_get_api_key():
    key = get_api_key()
    masked = key[:10] + '...' if len(key) > 10 else key
    return jsonify({"success": True, "api_key": masked, "has_key": bool(key)})


# ==================== 静态文件服务 ====================

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/style.css')
def style_css():
    return send_from_directory('.', 'style.css')

@app.route('/app.js')
def app_js():
    return send_from_directory('.', 'app.js')

@app.errorhandler(404)
def not_found(error):
    return jsonify({"success": False, "error": "资源未找到"}), 404

# ==================== 启动 ====================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
