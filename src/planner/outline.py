"""
内容规划器 — 生成分层大纲，分配 Token 预算，构建前置知识地图。
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..llm_provider import LLMClient, Settings

logger = logging.getLogger(__name__)


@dataclass
class Section:
    id: str
    title: str
    chapter: str
    learning_goal: str = ""
    key_points: list[str] = field(default_factory=list)
    target_chars: int = 1000
    evidence_queries: list[str] = field(default_factory=list)


@dataclass
class Outline:
    topic: str
    chapters: list[dict] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    total_target_chars: int = 50000


class OutlineGenerator:
    """基于 LLM 生成分层大纲并分配 Token 预算。"""

    def __init__(self, llm: LLMClient, settings: Settings):
        self.llm = llm
        self.pipeline_cfg = settings.pipeline
        self.target_chars = self.pipeline_cfg.get("target_chars", 50000)
        self.section_min = self.pipeline_cfg.get("section_min_chars", 700)
        self.section_max = self.pipeline_cfg.get("section_max_chars", 1500)
        self.sections_per_chapter = self.pipeline_cfg.get("sections_per_chapter", 6)

    def generate(self, topic: str, context_summary: str = "", template_path: str = None) -> Outline:
        template_hint = ""
        if template_path:
            template_hint = self._load_template(template_path)

        raw_outline = self._generate_raw_outline(topic, context_summary, template_hint)
        outline = self._parse_outline(topic, raw_outline)
        outline = self._allocate_budget(outline)
        logger.info(f"大纲生成完成: {len(outline.chapters)} 章, {len(outline.sections)} 节, 目标 {outline.total_target_chars} 字")
        return outline

    def _load_template(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            p = Path(__file__).parent.parent.parent / "config" / "templates" / path
        if p.exists():
            return p.read_text(encoding="utf-8")
        return ""

    def _generate_raw_outline(self, topic: str, context: str, template: str) -> str:
        system = """你是一位资深的课程架构师。你需要为一个付费教学文档设计详细的分层大纲。

要求：
1. 输出严格的 JSON 格式
2. 包含 10-15 个章节，每章 4-8 个小节
3. 每个章节需要有明确的学习目标
4. 内容从入门到进阶，逻辑递进
5. 要有实操章节和案例分析章节
6. 附录包含术语表和资源清单

JSON 格式：
{
  "chapters": [
    {
      "title": "章节标题",
      "summary": "本章概述",
      "sections": [
        {
          "title": "小节标题",
          "learning_goal": "学完本节后能...",
          "key_points": ["要点1", "要点2"],
          "evidence_queries": ["用于检索相关资料的搜索词"]
        }
      ]
    }
  ]
}"""

        user_msg = f"主题：{topic}\n\n"
        if context:
            user_msg += f"已收集到的背景信息摘要：\n{context[:3000]}\n\n"
        if template:
            user_msg += f"参考课程结构模板：\n{template[:2000]}\n\n"
        user_msg += "请生成完整的课程大纲（JSON）。"

        try:
            result = self.llm.call(
                "outline",
                [{"role": "user", "content": user_msg}],
                system=system,
                temperature=0.3,
            )
            return result
        except Exception as e:
            logger.warning(f"大纲生成调用失败，启用本地兜底大纲: {e}")
            fallback = self._fallback_outline(topic)
            return json.dumps(fallback, ensure_ascii=False)

    def _fallback_outline(self, topic: str) -> dict:
        chapter_titles = [
            "认知与全景",
            "基础概念",
            "工具与环境",
            "方法论",
            "核心实操",
            "进阶优化",
            "案例拆解",
            "故障排查",
            "协作与流程",
            "总结与行动清单",
        ]

        section_templates = [
            "为什么要做这件事",
            "关键概念与边界",
            "最小可行实践",
            "常见误区与规避",
            "实战清单",
        ]

        chapters = []
        for i, ch in enumerate(chapter_titles, start=1):
            sections = []
            for s in section_templates:
                sec_title = f"{ch}：{s}"
                sections.append({
                    "title": sec_title,
                    "learning_goal": f"理解并掌握{topic}在“{ch}”阶段的可执行方法",
                    "key_points": [f"{topic}基础原则", f"{ch}落地动作", "可验证结果"],
                    "evidence_queries": [topic, ch, sec_title],
                })
            chapters.append({
                "title": f"第{i}章 {ch}",
                "summary": f"围绕{topic}的“{ch}”建立从理解到执行的闭环。",
                "sections": sections,
            })

        return {"chapters": chapters}

    def _parse_outline(self, topic: str, raw: str) -> Outline:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError("无法解析大纲 JSON")

        outline = Outline(topic=topic)
        section_idx = 0
        for ch_idx, ch in enumerate(data.get("chapters", [])):
            ch_title = ch.get("title", f"第{ch_idx+1}章")
            outline.chapters.append({
                "index": ch_idx,
                "title": ch_title,
                "summary": ch.get("summary", ""),
            })
            for sec in ch.get("sections", []):
                outline.sections.append(Section(
                    id=f"ch{ch_idx}_s{section_idx}",
                    title=sec.get("title", ""),
                    chapter=ch_title,
                    learning_goal=sec.get("learning_goal", ""),
                    key_points=sec.get("key_points", []),
                    evidence_queries=sec.get("evidence_queries", []),
                ))
                section_idx += 1

        return outline

    def _allocate_budget(self, outline: Outline) -> Outline:
        n = len(outline.sections)
        if n == 0:
            return outline
        base = self.target_chars // n
        for sec in outline.sections:
            sec.target_chars = max(self.section_min, min(self.section_max, base))
        outline.total_target_chars = sum(s.target_chars for s in outline.sections)
        return outline
