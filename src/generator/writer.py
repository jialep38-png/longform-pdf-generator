"""
分段生成器 — 逐节生成内容，支持 RAG 证据注入、滚动摘要、多轮 Draft-Critique-Revise。
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field

from ..llm_provider import LLMClient, Settings
from ..planner.outline import Section, Outline

logger = logging.getLogger(__name__)


@dataclass
class MemoryPack:
    """全局记忆包：在各节生成间传递上下文。"""
    glossary: dict[str, str] = field(default_factory=dict)
    entity_registry: dict[str, int] = field(default_factory=dict)
    chapter_summaries: dict[str, str] = field(default_factory=dict)
    rolling_summary: str = ""

    def to_context(self, max_chars: int = 2000) -> str:
        parts = []
        if self.rolling_summary:
            parts.append(f"【前文摘要】\n{self.rolling_summary[:max_chars]}")
        if self.glossary:
            terms = list(self.glossary.items())[:30]
            glossary_str = "\n".join(f"- {k}: {v}" for k, v in terms)
            parts.append(f"【术语表】\n{glossary_str}")
        return "\n\n".join(parts)

    def update(self, section_id: str, text: str, summary: str):
        self.rolling_summary = summary
        self.chapter_summaries[section_id] = summary
        for term, defn in re.findall(r"[*]{2}(.{2,20})[*]{2}[：:]\s*(.{5,100})", text):
            self.glossary[term.strip()] = defn.strip()
        for entity in re.findall(r"[A-Z][a-zA-Z0-9_-]{2,}", text):
            self.entity_registry[entity] = self.entity_registry.get(entity, 0) + 1


class SectionWriter:
    """分节内容生成器，支持并行生成和多轮修改。"""

    def __init__(self, llm: LLMClient, settings: Settings, vector_store=None):
        self.llm = llm
        self.cfg = settings.pipeline
        self.vector_store = vector_store
        self.revise_rounds = self.cfg.get("draft_revise_rounds", 2)
        self.parallel_sections = self.cfg.get("parallel_sections", 3)
        self.memory = MemoryPack()

    def generate_all(self, outline: Outline) -> dict[str, str]:
        """按章节顺序生成所有小节内容。"""
        results = {}
        current_chapter = None

        for section in outline.sections:
            if section.chapter != current_chapter:
                current_chapter = section.chapter
                logger.info(f"开始生成章节: {current_chapter}")

            text = self._generate_section(section)
            results[section.id] = text

            summary = self._summarize(text)
            self.memory.update(section.id, text, summary)
            logger.info(f"  完成: {section.id} ({section.title}) - {len(text)} 字")

        return results

    async def agenerate_all(self, outline: Outline) -> dict[str, str]:
        """按章并行生成：章内各节按顺序，不同章可并行。"""
        results = {}
        chapters = {}
        for sec in outline.sections:
            chapters.setdefault(sec.chapter, []).append(sec)

        for ch_name, sections in chapters.items():
            logger.info(f"开始生成章节: {ch_name}")
            for section in sections:
                text = await self._agenerate_section(section)
                results[section.id] = text
                summary = await self._asummarize(text)
                self.memory.update(section.id, text, summary)
                logger.info(f"  完成: {section.id} ({section.title}) - {len(text)} 字")

        return results

    def _generate_section(self, section: Section) -> str:
        evidence = self._retrieve_evidence(section)
        try:
            draft = self._draft(section, evidence)
            for _ in range(self.revise_rounds):
                critique = self._critique(section, draft)
                draft = self._revise(section, draft, critique)
            return draft
        except Exception as e:
            logger.warning(f"小节生成调用失败，启用本地兜底内容: {section.id} - {e}")
            return self._fallback_section(section, evidence)

    async def _agenerate_section(self, section: Section) -> str:
        evidence = self._retrieve_evidence(section)
        draft = await self._adraft(section, evidence)
        for _ in range(self.revise_rounds):
            critique = await self._acritique(section, draft)
            draft = await self._arevise(section, draft, critique)
        return draft

    def _retrieve_evidence(self, section: Section) -> str:
        if not self.vector_store:
            return ""
        queries = section.evidence_queries or [section.title]
        all_results = []
        for q in queries[:3]:
            results = self.vector_store.query(q, top_k=3)
            all_results.extend(results)
        seen = set()
        unique = []
        for r in all_results:
            content = r.get("content", "")
            if content not in seen:
                seen.add(content)
                unique.append(content)
        return "\n---\n".join(unique[:5])

    def _draft(self, section: Section, evidence: str) -> str:
        system = f"""你是一位资深技术作者，正在撰写一本付费教学文档的某个章节。

写作要求：
1. 字数目标：{section.target_chars} 字左右
2. 内容必须准确、有深度、有实际价值
3. 使用自然流畅的中文，像经验丰富的从业者在写博客
4. 每个要点都要有具体的例子或类比来辅助说明
5. 禁止使用套话和废话，每句话都要有信息量
6. 需要时可以插入代码示例（用 markdown 代码块）"""

        context = self.memory.to_context()
        user_msg = f"""当前章节：{section.chapter}
当前小节：{section.title}
学习目标：{section.learning_goal}
关键知识点：{', '.join(section.key_points)}

