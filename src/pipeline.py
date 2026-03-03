"""
主管道编排 — 串联 5 层生成流程，管理状态流转和进度报告。
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from .llm_provider import LLMClient, Settings, load_settings
from .ingestion.collector import InfoCollector, VectorStore
from .planner.outline import OutlineGenerator, Outline
from .generator.writer import SectionWriter
from .humanizer.rewriter import StyleRewriter
from .assembler.builder import DocAssembler

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    topic: str = ""
    char_count: int = 0
    exported_files: list[str] = field(default_factory=list)
    quality_report: dict = field(default_factory=dict)
    review_result: str = ""
    elapsed_seconds: float = 0


class DocPipeline:
    """5 层文档生成管道。"""

    def __init__(self, settings: Settings = None, config_path: str = None):
        if settings is None:
            settings = load_settings(config_path)
        self.settings = settings
        self.llm = LLMClient(settings)

        # 初始化各层
        self.collector = InfoCollector(settings.ingestion)
        project_root = Path(__file__).resolve().parent.parent
        vector_db_path = Path(settings.ingestion.get("vector_db_path", "data/vectordb"))
        if not vector_db_path.is_absolute():
            vector_db_path = project_root / vector_db_path
        self.vector_store = VectorStore(
            persist_dir=str(vector_db_path),
            embedding_model=settings.ingestion.get("embedding_model", "all-MiniLM-L6-v2"),
        )
        self.planner = OutlineGenerator(self.llm, settings)
        self.writer = SectionWriter(self.llm, settings, self.vector_store)
        self.humanizer = StyleRewriter(self.llm, settings)
        self.assembler = DocAssembler(self.llm, settings)

    def run(
        self,
        topic: str,
        extra_urls: list[str] = None,
        local_docs: list[str] = None,
        template: str = None,
        skip_humanize: bool = False,
        skip_review: bool = False,
        render_options: dict | None = None,
    ) -> PipelineResult:
        start = time.time()
        result = PipelineResult(topic=topic)

        # --- Layer 1: 信息采集 ---
        self._report("Layer 1/5", "信息采集")
        docs = self.collector.collect(topic, extra_urls, local_docs)
        if docs:
            self.vector_store.add_docs(
                docs,
                chunk_size=self.settings.ingestion.get("chunk_size", 500),
                overlap=self.settings.ingestion.get("chunk_overlap", 50),
            )
        context_summary = self._build_context_summary(docs)

        # --- Layer 2: 内容规划 ---
        self._report("Layer 2/5", "内容规划")
        outline = self.planner.generate(topic, context_summary, template)

        # --- Layer 3: 分段生成 ---
        self._report("Layer 3/5", f"分段生成 ({len(outline.sections)} 节)")
        sections = self.writer.generate_all(outline)

        # --- Layer 4: 风格重写 ---
        if not skip_humanize:
            self._report("Layer 4/5", "风格人性化重写")
            sections = self.humanizer.rewrite_all(sections)
        else:
            self._report("Layer 4/5", "跳过风格重写")

        # --- Layer 5: 组装与质检 ---
        self._report("Layer 5/5", "组装与质检")
        full_text = self.assembler.assemble(outline, sections, self.writer.memory)
        result.quality_report = self.assembler.quality_check(full_text, outline)
        result.char_count = result.quality_report.get("char_count", 0)

        if not skip_review:
            result.review_result = self.assembler.llm_review(full_text)

        # 补充字数不足的处理
        if not result.quality_report.get("passed"):
            issues = result.quality_report.get("issues", [])
            char_issues = [i for i in issues if "字数不足" in i]
            if char_issues:
                self._report("补充", "字数不足，扩充内容中...")
                full_text = self._expand_content(full_text, outline, sections)
                result.quality_report = self.assembler.quality_check(full_text, outline)
                result.char_count = result.quality_report.get("char_count", 0)

        # 导出
        result.exported_files = self.assembler.export(full_text, topic, render_options=render_options)
        result.elapsed_seconds = time.time() - start

        self._report("完成", f"{result.char_count} 字, 耗时 {result.elapsed_seconds:.1f}s")
        return result

    def _build_context_summary(self, docs) -> str:
        if not docs:
            return ""
        summaries = []
        for doc in docs[:10]:
            summaries.append(f"[{doc.source}] {doc.title}: {doc.content[:300]}")
        return "\n".join(summaries)

    def _expand_content(self, text: str, outline: Outline, sections: dict) -> str:
        """字数不足时扩充内容。"""
        logger.info("字数不足，对较短的小节进行扩充...")
        section_lengths = {}
        for sec in outline.sections:
            content = sections.get(sec.id, "")
            section_lengths[sec.id] = len(content)

        short_sections = sorted(section_lengths.items(), key=lambda x: x[1])[:10]
        for sid, length in short_sections:
            sec = next((s for s in outline.sections if s.id == sid), None)
            if not sec:
                continue
            original = sections[sid]
            try:
                expanded = self.llm.call("draft", [
                    {"role": "user", "content": f"""以下内容需要扩充到至少 {sec.target_chars} 字。
在保持原有内容完整的基础上，增加更多细节、例子和深入解释。
不要改变原有结构，只做内容补充。

原文：
{original}

请输出扩充后的完整内容。"""}
                ])
                sections[sid] = expanded
            except Exception as e:
                logger.warning(f"扩充小节失败，保留原文: {sid} - {e}")

        return self.assembler.assemble(outline, sections, self.writer.memory)

    @staticmethod
    def _report(stage: str, message: str):
        logger.info(f"[{stage}] {message}")
        print(f"  [{stage}] {message}")
