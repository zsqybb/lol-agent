"""
讯飞星火API统一客户端
提供 call_spark_api() 供 web_server、chat_memory、skills 共享
"""
import logging
import requests
from config import get_spark_config

logger = logging.getLogger(__name__)

SPARK_API_URL = 'https://spark-api-open.xf-yun.com/x2/chat/completions'
SPARK_MODEL = 'spark-x'
DEFAULT_TIMEOUT = 30


def call_spark_api(messages, timeout=DEFAULT_TIMEOUT, config=None):
    """调用星火大模型，返回回复文本或 None"""
    if config is None:
        config = get_spark_config()

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
        resp = requests.post(SPARK_API_URL, headers=headers, json=payload, timeout=timeout)
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
