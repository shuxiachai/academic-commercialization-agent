"""Read-only capability contracts; production registration is opt-in."""

from academic_agent.tools.evidence_search import (
    ReadOnlySearchAdapter,
    ToolAdapterFailure,
    ToolAdapterResponse,
    ToolEvidenceCandidate,
)

__all__ = [
    "ReadOnlySearchAdapter",
    "ToolAdapterFailure",
    "ToolAdapterResponse",
    "ToolEvidenceCandidate",
]
