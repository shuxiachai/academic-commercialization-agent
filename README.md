# Academic Commercialization Assessment Agent

[English](#english) | [中文](#chinese)

---

<a name="english"></a>

## English

A multi-agent system built on [CrewAI](https://github.com/crewAIInc/crewAI) that evaluates the commercialization readiness of academic research.

Input a research direction or paper topic. Six specialized AI agents automatically gather evidence from academic literature, patent databases, and market intelligence sources, then produce a structured commercialization assessment report with verifiable citations and a quantitative scorecard.

---

### What's different from the CrewAI starter template

| | Original demo | This project |
|---|---|---|
| Agents | 2 (researcher + reporting_analyst) | 6 (specialized roles) |
| Tasks | 2 | 6 (sequential + guardrail validation) |
| Tools | None | OpenAlex + Semantic Scholar + SerperDevTool + Crossref |
| Source collection | None | Deterministic pre-run retrieval with URL reachability check |
| Output format | Free-form text | Markdown report with `[A1][P2][M3]` inline citations + References block + JSON scorecard |
| Output management | Fixed filename (overwritten) | Unique run ID per execution, stored in `outputs/` |
| Data quality | None | Structured evidence + citation integrity check + minimum summary length filter + auto-retry |
| Score reproducibility | — | JSON-mode agents all at `temperature=0`; same topic produces stable results across runs |
| Score traceability | — | Each dimension records source IDs (`trl_source_ids`, `patent_source_ids`, etc.) |

---

### Agent architecture

```
Agent 1: Academic Literature Analyst
         Sources: OpenAlex / Semantic Scholar papers (pre-validated in Step 0)
         Output:  Structured EvidenceReport JSON — maturity, breakthroughs, citations (A1/A2/…)

Agent 2: Patent Landscape Analyst
         Sources: Google Patents / WIPO records (Serper search + URL validation)
         Output:  Structured EvidenceReport JSON — holders, white spaces (P1/P2/…)

Agent 3: Market & Competitive Intelligence Analyst
         Sources: Domain-allowlisted market reports (Serper search)
         Output:  Structured EvidenceReport JSON — players, target industries, opportunities (M1/M2/…)

Agent 4: Technology Commercialization Report Writer
         Tools:   None (uses Agents 1–3 output as context only)
         Output:  Markdown draft with inline citations [A1][P2][M3] and References block
         Guard:   Section structure + citation integrity; auto-retries up to 2×

Agent 5: Report Reviewer
         Tools:   None (uses Agent 4 draft as input)
         Output:  Corrected final report; Reviewer Notes automatically split into reviewer_notes.md

Agent 6: Commercialization Readiness Scorer
         Tools:   None (reads Tasks 1–3 evidence JSON directly, independent of the report)
         Output:  CommercializationScore JSON — TRL / MRL / Patent / Market / Evidence confidence
         Guard:   JSON format validation + weighted formula correction; auto-retries up to 2×
```

---

### Execution flow

```
Step 0  Source collection & validation (pre-run, deterministic)
        Academic: OpenAlex Works API (filter=title.search, sorted by citation count)
                  → Semantic Scholar supplement (when OpenAlex count is below target)
                  → DOI deduplication; summaries < 100 chars auto-rejected
        Patent:   Serper → Google Patents / WIPO; URL reachability verified
        Market:   Serper + domain allowlist (30+ approved institutions); low-quality sites removed
        Metadata: Crossref API for DOI, journal name, publication date
        Output:   validated_sources.json passed into Crew

Step 1  Agent 1 — Academic literature analysis
Step 2  Agent 2 — Patent landscape analysis
Step 3  Agent 3 — Market intelligence analysis
Step 4  Agent 4 — Comprehensive report writing  (guardrail validates citations)
Step 5  Agent 5 — Quality review               (Reviewer Notes saved separately)
Step 6  Agent 6 — Quantitative scoring         (parallel to Step 4, formula-corrected)
```

---

### Report structure

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
    *Reference codes: A = Academic paper · P = Patent · M = Market/industry source*
    [A1] … [P1] … [M1] …
```

> **Multilingual support**: Language is auto-detected from the topic string. Reports in Simplified/Traditional Chinese, Japanese, Korean, German, French, and 6 more languages are fully localized — section headings, citation legend, and patent disclaimers all adapt automatically.

The scorecard (`commercialization_scores.json`) additionally contains: TRL score, patent strength, market accessibility, evidence confidence, overall score, key risks, and key opportunities.

---

### Quick start

#### 1. Install dependencies

```bash
uv sync
```

#### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

LLM — pick **one** of:

| Variable | Provider | Default model |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek ([get key](https://platform.deepseek.com/api-keys)) | `deepseek-chat` |
| `ANTHROPIC_API_KEY` | Anthropic Claude ([get key](https://console.anthropic.com/)) | `claude-sonnet-5` |
| `OPENAI_API_KEY` | OpenAI ([get key](https://platform.openai.com/api-keys)) | `gpt-4o` |

Also required:

| Variable | Where to get it |
|---|---|
| `SERPER_API_KEY` | [serper.dev/api-key](https://serper.dev/api-key) (free tier: 2 500 queries/month) |

Optional:

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | Override auto-detection: `deepseek` / `anthropic` / `openai` |
| `MAX_RPM` | API requests per minute (default `6`; raise to `20`+ for OpenAI/Anthropic) |
| `SEMANTIC_SCHOLAR_API_KEY` | Raises S2 rate limit from 1 req/s → 10 req/s; system works without it |

#### 3. Run

**Option A — Gradio web UI (recommended)**

```bash
uv run python app.py
```

Open `http://localhost:7860` in your browser, enter a research topic, and click **Run Analysis**.

UI features:
- **Live progress**: 6-agent pipeline stages + elapsed time
- **Scorecard**: Overall score (0–100) + four-dimension bar chart with source ID chips (e.g. `A2` `M1`) traceable to validated sources
- **Report**: Full Markdown render + `.md` / `.pdf` download buttons
- **History tab**: Browse all past runs; load any run by ID

**Option B — Command line**

```bash
uv run crewai run
```

Set the topic via `_DEFAULT_TOPIC` in `src/academic_agent/main.py`.

#### 4. Output

Each run creates an isolated directory that never overwrites previous results:

```
outputs/
└── 20260625T120000Z-a1b2c3d4e5/
    ├── commercialization_report.md    # Final report (Markdown)
    ├── commercialization_report.pdf   # Final report (PDF, CJK-font-aware)
    ├── commercialization_scores.json  # Quantitative scorecard
    ├── validated_sources.json         # Pre-validated source list
    └── reviewer_notes.md              # Reviewer change log (separated from main report)
```

---

### Benchmark

`benchmark.py` ships with 10 preset topics spanning different industries and expected TRL ranges, for validating scoring accuracy and consistency.

```bash
# Run all 10 topics (already-succeeded runs are skipped automatically)
uv run python benchmark.py

# Re-run a specific topic (delete its output directory first)
uv run python benchmark.py --only 3

# Generate summary table and CSV
uv run python benchmark_check.py
```

| # | Topic | Expected TRL | Industry |
|---|-------|-------------|---------|
| 01 | CAR-T cell therapy for solid tumors | 6–8 | Biotech |
| 02 | mRNA vaccines for non-infectious disease | 6–8 | Pharma |
| 03 | CRISPR base editing for monogenic disorders | 4–6 | Biotech |
| 04 | Perovskite solar cells for building-integrated PV | 5–7 | CleanTech |
| 05 | Solid-state batteries for EV | 5–7 | Energy |
| 06 | Green hydrogen via proton exchange membrane electrolysis | 5–7 | Energy |
| 07 | Cultivated meat for food manufacturing | 4–6 | FoodTech |
| 08 | Quantum key distribution for enterprise networks | 4–6 | Cybersecurity |
| 09 | Biodegradable microplastic alternatives for packaging | 5–7 | Materials |
| 10 | Room temperature superconductors | 1–3 | Materials |

`benchmark_check.py` produces `outputs/benchmark/benchmark_summary.csv` and auto-checks:
- 10/10 run success rate
- TRL scores within expected range (pass / flag)
- Weighted formula correctness
- Report section completeness
- Unsupported numeric claim count (hallucination-risk indicator)

---

### Project structure

```
academic_agent/
├── src/academic_agent/
│   ├── crew.py              # Crew definition (6 agents / tasks wired together)
│   ├── main.py              # CLI entry point (supports --topic argument)
│   ├── evidence.py          # Evidence models, guardrail validators, CommercializationScore
│   ├── source_pipeline.py   # Pre-run deterministic source collection & validation
│   ├── llm_config.py        # DeepSeek LLM config (standard / JSON mode / temperature)
│   ├── run_output.py        # Run ID, report & scorecard persistence
│   └── config/
│       ├── agents.yaml      # Agent role definitions (6 agents)
│       └── tasks.yaml       # Task requirements & citation rules (6 tasks)
├── tests/                   # Unit tests and crew wiring tests (79 tests)
├── app.py                   # Gradio web UI (scorecard with source ID chips)
├── benchmark.py             # 10-topic benchmark runner
├── benchmark_check.py       # Benchmark result analyzer (CSV + terminal table)
├── outputs/
│   ├── <run_id>/            # Per-run output directory
│   └── benchmark/           # benchmark.py outputs (includes benchmark_summary.csv)
├── .env.example             # Environment variable template
├── pyproject.toml           # Project dependencies
└── README.md
```

---

### Tech stack

- **Framework**: CrewAI 1.14.x
- **LLM**: DeepSeek-V3 / OpenAI GPT-4o / Anthropic Claude — auto-detected from API key, or set `LLM_PROVIDER` explicitly
- **Academic sources**: OpenAlex Works API (primary) + Semantic Scholar Academic Graph API (supplement)
- **Patent / market search**: SerperDevTool
- **Academic metadata**: Crossref API (DOI verification and abstract retrieval)
- **Data validation**: Pydantic v2 + custom guardrails (source structure, citation integrity, report structure, scoring formula)
- **Web UI**: Gradio 6.x
- **PDF export**: xhtml2pdf + reportlab (native CJK font registration for Chinese, Japanese, Korean)
- **Python**: 3.10+

Invalid or unreachable URLs/DOIs, mismatched citation IDs, References inconsistencies, malformed report sections, and scoring JSON format errors all block the task and trigger automatic retries.

---

### Scoring dimensions

| Dimension | Field | Max | Weight | Description |
|-----------|-------|-----|--------|-------------|
| Market accessibility | `market_accessibility` | 5 | 35% | 1 = no commercial activity, 5 = mature market with revenue data |
| Technology readiness | `trl_score` | 9 | 20% | NASA TRL 1–9; market deployment evidence is the primary signal |
| Manufacturing readiness | `mrl_score` | 10 | 15% | DoD MRL 1–10; reflects scalable production capability |
| IP landscape navigability | `patent_strength` | 5 | 20% | 1 = highly contested, 5 = minimal patent coverage |
| Evidence confidence | `evidence_confidence` | 5 | 10% | Cross-validation across multiple source types (meta-dimension) |
| **Overall score** | `overall_score` | **100** | — | `round((market/5)×35 + (TRL/9)×20 + (MRL/10)×15 + (patent/5)×20 + (confidence/5)×10)` |

Each dimension records its supporting source IDs (`trl_source_ids`, `patent_source_ids`, `market_source_ids`, `evidence_source_ids`), visible in the Gradio scorecard and traceable to the original validated sources.

---

---

<a name="chinese"></a>

## 中文

基于 [CrewAI](https://github.com/crewAIInc/crewAI) 框架开发的学术成果商业化评估智能体系统。

输入一个研究方向或论文主题，系统将自动调度多个专职 AI Agent，从学术文献、专利图谱、市场竞争三个维度完成分析，最终生成一份带可验证引用的结构化商业化评估报告和量化评分卡。

---

### 改造说明

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
| 评分确定性 | — | JSON 模式 Agent 全部 temperature=0，同一话题多次运行结果稳定 |
| 评分可追溯性 | — | 每个评分维度标注来源 ID（trl_source_ids / patent_source_ids 等） |

---

### Agent 架构

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
         输出：修正后的最终报告；审查员注记（Reviewer Notes）自动分离，单独保存至 reviewer_notes.md

Agent 6: Commercialization Readiness Scorer（量化评分员）
         工具：无（以 Task 1/2/3 结构化证据为输入，独立于报告流程）
         输出：CommercializationScore JSON 评分卡，含 TRL / MRL / 专利 / 市场 / 证据置信度五维评分
         校验：JSON 格式验证 + 加权公式自动修正 overall_score，不通过则自动重试（最多 2 次）
```

---

### 执行流程

```
Step 0  来源收集与验证（运行前，确定性）
        学术：OpenAlex Works API（filter=title.search，按引用数降序）
              → Semantic Scholar 补充（当 OpenAlex 不足最大来源数时触发）
              → 按 DOI 去重，摘要 <100 字符的记录自动剔除
        专利：Serper 检索 Google Patents / WIPO，验证 URL 可达性
        市场：Serper 检索 + 域名白名单过滤（30+ 认可机构），剔除低质量站点
        元数据：Crossref API 补充 DOI、期刊名、发表日期
        输出 validated_sources.json 并传入 Crew

Step 1  Agent 1 执行 — 学术文献分析
Step 2  Agent 2 执行 — 专利图谱分析
Step 3  Agent 3 执行 — 市场情报分析
Step 4  Agent 4 执行 — 综合报告撰写（guardrail 校验引用完整性）
Step 5  Agent 5 执行 — 质量审查（Reviewer Notes 单独保存）
Step 6  Agent 6 执行 — 量化评分（并行于 Step 4，公式自动修正）
```

---

### 报告结构

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
    *文献编码说明：A = 学术论文 · P = 专利 · M = 市场/行业来源*
    [A1] … [P1] … [M1] …
```

> **多语言支持**：系统根据研究主题自动检测输出语言（支持中文简体/繁体、日文、韩文、德文、法文等 12 种语言）。各语言版本的报告结构、章节标题、引用图例（A/P/M 说明行）及专利免责声明均自动本地化。

评分卡（`commercialization_scores.json`）额外包含：TRL 评分、专利强度、市场可及性、证据置信度、综合评分、关键风险和机遇列表。

---

### 快速开始

#### 1. 安装依赖

```bash
uv sync
```

#### 2. 配置环境变量

将 `.env.example` 复制为 `.env` 并填入你的 API Key：

```bash
cp .env.example .env
```

LLM — 三选一填入：

| 变量 | Provider | 默认模型 |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek（[申请](https://platform.deepseek.com/api-keys)） | `deepseek-chat` |
| `ANTHROPIC_API_KEY` | Anthropic Claude（[申请](https://console.anthropic.com/)） | `claude-sonnet-5` |
| `OPENAI_API_KEY` | OpenAI（[申请](https://platform.openai.com/api-keys)） | `gpt-4o` |

必填：

| 变量 | 申请地址 |
|---|---|
| `SERPER_API_KEY` | [serper.dev/api-key](https://serper.dev/api-key)（免费额度：2500 次/月） |

可选项：

| 变量 | 用途 |
|---|---|
| `LLM_PROVIDER` | 手动指定 provider：`deepseek` / `anthropic` / `openai` |
| `MAX_RPM` | API 每分钟请求数（默认 `6`；使用 OpenAI/Anthropic 可调高至 `20`+） |
| `SEMANTIC_SCHOLAR_API_KEY` | 将 S2 速率限制从 1 req/s 提升至 10 req/s；不填也可正常运行 |

#### 3. 运行

**方式一：Gradio 网页界面（推荐）**

```bash
uv run python app.py
```

浏览器打开 `http://localhost:7860`，在输入框填写研究方向，点击 Run Analysis。

界面功能：
- **实时进度**：6 个 Agent 流水线阶段 + 已用时间（mm:ss）
- **评分卡**：综合分（0–100）+ TRL / 专利 / 市场 / 证据四维条形图（动态颜色）；每个维度下方展示支撑该评分的来源 ID 标签（如 `A2` `M1`），可追溯至验证过的原始来源
- **报告**：Markdown 全文渲染 + `.md` / `.pdf` 双格式下载按钮
- **History 标签页**：浏览所有历史运行（含本地时间戳），输入 Run ID 一键加载历史报告和评分

**方式二：命令行**

```bash
uv run crewai run
```

研究主题在 `src/academic_agent/main.py` 中修改 `_DEFAULT_TOPIC` 字段。

#### 4. 查看报告

每次运行生成独立目录，不会覆盖历史结果：

```
outputs/
└── 20260625T120000Z-a1b2c3d4e5/
    ├── commercialization_report.md   # 最终报告（Markdown）
    ├── commercialization_report.pdf  # 最终报告（PDF，支持 CJK 字体）
    ├── commercialization_scores.json # 量化评分卡
    ├── validated_sources.json        # 预验证来源清单
    └── reviewer_notes.md             # 审查员修改记录（与正文分离，供追溯）
```

---

### 基准测试

`benchmark.py` 包含 10 个预设话题，覆盖不同行业和预期 TRL 范围，用于验证系统的评分准确性和一致性。

```bash
# 运行全部 10 个话题（已成功的自动跳过）
uv run python benchmark.py

# 单独重跑某个话题（先手动删除对应目录）
uv run python benchmark.py --only 3

# 生成摘要表格并输出 CSV
uv run python benchmark_check.py
```

| # | 话题 | 预期 TRL | 行业 |
|---|------|---------|------|
| 01 | CAR-T cell therapy for solid tumors | 6–8 | Biotech |
| 02 | mRNA vaccines for non-infectious disease | 6–8 | Pharma |
| 03 | CRISPR base editing for monogenic disorders | 4–6 | Biotech |
| 04 | Perovskite solar cells for building-integrated PV | 5–7 | CleanTech |
| 05 | Solid-state batteries for EV | 5–7 | Energy |
| 06 | Green hydrogen via proton exchange membrane electrolysis | 5–7 | Energy |
| 07 | Cultivated meat for food manufacturing | 4–6 | FoodTech |
| 08 | Quantum key distribution for enterprise networks | 4–6 | Cybersecurity |
| 09 | Biodegradable microplastic alternatives for packaging | 5–7 | Materials |
| 10 | Room temperature superconductors | 1–3 | Materials |

`benchmark_check.py` 生成 `outputs/benchmark/benchmark_summary.csv`，自动校验：
- 10/10 运行成功率
- TRL 评分是否落在预期范围（pass / flag）
- 加权公式正确性
- 报告章节完整性
- 悬空数字行数（幻觉风险指标）

---

### 项目文件结构

```
academic_agent/
├── src/academic_agent/
│   ├── crew.py              # Crew 定义（6 个 Agent / Task 接线）
│   ├── main.py              # 命令行入口（支持 --topic 参数）
│   ├── evidence.py          # 证据模型、guardrail 校验、CommercializationScore 模型
│   ├── source_pipeline.py   # 运行前确定性来源收集与验证
│   ├── llm_config.py        # DeepSeek LLM 配置（普通模式 / JSON 模式 / temperature）
│   ├── run_output.py        # 运行 ID、报告与评分 JSON 持久化
│   └── config/
│       ├── agents.yaml      # Agent 角色配置（6 个）
│       └── tasks.yaml       # Task 需求与引用规则（6 个）
├── tests/                   # 单元测试与 Crew 接线测试（79 个）
├── app.py                   # Gradio 网页界面（含评分卡来源 ID chips）
├── benchmark.py             # 10 话题基准测试运行器
├── benchmark_check.py       # 基准结果分析器（生成 CSV + 终端表格）
├── outputs/
│   ├── <run_id>/            # 每次正常运行的输出目录
│   └── benchmark/           # benchmark.py 输出目录（含 benchmark_summary.csv）
├── .env.example             # 环境变量模板
├── pyproject.toml           # 项目依赖
└── README.md
```

---

### 技术栈

- **框架**：CrewAI 1.14.x
- **LLM**：DeepSeek-V3 / OpenAI GPT-4o / Anthropic Claude — 自动从 API Key 检测，或通过 `LLM_PROVIDER` 显式指定
- **学术来源**：OpenAlex Works API（主力）+ Semantic Scholar Academic Graph API（补充）
- **专利 / 市场搜索**：SerperDevTool
- **学术元数据**：Crossref API（DOI 验证与摘要检索）
- **数据校验**：Pydantic v2 + 自定义 guardrail（来源结构、引用完整性、报告结构、评分算法验证）
- **网页界面**：Gradio 6.x
- **PDF 导出**：xhtml2pdf + reportlab（原生 CJK 字体注册，支持中文简繁体、日文、韩文等多语言报告）
- **Python**：3.10+

URL/DOI 无效或不可达、引用编号错误、References 不一致、报告结构错误和评分 JSON 格式错误都会阻止任务并触发重试。

---

### 评分维度说明

| 维度 | 字段 | 满分 | 权重 | 说明 |
|------|------|------|------|------|
| 市场可及性 | `market_accessibility` | 5 | 35% | 1=无商业活动，5=成熟市场有收入数据 |
| 技术成熟度 | `trl_score` | 9 | 20% | NASA TRL 1–9，以市场部署证据为主信号 |
| 制造成熟度 | `mrl_score` | 10 | 15% | DoD MRL 1–10，反映可规模化生产程度 |
| IP 景观可导航性 | `patent_strength` | 5 | 20% | 1=高度竞争，5=几乎无专利保护 |
| 证据置信度 | `evidence_confidence` | 5 | 10% | 多维来源交叉验证程度（元维度） |
| **综合分** | `overall_score` | **100** | — | `round((市场/5)×35 + (TRL/9)×20 + (MRL/10)×15 + (专利/5)×20 + (置信度/5)×10)` |

每个维度评分同时记录支撑来源 ID（`trl_source_ids` / `patent_source_ids` / `market_source_ids` / `evidence_source_ids`），可在 Gradio 评分卡中直接查看并追溯至原始文献。
