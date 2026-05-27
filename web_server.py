"""
LOL数据助手 - Web服务器
Flask后端，提供API端点和静态资源
集成Skill调度：玩法检索 / 背景故事 / 玩家查询 / 通用聊天
"""
from flask import Flask, jsonify, request, send_from_directory, send_file, Response
import json
import os
import logging
import re
from fuzzywuzzy import fuzz, process
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='/static')


def api_handler(f):
    """统一JSON错误处理装饰器"""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"API Error [{f.__name__}]: {e}")
            return jsonify({"success": False, "error": str(e)}), 400
    return wrapper


# ==================== Skill调度系统 ====================
try:
    from skills import SkillDispatcher
    skill_dispatcher = SkillDispatcher()
    HAS_SKILL_SYSTEM = True
    logger.info("Skill调度系统加载成功")
except Exception as e:
    HAS_SKILL_SYSTEM = False
    logger.warning(f"Skill调度系统加载失败: {e}")

try:
    from chat_memory import get_memory, delete_memory, new_session_id
    HAS_CHAT_MEMORY = True
    logger.info("对话记忆系统加载成功")
except Exception as e:
    HAS_CHAT_MEMORY = False
    logger.warning(f"对话记忆系统加载失败: {e}")

try:
    from lcu_connect import find_lcu, is_connected, get_current_summoner, lcu_get, lcu_post, force_reconnect, get_lcu_status
    HAS_LCU = True
    logger.info("LCU连接模块加载成功")
except Exception as e:
    HAS_LCU = False
    logger.warning(f"LCU连接模块加载失败: {e}")

# RAG知识库
KNOWLEDGE_BASE = {}
KNOWLEDGE_FILE = os.path.join(os.path.dirname(__file__), 'knowledge_base.json')

def load_knowledge_base():
    global KNOWLEDGE_BASE
    try:
        with open(KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
            KNOWLEDGE_BASE = json.load(f)
        logger.info("知识库加载成功")
    except Exception as e:
        logger.error(f"加载知识库失败: {e}")
        KNOWLEDGE_BASE = {}

load_knowledge_base()

# 工具定义
TOOLS = [
    {
        "name": "get_player_info",
        "description": "查询玩家信息，包括段位、熟练度、比赛记录等",
        "parameters": {
            "name": {"type": "string", "description": "玩家游戏名", "required": True},
            "tag": {"type": "string", "description": "玩家标签（如KR1）", "required": False}
        }
    },
    {
        "name": "get_match_detail",
        "description": "查询比赛详情，包括双方阵容、KDA等",
        "parameters": {
            "match_id": {"type": "string", "description": "比赛ID", "required": True}
        }
    },
    {
        "name": "get_champion_info",
        "description": "查询英雄信息，包括技能、定位、玩法技巧等",
        "parameters": {
            "champion_name": {"type": "string", "description": "英雄名称", "required": True}
        }
    },
    {
        "name": "get_item_info",
        "description": "查询装备信息，包括属性、合成路径等",
        "parameters": {
            "item_name": {"type": "string", "description": "装备名称", "required": True}
        }
    }
]

def rag_search(query, top_k=3):
    """RAG知识库检索（使用批量模糊匹配优化）"""
    results = []
    categories = [
        ("hero", "heroes", None),
        ("item", "items", None),
        ("strategy", "strategies", None),
        ("faq", "faq", lambda v: {"answer": v}),
    ]

    for cat_name, cat_key, wrap_fn in categories:
        cat_data = KNOWLEDGE_BASE.get(cat_key, {})
        if not cat_data:
            continue
        names = list(cat_data.keys())
        matches = process.extract(query, names, scorer=fuzz.token_set_ratio, limit=top_k)
        for name, score in matches:
            if score > RAG_MIN_SCORE:
                data = cat_data[name]
                results.append({
                    "type": cat_name,
                    "name": name,
                    "score": score,
                    "data": wrap_fn(data) if wrap_fn else data
                })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]

def format_rag_results(results):
    """格式化RAG结果"""
    if not results:
        return ""
    
    formatted = "【知识库检索结果】\n\n"
    for item in results:
        if item["type"] == "hero":
            formatted += f"🎮 **英雄：{item['name']}**\n"
            formatted += f"   称号：{item['data'].get('title', '')}\n"
            formatted += f"   定位：{', '.join(item['data'].get('role', []))}\n\n"
        elif item["type"] == "item":
            formatted += f"⚔️ **装备：{item['name']}**\n"
            formatted += f"   价格：{item['data'].get('price', 0)}金币\n\n"
        elif item["type"] == "strategy":
            formatted += f"📖 **策略：{item['name']}**\n"
            formatted += f"   说明：{item['data'].get('description', '')}\n\n"
        elif item["type"] == "faq":
            formatted += f"❓ **问答：{item['name']}**\n"
            formatted += f"   答案：{item['data'].get('answer', '')}\n\n"
    
    return formatted

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
try:
    from riot_api_client import get_player_full_info, get_match_detail, get_api_key, set_api_key
    HAS_RIOT_API = True