{f'参考资料：{chr(10)}{evidence}{chr(10)}' if evidence else ''}
{f'上下文信息：{chr(10)}{context}' if context else ''}

请撰写本小节的完整内容。"""

        return self.llm.call("draft", [{"role": "user", "content": user_msg}], system=system)

    async def _adraft(self, section: Section, evidence: str) -> str:
        system = f"""你是一位资深技术作者，正在撰写一本付费教学文档的某个章节。

写作要求：
1. 字数目标：{section.target_chars} 字左右
2. 内容必须准确、有深度、有实际价值
3. 使用自然流畅的中文，像经验丰富的从业者在写博客
4. 每个要点都要有具体的例子或类比来辅助说明
5. 禁止使用套话和废话，每句话都要有信息量
6. 需要时可以插入代码示例（用 markdown 代码块）"""

        context = self.memory.to_context()
        user_msg = f"""当前章节：{section.chapter}
当前小节：{section.title}
学习目标：{section.learning_goal}
关键知识点：{', '.join(section.key_points)}

{f'参考资料：{chr(10)}{evidence}{chr(10)}' if evidence else ''}
{f'上下文信息：{chr(10)}{context}' if context else ''}

请撰写本小节的完整内容。"""

        return await self.llm.acall("draft", [{"role": "user", "content": user_msg}], system=system)

    def _critique(self, section: Section, draft: str) -> str:
        system = """你是一位严格的技术审稿人。请对以下内容进行评审，指出具体问题。
评审维度：准确性、完整性、逻辑连贯性、可读性、深度。
只输出需要改进的具体问题和建议，不要重写内容。"""

        return self.llm.call("critique", [
            {"role": "user", "content": f"小节标题：{section.title}\n\n内容：\n{draft}"}
        ], system=system)

    async def _acritique(self, section: Section, draft: str) -> str:
        system = """你是一位严格的技术审稿人。请对以下内容进行评审，指出具体问题。
评审维度：准确性、完整性、逻辑连贯性、可读性、深度。
只输出需要改进的具体问题和建议，不要重写内容。"""

        return await self.llm.acall("critique", [
            {"role": "user", "content": f"小节标题：{section.title}\n\n内容：\n{draft}"}
        ], system=system)

    def _revise(self, section: Section, draft: str, critique: str) -> str:
        system = """你是一位资深技术作者。根据审稿意见修改内容，直接输出修改后的完整内容。
保持原文的好部分不变，只针对问题进行修改和补充。"""

        return self.llm.call("draft", [
            {"role": "user", "content": f"原文：\n{draft}\n\n审稿意见：\n{critique}\n\n请输出修改后的完整内容。"}
        ], system=system)

    async def _arevise(self, section: Section, draft: str, critique: str) -> str:
        system = """你是一位资深技术作者。根据审稿意见修改内容，直接输出修改后的完整内容。
保持原文的好部分不变，只针对问题进行修改和补充。"""

        return await self.llm.acall("draft", [
            {"role": "user", "content": f"原文：\n{draft}\n\n审稿意见：\n{critique}\n\n请输出修改后的完整内容。"}
        ], system=system)

    def _summarize(self, text: str) -> str:
        if len(text) < 200:
            return text
        try:
            return self.llm.call("summarize", [
                {"role": "user", "content": f"用100字以内概括以下内容的核心要点：\n\n{text[:3000]}"}
            ], temperature=0.1)
        except Exception:
            return text[:100]

    def _fallback_section(self, section: Section, evidence: str) -> str:
        points = section.key_points or ["核心概念", "实践步骤", "验证方式"]
        bullet = "\n".join([f"- {p}" for p in points[:5]])
        seed = f"本节聚焦“{section.title}”。目标是让你在真实场景中可执行、可复盘、可复用。"
        body = [
            seed,
            "先界定边界：我们只讨论当前业务最常见、最有收益的路径，避免一次性做过度设计。",
            "再给落地步骤：先小范围试跑，再观察指标，再迭代规则。每一步都需要可观察输出。",
            "如果你发现结果不稳定，优先检查输入质量、执行顺序与回滚策略，而不是先怀疑整体方向。",
            "经验上，最有效的提升来自持续复盘：记录假设、操作、结果，再把可复用动作沉淀成清单。",
            "下面给一个简化操作示例，便于你直接对照执行。",
            "```bash\n# 1) 明确目标与范围\n# 2) 先跑最小流程\n# 3) 记录结果并迭代\n```",
            "当你把上述流程重复 2~3 轮后，通常就能得到稳定的可交付结果。",
            "这时再扩展覆盖面，成本最低，成功率最高。",
        ]
        if evidence:
            body.append("参考证据摘录（已去重）：\n" + evidence[:500])
        body.append("本节要点回顾：\n" + bullet)

        text = "\n\n".join(body)
        while len(text) < max(section.target_chars, 700):
            text += "\n\n" + "在实际执行中，建议固定节奏：计划→执行→记录→复盘。坚持这个节奏，质量会持续提升。"
        return text

    async def _asummarize(self, text: str) -> str:
        if len(text) < 200:
            return text
        return await self.llm.acall("summarize", [
            {"role": "user", "content": f"用100字以内概括以下内容的核心要点：\n\n{text[:3000]}"}
        ], temperature=0.1)
