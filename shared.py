"""
LOL数据助手 - 共享模块
提供所有Blueprint路由需要的：日志、装饰器、知识库、模块加载、工具函数
"""
from flask import jsonify
import json
import os
import logging
import re
import time
from fuzzywuzzy import fuzz, process

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== 统一错误处理装饰器 ====================

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

# ==================== 模块加载 ====================

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

try:
    from riot_api_client import get_player_full_info, get_match_detail, get_api_key, set_api_key
    HAS_RIOT_API = True
except ImportError:
    HAS_RIOT_API = False
    logger.warning("Riot API客户端未找到")

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
    gameflow_manager_available = False
    logger.warning(f"游戏流程管理器加载失败: {e}")

from spark_client import call_spark_api
from config import get_spark_config, RAG_MIN_SCORE

# ==================== 知识库 ====================

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

# ==================== 工具定义 ====================

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

# ==================== RAG检索 ====================

def rag_search(query, top_k=3):
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

# ==================== AI配置 ====================

AI_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'ai_config.json')

def load_ai_config():
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
    tool_calls = []
    player_pattern = r'查询[玩家|召唤师|信息|数据]?\s*[:：]?\s*(\S+?)(?:#(\S+))?$'
    match = re.search(player_pattern, message)
    if match:
        game_name = match.group(1)
        tag_line = match.group(2) or ""
        tool_calls.append({
            "name": "get_player_info",
            "arguments": {"name": game_name, "tag": tag_line}
        })
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
    tool_results = []
    for tc in tool_calls:
        tool_name = tc["name"]
        args = tc["arguments"]
        if tool_name == "get_champion_info":
            name = args.get("champion_name", "")
            hero_data = KNOWLEDGE_BASE.get("heroes", {}).get(name, {})
            if hero_data:
                tool_results.append({"tool": tool_name, "result": hero_data, "name": name})
        elif tool_name == "get_item_info":
            name = args.get("item_name", "")
            item_data = KNOWLEDGE_BASE.get("items", {}).get(name, {})
            if item_data:
                tool_results.append({"tool": tool_name, "result": item_data, "name": name})
        elif tool_name == "get_player_info":
            tool_results.append({"tool": tool_name, "result": "请使用网页查询功能获取实时玩家数据", "name": args.get("name", "")})
        elif tool_name == "get_match_detail":
            tool_results.append({"tool": tool_name, "result": "请使用网页查询功能获取比赛详情", "name": args.get("match_id", "")})
    return tool_results

def generate_ai_response(message, rag_context="", tool_results=None):
    try:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        context = ""
        if rag_context:
            context += f"\n{rag_context}"
        if tool_results:
            for tr in tool_results:
                context += f"\n[工具调用结果 - {tr['tool']}]: {json.dumps(tr['result'], ensure_ascii=False)}"
        if context:
            messages.append({"role": "system", "content": f"参考信息：\n{context}"})
        messages.append({"role": "user", "content": message})
        result = call_spark_api(messages, temperature=0.7)
        if result.get("success"):
            return result.get("content", "")
        return f"[AI服务暂时不可用: {result.get('error', '未知错误')}]"
    except Exception as e:
        logger.error(f"生成AI回复失败: {e}")
        return f"[AI服务异常: {str(e)}]"

def _check_gfm():
    if not gameflow_manager_available:
        return jsonify({"success": False, "error": "游戏管理模块未加载"}), 503
    return None
