# Academic Commercialization Assessment Agent

基于 [CrewAI](https://github.com/crewAIInc/crewAI) 框架开发的学术成果商业化评估智能体系统。

输入一个研究方向或论文主题，系统将自动调度多个专职 AI Agent，从学术文献、专利图谱、市场竞争三个维度完成分析，最终生成一份带可验证引用的结构化商业化评估报告和量化评分卡。

---

## 改造说明

本项目基于 CrewAI 官方模板（researcher + reporting_analyst 两个 Agent）改造而来。

| | 原始 Demo | 本项目 |
|---|---|---|
| Agent 数量 | 2（researcher + reporting_analyst） | 6（专职分工） |
| Task 数量 | 2（research_task + reporting_task） | 6（顺序执行 + guardrail 验证） |
| 工具 | 无 | OpenAlex + Semantic Scholar + SerperDevTool + Crossref |
| 输入变量 | topic + current_year | research_topic |
| 来源收集 | 无 | 运行前确定性预检索，URL 可达性验证 |
| 输出格式 | 自由文本报告 | 带 [A1][P2][M3] 行内引用 + References 区块的 Markdown 报告 + JSON 评分卡 |
| 输出管理 | 固定文件名（覆盖） | 每次运行生成唯一 ID，存入 outputs/ 目录 |
| 数据质量保障 | 无 | 结构化证据 + 引用完整性校验 + 来源最低字数过滤 + 自动重试 |

---

## Agent 架构

```
Agent 1: Academic Literature Analyst（学术前沿分析师）
         来源：Step 0 预验证的 OpenAlex / Semantic Scholar 学术论文
         输出：结构化 EvidenceReport JSON，含技术成熟度、研究突破、引用来源（A1/A2/…）

Agent 2: Patent Landscape Analyst（专利图谱分析师）
         来源：Google Patents / WIPO 专利记录（经 Serper 检索 + URL 验证）
         输出：结构化 EvidenceReport JSON，含专利持有人、空白领域（P1/P2/…）

Agent 3: Market & Competitive Intelligence Analyst（市场情报分析师）
         来源：域名白名单过滤的市场报告（Serper 检索）
         输出：结构化 EvidenceReport JSON，含商业玩家、目标行业、市场机会（M1/M2/…）

Agent 4: Technology Commercialization Report Writer（报告撰写师）
         工具：无（以前三个 Agent 输出作为上下文）
         输出：Markdown 报告草稿，含行内引用标注 [A1][P2][M3] 和 References 区块
         校验：章节、正文引用、References 和数字引用完整性，不通过则自动重试（最多 2 次）

Agent 5: Report Reviewer（质量审查员）
         工具：无（以 Agent 4 草稿作为输入）
         输出：修正后的最终报告，末尾附 Reviewer Notes 列出所有修改

Agent 6: Commercialization Readiness Scorer（量化评分员）
         工具：无（以 Task 1/2/3 结构化证据为输入，独立于报告流程）
         输出：CommercializationScore JSON 评分卡，含 TRL / 专利 / 市场 / 证据置信度四维评分
         校验：JSON 格式验证 + 加权公式自动修正 overall_score，不通过则自动重试（最多 2 次）
```

---

## 执行流程

```
Step 0  来源收集与验证（运行前，确定性）
        学术：OpenAlex Works API（filter=title.search，按引用数降序）
              → Semantic Scholar 补充（当 OpenAlex 不足最大来源数时触发）
              → 按 DOI 去重，摘要 <150 字符的记录自动剔除
        专利：Serper 检索 Google Patents / WIPO，验证 URL 可达性
        市场：Serper 检索 + 域名白名单过滤（30+ 认可机构），剔除低质量站点
        元数据：Crossref API 补充 DOI、期刊名、发表日期
        输出 validated_sources.json 并传入 Crew

        ↓

Step 1  Agent 1 执行 — 学术文献分析
        仅分析 Step 0 预验证的学术来源（A1/A2/…）
        输出结构化 EvidenceReport JSON（guardrail 校验来源引用）

        ↓

Step 2  Agent 2 执行 — 专利图谱分析
        仅分析来自官方专利库的来源（P1/P2/…）
        输出结构化 EvidenceReport JSON（guardrail 校验来源引用）

        ↓

Step 3  Agent 3 执行 — 市场情报分析
        仅分析经域名白名单过滤的市场来源（M1/M2/…）
        输出结构化 EvidenceReport JSON（guardrail 校验来源引用）

        ↓

Step 4  Agent 4 执行 — 综合报告撰写
        以 Step 1/2/3 结构化证据为唯一来源，禁止引入新信息
        每个数字型结论必须带行内引用标注
        → guardrail 校验报告结构与引用一致性，最多重试 2 次
        报告草稿传入 Step 5

        ↓

Step 5  Agent 5 执行 — 质量审查
        对 Step 4 草稿执行 final inspection：引用完整性、悬空数字、
        过度乐观语言、专利法律免责
        输出修正后的最终报告，保存至 outputs/<run_id>/commercialization_report.md

        ↓（并行于 Step 4，但顺序执行）

Step 6  Agent 6 执行 — 量化评分
        直接读取 Step 1/2/3 原始证据 JSON，独立评分
        输出 CommercializationScore JSON，保存至 outputs/<run_id>/commercialization_scores.json
        加权公式：overall = (TRL/9)×30 + (专利/5)×30 + (市场/5)×25 + (置信度/5)×15
        guardrail 自动修正算数误差
```

---

## 报告结构

每次运行产出的 Markdown 报告包含以下章节：

```
# Academic Commercialization Assessment: <research_topic>
## Executive Summary
## 1. Technology Overview & Maturity
## 2. Patent Landscape & White Spaces
## 3. Target Industries & Use Cases
## 4. Competitive Landscape
## 5. Commercialization Opportunities & Recommendations
## Evidence Limitations
## References
## Reviewer Notes（审查员修改说明）
```

评分卡（`commercialization_scores.json`）额外包含：TRL 评分、专利强度、市场可及性、证据置信度、综合评分、关键风险和机遇列表。

---

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件：

```
DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
# Legacy OPENAI_API_KEY/API_BASE/MODEL_NAME names are also supported.
SERPER_API_KEY=your_serper_key

# 可选：Semantic Scholar API Key（提升速率限制，无 Key 也可运行）
# 申请地址：https://www.semanticscholar.org/product/api
SEMANTIC_SCHOLAR_API_KEY=your_s2_key
```

### 3. 运行

**方式一：Gradio 网页界面（推荐）**

```bash
uv run python app.py
```

浏览器打开 `http://localhost:7860`，在输入框填写研究方向，点击 Run Analysis。

界面功能：
- **实时进度**：6 个 Agent 流水线阶段 + 已用时间（mm:ss）
- **评分卡**：综合分（0–100）+ TRL / 专利 / 市场 / 证据四维条形图（动态颜色）
- **报告**：Markdown 全文渲染 + `.md` / `.pdf` 双格式下载按钮
- **History 标签页**：浏览所有历史运行（含本地时间戳），输入 Run ID 一键加载历史报告和评分

**方式二：命令行**

```bash
uv run crewai run
```

研究主题在 `src/academic_agent/main.py` 中修改 `_DEFAULT_TOPIC` 字段。

### 4. 查看报告

每次运行生成独立目录，不会覆盖历史结果：

```
outputs/
└── 20260625T120000Z-a1b2c3d4e5/
    ├── commercialization_report.md
    ├── commercialization_report.pdf
    ├── commercialization_scores.json
    └── validated_sources.json
```

---

## 项目文件结构

```
academic_agent/
├── src/academic_agent/
│   ├── crew.py              # Crew 定义（6 个 Agent / Task 接线）
│   ├── main.py              # 命令行入口
│   ├── evidence.py          # 证据模型、guardrail 校验、CommercializationScore 模型
│   ├── source_pipeline.py   # 运行前确定性来源收集与验证
│   ├── llm_config.py        # DeepSeek LLM 配置（普通模式 / JSON 模式）
│   ├── run_output.py        # 运行 ID 与报告持久化
│   └── config/
│       ├── agents.yaml      # Agent 角色配置（6 个）
│       └── tasks.yaml       # Task 需求与引用规则（6 个）
├── tests/                   # 单元测试与 Crew 接线测试
├── app.py                   # Gradio 网页界面
├── .env                     # API Key 配置（不提交 Git）
├── pyproject.toml           # 项目依赖
└── README.md
```

---

## 技术栈

- **框架**：CrewAI 1.14.x
- **LLM**：DeepSeek-V3（通过 DeepSeek API 或 OpenAI 兼容接口）
- **学术来源**：OpenAlex Works API（主力）+ Semantic Scholar Academic Graph API（补充）
- **专利 / 市场搜索**：SerperDevTool
- **学术元数据**：Crossref API（DOI 验证与摘要检索）
- **数据校验**：Pydantic v2 + 自定义 guardrail（来源结构、引用完整性、报告结构、评分算法验证）
- **网页界面**：Gradio 6.x
- **PDF 导出**：xhtml2pdf + reportlab（原生 CJK 字体注册，支持中文报告）
- **Python**：3.10+

URL/DOI 无效或不可达、引用编号错误、References 不一致、报告结构错误和评分 JSON 格式错误都会阻止任务并触发重试。
