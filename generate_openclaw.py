"""
OpenClaw 教学文档生成器 — 独立脚本
读取 text/ 参考资料，逐章调用 API 生成 50000+ 字教学文档。
仅依赖 openai + pyyaml。
"""

import json
import os
import time
import sys
import io
from pathlib import Path
from openai import OpenAI

# Windows 控制台 UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── 配置 ──────────────────────────────────────────────────
API_KEY = os.environ.get("DOCGEN_API_KEY", "").strip()
BASE_URL = os.environ.get("DOCGEN_BASE_URL", "").strip()
MODEL = os.environ.get("DOCGEN_MODEL", "gpt-4o-mini").strip()
MAX_TOKENS = int(os.environ.get("DOCGEN_MAX_TOKENS", "4096"))
TEMPERATURE = float(os.environ.get("DOCGEN_TEMPERATURE", "0.75"))
REF_CHAR_LIMIT = int(os.environ.get("DOCGEN_REF_CHAR_LIMIT", "2500"))
PART_TARGET_CHARS = int(os.environ.get("DOCGEN_PART_TARGET_CHARS", "1200"))
PART_MAX_TOKENS = int(os.environ.get("DOCGEN_PART_MAX_TOKENS", "1800"))
PART_RETRIES = int(os.environ.get("DOCGEN_PART_RETRIES", "4"))

PROJECT_DIR = Path(__file__).parent
TEXT_DIR = PROJECT_DIR / "text" / "openclaw101-main"
OUTPUT_DIR = PROJECT_DIR / "data" / "output"
OUTPUT_FILE = OUTPUT_DIR / "openclaw_complete_guide.md"
PROGRESS_FILE = OUTPUT_DIR / "progress.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

if not API_KEY:
    raise RuntimeError(
        "缺少环境变量 DOCGEN_API_KEY。为避免泄露，已禁止在代码中内置 API Key。"
    )

client_kwargs = {"api_key": API_KEY, "timeout": 300}
if BASE_URL:
    client_kwargs["base_url"] = BASE_URL
client = OpenAI(**client_kwargs)

# ── 参考文件映射 ──────────────────────────────────────────
REF_FILES = {
    "llms": TEXT_DIR / "public" / "llms-full.txt",
    "day1": TEXT_DIR / "content" / "days" / "day1.md",
    "day2": TEXT_DIR / "content" / "days" / "day2.md",
    "day3": TEXT_DIR / "content" / "days" / "day3.md",
    "day4": TEXT_DIR / "content" / "days" / "day4.md",
    "day5": TEXT_DIR / "content" / "days" / "day5.md",
    "day6": TEXT_DIR / "content" / "days" / "day6.md",
    "day7": TEXT_DIR / "content" / "days" / "day7.md",
}


def load_ref(key: str) -> str:
    path = REF_FILES.get(key)
    if path and path.exists():
        return path.read_text(encoding="utf-8")
    return ""


# ── 人设系统提示词 ──────────────────────────────────────────
PERSONA_SYSTEM = """你是一位拥有 10 年 AI 从业经验的资深架构师，从传统 ML 到大模型时代，亲历过多个百万级项目的落地。你正在撰写一本关于 OpenClaw（开源 AI 助手框架）的深度教学手册。

写作风格要求：
1. 务实直接，偶尔犀利。用工程圈的黑话但要让新手也能理解
2. 自然穿插个人经验（"我当年就是因为…"、"踩过这个坑的人都知道…"）
3. 用做菜、盖房子、开车等生活比喻解释技术概念
4. 约 20% 短句（<15字）增加节奏感，15% 设问句引导思考
5. 长段（3-5句）和短段（1-2句）交替出现
6. 代码示例保留完整，用 ```bash 或 ```markdown 包裹
7. 适当使用 💡提示框、⚠️注意框、🗣️经验分享框（用 > 引用块实现）
8. 绝对禁止使用以下词汇：总之、综上所述、深入浅出、值得注意的是、不仅如此、需要指出的是、毋庸置疑、显而易见、不言而喻、众所周知、由此可见、换言之、简而言之、一言以蔽之、与此同时、在这个过程中、从某种意义上说、不可否认、令人惊叹、令人瞩目
9. 每章要有清晰的内部结构：小标题、分点、代码示例、经验分享
10. 写出来的内容要像一个真正懂行的人在跟朋友分享经验，不是在写教科书"""