except ImportError:
    HAS_RIOT_API = False
    logger.warning("Riot API客户端未找到")

@app.route('/api/player', methods=['GET'])
def api_player():
    if not HAS_RIOT_API:
        return jsonify({"success": False, "error": "Riot API模块未加载"})
    
    game_name = request.args.get('name', '').strip()
    tag_line = request.args.get('tag_line', '').strip()  # 修正参数名
    platform = request.args.get('platform', 'kr')
    region = request.args.get('region', 'asia')
    
    if not game_name:
        return jsonify({"success": False, "error": "请输入游戏名"})
    
    # 如果没有标签，尝试搜索多个标签
    if not tag_line:
        return search_players_by_name(game_name, platform, region)
    
    result = get_player_full_info(game_name, tag_line, platform, region)
    if result.get("success"):
        result["fetch_time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        result = enhance_player_data(result)
    return jsonify(result)

def search_players_by_name(game_name, platform, region):
    """通过游戏名搜索玩家（并发优化版）"""
    common_tags = ["KR1", "KR2", "KR3", "CN1", "CN2", "SG2", "NA1", "EUW1", "EUNE1", "JP1", "TW1", "TW2", "VN1", "TH1", "PH1", "ID1"]
    
    # 步骤1：并发查询账号信息（只查PUUID，不查完整数据）
    accounts = []
    seen_puuids = set()
    
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from riot_api_client import get_account_by_riot_id
    
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
    
    # 步骤2：如果只有一个匹配，获取完整信息
    if len(accounts) == 1:
        account = accounts[0]
        result = get_player_full_info(account["game_name"], account["tag_line"], platform, region)
        if result.get("success"):
            result["fetch_time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            result = enhance_player_data(result)
        return jsonify(result)
    
    # 步骤3：如果多个匹配，只返回基本信息供用户选择
    return jsonify({
        "success": True,
        "players": accounts,
        "total": len(accounts),
        "message": f"找到 {len(accounts)} 个同名玩家，请补充标签后查询"
    })

def enhance_player_data(data):
    """增强玩家数据，添加英雄名称和图片"""
    champions = load_champions_data()
    
    # 增强熟练度数据
    for mastery in data.get("masteries", []):
        champ_id = mastery.get("champion_id", 0)
        champ = champions.get(str(champ_id))
        if champ:
            mastery["champion_name"] = champ.get("name", "")
            mastery["champion_image"] = champ.get("image", "")
    
    # 增强比赛数据
    for match in data.get("matches", []):
        for participant in match.get("participants", []):
            champ_id = participant.get("champion_id", 0)
            champ = champions.get(str(champ_id))
            if champ:
                participant["champion_name_cn"] = champ.get("name", "")
                participant["champion_image"] = champ.get("image", "")
    
    return data

@app.route('/api/match/<match_id>', methods=['GET'])
@api_handler
def api_match_detail(match_id):
    if not HAS_RIOT_API:
        return jsonify({"success": False, "error": "Riot API模块未加载"})
    
    region = request.args.get('region', 'asia')
    result = get_match_detail(match_id, region)
    
    if result.get("success"):
        champions = load_champions_data()
        for participant in result.get("participants", []):
            champ_id = participant.get("champion_id", 0)
            champ = champions.get(str(champ_id))
            if champ:
                participant["champion_name_cn"] = champ.get("name", "")
                participant["champion_image"] = champ.get("image", "")
    
    return jsonify(result)

# ==================== 英雄数据API ====================
CHAMPIONS_DATA = None
CHAMPIONS_FILE = os.path.join(os.path.dirname(__file__), 'static', 'data', 'zh_CN', 'champion.json')
_CHAMPION_DETAIL_CACHE = {}
_MAX_CHAMPION_CACHE = 30

def load_champions_data():
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

@app.route('/api/champions', methods=['GET'])
def api_champions():
    champions = load_champions_data()
    # 把 key 注入到每个英雄数据中，前端缓存用
    result = []
    for k, v in champions.items():
        v["key"] = int(k)
        result.append(v)
    return jsonify({"success": True, "champions": result})

@app.route('/api/champion/<champ_id>', methods=['GET'])
def api_champion(champ_id):
    # security: prevent path traversal
    if '..' in champ_id or '/' in champ_id or '\\' in champ_id:
        return jsonify({"success": False, "error": "非法的英雄ID"})
    # check cache first
    if champ_id in _CHAMPION_DETAIL_CACHE:
        return jsonify({"success": True, "data": {champ_id: _CHAMPION_DETAIL_CACHE[champ_id]}})
    try:
        file_path = os.path.join(os.path.dirname(__file__), 'static', 'data', 'zh_CN', 'champion', f'{champ_id}.json')
        # canonicalize and verify the resolved path stays within the champion dir
        champion_dir = os.path.join(os.path.dirname(__file__), 'static', 'data', 'zh_CN', 'champion')
        real_path = os.path.realpath(file_path)
        if not real_path.startswith(os.path.realpath(champion_dir)):
            return jsonify({"success": False, "error": "非法的英雄ID"})
        with open(real_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # cache with LRU eviction
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
    """刷新英雄数据: 从Data Dragon和OP.GG获取最新数据"""
    global CHAMPIONS_DATA
    try:
        from data_refresher import refresh_all, get_data_status
    except ImportError as e:
        return jsonify({"success": False, "error": f"刷新模块加载失败: {e}"})

    params = request.get_json(silent=True) or {}
    force = params.get('force', False)

    result = refresh_all(force_ddragon=force)
    if result.get('success'):
        CHAMPIONS_DATA = None  # 强制下次请求重新从磁盘加载
        _CHAMPION_DETAIL_CACHE.clear()
    return jsonify(result)

@app.route('/api/champions/refresh-status', methods=['GET'])
def api_refresh_status():
    """获取数据新鲜度状态"""
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
        return jsonify({"connected": False, "message": "LCU模块未加载"})
    status = get_lcu_status()
    connected = status.get("connected", False)
    health = status.get("health", "unknown")
    msg = "已连接" if connected and health == "ok" else "连接异常" if connected else "未连接"
    return jsonify({
        "connected": connected,
        "health": health,
        "message": msg,
        "port": status.get("port"),
    })

@app.route('/api/lcu/connect', methods=['GET'])
def api_lcu_connect():
    if not HAS_LCU:
        return jsonify({"success": False, "error": "LCU模块未加载"})
    result = find_lcu()
    if result.get("success"):
        return jsonify({
            "success": True,
            "message": f"连接成功 ({result.get('method', '')})",
            "port": result.get("port"),
            "method": result.get("method", ""),
        })
    return jsonify({"success": False, "error": result.get("error", "连接失败")})

@app.route('/api/lcu/force-reconnect', methods=['GET'])
def api_lcu_force_reconnect():
    if not HAS_LCU:
        return jsonify({"success": False, "error": "LCU模块未加载"})
    result = force_reconnect()
    if result.get("success"):
        return jsonify({
            "success": True,
            "message": f"重连成功 ({result.get('method', '')})",
            "port": result.get("port"),
            "method": result.get("method", ""),
        })
    return jsonify({"success": False, "error": result.get("error", "重连失败")})

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
    # 主端点：champion-mastery
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
    """一站式获取LCU全部数据：召唤师 + 排位 + 熟练度 + 钱包 + 比赛 + 游戏状态 + 周免 + 战利品 + 挑战"""
    if not HAS_LCU:
        return jsonify({"success": False, "error": "LCU模块未加载"})

    summoner_result = get_current_summoner()
    if not summoner_result.get("success"):
        return jsonify({"success": False, "error": summoner_result.get("error", "未登录")})

    from concurrent.futures import ThreadPoolExecutor, as_completed
    result = {"success": True, "summoner": summoner_result}

    # 并发请求所有LCU数据
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            "rank": executor.submit(lcu_get, "/lol-ranked/v1/current-ranked-stats"),
            "mastery": executor.submit(lcu_get, "/lol-champion-mastery/v1/local-player/champion-mastery"),
            "wallet": executor.submit(lcu_get, "/lol-store/v1/wallet"),
            "matches": executor.submit(lcu_get, "/lol-match-history/v1/products/lol/current-summoner/matches"),
            "gameflow": executor.submit(lcu_get, "/lol-gameflow/v1/session"),
            "collections": executor.submit(lcu_get, "/lol-collections/v1/inventories/chest-eligibility"),
            "champ_rotation": executor.submit(lcu_get, "/lol-champion-rotations/v1/champion-rotation"),
            "loot": executor.submit(lcu_get, "/lol-loot/v1/player-loot"),
            "challenges": executor.submit(lcu_get, "/lol-challenges/v1/summary"),
            "honor": executor.submit(lcu_get, "/lol-honor-v2/v1/ballot"),
            "stats": executor.submit(lcu_get, "/lol-career-stats/v1/summoner-games/total/453"),
        }

        # 排位数据
        rank_data = futures["rank"].result()
        if rank_data.get("success"):
            rd = rank_data["data"]
            rank_info = {}
            if rd.get("highestRankedEntry"):
                hre = rd["highestRankedEntry"]
                rank_info["solo"] = {"tier": hre.get("tier",""), "division": hre.get("division",""),
                                     "leaguePoints": hre.get("leaguePoints",0), "wins": hre.get("wins",0),
                                     "losses": hre.get("losses",0)}
            if rd.get("queues"):
                for q in rd["queues"]:
                    if q.get("queueType") == "RANKED_SOLO_5x5" and "solo" not in rank_info:
                        rank_info["solo"] = {"tier": q.get("tier",""), "division": q.get("division",""),
                                             "leaguePoints": q.get("leaguePoints",0), "wins": q.get("wins",0),
                                             "losses": q.get("losses",0)}
                    elif q.get("queueType") == "RANKED_FLEX_SR":
                        rank_info["flex"] = {"tier": q.get("tier",""), "division": q.get("division",""),
                                             "leaguePoints": q.get("leaguePoints",0), "wins": q.get("wins",0),
                                             "losses": q.get("losses",0)}
            result["rank"] = rank_info

        # 英雄熟练度
        mastery_data = futures["mastery"].result()
        if mastery_data.get("success"):
            masteries = []
            for m in mastery_data["data"][:15]:
                masteries.append({
                    "champion_id": m.get("championId", 0),
                    "champion_level": m.get("championLevel", 0),
                    "champion_points": m.get("championPoints", 0),
                    "last_played": m.get("lastPlayTime", 0),
                    "chest_granted": m.get("chestGranted", False),
                    "tokens_earned": m.get("tokensEarned", 0),
                })
            # 计算总熟练度
            total_mastery = sum(m.get("champion_points", 0) for m in mastery_data["data"])
            result["masteries"] = masteries
            result["total_mastery_score"] = total_mastery
            result["total_champions_played"] = len(mastery_data["data"])

        # 钱包
        wallet_data = futures["wallet"].result()
        if wallet_data.get("success"):
            result["wallet"] = {"ip": wallet_data["data"].get("ip", 0), "rp": wallet_data["data"].get("rp", 0)}

        # 最近比赛
        matches_data = futures["matches"].result()
        if matches_data.get("success"):
            lcu_matches = []
            for m in matches_data["data"]["games"]["games"][:10]:
                players = []
                for p in m.get("participants", []):
                    players.append({
                        "champion_id": p.get("championId", 0),
                        "summoner_name": p.get("summonerName", ""),
                        "team_id": p.get("teamId", 100),
                        "win": p.get("stats", {}).get("win", False),
                        "kills": p.get("stats", {}).get("kills", 0),
                        "deaths": p.get("stats", {}).get("deaths", 0),
                        "assists": p.get("stats", {}).get("assists", 0),
                        "item0": p.get("stats", {}).get("item0", 0),
                        "item6": p.get("stats", {}).get("item6", 0),
                    })
                lcu_matches.append({
                    "game_id": m.get("gameId", 0),
                    "game_mode": m.get("gameMode", ""),
                    "game_type": m.get("gameType", ""),
                    "game_duration": m.get("gameDuration", 0),
                    "game_creation": m.get("gameCreation", 0),
                    "participants": players,
                })
            result["matches"] = lcu_matches

        # 游戏状态
        gameflow_data = futures["gameflow"].result()
        if gameflow_data.get("success"):
            result["gameflow"] = gameflow_data["data"].get("phase", "None")

        # 宝箱资格
        collections_data = futures["collections"].result()
        if collections_data.get("success"):
            result["chest_eligibility"] = collections_data["data"]

        # 本周免费英雄
        rotation_data = futures["champ_rotation"].result()
        if rotation_data.get("success"):
            result["free_champion_ids"] = rotation_data["data"].get("freeChampionIds", [])
            result["free_champion_ids_new"] = rotation_data["data"].get("freeChampionIdsForNewPlayers", [])

        # 战利品
        loot_data = futures["loot"].result()
        if loot_data.get("success"):
            loots = []
            for item in loot_data["data"][:20]:
                loots.append({
                    "name": item.get("itemDesc", item.get("localizedDescription", "")),
                    "type": item.get("lootName", item.get("type", "")),
                    "count": item.get("count", 1),
                    "rarity": item.get("rarity", ""),
                })
            result["loot_count"] = len(loots)
            result["loot"] = loots[:10]

        # 挑战数据
        challenges_data = futures["challenges"].result()
        if challenges_data.get("success"):
            cd = challenges_data["data"]
            result["challenges"] = {
                "total_points": cd.get("totalPoints", {}).get("current", 0),
                "title": cd.get("title", ""),
                "crystal_level": cd.get("crystalLevel", ""),
            }

        # 荣誉等级
        honor_data = futures["honor"].result()
        if honor_data.get("success"):
            hd = honor_data["data"]
            result["honor"] = {
                "eligible": hd.get("eligibleToHonor", False),
                "games_played_since_last": hd.get("gamesPlayedSinceLastHonor", 0),
            }

    return jsonify(result)


# ==================== 游戏助手 API ====================
gameflow_manager_available = False
try:
    from gameflow_manager import (
        get_game_status_summary, accept_ready_check, get_champ_select_session,
        perform_action, get_current_summoner as gfm_current_summoner,
        get_rune_pages, set_current_rune_page, create_rune_page, delete_rune_page,
        get_gameflow_phase, get_eog_stats
    )
    gameflow_manager_available = True
    logger.info("游戏流程管理器加载成功")
except Exception as e:
    logger.warning(f"游戏流程管理器加载失败: {e}")


def _check_gfm():
    if not gameflow_manager_available:
        return jsonify({"success": False, "error": "游戏管理模块未加载"}), 503
    return None


@app.route('/api/game/status', methods=['GET'])
def api_game_status():
    err = _check_gfm()
    if err: return err  # noqa: E701
    summary = get_game_status_summary()
    return jsonify({"success": True, **summary})


@app.route('/api/game/accept', methods=['POST'])
def api_game_accept():
    err = _check_gfm()
    if err: return err  # noqa: E701
    result = accept_ready_check()
    return jsonify(result)


@app.route('/api/game/champ-select', methods=['GET'])
def api_game_champ_select():
    err = _check_gfm()
    if err: return err  # noqa: E701
    result = get_champ_select_session()
    return jsonify(result)


@app.route('/api/game/champ-select/action', methods=['POST'])
def api_game_champ_action():
    err = _check_gfm()
    if err: return err  # noqa: E701
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
    if err: return err  # noqa: E701
    data = request.get_json()
    primary_style = data.get('primary_style', 8000)
    sub_style = data.get('sub_style', 8400)
    rune_ids = data.get('rune_ids', [])
    shard_ids = data.get('shard_ids', [5008, 5008, 5001])
    name = data.get('name', 'LOL助手推荐符文')

    # 先创建符文页（设为当前）
    result = create_rune_page(name, primary_style, sub_style, rune_ids, shard_ids)
    if result.get('success'):
        return jsonify({"success": True, "message": "符文页已应用"})
    return jsonify({"success": False, "error": result.get('error', '应用失败')})


@app.route('/api/game/recommendations', methods=['GET'])
def api_game_recommendations():
    """根据当前选人位置推荐英雄（基于OP.GG韩服数据）"""
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
        if tier > 3:  # 只推荐T1-T3
            continue

        recommendations.append({
            'id': champ_id,
            'name': build.get('name', champ_id),
            'tier': tier,
            'tier_label': build.get('tier_label', ''),
            'win_rate': matching.get('win_rate', build.get('win_rate', 0)),
            'pick_rate': matching.get('pick_rate', build.get('pick_rate', 0)),
            'ban_rate': matching.get('ban_rate', build.get('ban_rate', 0)),
            'rank': build.get('rank', 99),
            'main_position': build.get('main_position', ''),
            'difficulty': build.get('difficulty', 2),
            'counters': build.get('counters', []),
            'synergies': build.get('synergies', []),
        })

    recommendations.sort(key=lambda x: x['rank'])
    return jsonify({"success": True, "position": role_cn, "recommendations": recommendations[:12]})


@app.route('/api/game/eog-detail', methods=['GET'])
def api_game_eog_detail():
    """获取对局结束的详细统计"""
    if not gameflow_manager_available:
        return jsonify({"success": False, "error": "游戏管理模块未加载"})
    if not is_connected():
        return jsonify({"success": False, "error": "LCU未连接"})

    eog = get_eog_stats()
    if not eog.get('success'):
        return jsonify({"success": False, "error": eog.get('error', '暂无结算数据')})

    # 获取本地玩家详细数据
    local = eog.get('local_player', {})
    teams = eog.get('teams', [])

    # 构建队伍数据
    my_team = []
    enemy_team = []
    local_team_id = local.get('teamId', 100)

    for team in teams:
        for player in team.get('players', []):
            pdata = {
                'summoner_name': player.get('summonerName', ''),
                'champion_id': player.get('championId', 0),
                'champion_name': player.get('championName', ''),
                'kills': player.get('kills', 0),
                'deaths': player.get('deaths', 0),
                'assists': player.get('assists', 0),
                'gold_earned': player.get('goldEarned', 0),
                'total_damage': player.get('totalDamageDealtToChampions', 0),
                'total_damage_taken': player.get('totalDamageTaken', 0),
                'vision_score': player.get('visionScore', 0),
                'minions_killed': player.get('totalMinionsKilled', 0),
                'cs_per_min': player.get('creepScorePerMinute', 0),
                'damage_per_gold': player.get('damagePerGold', 0),
                'items': [player.get(f'item{i}', 0) for i in range(6)],
                'spells': [player.get('spell1Id', 0), player.get('spell2Id', 0)],
                'keystone_id': player.get('keystoneId', 0),
                'is_me': player.get('summonerId') == local.get('summonerId'),
            }
            if player.get('teamId') == local_team_id:
                my_team.append(pdata)
            else:
                enemy_team.append(pdata)

    result = {
        'success': True,
        'game_id': eog.get('game_id'),
        'game_mode': eog.get('game_mode'),
        'game_duration': eog.get('game_duration'),
        'win': local.get('won', False),
        'my_team': my_team,
        'enemy_team': enemy_team,
        'local_player': {
            'kills': local.get('kills', 0),
            'deaths': local.get('deaths', 0),
            'assists': local.get('assists', 0),
            'kda': local.get('kda', 0),
            'champion_level': local.get('championLevel', 0),
            'gold_earned': local.get('goldEarned', 0),
            'total_damage': local.get('totalDamageDealtToChampions', 0),
            'vision_score': local.get('visionScore', 0),
            'cs_score': local.get('totalMinionsKilled', 0) or 0,
            'largest_multi_kill': local.get('largestMultiKill', 0),
            'wards_placed': local.get('wardsPlaced', 0),
            'items': [local.get(f'item{i}', 0) for i in range(6)],
            'spells': [local.get('spell1Id', 0), local.get('spell2Id', 0)],
        },
    }

    return jsonify(result)


@app.route('/api/game/runes/pages', methods=['GET'])
def api_game_rune_pages():
    err = _check_gfm()
    if err: return err  # noqa: E701
    result = get_rune_pages()
    return jsonify(result)


# ==================== 游戏助手增强 API ====================

@app.route('/api/game/ban-suggestions', methods=['GET'])
def api_game_ban_suggestions():
    """获取推荐禁用英雄（基于OP.GG韩服数据：高禁用率+高胜率）"""
    try:
        build_file = os.path.join(os.path.dirname(__file__), 'static', 'champion_builds.json')
        with open(build_file, 'r', encoding='utf-8') as f:
            builds = json.load(f)
    except Exception:
        return jsonify({"success": False, "error": "加载数据失败"})

    # 建立 string_id -> {key, name} 的映射
    champions = load_champions_data()
    id_to_key = {}
    for numeric_key, champ in champions.items():
        id_to_key[champ['id']] = {'key': int(numeric_key), 'name': champ['name']}

    suggestions = []
    for champ_id, build in builds.items():
        tier = build.get('tier', 5)
        ban_rate = build.get('ban_rate', 0)
        win_rate = build.get('win_rate', 0)
        if tier <= 2 or ban_rate >= 5:
            meta = id_to_key.get(champ_id, {})
            suggestions.append({
                'id': champ_id,
                'key': meta.get('key', 0),
                'name': meta.get('name', champ_id),
                'tier': tier,
                'tier_label': build.get('tier_label', ''),
                'ban_rate': ban_rate,
                'win_rate': win_rate,
                'rank': build.get('rank', 99),
                'positions': build.get('positions', []),
            })

    # 按禁用率降序，取前15
    suggestions.sort(key=lambda x: (-x['ban_rate'], x['rank']))
    return jsonify({"success": True, "suggestions": suggestions[:15]})


@app.route('/api/game/in-game-info', methods=['GET'])
def api_game_in_game_info():
    """获取游戏中实时信息"""
    if not gameflow_manager_available or not is_connected():
        return jsonify({"success": False, "error": "未连接"})

    # 游戏统计
    stats_result = lcu_get('/lol-gameflow/v1/session')
    if not stats_result.get('success'):
        return jsonify({"success": False, "error": "不在游戏中"})

    phase = stats_result['data'].get('phase', '')
    if phase != 'InProgress':
        return jsonify({"success": False, "error": "不在游戏中", "phase": phase})

    # 获取实时游戏数据
    from concurrent.futures import ThreadPoolExecutor
    result = {"success": True, "phase": phase}

    with ThreadPoolExecutor(max_workers=3) as executor:
        fut_chat = executor.submit(lcu_get, '/lol-chat/v1/me')
        fut_score = executor.submit(lcu_get, '/lol-gameflow/v1/session')

        chat_data = fut_chat.result()
        if chat_data.get('success'):
            result['summoner_name'] = chat_data['data'].get('gameName', '')

        score_data = fut_score.result()
        if score_data.get('success'):
            gd = score_data['data'].get('gameData', {})
            result['game_data'] = {
                'game_id': gd.get('gameId', 0),
                'game_mode': gd.get('queue', {}).get('name', ''),
                'map_id': gd.get('mapId', 0),
            }

    return jsonify(result)


@app.route('/api/game/honor', methods=['POST'])
def api_game_honor():
    """赛后点赞队友"""
    if not gameflow_manager_available or not is_connected():
        return jsonify({"success": False, "error": "未连接"})

    data = request.get_json()
    summoner_id = data.get('summoner_id', '')
    honor_type = data.get('honor_type', 'HEART')  # HEART/SHOTSHOT/GREATSHOT

    # 先获取可点赞列表
    ballot = lcu_get('/lol-honor-v2/v1/ballot')
    if ballot.get('success'):
        bd = ballot['data']
        eligible = bd.get('eligiblePlayers', bd.get('eligibleAllies', []))
        if not eligible:
            return jsonify({"success": False, "error": "没有可点赞的玩家"})

        # 如果没指定summoner_id，用第一个
        if not summoner_id and eligible:
            summoner_id = eligible[0].get('summonerId', '')

    if not summoner_id:
        return jsonify({"success": False, "error": "请指定要点赞的玩家"})

    result = lcu_post(f'/lol-honor-v2/v1/honor-player', json_data={
        'summonerId': summoner_id,
        'honorType': honor_type,
    })
    if result.get('success'):
        return jsonify({"success": True, "message": "点赞成功"})
    return jsonify({"success": False, "error": result.get('error', '点赞失败')})


@app.route('/api/game/honor-eligible', methods=['GET'])
def api_game_honor_eligible():
    """获取可点赞的队友列表"""
    if not gameflow_manager_available or not is_connected():
        return jsonify({"success": False, "error": "未连接"})

    ballot = lcu_get('/lol-honor-v2/v1/ballot')
    if ballot.get('success'):
        bd = ballot['data']
        eligible = bd.get('eligiblePlayers', bd.get('eligibleAllies', []))
        players = []
        for p in eligible:
            players.append({
                'summoner_id': p.get('summonerId', 0),
                'summoner_name': p.get('summonerName', p.get('gameName', '')),
                'champion_id': p.get('championId', 0),
            })
        return jsonify({"success": True, "players": players})

    return jsonify({"success": False, "error": "暂无数据"})


# ==================== API密钥管理 ====================
@app.route('/api/api-key/test', methods=['POST'])
def api_key_test():
    if not HAS_RIOT_API:
        return jsonify({"success": False, "error": "Riot API模块未加载"})
    
    data = request.get_json()
    test_key = data.get('api_key', '').strip()
    
    if not test_key:
        return jsonify({"success": False, "error": "请输入要测试的API密钥"})
    
    # 临时设置并测试
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

# ==================== 讯飞星火AI集成 ====================
from spark_client import call_spark_api
from config import get_spark_config, RAG_MIN_SCORE

AI_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'ai_config.json')

def load_ai_config():
    """优先从环境变量读取，回退到配置文件"""
    return get_spark_config()

SYSTEM_PROMPT = """你是LOL数据助手，一个专业的英雄联盟游戏顾问。你的职责是：
1. 回答关于英雄联盟的各种问题，包括英雄技能、装备、策略等
2. 根据知识库检索结果提供准确的游戏信息
3. 当用户查询玩家数据时，建议使用工具调用获取实时数据
4. 提供实用的游戏建议和上分攻略

注意事项：
- 优先使用知识库检索结果回答问题
- 如果知识库中没有相关信息，基于你的知识回答
- 对于实时数据（如玩家段位、比赛记录），建议用户通过网页查询功能获取
- 回答要简洁明了，重点突出"""

def parse_tool_call_from_message(message):
    """从用户消息中解析可能的工具调用意图"""
    tool_calls = []
    
    # 检测玩家查询意图
    player_pattern = r'查询[玩家|召唤师|信息|数据]?\s*[:：]?\s*(\S+?)(?:#(\S+))?$'
    match = re.search(player_pattern, message)
    if match:
        game_name = match.group(1)
        tag_line = match.group(2) or ""
        tool_calls.append({
            "name": "get_player_info",
            "arguments": {"name": game_name, "tag": tag_line}
        })
    
    # 检测英雄查询意图
    hero_keywords = ['技能', '出装', '符文', '攻略', '怎么玩', '怎么打', '玩法', '连招']
    for kw in hero_keywords:
        if kw in message:
            for hero_name in KNOWLEDGE_BASE.get("heroes", {}):
                if hero_name in message:
                    tool_calls.append({
                        "name": "get_champion_info",
                        "arguments": {"champion_name": hero_name}
                    })
                    break
            break
    
    # 检测装备查询意图
    item_keywords = ['装备', '出装', '物品', '买什么']
    for kw in item_keywords:
        if kw in message:
            for item_name in KNOWLEDGE_BASE.get("items", {}):
                if item_name in message:
                    tool_calls.append({
                        "name": "get_item_info",
                        "arguments": {"item_name": item_name}
                    })
                    break
            break
    
    return tool_calls

def execute_tool_calls(tool_calls):
    """执行工具调用，从知识库中查询英雄/装备信息"""
    tool_results = []
    for tc in tool_calls:
        tool_name = tc["name"]
        args = tc["arguments"]
        if tool_name == "get_champion_info":
            champ_name = args.get("champion_name", "")
            for hero_name, hero_data in KNOWLEDGE_BASE.get("heroes", {}).items():
                if hero_name == champ_name or fuzz.ratio(hero_name, champ_name) > 80:
                    result_str = f"英雄：{hero_data.get('name', '')}\n"
                    result_str += f"称号：{hero_data.get('title', '')}\n"
                    result_str += f"定位：{', '.join(hero_data.get('role', []))}\n"
                    result_str += f"技巧：{hero_data.get('tips', '')}\n"
                    skills = hero_data.get('skills', {})
                    for key, skill in skills.items():
                        result_str += f"  {key} - {skill.get('name', '')}: {skill.get('description', '')}\n"
                    tool_results.append({"name": tool_name, "result": result_str})
                    break
        elif tool_name == "get_item_info":
            item_name = args.get("item_name", "")
            for i_name, item_data in KNOWLEDGE_BASE.get("items", {}).items():
                if i_name == item_name or fuzz.ratio(i_name, item_name) > 80:
                    result_str = f"装备：{item_data.get('name', '')}\n"
                    result_str += f"类别：{item_data.get('category', '')}\n"
                    result_str += f"价格：{item_data.get('price', 0)}金币\n"
                    result_str += f"被动：{item_data.get('passive', '')}\n"
                    tool_results.append({"name": tool_name, "result": result_str})
                    break
    return tool_results


def generate_ai_response(message, rag_context="", tool_results=None):
    """生成AI回复"""
    tool_results = tool_results or []

    context_parts = []
    if rag_context:
        context_parts.append(f"【知识库信息】\n{rag_context}")
    if tool_results:
        for tr in tool_results:
            context_parts.append(f"【工具调用结果 - {tr['name']}】\n{tr['result']}")

    context_str = "\n\n".join(context_parts) if context_parts else ""

    user_content = message
    if context_str:
        user_content = f"参考信息：\n{context_str}\n\n用户问题：{message}"

    response = call_spark_api([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ])
    if response:
        return response

    if rag_context:
        return f"根据知识库信息：\n\n{rag_context}\n\n💡 以上是从知识库中检索到的相关信息。如需更详细的数据，请使用网页查询功能获取实时信息。"

    if tool_results:
        results_str = "\n".join([f"- {tr['name']}: {tr['result']}" for tr in tool_results])
        return f"工具调用结果：\n\n{results_str}"

    return "抱歉，我暂时无法回答这个问题。请尝试使用网页查询功能获取实时数据，或者询问关于英雄、装备、策略等具体问题。"

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
        }
        
        if mode == 'hero':
            result = skill_dispatcher.dispatch_skill(message, context, 'gameplay')
        elif mode == 'lore':
            result = skill_dispatcher.dispatch_skill(message, context, 'lore')
        else:
            result = skill_dispatcher.dispatch(message, context)
        
        formatted = skill_dispatcher.format_result(result)
        
        champ_id = result.get('data', {}).get('champ_id', '') if isinstance(result.get('data'), dict) else ''
        champ_name = result.get('data', {}).get('name', '') if isinstance(result.get('data'), dict) else ''
        if not champ_name and champ_id:
            champ_name = result.get('hero', '')
        
        if HAS_CHAT_MEMORY and session_id:
            mem = get_memory(session_id, mode)
            mem.add_round(message, formatted, champ_id, champ_name)
        
        return jsonify({
            "success": True,
            "reply": formatted,
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
        "reply": ai_response,
        "rag_context": rag_context,
        "tool_calls": tool_calls,
        "tool_results": tool_results
    })

