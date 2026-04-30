"""
Skill调度器 - 意图识别 + 优先级调度
1. 接收用户消息
2. 遍历所有Skill，判断是否触发
3. 按优先级选择最高匹配Skill
4. 执行Skill并返回结果
"""
import logging
from .base_skill import BaseSkill
from .gameplay_skill import GameplaySkill
from .lore_skill import LoreSkill
from .player_skill import PlayerSkill
from .general_skill import GeneralSkill

logger = logging.getLogger(__name__)


class SkillDispatcher:
    def __init__(self):
        self.skills = [
            PlayerSkill(),
            GameplaySkill(),
            LoreSkill(),
            GeneralSkill(),
        ]
        self.skills.sort(key=lambda s: s.priority, reverse=True)
        logger.info(f"Skill调度器初始化: {[s.name for s in self.skills]}")

    def dispatch(self, message: str, context: dict = None) -> dict:
        matched_skills = []

        for skill in self.skills:
            try:
                if skill.should_trigger(message):
                    matched_skills.append(skill)
            except Exception as e:
                logger.error(f"Skill {skill.name} should_trigger error: {e}")

        if not matched_skills:
            matched_skills = [self.skills[-1]]

        selected = matched_skills[0]
        logger.info(f"Selected skill: {selected.name} (priority={selected.priority})")

        try:
            result = selected.execute(message, context)
            result['skill_name'] = selected.name

            if result.get('success') and result.get('data', {}).get('need_counter'):
                general_skill = next((s for s in self.skills if s.name == 'general'), None)
                if general_skill:
                    hero_name = result.get('hero', '') or result['data'].get('name', '')
                    hero_title = result['data'].get('title', '')
                    hero_tags = result['data'].get('tags', [])
                    tag_cn = {'Fighter': '战士', 'Tank': '坦克', 'Mage': '法师', 'Assassin': '刺客', 'Marksman': '射手', 'Support': '辅助'}
                    tags_str = '/'.join([tag_cn.get(t, t) for t in hero_tags])
                    counter_msg = (
                        f"请详细分析如何克制英雄{hero_title}（{hero_name}），定位为{tags_str}。\n\n"
                        f"请按以下结构回答：\n"
                        f"1. **克制英雄推荐**（3-5个，说明每个克制的原因）\n"
                        f"2. **对线核心技巧**（站位、技能博弈、换血节奏）\n"
                        f"3. **装备针对**（推荐购买的反制装备）\n"
                        f"4. **团战处理**（如何限制该英雄的发挥）\n\n"
                        f"回答要实用、具体，基于真实游戏经验。"
                    )
                    counter_context = dict(context) if context else {}
                    counter_context['rag_context'] = ''
                    logger.info(f"克制查询: hero_title={hero_title}, hero_name={hero_name}, msg={counter_msg[:60]}")
                    try:
                        counter_result = general_skill.execute(counter_msg, counter_context)
                        logger.info(f"克制查询结果: success={counter_result.get('success')}, has_response={bool(counter_result.get('data', {}).get('response', ''))}")
                        if counter_result.get('success'):
                            counter_text = counter_result.get('data', {}).get('response', '')
                            if counter_text:
                                result['data']['counter_info'] = counter_text
                    except Exception as ce:
                        logger.error(f"克制查询GeneralSkill调用失败: {ce}")

            return result
        except Exception as e:
            logger.error(f"Skill {selected.name} execute error: {e}")
            return {
                'skill': selected.name,
                'success': False,
                'error': f'执行技能时出错: {str(e)}',
                'data': None,
            }

    def dispatch_skill(self, message: str, context: dict = None, skill_name: str = '') -> dict:
        for skill in self.skills:
            if skill.name == skill_name:
                logger.info(f"Forced dispatch to skill: {skill.name}")
                try:
                    result = skill.execute(message, context)
                    result['skill_name'] = skill.name
                    return result
                except Exception as e:
                    logger.error(f"Skill {skill.name} execute error: {e}")
                    return {
                        'skill': skill.name,
                        'success': False,
                        'error': f'执行技能时出错: {str(e)}',
                        'data': None,
                    }
        return self.dispatch(message, context)

    def format_result(self, result: dict) -> str:
        skill_name = result.get('skill_name', result.get('skill', ''))

        for skill in self.skills:
            if skill.name == skill_name:
                return skill.format_result(result)

        return str(result.get('data', ''))

    def get_skill_info(self) -> list:
        return [
            {
                'name': s.name,
                'description': s.description,
                'priority': s.priority,
                'keywords': s.keywords[:10],
            }
            for s in self.skills
        ]
