# 项目级执行约束（长文档生成主项目）

## 1. 项目范围
- 主项目：`main.py`、`run_book.py`、`render_pdf.py`、`src/`、`config/`、`data/`。
- `text/openclaw101-main` 为参考站点素材，不作为主流程代码改动目标，除非任务明确要求。

## 2. 通用开发约束
- Python 命令统一使用 `py`，禁止使用 `python`。
- 仅修改需求相关文件，优先复用现有实现。
- 禁止提交明文密钥、Token、账号密码；配置统一走环境变量。

## 3. 质量要求
- 单文件超过 1000 行时，优先拆分职责。
- 删除无用代码与无效配置，避免“兼容性残留”长期堆积。
- 代码注释使用中文，内容简洁、解释意图而非重复代码字面含义。

## 4. 测试与验证要求
每次代码改动后，至少执行以下本地检查（按需组合）：

1. 语法与导入检查（必跑）
```powershell
py -m compileall main.py run_book.py render_pdf.py src
```

2. CLI 接口检查（修改入口参数或命令行逻辑时必跑）
```powershell
py main.py --help
py run_book.py --help
py render_pdf.py --help
```

3. 渲染烟测（修改 assembler/renderer/export 相关逻辑时必跑）
```powershell
py render_pdf.py data/output/_smoke.md --title "烟测" --basename "smoke_pdf"
```

4. 单元测试与集成测试
- 若 `tests/` 已存在，必须执行：
```powershell
py -m unittest discover -s tests -p "test_*.py"
```
- 新增或变更功能时，必须补充单元测试与集成测试（使用内置 `unittest`，除非用户明确要求引入新框架）。

## 5. 提交前检查清单
- [ ] 需求相关代码改动已完成且无无关变更。
- [ ] 对应验证命令已运行并通过。
- [ ] 涉及文档治理变更时，`.agentdocs/index.md` 已同步更新。
- [ ] 无明文密钥与敏感信息泄露。
