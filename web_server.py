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
    from lcu_connect import find_lcu, is_connected, get_current_summoner, lcu_get
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
    """RAG知识库检索"""
    results = []
    
    for hero_name, hero_data in KNOWLEDGE_BASE.get("heroes", {}).items():
        score = fuzz.token_set_ratio(query, hero_name)
        if score > 60:
            results.append({"type": "hero", "name": hero_name, "score": score, "data": hero_data})
    
    for item_name, item_data in KNOWLEDGE_BASE.get("items", {}).items():
        score = fuzz.token_set_ratio(query, item_name)
        if score > 60:
            results.append({"type": "item", "name": item_name, "score": score, "data": item_data})
    
    for strategy_name, strategy_data in KNOWLEDGE_BASE.get("strategies", {}).items():
        score = fuzz.token_set_ratio(query, strategy_name)
        if score > 60:
            results.append({"type": "strategy", "name": strategy_name, "score": score, "data": strategy_data})
    
    for question, answer in KNOWLEDGE_BASE.get("faq", {}).items():
        score = fuzz.token_set_ratio(query, question)
        if score > 60:
            results.append({"type": "faq", "name": question, "score": score, "data": {"answer": answer}})
    
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
    return jsonify({"success": True, "champions": list(champions.values())})

@app.route('/api/champion/<champ_id>', methods=['GET'])
def api_champion(champ_id):
    try:
        file_path = os.path.join(os.path.dirname(__file__), 'static', 'data', 'zh_CN', 'champion', f'{champ_id}.json')
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({"success": True, "data": {champ_id: data}})
    except FileNotFoundError:
        return jsonify({"success": False, "error": "英雄数据未找到"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/champions/with-build', methods=['GET'])
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

# ==================== LCU API ====================
@app.route('/api/lcu/status', methods=['GET'])
def api_lcu_status():
    if not HAS_LCU:
        return jsonify({"connected": False, "message": "LCU模块未加载"})
    connected = is_connected()
    return jsonify({"connected": connected, "message": "已连接" if connected else "未连接"})

@app.route('/api/lcu/connect', methods=['GET'])
def api_lcu_connect():
    if not HAS_LCU:
        return jsonify({"success": False, "error": "LCU模块未加载"})
    result = find_lcu()
    if result.get("success"):
        return jsonify({"success": True, "message": "连接成功", "port": result.get("port")})
    return jsonify({"success": False, "error": result.get("error", "连接失败")})

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

# ==================== API密钥管理 ====================
@app.route('/api/api-key', methods=['GET', 'POST'])
def api_key_management():
    if request.method == 'GET':
        return jsonify({"success": True, "api_key": get_api_key()[:10] + "..." if HAS_RIOT_API else "未加载"})
    
    if request.method == 'POST':
        data = request.get_json()
        new_key = data.get('api_key', '').strip()
        
        if not new_key:
            return jsonify({"success": False, "error": "请输入API密钥"})
        
        if not new_key.startswith('RGAPI-'):
            return jsonify({"success": False, "error": "无效的API密钥格式，应以RGAPI-开头"})
        
        set_api_key(new_key)
        return jsonify({"success": True, "message": "API密钥更新成功"})

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
import requests as _requests

SPARK_API_URL = 'https://spark-api-open.xf-yun.com/x2/chat/completions'
SPARK_MODEL = 'spark-x'

AI_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'ai_config.json')

def load_ai_config():
    try:
        with open(AI_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载AI配置失败: {e}")
        return {}

def call_spark_api(messages):
    config = load_ai_config()
    api_key = config.get('aiApiKey', '')
    api_secret = config.get('xinghuoApiSecret', '')
    if not api_key or not api_secret:
        logger.error("星火API配置缺失")
        return None
    try:
        headers = {
            'Authorization': f'Bearer {api_key}:{api_secret}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': SPARK_MODEL,
            'messages': messages,
            'stream': False,
        }
        resp = _requests.post(SPARK_API_URL, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            return content if content else None
        else:
            logger.error(f"星火API错误: {resp.status_code} {resp.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"星火API调用失败: {e}")
        return None

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

def generate_ai_response(message, rag_context="", tool_results=None):
    """生成AI回复"""
    tool_results = tool_results or []
    
    # 构建上下文消息
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
    
    # 尝试使用讯飞星火API
    response = call_spark_api([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ])
    if response:
        return response
    
    # 回退模式：基于RAG结果生成回复
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
@app.route('/api/ai-config', methods=['GET', 'POST'])
def api_ai_config():
    if request.method == 'GET':
        config = load_ai_config()
        return jsonify({"success": True, "config": {
            "aiApiKey": config.get("aiApiKey", "")[:6] + "..." if config.get("aiApiKey") else "",
            "xinghuoAppId": config.get("xinghuoAppId", ""),
            "xinghuoApiSecret": config.get("xinghuoApiSecret", "")[:6] + "..." if config.get("xinghuoApiSecret") else ""
        }})
    
    if request.method == 'POST':
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
            return jsonify({"success": True, "message": "AI配置更新成功"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

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
