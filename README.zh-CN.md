# 学术成果商业化评估系统

输入论文或研究主题，生成**带来源、评分与风险提示的商业化评估草稿**，辅助科研成果转化初筛。

[打开在线应用](https://academic-commercialization-agent.up.railway.app) · [阅读公开报告样例](examples/solid-state-batteries-ev.md) · [本地运行](#快速启动) · [English](README.md)

**体验条件：** 需要作者提供的访问码，或使用 BYOK（支持的模型 API key + Serper 检索 key）。
新建分析和 PDF 提取会产生供应商用量；阅读下面的公开样例不需要 key，也不触发新分析。

![真实历史结果界面：CRISPR 评估的评分维度、来源数量及带引用的风险说明](assets/screenshot-results.png)

*真实界面归档于 2026-08-11，版本 [a343a95](https://github.com/shuxiachai/academic-commercialization-agent/commit/a343a95590ad83f0edec4002e3489355fc96a512)，不是当前发布版的新截图。*

**公开报告样例：**[电动汽车用固态电池](examples/solid-state-batteries-ev.md)
— [2026-07-19 冻结版本，9673a83](https://github.com/shuxiachai/academic-commercialization-agent/blob/9673a8346c15f11b989ce8fd2d85be484d1c27b3/examples/solid-state-batteries-ev.md)。
截图与样例来自不同历史运行，不代表当前模型准确率或最新市场判断。

[文档导航](docs/README.md) · [项目案例](docs/portfolio-case-study.md)

技术实现为 Python、CrewAI、FastAPI 和无需构建的 JavaScript 客户端。
生产环境刻意限制自主性：确定性代码先完成检索，六阶段模型工作流再分析
已验证证据。**补充检索 Tool Calling 仍是独立实验，尚未接入生产。**

## 可以做什么

市场评分卡会明确提示[估值可比性尚未核实](docs/results-2026-09-11-market-score-delivery-disclosure.md)。
这项修复让历史上限规则的局限可见，不代表市场评分规则本身已修正或验证准确。
新验证结果还会记录并展示[封顶前后分数及实际扣分](docs/results-2026-09-12-numeric-token-and-cap-provenance.md)；
历史结果没有保存这些记录时，不会倒推补造。
[20条市场来源核对](docs/results-2026-09-12-market-source-followup.md)仍未建立完整同口径真实配对，
不代表评分政策已经通过验证。

- 输入研究主题或上传论文 PDF，选择报告语言与评分档位。
- 可选填写 Decision Context：区分方向性探索和具体决策，标识阈值是否由
  决策所有者批准；上下文不完整仍能运行，不自动升级为可执行投资建议。
- 查看进度、引用、来源与可靠性提示，导出 Markdown/PDF，分享运行链接。
- 在“来源”页按完整编号或字面关键词定位，展开查看保存文本，无需模型调用。
  保存文本不等于论文全文或已验证的结论支持；详见[操作指南](docs/operating-guide.md#web-cli-and-http-api)。
- 将中断任务恢复为不可变子运行，复用连续、已验证的 Checkpoint 前缀，
  并重新提供必要凭证。
- 在启用门禁的部署中使用口令或自带密钥（BYOK）。

报告用于研究初筛，不代替技术、法律、监管、投资或 FTO 尽职调查。
“引用 ID 有效”不等于“来源在语义上支持该结论”。

## 系统架构

```text
研究主题 / PDF + 可选 Decision Context
                    │
确定性检索 → 来源验证 → 冻结来源注册表
                    │
          ┌─────────┼─────────┐
        学术分析   专利分析   市场分析
          └─────────┼─────────┘
                  报告撰写
                    │
                  质量审查
                    │
                  评分 → 代码重算加权总分
                    │
          共享运行产物 + 不可变终态
                    │
          FastAPI / 浏览器 / CLI / 恢复
```

三个证据节点并行，Writer、Reviewer、Scorer 顺序执行。六个阶段不代表
固定只有六次模型请求。修改编排前请阅读 [AGENTS.md](AGENTS.md)。

| 边界 | 已实现的能力 |
|---|---|
| 证据 | 原生数据客户端与网页检索，URL/DOI 验证、来源分层、去重和引用注册 |
| 输出 | Pydantic 契约、Guardrail、确定性评分与受限 Reviewer 修订 |
| 质量 | 精度优先的非阻断筛查；区分“未发现问题”和“未能检查” |
| 运行时 | 子进程隔离、内容寻址 Checkpoint、不可变恢复子运行和一次写入终态 |
| 费用 | PDF/正式运行共享准入，持久化日配额，完整/下界/不可用用量状态 |
| 可观测性 | 可选的脱敏 OpenTelemetry/OpenInference Trace，支持 Phoenix/OTLP |
| 部署 | FastAPI、原生 HTML/CSS/ES modules、Docker、Railway；单应用副本 |

### 实测结果

冻结基准包含 **10 个主题 × 每个主题 3 次实时检索运行**：

| 检查项 | 观测结果 |
|---|---|
| 端到端完成 | **30/30** |
| TRL 校准 | **26/30** |
| 加权公式正确 | **30/30** |
| 报告结构完整 | **30/30** |
| 无引用数值行 | **30 份报告中 0 行** |

这些是不同检查，不是统一准确率。TRL 预期区间曾在看过早期结果后调整，
因此不是独立未见集验证；数值引用筛查也不能证明不存在幻觉。
10 个主题中有 7 个在三次运行中均命中 TRL 区间。

其他已完成的证据：

- **90 单元消融实验**：四节点相对六节点的中位 Token 减少 54.89%，
  中位成本降低 47.03%；没有证明六节点在所有情形下都必要。
- **五人效用评审**：20 份有效判断，两轮完整流程偏好均为 6:4，
  但预注册成功标准未通过。
- **两位目标用户试点**：两人均维持 `DEFER`，再次使用意愿均为 `MAYBE`，
  未核验外部来源；不能据此宣称产品采用或商业价值已验证。
- **恢复测试**：离线故障注入 30/30 子运行完成，线上另有一例复用四节点。
  不等于 exactly-once 或普遍节费保证。
- **运行时 RTI02**：一例 Qwen 正常完成通过 12/12 主要终态检查，
  披露了轻微观察轮询间隔偏差；该次没有验证超时、回退路径或通用报告质量。

详细数据、方法限制和原始公开依据见[当前证据台账](docs/evidence-status.md)。

## Tool Calling 完成到哪里

这里需要区分三种能力：

- **保存来源定位**：已经接入独立生产页面和 API。模型最多从保存的标题/ID
  目录中选择一次，程序返回原样保存文本；不生成研究答案、不搜索新资料。
  执行需要报告所有者身份、明确的数据发送同意、付费准入和持久回执，并提供
  操作级核算。详见[运行边界](docs/operating-guide.md#optional-saved-source-locator)。
- **自动补充检索**：生产仍是零调用观察模式。最后一轮未见评估未通过准入要求，
  不会因为来源定位取得进展而自动启用。
- **生成式证据追问**：仍属实验，没有开放为生产问答功能。
  工具确实执行或 JSON 格式正确，都不等于答案得到证据支持。

2026 年 9 月 26 日，一次受限生产浏览器验收选中预先确定的来源，准确交付保存文本，
并在关闭执行、重新部署后通过同一回执恢复结果和核算。该操作报告用量为
1,199 Tokens，按固定工程价格估算 USD 0.000764436，不是供应商发票。
这只是一个准备案例的交付观察，不是未见准确率，也不证明优于已有免费的 Sources
关键词查找。**验收后已重新关闭新增付费执行，功能预算归零，并未持续开放。**

[验收记录与限制](docs/results-2026-09-26-production-source-locator-acceptance.md)
分别说明原 POST 响应体观察器的限制、实际页面与 GET 原始响应的核对，以及此前
同源校验失败的独立事实，不将不同批次拼成一次成功。

历史假设、失败和已关闭批次保留在[证据记录](docs/evidence-status.md#tool-calling-experiments)
及[实验档案](docs/experiment-index.md)，不累加成通用准确率，也不因本次验收而重新开启。

## 快速启动

优先使用 CI 覆盖的 Python 3.11/3.12 与 [uv](https://docs.astral.sh/uv/)。
安装依赖需要联网，默认测试不调用供应商。

```bash
git clone https://github.com/shuxiachai/academic-commercialization-agent.git
cd academic-commercialization-agent
uv sync
```

将 [.env.example](.env.example) 复制为 `.env`。使用 Qwen 时填写：

```dotenv
LLM_PROVIDER=qwen
DASHSCOPE_API_KEY=your-key
QWEN_MODEL=qwen3.5-plus
QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
TAVILY_API_KEY=your-search-key
```

密钥只在本地填写，不要提交或分享。运营者端点需要匹配账户和地域；
浏览器 BYOK 默认使用中国区端点。保留多个模型密钥时请明确设置
`LLM_PROVIDER`，否则自动选择顺序为 DeepSeek → Qwen → Anthropic → OpenAI。
两个搜索密钥同时存在时 Tavily 优先；删除不用的占位密钥。

```bash
uv run uvicorn api.main:app --reload
# 浏览器打开 http://localhost:8000
# 或通过 CLI 发起真实分析：
uv run academic_agent --topic "solid-state batteries for electric vehicles"
```

真实运行产生供应商用量。Qwen 已观察到的完成样本包括 306 秒和 885 秒，
不承诺三分钟 SLA。[操作指南](docs/operating-guide.md)包含 HTTP 接口、
运行产物、Docker、门禁、BYOK、Trace 与恢复说明。

## 安全与部署

运行链接具有 **128 位随机性**，是读取能力凭证：知道完整链接的人可以
读取该运行，直到留存策略删除它。口令归属运行的修改还需 owner/admin
口令；无归属 BYOK 运行没有第二个服务端身份。不要公开私人运行链接。

部署前配置访问控制、付费准入、留存和持久化存储。PDF 提取同样是付费操作。
保持 **一个应用副本 / 一个 Uvicorn worker**，文件账本和内存所有权不是
分布式队列。详见[部署控制](docs/operating-guide.md#deploying-publicly)与
[Checkpoint 设计](docs/checkpoint-recovery.md)。

## 测试与基准

整理前的 `0fdaa76` 基线通过 **2071 项测试、678 个子测试**。
CI 包含 Linux/Windows × Python 3.11/3.12、最新版 Ruff、窄范围 Pylint、
85% coverage 门槛、零供应商调用 Chromium 测试及 Docker。
这些不构成真实供应商生产 SLO。

```bash
uv run pytest -q
uv run --with ruff ruff check .
# 仅预览调度，不调用供应商：
uv run python benchmark.py --dry-run
```

### 基准主题

新测量使用绑定版本的独立批次，不覆盖历史产物；复用需要显式选择身份一致且
产物完好的批次。费用只覆盖 Crew 节点，不包含辅助调用、PDF 和搜索费用。
参见[执行与费用边界](docs/operating-guide.md#benchmark)。

| # | Topic | Expected TRL | Industry |
|---|-------|-------------|---------|
| 01 | CAR-T cell therapy for blood cancers | 7–9 | Biomed |
| 02 | mRNA vaccines for cancer immunotherapy | 6–8 | Biomed |
| 03 | solid-state batteries for electric vehicles | 5–7 | Energy |
| 04 | perovskite solar cells for utility-scale power generation | 6–8 | Clean Energy |
| 05 | CRISPR gene editing for genetic diseases | 7–9 | Biomed |
| 06 | carbon capture and storage for industrial emissions | 6–8 | Climate |
| 07 | cultivated meat for food industry | 6–8 | Food |
| 08 | quantum computing for drug discovery | 2–4 | Computing |
| 09 | graphene-based flexible electronics | 3–5 | Materials |
| 10 | room temperature ambient pressure superconductors | 1–2 | Materials |

[基准操作说明](docs/operating-guide.md#benchmark)解释重复运行、冻结证据和
付费注意事项。不要通过修改评分规则来“改善”这批历史指标。

## 文档与限制

- [文档地图](docs/README.md)：区分当前说明与历史决策。
- [证据台账](docs/evidence-status.md)：数据及其不能证明的内容。
- [操作指南](docs/operating-guide.md)：配置、API、部署与评分。
- [贡献指南](CONTRIBUTING.md)、[AGENTS.md](AGENTS.md)：约束与被否决的方法。
- [实验档案索引](docs/experiment-index.md)：未改写的预注册、结果与勘误。

前端付费请求支持[持久化回执](docs/operating-guide.md#paid-request-receipts)：回包丢失或刷新后，
可在最长 24 小时内通过只读查询找回分析、PDF 或恢复子运行的接收结果，不重复提交付费请求。
未知结果仍明确标注；这不等于供应商 exactly-once 或多副本调度。

仍需补强定性结论的引用支持、独立决策效用、中文/极短/非技术输入的基准、
旧运行元数据读取状态，以及单副本之外的扩展边界。增加 Agent、向量库或
Kubernetes 本身不能解决这些缺口。

## 界面截图

<details>
<summary>历史首页与运行中界面 — a343a95，2026-08-11 归档</summary>

下图为版本 [a343a95](https://github.com/shuxiachai/academic-commercialization-agent/commit/a343a95590ad83f0edec4002e3489355fc96a512)
的真实界面，当前控件和文案可能不同；结果截图已放在首屏。

![首页](assets/screenshot-home.png)
![分析运行中](assets/screenshot-running.png)

</details>

## 作者与更多作品

作者：[shuxiachai](https://github.com/shuxiachai)。
更多项目与实践见 [GitHub 个人主页](https://github.com/shuxiachai)。
