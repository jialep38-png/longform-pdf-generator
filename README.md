# Long-Form PDF Generator / 长文档 PDF 生成器

Generate highly readable long-form teaching documents from a topic and source materials, then export to Markdown / DOCX / PDF.

输入一个主题与参考资料，自动生成结构化长文，并导出 Markdown / DOCX / PDF（适合上百页教学文档）。

## 中文说明

### 项目定位
- 面向“长文档交付”，不是单次短回答工具。
- 目标产物是可阅读、可分发、可复用的 PDF 教学文档。

### 核心能力
- 五层流水线：采集 -> 规划 -> 生成 -> 重写 -> 组装导出。
- 多模型路由：OpenAI Compatible / Anthropic / Google。
- RAG 检索增强：可选 ChromaDB，提升上下文一致性。
- 出版级 PDF：目录、书签、页眉页脚、代码块、中文排版。
- CLI 入口：`main.py`、`run_book.py`、`render_pdf.py`。

### 快速开始（Windows）
1. 安装依赖
```powershell
py -m pip install -r requirements.txt
```

2. 配置环境变量
```powershell
copy .env.example .env
```
按需填入 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` 等变量。

3. 运行生成
```powershell
py main.py "Claude Code 完全指南" --template generic_ai_course.yaml --to-pdf
```

4. 查看输出
- 默认目录：`data/output/`

### 生成上百页 PDF 的建议
- 提高 `config/settings.yaml` 中 `pipeline.target_chars`（如 70000+）。
- 增加章节规模：`sections_per_chapter`、`section_max_chars`。
- 保留可读性结构：案例、小节标题、代码块、总结段落。
- 先做小规模试跑，再进行大规模正式生成。

### 开源合规与隐私
- 本仓库不内置任何真实密钥，统一使用环境变量。
- `.gitignore` 默认排除会话记录、输出产物、向量库与缓存。
- 发布前执行审计：
```powershell
powershell -ExecutionPolicy Bypass -File scripts/open_source_audit.ps1
```

## English

### What This Project Is
- Built for long-form document delivery, not short chat answers.
- Produces publishable teaching documents, especially large PDF outputs.

### Key Features
- 5-stage pipeline: Ingestion -> Planning -> Writing -> Humanizing -> Assembly.
- Multi-provider LLM routing via config.
- Optional RAG with ChromaDB for better factual context.
- Publication-grade PDF rendering (TOC, bookmarks, headers/footers, code blocks).
- CLI-first workflow for automation and batch generation.

### Quick Start
1. Install dependencies
```powershell
py -m pip install -r requirements.txt
```

2. Configure environment
```powershell
copy .env.example .env
```
Fill in your API keys (for example `OPENAI_API_KEY`).

3. Generate a document
```powershell
py main.py "AI Agent Engineering Guide" --template generic_ai_course.yaml --to-pdf
```

4. Output location
- `data/output/`

### Recommended for 100+ Page PDFs
- Increase `pipeline.target_chars` in `config/settings.yaml`.
- Expand section/chapter budget (`sections_per_chapter`, `section_max_chars`).
- Keep readability constraints (headings, examples, summaries, code snippets).

### OSS Safety Checklist
- Run local audit before publishing:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/open_source_audit.ps1
```
- Optional packaging:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/package_open_source.ps1
```

## Project Structure
```text
.
├── main.py / run_book.py / render_pdf.py
├── src/
├── config/
├── data/
└── scripts/
```

## License
MIT. See `LICENSE`.