# ── 章节定义 ──────────────────────────────────────────────
CHAPTERS = [
    {
        "id": "preface",
        "title": "序章：为什么你需要一个 AI 分身",
        "refs": ["llms", "day1"],
        "target_chars": 2500,
        "prompt": """撰写序章，主题：为什么每个人都需要一个 AI 私人助手。

要点：
- 以一个生动的场景开头（比如凌晨被邮件吵醒、出差时忘记重要日程等）
- AI 聊天机器人 vs 真正的 AI 助手：本质区别
- OpenClaw 是什么：一句话概括（开源 AI 助手框架，让 AI 有了"身体"）
- 这本手册会带读者走完从零到拥有一个 24 小时在线私人助手的完整旅程
- 适合谁读：对 AI 感兴趣的技术人、想提升效率的职场人、独立开发者
- 不需要什么：不需要深厚的编程基础，会用命令行就够了

目标字数：约 2500 字。语气：轻松但有分量，让读者感到"这件事值得我花时间"。"""
    },
    {
        "id": "ch01",
        "title": "第一章：AI 助手的真正形态——不只是聊天",
        "refs": ["day1", "llms"],
        "target_chars": 3500,
        "prompt": """撰写第一章，深入解释 AI 助手与聊天机器人的本质区别。

要点：
- 从 ChatGPT/文心一言等聊天工具说起，大家已经习惯了"对话式 AI"
- 但这些工具的局限：没有持久记忆、不能主动行动、不能操作外部工具
- 真正的 AI 助手需要什么：记忆（Memory）、工具（Tools）、自主性（Autonomy）
- 类比：ChatGPT 是一个很聪明的接线员，OpenClaw 助手是你的私人秘书
- OpenClaw 的核心架构简介：Gateway（大脑）、Channels（感官）、Skills（技能）
- 文件式记忆系统：SOUL.md（灵魂/性格）、USER.md（关于你的信息）、MEMORY.md（记忆）
- 一个真实场景的完整流程：你说"帮我看看今天有没有重要邮件"→ 助手的处理链路
- 为什么选 OpenClaw：开源、自托管、数据安全、高度可定制

参考资料中的关键信息要融入文中，但不要照抄，要用自己的话重新组织。
目标字数：约 3500 字。"""
    },
    {
        "id": "ch02",
        "title": "第二章：OpenClaw 深度解读——架构、生态与社区",
        "refs": ["llms", "day1", "day7"],
        "target_chars": 3500,
        "prompt": """撰写第二章，全面介绍 OpenClaw 的技术架构和生态系统。

要点：
- OpenClaw 的前世今生：从 Clawdbot/Moltbot 到 OpenClaw 的演变
- 技术栈：Node.js + TypeScript，为什么选这个技术栈（生态丰富、异步IO天然适合）
- 三大核心组件详解：
  * Gateway：中枢大脑，负责理解意图、调度技能、管理记忆
  * Channels：连接外部世界的通道（Telegram、Discord、WhatsApp）
  * Skills：插件化的能力扩展系统
- 支持的 AI 模型：Claude（推荐）、GPT-4、Gemini、Grok、OpenRouter
- 社区现状：GitHub 星标增长、Discord 活跃度、中文社区
- 与其他框架的对比（LangChain、AutoGPT、MetaGPT），OpenClaw 的差异化优势
- 成本概览：服务器 $5-20/月 + API $3-15/月 ≈ 一杯咖啡的日均成本

目标字数：约 3500 字。用架构图的文字描述代替真实图片。"""
    },
    {
        "id": "ch03",
        "title": "第三章：环境准备——磨刀不误砍柴工",
        "refs": ["day2"],
        "target_chars": 3500,
        "prompt": """撰写第三章，详细的环境准备指南。

要点：
- 需要什么：一台 Linux 服务器（推荐）或本地电脑（测试用）
- 服务器选择指南：
  * Hetzner（性价比之王，CAX11 约 $4/月）
  * DigitalOcean（新手友好）
  * 国内：腾讯云/阿里云轻量应用服务器
  * 配置建议：2核4G 起步
- 从零开始的服务器初始化：
  * 创建非 root 用户
  * SSH 密钥配置（附完整命令）
  * 基础安全设置（防火墙、fail2ban）
- Node.js 20+ 安装（用 nvm，附命令）
- AI API 密钥获取：
  * Anthropic Claude（推荐，最适合 Agent 场景）
  * OpenAI
  * 第三方中转（适合国内用户）
- Telegram Bot 创建：@BotFather 完整流程
- 环境变量配置与 .env 文件

每个步骤都要附带完整的可执行命令。
目标字数：约 3500 字。"""
    },
    {
        "id": "ch04",
        "title": "第四章：安装 OpenClaw——十分钟上线你的 AI 助手",
        "refs": ["day2"],
        "target_chars": 4000,
        "prompt": """撰写第四章，OpenClaw 的完整安装流程。

要点：
- 安装前检查清单（Node.js 版本、API Key 就绪、Telegram Bot Token）
- 克隆仓库（附命令）
- 首次运行配置向导（逐步截图式描述每一步选择）
- 配置文件详解：
  * 主配置文件结构
  * AI 模型选择与切换
  * Telegram 通道配置
- 第一次启动：`openclaw start`
- 验证安装：在 Telegram 里发第一条消息
- 常见安装问题排查：
  * Node.js 版本不对
  * API Key 无效
  * 网络连接问题（特别是国内环境）
  * 端口被占用
  * 权限问题
- 用 PM2 保持后台运行（附完整配置）
- 开机自启动设置

> 🗣️ 经验分享：我见过最多的安装失败原因不是技术问题，是…

目标字数：约 4000 字。要让完全没经验的人也能跟着做成功。"""
    },
    {
        "id": "ch05",
        "title": "第五章：灵魂塑造——让 AI 从「通用」变成「你的」",
        "refs": ["day3"],
        "target_chars": 4000,
        "prompt": """撰写第五章，深入讲解 OpenClaw 的灵魂配置系统。

要点：
- 为什么需要"灵魂"：同样的大模型，配置不同，表现天差地别
- 灵魂三件套详解：
  * SOUL.md — 定义助手的身份、性格、行为边界
    - 名字和人设
    - 语气风格（严肃/轻松/专业）
    - "绝对不做"清单（安全边界）
    - 常用工具偏好
  * USER.md — 关于你的一切
    - 工作习惯
    - 项目信息
    - 偏好设置
    - 重要联系人
  * AGENTS.md — 工作空间规则
    - 目录结构说明
    - 代码规范
    - 工作流程偏好
- 提供 3 个完整的 SOUL.md 示例：
  * 风格 A：严谨专业型（适合工作场景）
  * 风格 B：轻松幽默型（适合个人助手）
  * 风格 C：极简高效型（适合开发者）
- Prompt Engineering 技巧：
  * 具体 > 模糊
  * 正面描述 > 负面描述
  * 给例子 > 给规则
- 迭代优化：灵魂是"养"出来的，不是一次写好的

目标字数：约 4000 字。附带完整可复制的配置示例。"""
    },
    {
        "id": "ch06",
        "title": "第六章：接入 Gmail——让助手管理你的邮件",
        "refs": ["day4"],
        "target_chars": 3500,
        "prompt": """撰写第六章，Gmail 集成的完整教程。

要点：
- 为什么从邮件开始：邮件是最普遍的工作入口，也是最耗时的
- Google OAuth 2.0 配置（这是最复杂的部分，要写得特别详细）：
  * 创建 Google Cloud 项目
  * 启用 Gmail API
  * 配置 OAuth 同意屏幕
  * 创建 OAuth 客户端凭证
  * 下载 credentials.json
  * 首次授权流程
- OpenClaw 中配置 Gmail：
  * 将凭证文件放到正确位置
  * 测试连接
  * 授权范围说明（读取、发送、标签管理）
- 实际使用场景：
  * "帮我看看今天有没有重要邮件" — 助手如何筛选
  * "给张总回一封邮件，就说…" — 助手如何草拟和发送
  * 自动邮件分类和摘要
- 安全注意事项：
  * Token 文件权限设置
  * 定期检查授权范围
  * 发送邮件前确认机制
- 常见问题：OAuth 回调失败、Token 过期、权限不足

目标字数：约 3500 字。OAuth 部分要写得像手把手教。"""
    },
    {
        "id": "ch07",
        "title": "第七章：接入 Google Calendar——你的时间管理搭档",
        "refs": ["day4"],
        "target_chars": 3000,
        "prompt": """撰写第七章，Google Calendar 集成教程。

要点：
- 日历 + AI = 智能时间管理
- 配置步骤（比 Gmail 简单，因为 OAuth 已完成）：
  * 启用 Calendar API
  * 授权日历访问
  * 测试读取今日日程
- 核心功能演示：
  * 查看日程："我今天下午有什么安排？"
  * 创建事件："帮我约周五下午两点和李明开会，地点在 3 号会议室"
  * 智能提醒："明天有什么重要的事需要准备？"
  * 冲突检测："下周三下午有空吗？"
- 与邮件的协同：
  * 收到会议邀请邮件 → 自动添加到日历
  * 日程变更 → 自动通知相关人
- 进阶玩法：
  * 每日日程摘要（配合心跳机制，第十章会详细讲）
  * 智能排程建议
  * 多日历管理

目标字数：约 3000 字。"""
    },
    {
        "id": "ch08",
        "title": "第八章：浏览器与搜索——给助手装上眼睛",
        "refs": ["day4"],
        "target_chars": 3500,
        "prompt": """撰写第八章，Web 浏览和搜索能力的集成。

要点：
- 为什么 AI 助手需要"上网"：信息实时性、价格查询、竞品分析等
- Browser Relay 机制：
  * 原理：在你的电脑上安装浏览器扩展，助手通过它操控真实的 Chrome
  * 为什么不用无头浏览器：反爬虫、登录态、Cookie
  * 安装 Browser Relay 扩展
  * 配置连接
- 搜索能力：
  * 内置搜索（DuckDuckGo）
  * Google 搜索集成
  * 搜索结果解析和摘要
- 实际应用场景：
  * "帮我搜一下最近 Transformer 架构的新进展"
  * "查一下从北京到上海的高铁票价"
  * "打开我的 GitHub 仓库，看看有没有新的 Issue"
  * "帮我在京东上找一款性价比高的机械键盘"
- 浏览器自动化的边界：
  * 能做什么：读取页面、填写表单、点击按钮
  * 不该做什么：绕过验证码、自动购物（除非你明确授权）
- 安全提醒：浏览器是强大但敏感的工具

目标字数：约 3500 字。"""
    },
    {
        "id": "ch09",
        "title": "第九章：Skills 技能系统——像 App Store 一样扩展能力",
        "refs": ["day5"],
        "target_chars": 4000,
        "prompt": """撰写第九章，Skills 技能生态的完整介绍。

要点：
- Skills 的设计哲学：一个 Markdown 文件就是一个技能
- 这个设计有多优雅：
  * 不需要写代码（大部分情况）
  * 不需要 SDK 或注册
  * 人类可读、AI 可理解
  * 版本控制友好（就是文本文件）
- 安装 Skill 的三种方式：
  * 从 ClawHub 一键安装
  * 从 GitHub 克隆
  * 自己写
- 热门 Skills 推荐（每个都详细介绍用途和效果）：
  * SEO 分析（Google Search Console + Analytics）
  * PDF 解析与生成
  * 文字转语音（TTS）
  * 社交媒体管理
  * 代码仓库管理
  * 图片分析
  * 翻译
- SKILL.md 的结构解析：
  * 能力声明
  * 使用方法
  * 输出格式
  * 错误处理
- 自己写一个 Skill 的完整教程：
  * 以"天气查询"为例
  * 从需求到实现的完整过程
  * 调试技巧
- Skills 生态的未来：社区驱动、能力无限扩展

目标字数：约 4000 字。"""
    },
    {
        "id": "ch10",
        "title": "第十章：心跳机制——让助手主动为你工作",
        "refs": ["day6"],
        "target_chars": 4000,
        "prompt": """撰写第十章，心跳（Heartbeat）机制的深度教程。

要点：
- 从"被动响应"到"主动工作"：这是 AI 助手的分水岭
- 什么是心跳：定期唤醒助手，让它检查是否有需要做的事
- 心跳的工作原理：
  * 定时触发（默认每 30 分钟）
  * 读取 HEARTBEAT.md 配置
  * 按照配置检查各项任务
  * 有事就处理，没事就静默
- HEARTBEAT.md 配置详解：
  * 检查频率设置
  * 检查项目列表
  * 优先级排序
  * 通知条件
- 实际配置示例（完整可用）：
  * 每 30 分钟检查重要邮件
  * 每天早上 8 点发送日程摘要
  * 监控 GitHub 仓库的新 Issue
  * 定期检查服务器状态
- 与人的边界：
  * 什么时候该通知你
  * 什么时候该自动处理
  * 什么时候该等你确认
- 调优建议：
  * 频率不要太高（烧钱 + 打扰）
  * 从少量检查项开始，逐步增加
  * 定期清理不再需要的检查项

> 🗣️ 经验分享：心跳机制的最佳实践——配好心跳后第一周你会觉得"好像也没干什么"，一个月后你会发现离不开它了。

目标字数：约 4000 字。"""
    },
    {
        "id": "ch11",
        "title": "第十一章：定时任务与自动化工作流",
        "refs": ["day6"],
        "target_chars": 3000,
        "prompt": """撰写第十一章，Cron 定时任务和自动化工作流。

要点：
- 心跳 vs Cron：心跳是"巡逻"，Cron 是"定点执行"
- OpenClaw 的 Cron 系统：
  * 配置语法（类似 Linux crontab）
  * 任务定义格式
  * 执行日志查看
- 常用自动化任务模板（每个都附完整配置）：
  * 每日晨报：天气 + 日程 + 重要邮件摘要
  * 每周周报：自动汇总本周工作
  * 定期备份：工作目录和配置文件
  * 数据监控：API 用量、服务器状态
  * 社交媒体定时发布
- 自动化工作流设计思路：
  * 触发条件 → 处理逻辑 → 输出动作
  * 链式任务：A 完成后自动触发 B
  * 条件分支：根据结果决定下一步
- 实战案例：搭建一个自动化邮件监控 + 摘要 + 日历提醒的完整工作流
- 调试和监控：
  * 查看任务执行历史
  * 失败重试机制
  * 告警设置

目标字数：约 3000 字。"""
    },
    {
        "id": "ch12",
        "title": "第十二章：记忆系统——越用越懂你",
        "refs": ["day6", "day3"],
        "target_chars": 3500,
        "prompt": """撰写第十二章，OpenClaw 的记忆管理系统。

要点：
- AI 记忆的三个层次：
  * 短期记忆：当前对话上下文（所有 LLM 都有）
  * 中期记忆：会话间的任务状态和偏好
  * 长期记忆：持久化的知识和关于你的认识
- OpenClaw 的文件式记忆：
  * MEMORY.md — 自动积累的认知
  * 记忆是如何写入的：助手在交互中自动总结和存储
  * 记忆格式和结构
- 记忆管理实践：
  * 定期检查：看看助手记住了什么
  * 手动修正：助手记错了？直接编辑文件
  * 记忆迁移：换服务器时如何保留记忆
  * 记忆清理：删除过时信息
- 记忆驱动的智能行为：
  * 了解你的工作习惯后自动调整通知时间
  * 记住你常用的项目和工具
  * 积累对你的问题解决偏好的认知
- 先发优势：
  * 使用 1 周 vs 1 个月 vs 半年的助手，能力差距是指数级的
  * 这就是为什么"现在就开始"比"等更好的版本"重要
- 隐私与安全：
  * 记忆存在你自己的服务器上
  * 没有第三方能访问
  * 你可以随时查看和删除

目标字数：约 3500 字。"""
    },
    {
        "id": "ch13",
        "title": "第十三章：多设备协作——Nodes 节点系统",
        "refs": ["day7"],
        "target_chars": 3000,
        "prompt": """撰写第十三章，OpenClaw 的 Nodes 多设备系统。

要点：
- 想象一下：你的 AI 助手不只在一台服务器上，它能"看到"你的手机、"操控"你的电脑
- Nodes 是什么：安装在不同设备上的轻量级客户端
- 三种 Node 类型：
  * 手机 Node：拍照、定位、系统通知
  * 电脑 Node：截屏、录屏、浏览器控制
  * IoT Node（树莓派）：智能家居控制
- 安装与配对流程
- 实际场景演示：
  * "帮我看看公司电脑屏幕上显示什么" → 远程截屏
  * "帮我把客厅灯关了" → 智能家居控制
  * 手机推送提醒 + 一键确认操作
- 安全考虑：
  * 设备配对审批机制
  * 操作权限分级
  * 敏感操作确认
- 这不是科幻，这是现在就能用的功能

目标字数：约 3000 字。"""
    },
    {
        "id": "ch14",
        "title": "第十四章：安全与成本——运维指南",
        "refs": ["day7"],
        "target_chars": 3500,
        "prompt": """撰写第十四章，安全加固和成本控制的完整指南。

要点：
- 你的 AI 助手能访问邮件、日历、文件、浏览器——安全是必选项
- 服务器安全清单：
  * SSH 密钥认证 + 禁用密码
  * 防火墙配置
  * fail2ban 防暴力破解
  * 非 root 用户运行
  * 系统更新策略
- API 密钥安全：
  * 环境变量存储
  * .env 文件权限
  * 定期轮换（建议 3 个月）
  * 使用限额设置
- 数据安全：
  * OAuth Token 文件权限
  * 备份策略
  * 敏感文件不入 Git
- 行为安全：
  * SOUL.md 中设置"绝对不做"清单
  * 外发消息强制确认
  * 用 trash 代替 rm
- 成本控制：
  * 典型月费：$10-35
  * API 用量监控方法
  * 心跳间隔优化
  * 大小模型混用策略
  * 不用的 Skill 及时禁用
- 月度安全检查模板（可直接使用的 checklist）

目标字数：约 3500 字。"""
    },
    {
        "id": "ch15",
        "title": "终章：这才刚刚开始",
        "refs": ["day7", "llms"],
        "target_chars": 3000,
        "prompt": """撰写终章，回顾旅程并展望未来。

要点：
- 回顾整本手册的旅程（用表格总结每章内容和成果）
- 你现在拥有的不是一个聊天机器人，是一个数字世界里的分身
- 未来趋势：
  * 模型会更强：你的助手会自动变聪明（无需改配置）
  * 成本会更低：$10/月 → 可能 $3/月
  * 多模态普及：看、听、说、动
  * Agent 协作网络：多个专业 Agent 各司其职
- 先发优势的重要性：
  * 记忆积累是指数级的
  * 用了 6 个月的助手 vs 刚搭建的，差距不是 6 个月而是 6 个月的认知积累
  * 别等"更好的版本"——最好的开始时间就是现在
- 下一步行动建议（具体可执行）：
  * 每天至少和助手对话 10 分钟
  * 每周调一次 SOUL.md
  * 每月尝试 2-3 个新 Skill
  * 加入社区（GitHub、Discord、中文社区）
- 最后一句话：工具就摆在那里。用不用，是你的事。

语气：有力量、有温度、让读者有冲劲去行动。
目标字数：约 3000 字。"""
    },
]


