"""
配置管理模块
优先从环境变量读取敏感配置，找不到时回退到 ai_config.json 文件
"""
import os
import json
import logging

logger = logging.getLogger(__name__)

_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'ai_config.json')

# 超时与限速常量
DEFAULT_SPARK_TIMEOUT = 30
DEFAULT_LCU_TIMEOUT = 10
RIOT_API_MIN_INTERVAL = 1.2

# RAG 相关
RAG_MIN_SCORE = 60

# Riot API Key 管理（支持运行时覆盖）
_riot_api_key = os.environ.get('RIOT_API_KEY', '')


def get_riot_api_key():
    global _riot_api_key
    if _riot_api_key:
        return _riot_api_key
    return os.environ.get('RIOT_API_KEY', '')


def set_riot_api_key(new_key):
    global _riot_api_key
    _riot_api_key = new_key
    logger.info(f"API密钥已更新: {new_key[:10]}...")


def _load_file_config():
    """从配置文件读取（作为回退）"""
    try:
        with open(_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def get_spark_config():
    """获取讯飞星火 API 配置，优先使用环境变量"""
    env_key = os.environ.get('SPARK_API_KEY', '')
    env_secret = os.environ.get('SPARK_API_SECRET', '')
    env_app_id = os.environ.get('SPARK_APP_ID', '')

    if env_key and env_secret:
        return {
            'aiApiKey': env_key,
            'xinghuoApiSecret': env_secret,
            'xinghuoAppId': env_app_id,
        }

    file_config = _load_file_config()
    return {
        'aiApiKey': file_config.get('aiApiKey', ''),
        'xinghuoApiSecret': file_config.get('xinghuoApiSecret', ''),
        'xinghuoAppId': file_config.get('xinghuoAppId', ''),
    }
