"""Code-owned applicability text inserted at the report delivery seam."""

from __future__ import annotations

from typing import Any


_MARKER = "<!-- decision-applicability:v1 -->"

_COPY: dict[str, dict[str, str]] = {
    "English": {
        "label": "Assessment applicability (code-derived)",
        "allowed": (
            "Actor-specific `GO/NO_GO` is permitted by context completeness; "
            "the conclusion still depends on the cited evidence."
        ),
        "not_allowed": "Actor-specific `GO/NO_GO` is not assessed.",
        "provenance": "Success-criteria provenance",
        "caveat": (
            "Any additional decision threshold is an analyst proposal unless "
            "explicitly identified as owner-approved; a cited benchmark does "
            "not establish owner approval."
        ),
    },
    "Simplified Chinese": {
        "label": "评估适用范围（代码判定）",
        "allowed": (
            "决策上下文完整，允许针对具体决策者给出 `GO/NO_GO`；最终结论仍须由引用证据支持。"
        ),
        "not_allowed": "未评估针对具体决策者的 `GO/NO_GO`。",
        "provenance": "成功标准来源",
        "caveat": (
            "除非明确标注为决策者已批准，否则报告新增的决策阈值均为分析者建议；"
            "引用外部基准并不代表决策者已经批准。"
        ),
    },
    "Japanese": {
        "label": "評価の適用範囲（コード判定）",
        "allowed": (
            "意思決定コンテキストが完全なため、特定の担当者向け `GO/NO_GO` を提示できます。"
            "ただし結論には引用証拠が必要です。"
        ),
        "not_allowed": "特定の担当者向け `GO/NO_GO` は評価していません。",
        "provenance": "成功基準の出所",
        "caveat": (
            "担当者承認済みと明記されない追加の判断閾値は分析者案です。"
            "引用された外部ベンチマークは担当者承認を意味しません。"
        ),
    },
    "German": {
        "label": "Anwendungsbereich der Bewertung (codebasiert)",
        "allowed": (
            "Der Entscheidungskontext erlaubt ein akteursbezogenes `GO/NO_GO`; "
            "die Schlussfolgerung bleibt von den zitierten Belegen abhängig."
        ),
        "not_allowed": "Ein akteursbezogenes `GO/NO_GO` wurde nicht bewertet.",
        "provenance": "Herkunft der Erfolgskriterien",
        "caveat": (
            "Jeder zusätzliche Entscheidungsschwellenwert ist ein Analystenvorschlag, "
            "sofern er nicht ausdrücklich als genehmigt gekennzeichnet ist; ein "
            "zitierter Benchmark belegt keine Genehmigung."
        ),
    },
    "French": {
        "label": "Applicabilité de l’évaluation (déterminée par le code)",
        "allowed": (
            "Le contexte permet un `GO/NO_GO` propre au décideur ; la conclusion "
            "reste conditionnée par les preuves citées."
        ),
        "not_allowed": "Le `GO/NO_GO` propre au décideur n’est pas évalué.",
        "provenance": "Provenance des critères de réussite",
        "caveat": (
            "Tout seuil décisionnel supplémentaire est une proposition d’analyste "
            "sauf s’il est explicitement approuvé ; un benchmark cité ne prouve "
            "pas cette approbation."
        ),
    },
    "Spanish": {
        "label": "Aplicabilidad de la evaluación (determinada por código)",
        "allowed": (
            "El contexto permite un `GO/NO_GO` específico del responsable; la "
            "conclusión sigue dependiendo de la evidencia citada."
        ),
        "not_allowed": "No se evalúa un `GO/NO_GO` específico del responsable.",
        "provenance": "Procedencia de los criterios de éxito",
        "caveat": (
            "Todo umbral de decisión adicional es una propuesta del analista salvo "
            "que se identifique explícitamente como aprobado; un benchmark citado "
            "no demuestra esa aprobación."
        ),
    },
}


def add_applicability_block(
    report: str,
    *,
    decision_gate: dict[str, Any] | None,
    output_language: str,
) -> str:
    """Insert one idempotent, deterministic block after the first H1.

    Runs predating Decision Context have no gate.  Leaving their bytes alone is
    more honest than backfilling them as orientation reports after the fact.
    """

    if not decision_gate or _MARKER in report:
        return report
    copy = _COPY.get(output_language, _COPY["English"])
    mode = str(decision_gate.get("mode") or "unknown")
    provenance = decision_gate.get("threshold_provenance") or {}
    provenance_status = str(provenance.get("status") or "unknown")
    applicability = (
        copy["allowed"]
        if decision_gate.get("go_no_go_allowed") is True
        else copy["not_allowed"]
    )
    block = (
        f"{_MARKER}\n\n> **{copy['label']}:** Mode `{mode}`. {applicability} "
        f"{copy['provenance']}: `{provenance_status}`. {copy['caveat']}"
    )

    lines = report.splitlines()
    insert_at = next(
        (index + 1 for index, line in enumerate(lines) if line.startswith("# ")),
        0,
    )
    lines[insert_at:insert_at] = ["", block, ""]
    rendered = "\n".join(lines)
    if report.endswith("\n"):
        rendered += "\n"
    return rendered
