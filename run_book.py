#!/usr/bin/env python3
"""统一编排入口：主题素材 -> Markdown 长文 -> 出版级 PDF。"""

import argparse
import json
from pathlib import Path

import yaml

from src.llm_provider import load_settings
from src.pipeline import DocPipeline


def _load_manifest(path: str | None) -> dict:
    if not path:
        return {}
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(text) or {}
    return json.loads(text)


def _json_or_none(value: str | None) -> dict | None:
    if not value:
        return None
    return json.loads(value)


def main():
    parser = argparse.ArgumentParser(description="Run generic book pipeline")
    parser.add_argument("--topic", required=False, default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--urls", nargs="*", default=[])
    parser.add_argument("--docs", nargs="*", default=[])
    parser.add_argument("--template", default=None)
    parser.add_argument("--style-profile", default=None)
    parser.add_argument("--to-pdf", action="store_true")
    parser.add_argument("--pdf-theme", default=None, help="JSON string")
    parser.add_argument("--illustrations", default=None, help="JSON string")
    parser.add_argument("--skip-humanize", action="store_true")
    parser.add_argument("--skip-review", action="store_true")
    args = parser.parse_args()

    manifest = _load_manifest(args.manifest)
    topic = args.topic or manifest.get("topic") or manifest.get("title")
    if not topic:
        raise ValueError("Missing topic. Provide --topic or --manifest.")

    config_path = args.config or (Path(__file__).parent / "config" / "settings.yaml")
    settings = load_settings(config_path)

    sources = manifest.get("sources", {})
    output_cfg = manifest.get("output", {})
    pdf_cfg = manifest.get("pdf", {})

    urls = args.urls if args.urls else sources.get("urls", [])
    docs = args.docs if args.docs else sources.get("local_docs", [])

    render_options = {
        "to_pdf": bool(args.to_pdf or manifest.get("to_pdf")),
        "title": manifest.get("title") or topic,
        "subtitle": manifest.get("subtitle", ""),
        "author": manifest.get("author", ""),
        "basename": output_cfg.get("basename"),
        "style_profile": args.style_profile or manifest.get("style_profile"),
        "pdf_theme": (pdf_cfg.get("theme") or {}) | (_json_or_none(args.pdf_theme) or {}),
        "illustration": (manifest.get("illustration") or {}) | (_json_or_none(args.illustrations) or {}),
    }

    pipeline = DocPipeline(settings=settings)
    result = pipeline.run(
        topic=topic,
        extra_urls=urls or None,
        local_docs=docs or None,
        template=args.template or manifest.get("template"),
        skip_humanize=args.skip_humanize,
        skip_review=args.skip_review,
        render_options=render_options,
    )

    print("Done")
    for item in result.exported_files:
        print(item)


if __name__ == "__main__":
    main()
