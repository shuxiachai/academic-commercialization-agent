# Target-user decision pilot guide

This guide operationalizes the frozen protocol in
[`prereg-2026-08-26-target-user-decision-pilot.md`](prereg-2026-08-26-target-user-decision-pilot.md).
It is a two-person descriptive pilot over existing reports, not an extension of
the closed topology utility audit.

## Who to recruit

Use the two registered slots `T01` and `T02`. Prioritize people who actually
make or support commercialization decisions:

1. technology-transfer or research-commercialization staff;
2. investors, venture analysts, or due-diligence personnel;
3. industry strategy, product, consulting, or commercialization staff; or
4. founders or senior researchers with direct commercialization evaluation
   responsibility.

A technically capable friend can still complete a packet, but their role must
be `PROXY` and their response cannot become target-user evidence. Do not infer
eligibility from prestige, education, or a job title; ask what decisions they
actually make.

## Honest recruitment message

Send this before sending any packet:

> 你好，我在验证一个科研成果商业化评估系统是否真的能帮助实际决策者，而不只是
> 验证程序能运行。想邀请你参加一次两阶段的小型试用：第一阶段只看 10 个主题名称，
> 选择一个你熟悉的方向并记录当前判断；我锁定这份基线后，再发送该主题的一份历史
> 报告，请你评价它增加了什么信息、需要怎样修改、是否会影响判断。报告约 4,000–
> 6,000 个英文词，预计阅读和填表需要 45–90 分钟。如果时间或专业方向不合适可以
> 直接拒绝。这不是考试，也没有标准答案；请不要用生成式 AI 代替你的实质判断。
> 结果仅使用 T01/T02 编号，姓名和单位不会写入公开材料。你愿意参加吗？

Do not mention a desired outcome, the earlier 6:4 result, a pass threshold, or
which workflow generated the report. There is no pass threshold in this pilot.

## Prepare Stage 1

The command is zero-network and makes no model or search call:

```bash
uv run python target_user_pilot.py prepare \
  outputs/ablation/20260821T234300Z-7dd894ef \
  outputs/target-user-pilot/20260826-packet \
  outputs/target-user-pilot-private/20260826-source-lock.json
```

Keep the source lock private. Send only one of these directories:

```text
outputs/target-user-pilot/20260826-packet/stage-1/T01/
outputs/target-user-pilot/20260826-packet/stage-1/T02/
```

Stage 1 contains a topic catalog, profile, and baseline form but no report.
This is an information barrier, not a convenience split. If a reviewer sees a
report before returning the baseline, do not reconstruct their initial answer
from memory; archive the slot as protocol-deviating.

## Lock intake and materialize Stage 2

Copy the returned `reviewer_profile.csv` and `baseline_form.csv` into the same
canonical Stage-1 directory. Preserve the reviewer ID and topic text exactly.
Then run, for example:

```bash
uv run python target_user_pilot.py materialize \
  outputs/ablation/20260821T234300Z-7dd894ef \
  outputs/target-user-pilot/20260826-packet \
  outputs/target-user-pilot-private/20260826-source-lock.json \
  T01
```

The command refuses blank or partial intake, source drift, topic drift, and a
second materialization. Send only the new `stage-2/T01/` directory. It contains
the exact selected report, a follow-up form, and a selection snapshot binding
the source, baseline, and delivered report hashes.

If an untouched slot cannot be recruited, edit only
`coordinator/slot_status.csv`: set it to `CLOSED_NO_RESPONSE` or `WITHDREW` and
write a short reason. Never close a slot that already contains participant
data, and do not add a third slot after seeing a follow-up.

## Required response semantics

- `citation_check=NONE` requires `factual_error_state=NOT_CHECKED`.
- `NONE_FOUND` means external sources were actually opened and no error was
  found among what was checked; it never means the report is proven correct.
- `blocking_error=YES` requires details describing how the issue could change a
  commercialization decision.
- Substantive AI-generated judgment is retained but excluded.
- Translation or clerical AI use is retained with disclosure.
- A changed go/no-go/defer decision is not assumed to be more correct.
- Time saved is a self-reported estimate, not an instrumented productivity
  result.

## Validate and summarize

After returned follow-ups are copied into the canonical Stage-2 directories:

```bash
uv run python target_user_pilot.py summarize \
  outputs/ablation/20260821T234300Z-7dd894ef \
  outputs/target-user-pilot/20260826-packet \
  outputs/target-user-pilot-private/20260826-source-lock.json \
  outputs/target-user-pilot-private/20260826-private-result.json \
  --public-output outputs/target-user-pilot-private/20260826-public-result.json
```

The private result retains free-text corrections for product learning. The
public projection omits free text and calculates outcomes only from reviewers
who consented to anonymous aggregate publication. Both outputs are immutable;
choose a new filename if a disclosed normalization is ever required.

Possible study states are deliberately distinct:

- `in_progress`: an open slot has not reached a complete follow-up;
- `single_target_user_observation`: one eligible target user completed and the
  other slot was closed;
- `descriptive_pilot_complete`: both eligible target users completed; or
- `no_eligible_target_user_observation`: completed rows were proxies or excluded
  for substantive AI use.

None of these states is a product-validation pass. Report exact observations
and limitations instead of converting two people into a percentage claim about
the market.
