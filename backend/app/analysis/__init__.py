"""Analysis engines package (P6, P10, P13)."""

from app.analysis.qa import AnswerResult, EvidenceItem, answer_question
from app.analysis.risks import (
    RiskFinding,
    RiskReport,
    analyze_risks,
    detect_circular_dependencies,
    detect_database_coupling,
    detect_high_coupling,
    detect_testing_gaps,
)

__all__ = [
    "AnswerResult",
    "EvidenceItem",
    "RiskFinding",
    "RiskReport",
    "analyze_risks",
    "answer_question",
    "detect_circular_dependencies",
    "detect_database_coupling",
    "detect_high_coupling",
    "detect_testing_gaps",
]
