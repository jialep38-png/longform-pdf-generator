#!/usr/bin/env python3
"""
教学文档自动生成系统 — CLI 入口
用法:
    py main.py "Claude Code 完全指南"
    py main.py "大模型微调实战" --template llm_engineering.yaml
    py main.py "AI Agent 开发" --urls https://example.com/article1
    py main.py "Prompt Engineering" --skip-humanize --skip-review
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

# 确保 src 在 import path 中
sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline import DocPipeline
from src.llm_provider import load_settings


def _load_manifest(manifest_path: str) -> dict:
    path = Path(manifest_path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return data or {}


def _parse_json_arg(value: str | None) -> dict | None:
    if not value:
        return None
    return json.loads(value)


def main():
    parser = argparse.ArgumentParser(
        description="教学文档自动生成系统 — 一键生成 5 万字以上高质量教学文档",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("topic", nargs="?", default=None, help="文档主题（如：'Claude Code 完全指南'）")
    parser.add_argument("--config", default=None, help="配置文件路径（默认 config/settings.yaml）")
    parser.add_argument("--manifest", default=None, help="任务描述文件（yaml/json）")
    parser.add_argument("--template", default=None, help="课程结构模板文件名（在 config/templates/ 下）")
    parser.add_argument("--urls", nargs="*", default=[], help="额外的参考资料 URL 列表")
    parser.add_argument("--docs", nargs="*", default=[], help="额外的本地文档/目录路径列表")
    parser.add_argument("--style-profile", default=None, help="风格画像标识")
    parser.add_argument("--to-pdf", action="store_true", help="生成出版级 PDF")
    parser.add_argument("--pdf-theme", default=None, help="JSON 字符串，覆盖 PDF 主题参数")
    parser.add_argument("--illustrations", default=None, help="JSON 字符串，覆盖插图配置")
    parser.add_argument("--skip-humanize", action="store_true", help="跳过风格人性化重写")
    parser.add_argument("--skip-review", action="store_true", help="跳过 LLM 质检审核")
    parser.add_argument("--debug", action="store_true", help="启用 DEBUG 日志")

    args = parser.parse_args()

    manifest = _load_manifest(args.manifest) if args.manifest else {}

    topic = args.topic or manifest.get("topic") or manifest.get("title")
    if not topic:
        raise ValueError("缺少 topic，请通过位置参数或 --manifest 提供")

    # 日志配置
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("data/generation.log", encoding="utf-8"),
        ],
    )

    print(f"\n{'='*60}")
    print("  教学文档自动生成系统")
    print(f"  主题: {topic}")
    print(f"{'='*60}\n")

    # 加载配置
    config_path = args.config
    if config_path is None:
        config_path = Path(__file__).parent / "config" / "settings.yaml"
    settings = load_settings(config_path)

    source_cfg = manifest.get("sources", {})
    output_cfg = manifest.get("output", {})

    urls = args.urls if args.urls else source_cfg.get("urls", [])
    docs = args.docs if args.docs else source_cfg.get("local_docs", [])
    template = args.template or manifest.get("template")

    pdf_theme_arg = _parse_json_arg(args.pdf_theme)
    illu_arg = _parse_json_arg(args.illustrations)

    pdf_cfg = manifest.get("pdf", {})
    render_options = {
        "to_pdf": bool(args.to_pdf or manifest.get("to_pdf")),
        "title": manifest.get("title") or topic,
        "subtitle": manifest.get("subtitle", ""),
        "author": manifest.get("author", ""),
        "basename": output_cfg.get("basename"),
        "style_profile": args.style_profile or manifest.get("style_profile"),
        "pdf_theme": (pdf_cfg.get("theme") or {}) | (pdf_theme_arg or {}),
        "illustration": (manifest.get("illustration") or {}) | (illu_arg or {}),
    }

    # 创建管道并运行
    pipeline = DocPipeline(settings=settings)
    result = pipeline.run(
        topic=topic,
        extra_urls=urls if urls else None,
        local_docs=docs if docs else None,
        template=template,
        skip_humanize=args.skip_humanize,
        skip_review=args.skip_review,
        render_options=render_options,
    )

    # 输出结果
    print(f"\n{'='*60}")
    print("  生成完成!")
    print(f"  总字数: {result.char_count:,}")
    print(f"  耗时: {result.elapsed_seconds:.1f} 秒")
    print("  导出文件:")
    for f in result.exported_files:
        print(f"    - {f}")
    if result.quality_report.get("issues"):
        print("  质量问题:")
        for issue in result.quality_report["issues"]:
            print(f"    ! {issue}")
    else:
        print("  质量检查: 通过")
    if result.review_result:
        print(f"  审核结果: {result.review_result[:200]}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
