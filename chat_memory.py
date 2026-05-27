"""
对话记忆管理模块
- 每次新对话创建一个记忆文件
- 回答时读取记忆提供上下文
- 每5轮对话自动总结压缩（后台线程，不阻塞响应）
- 对话结束时删除记忆文件
"""
import os
import json
import time
import uuid
import logging
import threading
from spark_client import call_spark_api

logger = logging.getLogger(__name__)

MEMORY_DIR = os.path.join(os.path.dirname(__file__), 'chat_memory')
os.makedirs(MEMORY_DIR, exist_ok=True)

SUMMARY_PROMPT = """请将以下英雄联盟游戏对话记录总结为简洁的要点，必须保留以下关键信息：
1. 用户提到的英雄名称（如亚索、盲僧等）
2. 用户查询的具体内容（如出装、符文、背景故事等）
3. 助手提供的关键结论（如推荐出装、克制英雄等）
4. 用户当前关注的英雄和话题方向

去除冗余的客套话和重复内容，总结不超过200字。

对话记录：
{content}

请输出总结："""


class ChatMemory:
    def __init__(self, session_id: str, mode: str = 'ai'):
        self.session_id = session_id
        self.mode = mode
        self.filepath = os.path.join(MEMORY_DIR, f'{mode}_{session_id}.json')
        self.round_count = 0
        self.last_champ_id = ''
        self.last_champ_name = ''
        self.summary = ''
        self.recent_messages = []
        self._lock = threading.Lock()
        self._summarizing = False
        self._load()

    def _save(self):
        with self._lock:
            data = {
                'session_id': self.session_id,
                'mode': self.mode,
                'round_count': self.round_count,
                'last_champ_id': self.last_champ_id,
                'last_champ_name': self.last_champ_name,
                'summary': self.summary,
                'recent_messages': self.recent_messages[-10:],
                'updated_at': time.time(),
            }
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存记忆失败: {e}")

    def _load(self):
        if not os.path.exists(self.filepath):
            return
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.round_count = data.get('round_count', 0)
            self.last_champ_id = data.get('last_champ_id', '')
            self.last_champ_name = data.get('last_champ_name', '')
            self.summary = data.get('summary', '')
            self.recent_messages = data.get('recent_messages', [])
        except Exception as e:
            logger.error(f"加载记忆失败: {e}")

    def add_round(self, user_msg: str, assistant_msg: str, champ_id: str = '', champ_name: str = ''):
        self.round_count += 1
        if champ_id:
            self.last_champ_id = champ_id
            self.last_champ_name = champ_name
        self.recent_messages.append({
            'round': self.round_count,
            'user': user_msg,
            'assistant': assistant_msg[:200],
            'champ_id': champ_id,
            'champ_name': champ_name,
        })
        self.recent_messages = self.recent_messages[-10:]

        if self.round_count > 0 and self.round_count % 5 == 0:
            self._summarize_async()

        self._save()

    def _summarize_async(self):
        """后台线程执行总结，不阻塞请求响应"""
        if self._summarizing:
            return
        self._summarizing = True
        t = threading.Thread(target=self._summarize, daemon=True)
        t.start()

    def _summarize(self):
        try:
            content_parts = []
            if self.summary:
                content_parts.append(f"[历史总结] {self.summary}")

            with self._lock:
                msgs_snapshot = list(self.recent_messages)

            for msg in msgs_snapshot:
                content_parts.append(f"第{msg['round']}轮 - 用户: {msg['user']}")
                content_parts.append(f"第{msg['round']}轮 - 助手: {msg['assistant']}")

            full_content = '\n'.join(content_parts)
            if len(full_content) < 50:
                return

            messages = [
                {"role": "system", "content": "你是一个对话总结助手，专门总结英雄联盟游戏相关的对话。请提取关键信息，保留英雄名、查询内容、核心结论，去除冗余。"},
                {"role": "user", "content": SUMMARY_PROMPT.format(content=full_content)}
            ]

            summary_result = call_spark_api(messages, timeout=60)
            with self._lock:
                if summary_result:
                    self.summary = summary_result
                    self.recent_messages = self.recent_messages[-3:]
                    logger.info(f"会话{self.session_id}记忆已压缩，第{self.round_count}轮")
                else:
                    if len(self.recent_messages) > 5:
                        self.recent_messages = self.recent_messages[-3:]
                    self.summary = self._manual_summarize(full_content)
        finally:
            self._summarizing = False
            self._save()

    def _manual_summarize(self, content: str) -> str:
        lines = content.split('\n')
        keywords = []
        for line in lines:
            if '用户:' in line:
                user_part = line.split('用户:')[1].strip()
                if len(user_part) > 50:
                    user_part = user_part[:50] + '...'
                keywords.append(user_part)
        result = '；'.join(keywords[-5:])
        return f"用户曾问: {result}" if result else ""

    def get_context(self) -> str:
        self._load()
        parts = []
        if self.summary:
            parts.append(f"[对话历史总结] {self.summary}")
        if self.last_champ_name:
            parts.append(f"[最近讨论的英雄] {self.last_champ_name}")
        if self.recent_messages:
            last = self.recent_messages[-1]
            parts.append(f"[上一轮] 用户问: {last['user']} | 助手答: {last['assistant'][:80]}")
        return '\n'.join(parts)

    def get_last_champ(self) -> tuple:
        self._load()
        return self.last_champ_id, self.last_champ_name

    def delete(self):
        try:
            if os.path.exists(self.filepath):
                os.remove(self.filepath)
                logger.info(f"会话{self.session_id}记忆已删除")
        except Exception as e:
            logger.error(f"删除记忆失败: {e}")


_memory_cache = {}
MAX_CACHED_SESSIONS = 50


def get_memory(session_id: str, mode: str = 'ai') -> ChatMemory:
    key = f'{mode}_{session_id}'
    if key not in _memory_cache:
        # evict oldest entries if cache is full
        if len(_memory_cache) >= MAX_CACHED_SESSIONS:
            oldest_key = next(iter(_memory_cache))
            oldest = _memory_cache.pop(oldest_key)
            oldest._save()
            logger.debug(f"淘汰旧会话缓存: {oldest_key}")
        mem = ChatMemory(session_id, mode)
        _memory_cache[key] = mem
    return _memory_cache[key]


def delete_memory(session_id: str, mode: str = 'ai'):
    key = f'{mode}_{session_id}'
    if key in _memory_cache:
        _memory_cache[key].delete()
        del _memory_cache[key]
    else:
        mem = ChatMemory(session_id, mode)
        mem.delete()


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]