# ==================== 对话记忆管理 ====================
@app.route('/api/chat/session', methods=['POST'])
def api_chat_session():
    if not HAS_CHAT_MEMORY:
        return jsonify({"success": False, "error": "记忆系统未加载"})
    sid = new_session_id()
    return jsonify({"success": True, "session_id": sid})

@app.route('/api/chat/clear', methods=['POST'])
def api_chat_clear():
    data = request.get_json()
    session_id = data.get('session_id', '')
    mode = data.get('mode', 'ai')
    if HAS_CHAT_MEMORY and session_id:
        delete_memory(session_id, mode)
    return jsonify({"success": True})

# ==================== AI配置管理 ====================
@app.route('/api/get-ai-config', methods=['GET'])
def api_get_ai_config():
    config = load_ai_config()
    return jsonify({
        "success": True,
        "config": {
            "aiApiKey": config.get("aiApiKey", ""),
            "xinghuoAppId": config.get("xinghuoAppId", ""),
            "xinghuoApiSecret": config.get("xinghuoApiSecret", "")
        }
    })

@app.route('/api/save-ai-config', methods=['POST'])
def api_save_ai_config():
    new_config = request.get_json()
    current_config = load_ai_config()
    
    if new_config.get("aiApiKey"):
        current_config["aiApiKey"] = new_config["aiApiKey"]
    if new_config.get("xinghuoAppId"):
        current_config["xinghuoAppId"] = new_config["xinghuoAppId"]
    if new_config.get("xinghuoApiSecret"):
        current_config["xinghuoApiSecret"] = new_config["xinghuoApiSecret"]
    
    try:
        with open(AI_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(current_config, f, indent=2, ensure_ascii=False)
        return jsonify({"success": True, "message": "AI配置保存成功"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/update-api-key', methods=['POST'])
def api_update_api_key():
    if not HAS_RIOT_API:
        return jsonify({"success": False, "error": "Riot API模块未加载"})
    
    data = request.get_json()
    new_key = data.get('apiKey', '').strip()
    
    if not new_key:
        return jsonify({"success": False, "error": "请输入API密钥"})
    
    if not new_key.startswith('RGAPI-'):
        return jsonify({"success": False, "error": "无效的API密钥格式，应以RGAPI-开头"})
    
    set_api_key(new_key)
    return jsonify({
        "success": True,
        "message": "API密钥更新成功",
        "currentKey": new_key[:10] + "..."
    })

@app.route('/api/get-api-key', methods=['GET'])
def api_get_api_key():
    if HAS_RIOT_API:
        return jsonify({"success": True, "currentKey": get_api_key()[:10] + "..."})
    return jsonify({"success": False, "error": "Riot API模块未加载"})

# ==================== 静态文件服务 ====================
@app.route('/')
def index():
    return send_file('index.html')

@app.route('/style.css')
def style_css():
    return send_file('style.css')

@app.route('/app.js')
def app_js():
    return send_file('app.js')

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
