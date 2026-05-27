"""
通用聊天Skill - 兜底处理，当其他Skill都不匹配时使用
直接调用讯飞星火HTTP API生成回复
"""
import os
import logging
from spark_client import call_spark_api
from .base_skill import BaseSkill

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是「LOL数据助手」，一位专业的英雄联盟游戏顾问，拥有丰富的游戏知识和实战经验。

## 核心身份
- 你精通英雄联盟的版本动态、英雄机制、装备体系和战术策略
- 你的回答基于真实游戏数据和实践经验，不编造不存在的英雄、装备或机制
- 当不确定时，诚实告知用户并建议更精确的查询方式

## 回答风格
- 语言简洁有力，重点信息优先呈现
- 使用适当的emoji增强可读性（如⚔️🗡️🛡️🎯💡等）
- 善用加粗标记关键内容（如**核心装备**、**关键技巧**）
- 使用编号列表或分点阐述，避免大段文字堆砌
- 回答长度适中，一般控制在200字以内，复杂问题不超过500字

## 引导策略
- 如果用户问英雄玩法/出装/符文，建议使用「英雄问答」模式获取精确数据
- 如果用户问英雄背景/故事，建议使用「故事问答」模式获取完整故事
- 如果用户问玩家战绩/段位，提示格式：玩家名#标签（如 Selfless#KR11）
- 对于模糊问题，主动提供2-3个可能的解读方向

## 知识边界
- 你了解英雄联盟的基本机制、主流英雄、常见战术
- 你可以讨论版本趋势、赛事动态、上分策略等话题
- 你不会编造不存在的英雄、皮肤、装备或游戏机制
- 当信息不足时，引导用户使用更精确的查询方式"""


class GeneralSkill(BaseSkill):
    name = "general"
    description = "通用聊天（兜底）"
    priority = 10

    keywords = []

    def should_trigger(self, message: str) -> bool:
        return True

    def execute(self, message: str, context: dict = None) -> dict:
        rag_context = ""
        memory_context = ""
        if context and context.get('rag_context'):
            rag_context = context['rag_context']
        if context and context.get('memory_context'):
            memory_context = context['memory_context']

        try:
            user_content = message
            context_parts = []
            if memory_context:
                context_parts.append(f"【对话记忆】\n{memory_context}\n")
            if rag_context:
                context_parts.append(f"【知识库参考】\n{rag_context}\n")
            if context_parts:
                user_content = '\n'.join(context_parts) + f"【用户当前问题】\n{message}"

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ]

            response = call_spark_api(messages, timeout=60)
            if response:
                return {
                    'skill': self.name,
                    'success': True,
                    'data': {'response': response},
                }
        except Exception as e:
            logger.error(f"星火API调用失败: {e}")

        if rag_context:
            return {
                'skill': self.name,
                'success': True,
                'data': {'response': f"根据知识库信息：\n\n{rag_context}"},
            }

        return {
            'skill': self.name,
            'success': False,
            'data': {'response': '⚠️ 抱歉，我暂时无法回答这个问题。\n💡 你可以尝试：\n- 询问英雄出装/符文（如"亚索出装"）\n- 查询英雄背景故事（如"亚索的背景故事"）\n- 了解克制攻略（如"怎么克制亚索"）'},
        }

    def format_result(self, result: dict) -> str:
        data_resp = result.get('data', {}).get('response', '')
        if data_resp:
            return data_resp
        return '暂时无法回复'
