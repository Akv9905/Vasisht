"""Evidence-backed Question Answering engine (P10).

Full pipeline:
Question
  -> Question analysis
  -> Structured retrieval
  -> Graph retrieval
  -> Optional semantic retrieval
  -> Evidence package
  -> Optional LLM reasoning
  -> Answer validation
  -> Evidence-backed response

Constraints:
- Response schema: { answer, evidence, flow, limitations }
- Evidence must reference actual files, classes, methods, source locations, and relationships.
- If evidence is insufficient: "Insufficient evidence in the analyzed repository."
- Never hallucinate; never invent classes or database relationships.
- If LLM is unavailable: return deterministic evidence and explain that AI reasoning is unavailable.
- Project isolation: users/requests cannot access another project's analysis data.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph.models import DependencyGraph, RelationshipType
from app.graph.traversal import RequestFlowResult, trace_request_flow
from app.llm import (
    DETERMINISTIC_FALLBACK_MESSAGE,
    DeterministicFallbackLLMProvider,
    LLMProvider,
    get_llm_provider,
)
from app.models import AnalysisRun, Project, Repository
from app.parser.models import ParseResult
from app.retrieval import (
    CombinedRetrievalResult,
    CombinedRetriever,
    EmbeddingProvider,
    get_embedding_provider,
)

logger = logging.getLogger(__name__)


@dataclass
class EvidenceItem:
    """A concrete piece of source code evidence referencing actual repository facts."""

    symbol: str
    kind: str
    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    relationship: str | None = None
    details: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FlowStepItem:
    """Individual architectural execution step."""

    step: int
    role: str
    symbol: str
    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    relationship_to_next: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FlowList(list):
    """List of flow steps with backwards-compatible attributes for RequestFlowResult."""

    def __init__(
        self,
        items: list[dict[str, Any]] | None = None,
        reaches_database: bool = False,
        database_table: str | None = None,
        unresolved_steps: list[str] | None = None,
    ) -> None:
        super().__init__(items or [])
        self.reaches_database = reaches_database
        self.database_table = database_table
        self.unresolved_steps = unresolved_steps or []
        self.steps = list(items or [])

    def to_dict(self) -> dict[str, Any]:
        return {
            "reaches_database": self.reaches_database,
            "database_table": self.database_table,
            "steps": list(self),
            "unresolved_steps": self.unresolved_steps,
        }


@dataclass
class AnswerResult:
    """Complete evidence-grounded answer to a developer question."""

    question: str
    answer: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    flow: Any = field(default_factory=FlowList)
    limitations: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [
            f"Question: {self.question}",
            "",
            f"Answer: {self.answer}",
        ]
        if self.flow:
            lines.append("")
            lines.append("Execution Flow:")
            for s in self.flow:
                if isinstance(s, dict):
                    step_num = s.get("step")
                    role = s.get("role")
                    symbol = s.get("symbol")
                    rel = f" --[{s.get('relationship_to_next')}]--> " if s.get("relationship_to_next") else ""
                else:
                    step_num = getattr(s, "step_number", "?")
                    role = getattr(s, "node_kind", "?")
                    symbol = getattr(s, "node_name", "?")
                    rel = f" --[{getattr(s, 'relationship', '')}]--> " if getattr(s, "relationship", None) else ""
                lines.append(f"  {step_num}. [{role}] {symbol}{rel}")

        if self.evidence:
            lines.append("")
            lines.append("Evidence:")
            for ev in self.evidence:
                loc = f":{ev.get('start_line')}" if ev.get("start_line") else ""
                lines.append(f"  - [{ev.get('kind') or ev.get('type')}] {ev.get('symbol')} in {ev.get('file_path')}{loc}")
                if ev.get("details") or ev.get("relationship"):
                    info = ev.get("relationship") or ev.get("details")
                    lines.append(f"    {info}")

        if self.limitations:
            lines.append("")
            lines.append("Limitations:")
            for lim in self.limitations:
                lines.append(f"  - {lim}")

        return lines

    def to_dict(self) -> dict[str, Any]:
        flow_data = list(self.flow) if isinstance(self.flow, (list, FlowList)) else []
        return {
            "answer": self.answer,
            "evidence": self.evidence,
            "flow": flow_data,
            "limitations": self.limitations,
        }


class CodebaseQAEngine:
    """Orchestrates structured retrieval, graph traversal, semantic retrieval, and optional LLM reasoning."""

    def __init__(
        self,
        session: Session,
        project_id: int,
        analysis_run_id: int | None = None,
        llm_provider: LLMProvider | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.session = session
        self.project_id = project_id
        self.llm = llm_provider or get_llm_provider()
        self.embedding_provider = embedding_provider or get_embedding_provider()

        # 1. Project Isolation Check
        project = self.session.get(Project, project_id)
        if project is None:
            raise ValueError(f"Project with ID {project_id} not found.")

        # Find latest completed run belonging strictly to this project's repositories
        stmt = (
            select(AnalysisRun)
            .join(Repository, AnalysisRun.repository_id == Repository.id)
            .where(
                Repository.project_id == project_id,
                AnalysisRun.status.in_(["completed", "completed_with_errors"]),
            )
        )
        if analysis_run_id is not None:
            stmt = stmt.where(AnalysisRun.id == analysis_run_id)

        run = self.session.scalar(stmt.order_by(AnalysisRun.id.desc()).limit(1))
        if run is None:
            if analysis_run_id is not None:
                # Run was requested but does not belong to this project!
                raise PermissionError(
                    f"Access denied: AnalysisRun {analysis_run_id} does not belong to project {project_id}."
                )
            self.run_id = None
        else:
            self.run_id = run.id

        self.retriever = (
            CombinedRetriever(session, self.run_id, self.embedding_provider)
            if self.run_id
            else None
        )

    def answer(self, question: str) -> AnswerResult:
        """Execute the full Q&A pipeline."""
        if not question or not question.strip():
            return AnswerResult(
                question=question,
                answer="Insufficient evidence in the analyzed repository.",
                limitations=["No question was provided."],
            )

        if not self.run_id or not self.retriever:
            return AnswerResult(
                question=question,
                answer="Insufficient evidence in the analyzed repository.",
                limitations=["No completed analysis runs found for this project."],
            )

        # 2. Combined Retrieval: Structured + Graph + Optional Semantic
        combined = self.retriever.retrieve(question, top_chunks=5)

        # 3. Assemble flow
        flow_steps: list[dict[str, Any]] = []
        if combined.flow and combined.flow.steps:
            for s in combined.flow.steps:
                flow_steps.append({
                    "step": s.step,
                    "role": s.role,
                    "symbol": s.symbol,
                    "file_path": s.file_path,
                    "start_line": s.lines[0],
                    "end_line": s.lines[1],
                    "relationship_to_next": s.relationship_to_next,
                })

        # Check if question asked about a flow / endpoint / reach
        is_flow_or_endpoint_query = bool(
            re.search(r"(/api/[a-zA-Z0-9_\-\./{}]*)", question)
        ) or any(k in question.lower() for k in ["reach", "flow", "lead to", "path from", "trace"])

        if is_flow_or_endpoint_query and not flow_steps:
            return AnswerResult(
                question=question,
                answer="Insufficient evidence in the analyzed repository.",
                flow=[],
                evidence=[],
                limitations=[
                    "The requested endpoint or architectural flow could not be resolved from repository facts.",
                ],
            )

        # 4. Check for sufficient evidence
        has_sufficient_evidence = bool(
            flow_steps
            or combined.classes
            or combined.methods
            or combined.graph_edges
            or (combined.chunks and combined.chunks[0].score > 0.30)
        )

        if not has_sufficient_evidence:
            return AnswerResult(
                question=question,
                answer="Insufficient evidence in the analyzed repository.",
                flow=[],
                evidence=[],
                limitations=[
                    "The question did not match any identifiable endpoints, classes, dependencies, or database structures in the repository.",
                    "Ask about specific endpoints (e.g. '/api/payment'), classes (e.g. 'PaymentService'), or database tables.",
                ],
            )

        # 5. Build standardized evidence package
        evidence_list: list[dict[str, Any]] = []
        for ev in combined.evidence:
            evidence_list.append({
                "type": ev.get("type") or ev.get("role") or "evidence",
                "symbol": ev.get("symbol", ""),
                "file_path": ev.get("file_path", "unknown"),
                "start_line": ev.get("start_line"),
                "end_line": ev.get("end_line"),
                "relationship": ev.get("relationship") or ev.get("role"),
                "details": ev.get("details") or ev.get("snippet"),
            })

        limitations: list[str] = [
            "Static compile-time analysis; dynamic runtime reflection and proxies are not resolved.",
        ]

        # 6. Optional LLM reasoning or deterministic synthesis
        if self.llm.is_available():
            llm_resp = self.llm.explain_evidence(question, evidence_list, flow=flow_steps)
            if llm_resp.success and llm_resp.content:
                answer_text = llm_resp.content
            else:
                answer_text = self._synthesize_deterministic_answer(question, combined, flow_steps)
                limitations.append("AI reasoning unavailable — deterministic analysis mode enabled.")
        else:
            answer_text = self._synthesize_deterministic_answer(question, combined, flow_steps)
            limitations.append("AI reasoning unavailable — deterministic analysis mode enabled.")

        # 7. Answer Validation: Ensure answer mentions valid entities
        if not flow_steps and not combined.classes and not combined.methods and not combined.chunks:
            answer_text = "Insufficient evidence in the analyzed repository."

        flow_list_obj = FlowList(
            flow_steps,
            reaches_database=combined.flow.reaches_database if combined.flow else False,
            database_table=combined.flow.database if combined.flow else None,
        )

        return AnswerResult(
            question=question,
            answer=answer_text,
            flow=flow_list_obj,
            evidence=evidence_list,
            limitations=limitations,
        )

    def _synthesize_deterministic_answer(
        self,
        question: str,
        combined: CombinedRetrievalResult,
        flow_steps: list[dict[str, Any]],
    ) -> str:
        """Construct grounded, deterministic explanation without hallucinating."""
        if flow_steps and combined.flow:
            chain_str = " -> ".join(
                f"{s['symbol']} ({s['role']})" for s in flow_steps
            )
            db_status = (
                f"and reaches the '{combined.flow.database}' database table"
                if combined.flow.reaches_database
                else "without reaching a database table"
            )
            return (
                f"Request to '{combined.flow.endpoint}' is processed sequentially through: "
                f"{chain_str}, {db_status}."
            )

        if combined.classes:
            names = [c.name for c in combined.classes]
            return f"Identified matching class(es): {', '.join(names)}."

        if combined.methods:
            names = [f"{m.class_name}.{m.name}" for m in combined.methods]
            return f"Identified matching method(s): {', '.join(names)}."

        if combined.chunks:
            top_c = combined.chunks[0]
            return f"Relevant content identified in {top_c.symbol_ref} ({top_c.file_path or 'unknown'})."

        return "Insufficient evidence in the analyzed repository."


def answer_question(
    question: str,
    parse_result: ParseResult | None = None,
    graph: DependencyGraph | None = None,
    session: Session | None = None,
    project_id: int | None = None,
    analysis_run_id: int | None = None,
    llm_provider: LLMProvider | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> AnswerResult:
    """Unified entrypoint for Q&A answering.

    Supports both in-memory graph queries (P6 CLI) and PostgreSQL/combined retrieval (P10).
    """
    # If session and project_id are provided, use the full P10 CodebaseQAEngine
    if session is not None and project_id is not None:
        engine = CodebaseQAEngine(
            session=session,
            project_id=project_id,
            analysis_run_id=analysis_run_id,
            llm_provider=llm_provider,
            embedding_provider=embedding_provider,
        )
        return engine.answer(question)

    # In-memory execution for standalone CLI / tests without database
    q_lower = question.lower()
    if graph is None and parse_result is None:
        return AnswerResult(
            question=question,
            answer="Insufficient evidence in the analyzed repository (no parsed codebase available).",
            limitations=["Analysis must be performed before answering questions."],
        )

    # Check for flow queries
    is_flow_query = any(k in q_lower for k in ["reach", "flow", "trace", "path", "how does", "lead to"])
    endpoint_match = re.search(r"(/api/[a-zA-Z0-9_\-\/\{\}]+)", question)

    if (is_flow_query or endpoint_match) and graph is not None:
        target_endpoint = endpoint_match.group(1) if endpoint_match else None
        if not target_endpoint:
            for n in graph.nodes:
                if n.kind == "endpoint" and n.name.replace("POST ", "").replace("GET ", "") in question:
                    target_endpoint = n.name
                    break

        if target_endpoint:
            flow_res = trace_request_flow(graph, target_endpoint)
            if flow_res.steps:
                flow_items: list[dict[str, Any]] = []
                evidence_items: list[dict[str, Any]] = []
                chain_parts: list[str] = []

                for step in flow_res.steps:
                    chain_parts.append(f"{step.node_name} ({step.node_kind})")
                    step_dict = {
                        "step": step.step_number,
                        "role": step.node_kind.capitalize(),
                        "symbol": step.node_name,
                        "file_path": step.file_path or "unknown",
                        "start_line": step.details.get("start_line"),
                        "end_line": step.details.get("end_line"),
                        "relationship_to_next": step.relationship,
                    }
                    flow_items.append(step_dict)
                    if step.file_path:
                        evidence_items.append({
                            "type": step.node_kind,
                            "symbol": step.node_name,
                            "file_path": step.file_path,
                            "start_line": step.details.get("start_line"),
                            "end_line": step.details.get("end_line"),
                            "relationship": step.relationship or "entry point",
                            "details": f"Participates in request chain via {step.relationship or 'entry point'}",
                        })

                db_status = (
                    f"and reaches the '{flow_res.database_table}' database table"
                    if flow_res.reaches_database
                    else "but does not reach a database table"
                )
                answer_text = (
                    f"Request to '{target_endpoint}' is processed sequentially through: "
                    + " -> ".join(chain_parts)
                    + f", {db_status}."
                )

                limitations = [
                    "Static call graph analysis; runtime reflection or dynamic proxies are not resolved.",
                ]
                if flow_res.unresolved_steps:
                    limitations.append(f"Unresolved calls encountered: {', '.join(flow_res.unresolved_steps)}")

                flow_list_obj = FlowList(
                    flow_items,
                    reaches_database=flow_res.reaches_database,
                    database_table=flow_res.database_table,
                    unresolved_steps=flow_res.unresolved_steps,
                )
                return AnswerResult(
                    question=question,
                    answer=answer_text,
                    flow=flow_list_obj,
                    evidence=evidence_items,
                    limitations=limitations,
                )
            else:
                return AnswerResult(
                    question=question,
                    answer="Insufficient evidence in the analyzed repository.",
                    limitations=[
                        f"The endpoint '{target_endpoint}' was not found in the analyzed repository.",
                    ],
                )

    # Dependency questions
    if any(k in q_lower for k in ["depend", "call", "use", "require"]) and graph is not None:
        for node in graph.nodes:
            if node.kind in ("class", "interface") and node.name.lower() in q_lower:
                out_deps = graph.outgoing_edges(node.id, RelationshipType.DEPENDS_ON)
                target_names = list(dict.fromkeys(
                    (graph.get_node(e.target_id) or node).name for e in out_deps if e.resolved
                ))
                ev = [{
                    "type": node.kind,
                    "symbol": node.name,
                    "file_path": node.file_path or "unknown",
                    "details": f"Defined with {len(out_deps)} direct dependencies",
                }]
                ans = (
                    f"{node.name} directly depends on: {', '.join(target_names)}."
                    if target_names
                    else f"{node.name} has no outgoing type dependencies."
                )
                return AnswerResult(
                    question=question,
                    answer=ans,
                    evidence=ev,
                    limitations=["Only static compile-time dependencies are tracked."],
                )

    # Database / table questions
    if any(k in q_lower for k in ["table", "database", "sql", "entity", "schema"]) and graph is not None:
        tables = graph.find_nodes(kind="database_table")
        if tables:
            tbl_names = [t.name for t in tables]
            ev = [
                {
                    "type": "database_table",
                    "symbol": t.name,
                    "file_path": t.file_path or "database schema",
                    "details": f"Table referenced in codebase: {t.name}",
                }
                for t in tables
            ]
            return AnswerResult(
                question=question,
                answer=f"The repository references database table(s): {', '.join(tbl_names)}.",
                evidence=ev,
                limitations=["Database tables extracted from JPA @Table annotations and SQL migration scripts."],
            )

    # Test questions
    if any(k in q_lower for k in ["test", "testing", "coverage"]) and graph is not None:
        test_nodes = [n for n in graph.nodes if "test" in n.name.lower() and n.kind == "class"]
        if test_nodes:
            names = [t.name for t in test_nodes]
            ev = [
                {
                    "type": "test_class",
                    "symbol": t.name,
                    "file_path": t.file_path or "src/test",
                    "details": "Automated test suite class",
                }
                for t in test_nodes
            ]
            return AnswerResult(
                question=question,
                answer=f"Identified automated test classes: {', '.join(names)}.",
                evidence=ev,
                limitations=["Tests detected by @Test annotations and test directory conventions."],
            )

    # Default fallback when question cannot be grounded
    return AnswerResult(
        question=question,
        answer="Insufficient evidence in the analyzed repository.",
        limitations=[
            "The question did not match any identifiable endpoints, classes, dependencies, or database structures in the repository.",
            "Ask about specific endpoints (e.g. '/api/payment'), classes (e.g. 'PaymentService'), or database tables.",
        ],
    )
