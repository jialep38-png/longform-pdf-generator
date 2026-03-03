# 教学文档自动生成器（Long-Form PDF Generator）

一个面向开源发布的长文档生成项目：输入主题与资料，自动完成采集、规划、写作、重写、质检与导出，输出可读性强的长篇 Markdown / DOCX / PDF 文档。

## 核心能力
- 五层流水线：信息采集 -> 大纲规划 -> 分节生成 -> 风格重写 -> 组装导出。
- 多模型路由：支持 OpenAI 兼容、Anthropic、Google（通过 `config/settings.yaml` 配置）。
- RAG 检索增强：可选 ChromaDB 向量检索，增强事实与上下文一致性。
- 出版级 PDF：基于 ReportLab，支持目录、书签、页眉页脚、代码块与中文排版。
- CLI 一键运行：可通过 `main.py` / `run_book.py` 快速启动。

## 项目结构
```text
.
├── main.py / run_book.py / render_pdf.py
├── src/
│   ├── pipeline.py
│   ├── llm_provider.py
│   ├── ingestion/ planner/ generator/ humanizer/ assembler/ renderer/
├── config/
│   ├── settings.yaml
│   └── templates/*.yaml
├── data/
│   ├── output/
│   ├── raw/
│   └── vectordb/
└── scripts/
    ├── package_open_source.ps1
    └── open_source_audit.ps1
```

## 快速开始
1. 安装依赖
```powershell
py -m pip install -r requirements.txt
```

2. 配置环境变量
- 复制 `.env.example`，填入你自己的 Key。
- 不要把 `.env`、真实 Key 或会话数据提交到 GitHub。

3. 运行生成
```powershell
py main.py "你的主题" --template generic_ai_course.yaml --to-pdf
```

4. 查看产物
- 默认输出目录：`data/output/`

## 生成上百页 PDF 的建议
- 提高总字数目标：`config/settings.yaml` 中 `pipeline.target_chars`。
- 适当提高章节规模：`sections_per_chapter`、`section_max_chars`。
- 保持可读性：不要只堆字数，建议保留案例、小节结构、代码块与要点回顾。
- 先小规模验证模板，再跑大规模任务。

## 开源合规与隐私安全
- 已移除代码中的明文密钥，统一使用环境变量。
- 已提供 `.gitignore`，默认忽略输出产物、缓存、会话记录与本地私有文件。
- 发布前建议执行：
```powershell
powershell -ExecutionPolicy Bypass -File scripts/open_source_audit.ps1
```

## 常用命令
```powershell
py main.py --help
py run_book.py --help
py render_pdf.py --help
```

## 许可证
MIT（见 `LICENSE`）。
