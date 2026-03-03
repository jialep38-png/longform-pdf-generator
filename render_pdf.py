#!/usr/bin/env python3
"""Stable CLI: Markdown -> publication-grade PDF."""

import argparse
from pathlib import Path

from src.assembler.builder import DocAssembler
from src.llm_provider import load_settings


def main():
    parser = argparse.ArgumentParser(description="Render publication-grade PDF from markdown")
    parser.add_argument("markdown", help="Input markdown path")
    parser.add_argument("--config", default=None)
    parser.add_argument("--title", default=None)
    parser.add_argument("--subtitle", default="")
    parser.add_argument("--author", default="")
    parser.add_argument("--basename", default=None)
    parser.add_argument("--illustration-mode", default=None, choices=["none", "placeholder", "generated"])
    args = parser.parse_args()

    config_path = args.config or (Path(__file__).parent / "config" / "settings.yaml")
    settings = load_settings(config_path)
    assembler = DocAssembler(llm=None, settings=settings)

    illustration = None
    if args.illustration_mode:
        illustration = {"mode": args.illustration_mode}

    markdown_path = Path(args.markdown)
    title = args.title or markdown_path.stem
    pdf_path = assembler.render_pdf(
        markdown_path=markdown_path,
        title=title,
        subtitle=args.subtitle,
        author=args.author,
        basename=args.basename,
        illustration=illustration,
    )
    print(pdf_path)


if __name__ == "__main__":
    main()