# ── 生成逻辑 ──────────────────────────────────────────────

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return {"completed": [], "chapters": {}}


def save_progress(progress: dict):
    PROGRESS_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def _call_generation(system_prompt: str, user_message: str, max_tokens: int) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=TEMPERATURE,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content


def generate_chapter_by_parts(chapter: dict, prev_summary: str) -> str:
    """分段生成章节，降低单次请求超时概率。"""
    # 加载参考资料
    ref_texts = []
    for ref_key in chapter["refs"]:
        content = load_ref(ref_key)
        if content:
            ref_texts.append(f"--- 参考资料 [{ref_key}] ---\n{content[:REF_CHAR_LIMIT]}\n")

    ref_block = "\n".join(ref_texts) if ref_texts else "（无额外参考资料）"
    context_block = f"\n\n前文摘要（保持连贯性）：\n{prev_summary}\n" if prev_summary else ""

    part_count = max(1, (chapter["target_chars"] + PART_TARGET_CHARS - 1) // PART_TARGET_CHARS)
    parts = []

    for idx in range(1, part_count + 1):
        print(f"  正在生成分段 {idx}/{part_count}...")

        previous_parts = "\n\n".join(
            [f"[已生成片段 {i + 1}]\n{p[:1200]}" for i, p in enumerate(parts)]
        ) if parts else "（无）"

        user_message = f"""# 当前章节：{chapter['title']}

## 参考资料
{ref_block}
{context_block}
## 写作指令
{chapter['prompt']}

## 当前任务
你正在写本章的第 {idx}/{part_count} 个连续片段。
每个片段目标约 {PART_TARGET_CHARS} 字，片段之间要自然衔接，不要重复。

已生成片段（供衔接，避免重复）：
{previous_parts}

重要：
- 只输出当前片段正文，不要输出“第X部分”等标签
- 保持与本章整体风格一致
- 输出纯 Markdown 格式
- 内容必须安全合规：不要涉及违法、危险、规避限制或恶意行为"""

        part_text = ""
        for attempt in range(PART_RETRIES):
            try:
                start = time.time()
                part_text = _call_generation(PERSONA_SYSTEM, user_message, PART_MAX_TOKENS)
                elapsed = time.time() - start
                print(f"    分段完成，{len(part_text)} 字，耗时 {elapsed:.1f}s")
                break
            except Exception as e:
                print(f"    ⚠ 分段第 {attempt + 1} 次尝试失败: {e}")
                if attempt < PART_RETRIES - 1:
                    wait = 2 ** (attempt + 1)
                    print(f"    {wait}s 后重试...")
                    time.sleep(wait)
                else:
                    raise

        parts.append(part_text)
        time.sleep(1)

    merged = "\n\n".join(parts).strip()
    print(f"  章节分段合并完成，合计 {len(merged)} 字")
    return merged


def generate_summary(chapter_title: str, chapter_text: str) -> str:
    """为已生成的章节生成摘要，用于后续章节的上下文。"""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "你是一个文档摘要助手。用 2-3 句中文概括以下章节的核心内容和关键知识点。"},
            {"role": "user", "content": f"章节标题：{chapter_title}\n\n{chapter_text[:3000]}"},
        ],
        temperature=0.3,
        max_tokens=300,
    )
    return resp.choices[0].message.content.strip()


