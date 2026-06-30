# Academic Commercialization Assessment Agent

基于 [CrewAI](https://github.com/crewAIInc/crewAI) 框架开发的学术成果商业化评估智能体系统。

输入一个研究方向或论文主题，系统将自动调度多个专职 AI Agent，从学术文献、专利图谱、市场竞争三个维度完成分析，最终生成一份带可验证引用的结构化商业化评估报告。

---

## 改造说明

本项目基于 CrewAI 官方模板（researcher + reporting_analyst 两个 Agent）改造而来。

| | 原始 Demo | 本项目 |
|---|---|---|
| Agent 数量 | 2（researcher + reporting_analyst） | 4（专职分工） |
| Task 数量 | 2（research_task + reporting_task） | 4（顺序执行 + guardrail 验证） |
| 工具 | 无 | ArxivPaperTool + SerperDevTool |
| 输入变量 | topic + current_year | research_topic |
| 输出格式 | 自由文本报告 | 带 [A1][P2][M3] 行内引用 + References 区块的 Markdown 报告 |
| 输出管理 | 固定文件名（覆盖） | 每次运行生成唯一 ID，存入 outputs/ 目录 |
| 数据质量保障 | 无 | 结构化证据 + 引用完整性校验 + URL 可达性检查 + 自动重试 |

---

## Agent 架构

```
Agent 1: Academic Literature Analyst（学术前沿分析师）
         工具：ArxivPaperTool + SerperDevTool
         输出：结构化 EvidenceReport，含技术成熟度、研究突破、引用来源（A1/A2/…）

Agent 2: Patent Landscape Analyst（专利图谱分析师）
         工具：SerperDevTool
         输出：结构化 EvidenceReport，含专利持有人、空白领域（P1/P2/…）

Agent 3: Market & Competitive Intelligence Analyst（市场情报分析师）
         工具：SerperDevTool
         输出：结构化 EvidenceReport，含商业玩家、目标行业、市场机会（M1/M2/…）

Agent 4: Technology Commercialization Report Writer（报告撰写师）
         工具：无（以前三个 Agent 输出作为上下文）
         输出：Markdown 报告，含行内引用标注 [A1][P2][M3] 和 References 区块
         校验：章节、引用、References、数字引用和专利免责声明，不通过则自动重试（最多 2 次）
```

---

## 执行流程

```
Step 1  接收输入
        用户在 Gradio 界面或 main.py 中设置 research_topic
        系统生成唯一运行编号（run_id），格式：20260625T120000Z-a1b2c3d4e5

        ↓

Step 2  Agent 1 执行 — 学术文献分析
        调用 ArxivPaperTool 检索最新论文
        调用 SerperDevTool 补充学术资源
        输出结构化 EvidenceReport，每条结论关联 A1/A2/… 来源

        ↓

Step 3  Agent 2 执行 — 专利图谱分析
        调用 SerperDevTool 检索 Google Patents / WIPO / Espacenet
        输出结构化 EvidenceReport，每条结论关联 P1/P2/… 来源

        ↓

Step 4  Agent 3 执行 — 市场情报分析
        调用 SerperDevTool 检索商业化动态、融资信号、公司披露
        输出结构化 EvidenceReport，每条结论关联 M1/M2/… 来源

        ↓

Step 5  Agent 4 执行 — 综合报告撰写
        以前三步结构化证据为唯一来源，禁止引入新信息
        每个数字型结论必须带行内引用标注，如 [A1][P2][M3]
        → guardrail 校验：章节、正文引用、References、数字引用和免责声明
        报告保存至 outputs/<run_id>/commercialization_report.md
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
```

---

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件：

```
OPENAI_API_KEY=your_api_key
OPENAI_API_BASE=https://api.deepseek.com
OPENAI_MODEL_NAME=deepseek-chat
SERPER_API_KEY=your_serper_key
```

### 3. 运行

**方式一：Gradio 网页界面（推荐）**

```bash
uv run python app.py
```

浏览器自动打开 `http://localhost:7860`，在输入框填写研究方向，点击 Run Analysis，页面实时显示运行进度，完成后报告直接渲染在页面上。

**方式二：命令行**

```bash
uv run crewai run
```

研究主题在 `src/academic_agent/main.py` 中修改 `research_topic` 字段。

### 4. 查看报告

每次运行生成独立目录，不会覆盖历史结果：

```
outputs/
└── 20260625T120000Z-a1b2c3d4e5/
    └── commercialization_report.md
```

注意：修复证据链之前生成的历史报告不应视为已通过引用完整性验证。

---

## 项目文件结构

```
academic_agent/
├── src/academic_agent/
│   ├── crew.py              # Crew 定义与证据管线接线
│   ├── main.py              # 命令行入口
│   ├── evidence.py          # 证据模型与 guardrail 校验
│   ├── run_output.py        # 运行 ID 与报告持久化
│   └── config/
│       ├── agents.yaml      # Agent 角色配置
│       └── tasks.yaml       # Task 需求与引用规则
├── tests/                   # 单元测试与 Crew 接线测试
├── app.py                   # Gradio 网页界面
├── outputs/                 # 每次运行的报告存档目录
├── .env                     # API Key 配置（不提交 Git）
├── pyproject.toml           # 项目依赖
└── README.md
```

---

## 技术栈

- **框架**：CrewAI 1.14.x
- **LLM**：DeepSeek-V3（通过 DeepSeek API 或 OpenAI 兼容接口）
- **搜索工具**：SerperDevTool、ArxivPaperTool
- **数据校验**：Pydantic v2 + 自定义 guardrail（来源结构、引用完整性和报告结构验证）
- **网页界面**：Gradio 6.x
- **Python**：3.10+

URL/DOI 无效或不可达、引用编号错误、References 不一致和报告结构错误都会阻止任务并触发重试。
