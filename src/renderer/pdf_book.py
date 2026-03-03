from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    XPreformatted,
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String


class PDFBookRenderer:
    def __init__(self, render_config: dict | None = None):
        self.render_config = render_config or {}

        self.anchor_re = re.compile(r'<a\s+id="([^"]+)"\s*></a>', re.I)
        self.fence_re = re.compile(r"^\s*```")
        self.link_re = re.compile(r'\[([^\]]+)\]\(#([^\)]+)\)')
        self.unfenced_cmd_re = re.compile(
            r"^(?:[$#]\\s*)?(?:sudo\\s+)?(?:"
            r"cd|ls|pwd|cat|echo|grep|find|awk|sed|xargs|curl|wget|git|py|python|python3|pip|pip3|"
            r"npm|npx|pnpm|yarn|node|uv|docker|docker-compose|kubectl|helm|systemctl|service|"
            r"chmod|chown|cp|mv|rm|mkdir|touch|export|set|source|ssh|scp|rsync|crontab|pm2|"
            r"nohup|tail|head|less|vim|nano|tee|jq|make|cmake|go|cargo|java|mvn|gradle|poetry|"
            r"bash|sh)\\b"
        )
        self.unfenced_assign_re = re.compile(r"^[A-Z_][A-Z0-9_]*\\s*=\\s*.+$")
        self.unfenced_path_re = re.compile(r"^(?:\\./|\\.\\./|/|~/)\\S+")

        self.default_font = "Helvetica"
        self._register_fonts()
        self.styles = self._build_styles()

    def _register_fonts(self):
        # Prefer real CJK fonts on Windows for stable Chinese rendering.
        candidates = [
            ("SimHei", "C:/Windows/Fonts/simhei.ttf"),
            ("MicrosoftYaHei", "C:/Windows/Fonts/msyh.ttc"),
            ("SimSun", "C:/Windows/Fonts/simsun.ttc"),
            ("STSong-Light", None),
        ]

        for font_name, font_path in candidates:
            try:
                if font_path is None:
                    pdfmetrics.registerFont(UnicodeCIDFont(font_name))
                else:
                    if Path(font_path).exists() and font_name not in pdfmetrics.getRegisteredFontNames():
                        pdfmetrics.registerFont(TTFont(font_name, font_path))
                self.default_font = font_name
                return
            except Exception:
                continue

    def _build_styles(self):
        theme = self.render_config.get("pdf", {}).get("theme", {})
        base_font = self._select_font(theme.get("font"))
        self.base_font = base_font

        styles = getSampleStyleSheet()
        h2 = ParagraphStyle(
            "H2",
            parent=styles["Heading2"],
            fontName=base_font,
            fontSize=theme.get("h2_size", 16),
            leading=theme.get("h2_leading", 24),
            spaceBefore=10,
            spaceAfter=6,
            textColor=colors.HexColor(theme.get("heading_color", "#111827")),
            wordWrap="CJK",
        )
        h3 = ParagraphStyle(
            "H3",
            parent=styles["Heading3"],
            fontName=base_font,
            fontSize=theme.get("h3_size", 13),
            leading=theme.get("h3_leading", 20),
            spaceBefore=8,
            spaceAfter=4,
            textColor=colors.HexColor(theme.get("subheading_color", "#1F2937")),
            wordWrap="CJK",
        )
        body = ParagraphStyle(
            "Body",
            parent=styles["BodyText"],
            fontName=base_font,
            fontSize=theme.get("body_size", 11.2),
            leading=theme.get("line_height", 18.5),
            spaceBefore=1,
            spaceAfter=6,
            textColor=colors.HexColor(theme.get("body_color", "#111827")),
            wordWrap="CJK",
        )
        list_style = ParagraphStyle("List", parent=body, leftIndent=12, wordWrap="CJK")
        quote = ParagraphStyle(
            "Quote",
            parent=body,
            leftIndent=12,
            rightIndent=6,
            backColor=colors.HexColor("#F8FAFC"),
            borderPadding=6,
            wordWrap="CJK",
        )
        warn = ParagraphStyle(
            "Warn",
            parent=body,
            leftIndent=8,
            rightIndent=6,
            backColor=colors.HexColor(theme.get("warning_bg", "#FFF9C4")),
            borderPadding=6,
            textColor=colors.HexColor(theme.get("warning_color", "#4B5563")),
            wordWrap="CJK",
        )
        code = ParagraphStyle(
            "Code",
            parent=styles["Code"],
            fontName=base_font,
            fontSize=theme.get("code_size", 9.8),
            leading=14,
            leftIndent=8,
            rightIndent=8,
            backColor=colors.HexColor("#F3F4F6"),
            textColor=colors.HexColor("#111827"),
            borderPadding=6,
            borderColor=colors.HexColor("#D1D5DB"),
            borderWidth=0.6,
            spaceBefore=5,
            spaceAfter=9,
            wordWrap="CJK",
        )
        toc_entry = ParagraphStyle("TOCEntry", parent=body, fontSize=11, leading=16)
        cover_title = ParagraphStyle(
            "CoverTitle",
            parent=styles["Title"],
            fontName=base_font,
            fontSize=30,
            leading=38,
            textColor=colors.HexColor("#0F172A"),
        )
        cover_sub = ParagraphStyle(
            "CoverSub",
            parent=styles["Normal"],
            fontName=base_font,
            fontSize=16,
            leading=24,
            textColor=colors.HexColor("#334155"),
        )
        cover_meta = ParagraphStyle(
            "CoverMeta",
            parent=styles["Normal"],
            fontName=base_font,
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#64748B"),
        )
        toc_title = ParagraphStyle(
            "TOCTitle",
            parent=styles["Heading1"],
            fontName=base_font,
            fontSize=24,
            leading=30,
            textColor=colors.HexColor("#0F172A"),
        )

        return {
            "H2": h2,
            "H3": h3,
            "BODY": body,
            "LIST": list_style,
            "QUOTE": quote,
            "WARN": warn,
            "CODE": code,
            "TOC_ENTRY": toc_entry,
            "COVER_TITLE": cover_title,
            "COVER_SUB": cover_sub,
            "COVER_META": cover_meta,
            "TOC_TITLE": toc_title,
        }

    def _select_font(self, preferred: str | None) -> str:
        if preferred:
            if preferred in pdfmetrics.standardFonts or preferred in pdfmetrics.getRegisteredFontNames():
                return preferred
        return self.default_font

    def render(
        self,
        markdown_text: str,
        output_path: str | Path,
        *,
        title: str,
        subtitle: str = "",
        author: str = "",
        illustration: dict | None = None,
    ) -> str:
        lines = markdown_text.splitlines()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        body_lines = self._strip_old_toc(lines)
        has_fenced_code = any(self.fence_re.match(ln) for ln in body_lines)
        use_unfenced_heuristic = not has_fenced_code and self.render_config.get("pdf", {}).get("unfenced_code_fallback", True)

        story = self._build_frontmatter(title=title, subtitle=subtitle, author=author)
        toc = TableOfContents()
        toc.levelStyles = [self.styles["TOC_ENTRY"]]
        toc.dotsMinLevel = 0
        story.append(toc)
        story.append(PageBreak())

        in_code = False
        code_buf = []
        auto_code_buf = []
        pending_anchor = None
        h2_count = 0

        for ln in body_lines:
            raw = ln.rstrip("\n")
            m = self.anchor_re.search(raw.strip())
            if m:
                pending_anchor = m.group(1)
                continue

            if raw.strip().startswith("```"):
                if not in_code:
                    in_code = True
                    code_buf = []
                else:
                    in_code = False
                    flow = self._render_code_block(code_buf)
                    if flow:
                        story.append(flow)
                    code_buf = []
                continue

            if in_code:
                code_buf.append(raw)
                continue

            if use_unfenced_heuristic:
                if auto_code_buf:
                    if self._looks_like_unfenced_code(raw) or not raw.strip():
                        auto_code_buf.append(raw)
                        continue
                    flow = self._render_code_block(auto_code_buf)
                    if flow:
                        story.append(flow)
                    auto_code_buf = []
                if self._looks_like_unfenced_code(raw):
                    auto_code_buf = [raw]
                    continue

            plain = self._clean_plain(raw)
            if not plain:
                story.append(Spacer(1, 2.5 * mm))
                continue

            if raw.startswith("# "):
                continue

            if raw.startswith("## "):
                h2_count += 1
                title_rich = self._to_rich_text(raw[3:])
                p = Paragraph(title_rich, self.styles["H2"])
                if pending_anchor:
                    p._bookmarkName = pending_anchor
                    pending_anchor = None
                else:
                    plain_title = self._clean_plain(raw[3:])
                    p._bookmarkName = f"toc_{h2_count}_{self._slugify(plain_title)}"
                story.append(p)
                visual = self._chapter_visual(h2_count, plain, illustration)
                if visual:
                    story.append(Spacer(1, 2 * mm))
                    story.append(visual)
                    story.append(Spacer(1, 3 * mm))
                continue

            if raw.startswith("### "):
                story.append(Paragraph(self._to_rich_text(raw[4:]), self.styles["H3"]))
                continue

            if raw.strip() == "---":
                story.append(Spacer(1, 1 * mm))
                continue

            if raw.lstrip().startswith("- ") or raw.lstrip().startswith("* "):
                story.append(Paragraph(self._to_rich_text(raw.lstrip()[2:]), self.styles["LIST"], bulletText="•"))
                continue

            if raw.lstrip().startswith("> "):
                q = raw.lstrip()[2:]
                style = self.styles["WARN"] if ("⚠" in q or "注意" in q or "风险" in q) else self.styles["QUOTE"]
                story.append(Paragraph(self._to_rich_text(q), style))
                continue

            rich = self._to_rich_text(raw)
            if "⚠" in raw or "注意" in raw:
                rich = f"<font backColor='#FFF59D'>{rich}</font>"
            story.append(Paragraph(rich, self.styles["BODY"]))

        if code_buf:
            flow = self._render_code_block(code_buf)
            if flow:
                story.append(flow)

        if auto_code_buf:
            flow = self._render_code_block(auto_code_buf)
            if flow:
                story.append(flow)

        doc = self._build_doc(str(output_path), title)
        doc.multiBuild(story)
        return str(output_path)

    def _build_doc(self, filename: str, default_heading: str):
        styles = self.styles
        outer = self

        class BookDoc(BaseDocTemplate):
            def __init__(self, filename, **kw):
                super().__init__(filename, **kw)
                self.outer = outer
                frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
                self.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=self._on_page)])
                self.current_heading = default_heading

            def _on_page(self, canv, doc):
                p = canv.getPageNumber()
                if p <= 2:
                    return
                canv.setStrokeColor(colors.HexColor("#E5E7EB"))
                canv.setLineWidth(0.7)
                canv.line(doc.leftMargin, A4[1] - 32, A4[0] - doc.rightMargin, A4[1] - 32)
                canv.line(doc.leftMargin, 30, A4[0] - doc.rightMargin, 30)
                canv.setFont(self.outer.base_font, 9.5)
                canv.setFillColor(colors.HexColor("#64748B"))
                canv.drawString(doc.leftMargin, A4[1] - 25, self.current_heading[:42])
                canv.drawCentredString(A4[0] / 2, 18, str(p))

            def afterFlowable(self, flowable):
                if isinstance(flowable, Paragraph) and flowable.style.name == "H2":
                    txt = flowable.getPlainText()
                    key = getattr(flowable, "_bookmarkName", None) or f"h2_{self.page}_{abs(hash(txt)) % 100000}"
                    self.canv.bookmarkPage(key)
                    self.canv.addOutlineEntry(txt, key, level=0, closed=False)
                    self.notify("TOCEntry", (0, txt, self.page, key))
                    self.current_heading = txt

        theme = self.render_config.get("pdf", {}).get("theme", {})
        return BookDoc(
            filename,
            pagesize=A4,
            leftMargin=float(theme.get("margin_left_mm", 18)) * mm,
            rightMargin=float(theme.get("margin_right_mm", 18)) * mm,
            topMargin=float(theme.get("margin_top_mm", 16)) * mm,
            bottomMargin=float(theme.get("margin_bottom_mm", 14)) * mm,
        )

    def _build_frontmatter(self, *, title: str, subtitle: str, author: str):
        story = [Spacer(1, 28 * mm)]
        story.append(Paragraph(escape(title), self.styles["COVER_TITLE"]))
        if subtitle:
            story.append(Spacer(1, 6 * mm))
            story.append(Paragraph(escape(subtitle), self.styles["COVER_SUB"]))
        if author:
            story.append(Spacer(1, 10 * mm))
            story.append(Paragraph(escape(author), self.styles["COVER_META"]))
        story.append(Spacer(1, 150 * mm))
        story.append(Paragraph("AI Teaching Guide", self.styles["COVER_META"]))
        story.append(PageBreak())
        story.append(Paragraph("目录", self.styles["TOC_TITLE"]))
        story.append(Spacer(1, 4 * mm))
        return story

    def _strip_old_toc(self, lines: list[str]) -> list[str]:
        filtered = []
        in_old_toc = False

        for ln in lines:
            stripped = ln.strip()

            if stripped == "## 目录":
                in_old_toc = True
                continue

            if in_old_toc:
                if stripped.startswith("## ") and stripped != "## 目录":
                    in_old_toc = False
                    filtered.append(ln)
                elif not stripped or stripped.startswith("-"):
                    continue
                else:
                    continue
            else:
                filtered.append(ln)

        return filtered


    def _to_rich_text(self, s: str) -> str:
        s = self.link_re.sub(lambda m: m.group(1), s)
        s = s.replace("`", "")

        token_re = re.compile(r"(\\*\\*.*?\\*\\*|==.*?==)")
        parts = token_re.split(s)
        out = []
        for p in parts:
            if not p:
                continue
            if p.startswith("**") and p.endswith("**") and len(p) >= 4:
                out.append(f"<b>{escape(p[2:-2])}</b>")
            elif p.startswith("==") and p.endswith("==") and len(p) >= 4:
                out.append(f"<font backColor='#FFF59D'>{escape(p[2:-2])}</font>")
            else:
                out.append(escape(p))
        return "".join(out).strip()

    def _clean_plain(self, s: str) -> str:
        s = s.replace("**", "").replace("`", "")
        s = re.sub(r"==(.+?)==", r"\\1", s)
        s = self.link_re.sub(lambda m: m.group(1), s)
        s = re.sub(r"<[^>]+>", "", s)
        return s.strip()

    def _looks_like_unfenced_code(self, raw: str) -> bool:
        stripped = raw.strip()
        if not stripped:
            return False
        if raw.startswith("    ") or raw.startswith("\t"):
            return True
        if raw.startswith("##") or raw.startswith("###") or raw.startswith("# "):
            return False
        if raw.lstrip().startswith("- ") or raw.lstrip().startswith("* ") or raw.lstrip().startswith("> "):
            return False
        if stripped == "---":
            return False
        if self.unfenced_cmd_re.match(stripped):
            return True
        if self.unfenced_assign_re.match(stripped):
            return True
        if self.unfenced_path_re.match(stripped):
            return True
        return False

    def _chapter_illustration(self, title: str) -> Drawing:
        d = Drawing(460, 90)
        d.add(Rect(0, 0, 460, 90, rx=8, ry=8, fillColor=colors.HexColor("#F8FAFC"), strokeColor=colors.HexColor("#CBD5E1")))
        d.add(Rect(0, 0, 8, 90, fillColor=colors.HexColor("#3B82F6"), strokeColor=colors.HexColor("#3B82F6")))
        d.add(String(18, 62, "章节导图", fontName=self.base_font, fontSize=11, fillColor=colors.HexColor("#1E3A8A")))
        d.add(String(18, 40, self._clean_plain(title)[:42], fontName=self.base_font, fontSize=10, fillColor=colors.HexColor("#1F2937")))
        d.add(Circle(340, 50, 8, fillColor=colors.HexColor("#93C5FD"), strokeColor=colors.HexColor("#60A5FA")))
        d.add(Circle(380, 50, 8, fillColor=colors.HexColor("#86EFAC"), strokeColor=colors.HexColor("#4ADE80")))
        d.add(Circle(420, 50, 8, fillColor=colors.HexColor("#FDE68A"), strokeColor=colors.HexColor("#FACC15")))
        d.add(Line(348, 50, 372, 50, strokeColor=colors.HexColor("#94A3B8"), strokeWidth=1))
        d.add(Line(388, 50, 412, 50, strokeColor=colors.HexColor("#94A3B8"), strokeWidth=1))
        return d

    def _chapter_visual(self, h2_index: int, heading: str, illustration: dict | None):
        cfg = {**self.render_config.get("illustration", {}), **(illustration or {})}
        mode = cfg.get("mode", "placeholder")
        if mode == "none":
            return None

        slots = set(cfg.get("slots", []))
        if slots and h2_index not in slots:
            return None

        if mode == "generated":
            title_map = cfg.get("images_by_title", {})
            for key, path in title_map.items():
                if key in heading and Path(path).exists():
                    img = Image(str(path), width=460, height=258)
                    img.hAlign = "CENTER"
                    return img

        if mode in {"placeholder", "generated"}:
            return self._chapter_illustration(heading)

        return None

    def _render_code_block(self, code_lines: list[str]):
        text = "\n".join(code_lines).rstrip()
        if not text:
            return None
        return XPreformatted(escape(text), self.styles["CODE"])

    def _slugify(self, text: str) -> str:
        text = text.strip().lower()
        text = re.sub(r"\s+", "-", text)
        text = re.sub(r"[^a-z0-9\-\u4e00-\u9fff]", "", text)
        return text[:48] or "chapter"