def assemble_document(progress: dict) -> str:
    """组装最终文档。"""
    parts = []
    # 封面
    parts.append("# OpenClaw 完全指南：从零搭建你的 AI 私人助手\n")
    parts.append("> **一本写给所有人的 AI 助手实战手册**\n")
    parts.append("> 作者：资深 AI 架构师 | 基于 OpenClaw 开源框架\n")
    parts.append("---\n")

    # 目录
    parts.append("## 目录\n")
    for ch in CHAPTERS:
        anchor = ch["id"]
        parts.append(f"- [{ch['title']}](#{anchor})")
    parts.append("\n---\n")

    # 正文
    for ch in CHAPTERS:
        text = progress["chapters"].get(ch["id"], "")
        if text:
            parts.append(f"<a id=\"{ch['id']}\"></a>\n")
            parts.append(f"## {ch['title']}\n")
            parts.append(text)
            parts.append("\n\n---\n")

    # 尾注
    parts.append("## 附录：资源汇总\n")
    parts.append("""
| 资源 | 链接 |
|------|------|
| OpenClaw GitHub | https://github.com/openclaw/openclaw |
| 官方文档 | https://docs.openclaw.ai |
| ClawHub 技能市场 | https://clawhub.com |
| Discord 社区 | https://discord.com/invite/clawd |
| OpenClaw 101 教程 | https://openclaw101.dev |

---

*本手册基于 OpenClaw 开源框架编写，内容持续更新。*
*如有问题或建议，欢迎在社区交流。*
""")

    return "\n".join(parts)


