"""
风格人性化重写器 — 注入个人 IP 人设、句式多样化、去 AI 高频词、场景化描写。
"""

import logging
import random
import re
from pathlib import Path

import yaml

from ..llm_provider import LLMClient, Settings

logger = logging.getLogger(__name__)


class PersonaManager:
    """管理写作人设配置。"""

    DEFAULT_PERSONAS = {
        "veteran_architect": {
            "name": "资深架构师",
            "background": "10年AI从业经验，从传统ML到大模型时代，亲历过多个百万级项目的落地",
            "tone": "务实直接，偶尔犀利，会用工程圈的黑话",
            "metaphors": ["做菜", "盖房子", "开车"],
            "catchphrases": [
                "说句掏心窝的话",
                "踩过这个坑的人都知道",
                "这里有个容易被忽略的细节",
                "我当年就是因为没注意这个，项目差点翻车",
                "别被表面的简单骗了",
                "实际生产中完全是另一回事",
            ],
        },
        "tech_explorer": {
            "name": "技术探索者",
            "background": "AI独立开发者，GitHub上有几个小有名气的开源项目，享受把复杂的东西讲简单",
            "tone": "轻松有趣，善于用类比，偶尔吐槽",
            "metaphors": ["游戏", "旅行", "乐高积木"],
            "catchphrases": [
                "你可能觉得这没什么，但接下来的操作会让你惊掉下巴",
                "这个功能我自己用了之后就再也回不去了",
                "说实话，官方文档写得像天书",
                "如果你跟我一样懒，这个方法绝对适合你",
                "先别急着往下看，想想你会怎么做",
            ],
        },
        "industry_consultant": {
            "name": "行业顾问",
            "background": "咨询公司合伙人，帮助过上百家企业做AI转型，擅长从商业视角看技术",
            "tone": "沉稳专业，注重数据和案例，习惯用商业思维解读",
            "metaphors": ["投资", "打仗", "经营餐厅"],
            "catchphrases": [
                "从ROI角度看",
                "跟你分享一个我在客户现场见到的真实案例",
                "很多团队在这一步犯了同样的错误",
                "这不是技术问题，是认知问题",
                "数据不会骗人",
            ],
        },
    }

    def __init__(self, settings: Settings):
        self.active = settings.humanizer.get("active_persona", "veteran_architect")
        self._personas = dict(self.DEFAULT_PERSONAS)
        custom_path = Path(__file__).parent.parent.parent / "config" / "personas.yaml"
        if custom_path.exists():
            with open(custom_path, "r", encoding="utf-8") as f:
                custom = yaml.safe_load(f) or {}
                self._personas.update(custom)

    def get_active(self) -> dict:
        return self._personas.get(self.active, self.DEFAULT_PERSONAS["veteran_architect"])

    def get_prompt_injection(self) -> str:
        p = self.get_active()
        return f"""你的写作人设：
- 身份：{p['name']}，{p['background']}
- 语气风格：{p['tone']}
- 喜欢用的比喻领域：{', '.join(p['metaphors'])}
- 口头禅/过渡语（需自然穿插，不要每段都用）：
  {chr(10).join(f'  * "{c}"' for c in p['catchphrases'])}"""


class StyleRewriter:
    """对生成的草稿进行去 AI 化风格重写。"""

    def __init__(self, llm: LLMClient, settings: Settings):
        self.llm = llm
        self.settings = settings
        self.persona = PersonaManager(settings)
        self.blacklist = settings.humanizer.get("blacklisted_words", [])
        self.variety = settings.humanizer.get("sentence_variety", {})

    def rewrite_all(self, sections: dict[str, str]) -> dict[str, str]:
        results = {}
        for sid, text in sections.items():
            results[sid] = self.rewrite(text)
            logger.info(f"  风格重写完成: {sid}")
        return results

    async def arewrite_all(self, sections: dict[str, str]) -> dict[str, str]:
        results = {}
        for sid, text in sections.items():
            results[sid] = await self.arewrite(text)
            logger.info(f"  风格重写完成: {sid}")
        return results

    def rewrite(self, text: str) -> str:
        text = self._remove_blacklisted(text)
        text = self._llm_rewrite(text)
        text = self._remove_blacklisted(text)
        return text

    async def arewrite(self, text: str) -> str:
        text = self._remove_blacklisted(text)
        text = await self._allm_rewrite(text)
        text = self._remove_blacklisted(text)
        return text

    def _remove_blacklisted(self, text: str) -> str:
        pattern = "|".join(re.escape(w) for w in self.blacklist)
        if pattern:
            text = re.sub(rf"({pattern})[,，。]?\s?", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"  +", " ", text)
        return text.strip()

    def _build_rewrite_prompt(self, text: str) -> tuple[str, str]:
        persona_prompt = self.persona.get_prompt_injection()
        short_r = self.variety.get("short_ratio", 0.2)
        q_r = self.variety.get("question_ratio", 0.15)

        system = f"""你是一位专业的文案改写专家。你的任务是把下面的技术文章改写得更像一个真实的人类作者写的。

{persona_prompt}

改写规则：
1. 保留所有技术事实和核心信息，不增不减
2. 约 {int(short_r*100)}% 的句子控制在15字以内（短句增加节奏感）
3. 约 {int(q_r*100)}% 的地方使用设问句引导读者思考
4. 自然穿插1-2句口头禅/过渡语（不要生硬）
5. 把平淡的描述替换为有画面感的具体场景
6. 删除所有以下词汇及类似的 AI 腔调表述：{', '.join(self.blacklist[:10])}
7. 段落长短交替：长段（3-5句）和短段（1-2句）穿插
8. 如果原文有代码示例，保持代码不变，只改写文字部分
9. 不要添加额外的 markdown 标题层级

直接输出改写后的完整内容，不要输出任何元说明。"""

        user_msg = f"请改写以下内容：\n\n{text}"
        return system, user_msg

    def _llm_rewrite(self, text: str) -> str:
        system, user_msg = self._build_rewrite_prompt(text)
        return self.llm.call("humanize", [{"role": "user", "content": user_msg}], system=system)

    async def _allm_rewrite(self, text: str) -> str:
        system, user_msg = self._build_rewrite_prompt(text)
        return await self.llm.acall("humanize", [{"role": "user", "content": user_msg}], system=system)