# ── 主流程 ──────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  OpenClaw 教学文档生成器")
    print("=" * 60)
    print(f"  模型: {MODEL}")
    print(f"  章节数: {len(CHAPTERS)}")
    print(f"  输出: {OUTPUT_FILE}")
    print()

    progress = load_progress()

    # 修复历史状态：失败占位章节不应视为 completed
    chapters_map = progress.get("chapters", {})
    failed_placeholder = "*[章节生成失败，请重新运行]*"
    normalized_completed = []
    for cid in progress.get("completed", []):
        text = chapters_map.get(cid, "")
        if isinstance(text, str) and text.strip().startswith(failed_placeholder):
            continue
        normalized_completed.append(cid)
    progress["completed"] = normalized_completed

    completed = set(progress.get("completed", []))
    rolling_summary = ""

    # 构建前文摘要
    for ch in CHAPTERS:
        if ch["id"] in completed:
            s = progress.get("summaries", {}).get(ch["id"], "")
            if s:
                rolling_summary = s  # 使用最近完成的章节摘要

    total_chars = 0
    for ch in CHAPTERS:
        cid = ch["id"]

        if cid in completed:
            existing = progress["chapters"].get(cid, "")
            char_count = len(existing)
            total_chars += char_count
            print(f"[跳过] {ch['title']}（已完成，{char_count} 字）")
            continue

        print(f"\n{'─' * 50}")
        print(f"[生成] {ch['title']}")
        print(f"{'─' * 50}")

        retries = 3
        text = ""
        success = False
        for attempt in range(retries):
            try:
                text = generate_chapter_by_parts(ch, rolling_summary)
                success = True
                break
            except Exception as e:
                print(f"  ⚠ 第 {attempt+1} 次尝试失败: {e}")
                if attempt < retries - 1:
                    wait = 2 ** (attempt + 1)
                    print(f"  {wait}s 后重试...")
                    time.sleep(wait)
                else:
                    print(f"  ✗ 章节 {cid} 生成失败，跳过")
                    text = f"*[章节生成失败，请重新运行]*\n"

        # 保存章节
        progress.setdefault("chapters", {})[cid] = text
        if success:
            progress.setdefault("completed", []).append(cid)
            completed.add(cid)

            # 生成摘要
            try:
                summary = generate_summary(ch["title"], text)
                progress.setdefault("summaries", {})[cid] = summary
                rolling_summary = summary
            except Exception as e:
                print(f"  ⚠ 摘要生成失败: {e}")

        total_chars += len(text)
        save_progress(progress)
        print(f"  ✓ 累计字数: {total_chars}")

        # 避免 rate limit
        time.sleep(2)

    # 组装最终文档
    print(f"\n{'=' * 60}")
    print("组装最终文档...")
    document = assemble_document(progress)
    OUTPUT_FILE.write_text(document, encoding="utf-8")

    total_final = len(document)
    print(f"\n✅ 文档生成完成！")
    print(f"  总字数: {total_final}")
    print(f"  文件: {OUTPUT_FILE}")
    print(f"{'=' * 60}")

    if total_final < 45000:
        print(f"\n⚠ 总字数 {total_final} 未达到 45000 目标，建议重新运行补充章节。")


if __name__ == "__main__":
    main()
