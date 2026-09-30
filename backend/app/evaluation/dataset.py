"""Evaluation benchmark dataset with 35 grounded questions across 10 categories (P21).

Categories:
1. architecture
2. request_flow
3. dependencies
4. classes
5. methods
6. apis
7. database_interaction
8. impact
9. risk
10. modernization
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvaluationItem:
    id: str
    category: str
    question: str
    expected_entities: list[str]
    expected_relationships: list[str]
    evidence_requirements: list[str]
    acceptable_answer_characteristics: list[str]
    target_symbol: str | None = None


EVALUATION_DATASET: list[EvaluationItem] = [
    # -------------------------------------------------------------------------
    # 1. Architecture (Items 1-4)
    # -------------------------------------------------------------------------
    EvaluationItem(
        id="arch-01",
        category="architecture",
        question="What is the high-level architecture of payment-service?",
        expected_entities=["PaymentController", "PaymentService", "PaymentRepository", "payments"],
        expected_relationships=["EXPOSES", "DEPENDS_ON", "QUERIES"],
        evidence_requirements=["Controller -> Service -> Repository chain verified"],
        acceptable_answer_characteristics=["Identifies 3-tier Spring Boot architecture with REST controller and JPA repository."],
    ),
    EvaluationItem(
        id="arch-02",
        category="architecture",
        question="Which classes serve as controllers in the application?",
        expected_entities=["PaymentController", "RefundController"],
        expected_relationships=["EXPOSES"],
        evidence_requirements=["Annotated with @RestController or exposes endpoints"],
        acceptable_answer_characteristics=["Lists PaymentController and RefundController."],
    ),
    EvaluationItem(
        id="arch-03",
        category="architecture",
        question="What services coordinate business logic?",
        expected_entities=["PaymentService", "NotificationService", "MetricsFacade"],
        expected_relationships=["DEPENDS_ON"],
        evidence_requirements=["Annotated with @Service or acts as facade"],
        acceptable_answer_characteristics=["Mentions PaymentService and NotificationService."],
    ),
    EvaluationItem(
        id="arch-04",
        category="architecture",
        question="How does the repository layer interact with persistence?",
        expected_entities=["PaymentRepository", "PaymentEntity", "payments"],
        expected_relationships=["QUERIES", "REFERENCES"],
        evidence_requirements=["Repository queries payments table"],
        acceptable_answer_characteristics=["Explains that PaymentRepository manages PaymentEntity and queries table payments."],
    ),

    # -------------------------------------------------------------------------
    # 2. Request Flow (Items 5-8)
    # -------------------------------------------------------------------------
    EvaluationItem(
        id="flow-01",
        category="request_flow",
        question="How does /api/payment reach the database?",
        expected_entities=["/api/payment", "PaymentController", "PaymentService", "PaymentRepository", "payments"],
        expected_relationships=["EXPOSES", "CALLS", "QUERIES"],
        evidence_requirements=["Step 1 endpoint, Step 2 controller, Step 3 service, Step 4 repository, Step 5 database"],
        acceptable_answer_characteristics=["Traces full path from HTTP endpoint to payments database table."],
    ),
    EvaluationItem(
        id="flow-02",
        category="request_flow",
        question="Trace the request flow for POST /api/refund/{paymentId}.",
        expected_entities=["/api/refund/{paymentId}", "RefundController", "PaymentService", "PaymentRepository"],
        expected_relationships=["EXPOSES", "CALLS", "QUERIES"],
        evidence_requirements=["RefundController handler method invoked"],
        acceptable_answer_characteristics=["Traces RefundController calling PaymentService."],
    ),
    EvaluationItem(
        id="flow-03",
        category="request_flow",
        question="What components execute during payment creation?",
        expected_entities=["PaymentController", "PaymentService", "PaymentRepository"],
        expected_relationships=["CALLS"],
        evidence_requirements=["Method create calls processPayment"],
        acceptable_answer_characteristics=["Includes PaymentController.create and PaymentService.processPayment."],
    ),
    EvaluationItem(
        id="flow-04",
        category="request_flow",
        question="Does request flow /api/payment reach any external notification system?",
        expected_entities=["PaymentService", "NotificationService"],
        expected_relationships=["DEPENDS_ON"],
        evidence_requirements=["PaymentService invokes NotificationService"],
        acceptable_answer_characteristics=["Explains that PaymentService calls NotificationService."],
    ),

    # -------------------------------------------------------------------------
    # 3. Dependencies (Items 9-12)
    # -------------------------------------------------------------------------
    EvaluationItem(
        id="dep-01",
        category="dependencies",
        question="What does PaymentController depend on?",
        expected_entities=["PaymentController", "PaymentService"],
        expected_relationships=["DEPENDS_ON"],
        evidence_requirements=["Field or constructor injection of PaymentService"],
        acceptable_answer_characteristics=["PaymentService is injected into PaymentController."],
    ),
    EvaluationItem(
        id="dep-02",
        category="dependencies",
        question="What are the outgoing dependencies of PaymentService?",
        expected_entities=["PaymentService", "PaymentRepository", "NotificationService", "MetricsFacade"],
        expected_relationships=["DEPENDS_ON", "USES"],
        evidence_requirements=["Injected repository and notification service"],
        acceptable_answer_characteristics=["Lists PaymentRepository and NotificationService."],
    ),
    EvaluationItem(
        id="dep-03",
        category="dependencies",
        question="Which components depend on MetricsFacade?",
        expected_entities=["MetricsFacade", "PaymentService"],
        expected_relationships=["DEPENDS_ON", "CALLS"],
        evidence_requirements=["Incoming dependency from PaymentService"],
        acceptable_answer_characteristics=["PaymentService utilizes MetricsFacade for telemetry."],
    ),
    EvaluationItem(
        id="dep-04",
        category="dependencies",
        question="Are there circular dependencies between services?",
        expected_entities=["PaymentService", "NotificationService"],
        expected_relationships=["DEPENDS_ON"],
        evidence_requirements=["PaymentService -> NotificationService and NotificationService -> PaymentService"],
        acceptable_answer_characteristics=["Identifies cycle between PaymentService and NotificationService."],
    ),

    # -------------------------------------------------------------------------
    # 4. Classes (Items 13-16)
    # -------------------------------------------------------------------------
    EvaluationItem(
        id="cls-01",
        category="classes",
        question="Where is PaymentController defined and what annotations does it have?",
        expected_entities=["PaymentController"],
        expected_relationships=["CONTAINS"],
        evidence_requirements=["File path src/.../PaymentController.java", "@RestController"],
        acceptable_answer_characteristics=["References source file and @RestController annotation."],
    ),
    EvaluationItem(
        id="cls-02",
        category="classes",
        question="What is the package name of PaymentEntity?",
        expected_entities=["PaymentEntity"],
        expected_relationships=["CONTAINS"],
        evidence_requirements=["com.example.payment.entity"],
        acceptable_answer_characteristics=["Identifies com.example.payment.entity."],
    ),
    EvaluationItem(
        id="cls-03",
        category="classes",
        question="What interfaces are declared in the codebase?",
        expected_entities=["PaymentRepository"],
        expected_relationships=["EXTENDS"],
        evidence_requirements=["PaymentRepository is an interface"],
        acceptable_answer_characteristics=["Names PaymentRepository as interface."],
    ),
    EvaluationItem(
        id="cls-04",
        category="classes",
        question="Which classes define JPA entity mappings?",
        expected_entities=["PaymentEntity"],
        expected_relationships=["REFERENCES"],
        evidence_requirements=["@Entity or @Table annotation"],
        acceptable_answer_characteristics=["Identifies PaymentEntity."],
    ),

    # -------------------------------------------------------------------------
    # 5. Methods (Items 17-20)
    # -------------------------------------------------------------------------
    EvaluationItem(
        id="mth-01",
        category="methods",
        question="What method handles payment creation in PaymentService?",
        expected_entities=["processPayment", "PaymentService"],
        expected_relationships=["CONTAINS"],
        evidence_requirements=["Method signature in PaymentService.java"],
        acceptable_answer_characteristics=["Identifies processPayment."],
    ),
    EvaluationItem(
        id="mth-02",
        category="methods",
        question="What is the return type of PaymentController.create?",
        expected_entities=["create", "PaymentController"],
        expected_relationships=["CONTAINS"],
        evidence_requirements=["return_type ResponseEntity"],
        acceptable_answer_characteristics=["ResponseEntity."],
    ),
    EvaluationItem(
        id="mth-03",
        category="methods",
        question="Which method in PaymentRepository saves records?",
        expected_entities=["save", "PaymentRepository"],
        expected_relationships=["CONTAINS"],
        evidence_requirements=["save method declaration"],
        acceptable_answer_characteristics=["Names save method."],
    ),
    EvaluationItem(
        id="mth-04",
        category="methods",
        question="What notification method does NotificationService expose?",
        expected_entities=["NotificationService"],
        expected_relationships=["CONTAINS"],
        evidence_requirements=["Notification method in NotificationService.java"],
        acceptable_answer_characteristics=["Mentions receipt or notification dispatch method."],
    ),

    # -------------------------------------------------------------------------
    # 6. APIs (Items 21-23)
    # -------------------------------------------------------------------------
    EvaluationItem(
        id="api-01",
        category="apis",
        question="What HTTP methods and paths are mapped by PaymentController?",
        expected_entities=["POST", "/api/payment"],
        expected_relationships=["EXPOSES"],
        evidence_requirements=["POST /api/payment mapping"],
        acceptable_answer_characteristics=["POST /api/payment."],
    ),
    EvaluationItem(
        id="api-02",
        category="apis",
        question="What endpoint handles refunds?",
        expected_entities=["RefundController", "/api/refund/{paymentId}"],
        expected_relationships=["EXPOSES"],
        evidence_requirements=["POST /api/refund/{paymentId}"],
        acceptable_answer_characteristics=["POST /api/refund/{paymentId}."],
    ),
    EvaluationItem(
        id="api-03",
        category="apis",
        question="How many REST endpoints are exposed by the application?",
        expected_entities=["/api/payment", "/api/refund/{paymentId}"],
        expected_relationships=["EXPOSES"],
        evidence_requirements=["Total endpoints: 2"],
        acceptable_answer_characteristics=["Mentions 2 endpoints."],
    ),

    # -------------------------------------------------------------------------
    # 7. Database Interaction (Items 24-26)
    # -------------------------------------------------------------------------
    EvaluationItem(
        id="db-01",
        category="database_interaction",
        question="Which database tables are referenced in payment-service?",
        expected_entities=["payments"],
        expected_relationships=["QUERIES", "REFERENCES"],
        evidence_requirements=["payments table"],
        acceptable_answer_characteristics=["Names payments table."],
    ),
    EvaluationItem(
        id="db-02",
        category="database_interaction",
        question="Does PaymentController interact directly with database tables?",
        expected_entities=["PaymentController", "payments"],
        expected_relationships=["QUERIES"],
        evidence_requirements=["Controller queries zero tables directly; delegates to service"],
        acceptable_answer_characteristics=["Affirms that PaymentController delegates to service and does not bypass."],
    ),
    EvaluationItem(
        id="db-03",
        category="database_interaction",
        question="What component maps to the payments database table?",
        expected_entities=["PaymentEntity", "payments"],
        expected_relationships=["REFERENCES"],
        evidence_requirements=["PaymentEntity @Table(name = 'payments')"],
        acceptable_answer_characteristics=["Identifies PaymentEntity."],
    ),

    # -------------------------------------------------------------------------
    # 8. Impact (Items 27-29)
    # -------------------------------------------------------------------------
    EvaluationItem(
        id="imp-01",
        category="impact",
        target_symbol="PaymentService.processPayment",
        question="What is the blast radius if PaymentService.processPayment is modified?",
        expected_entities=["PaymentController", "PaymentServiceTest", "payments"],
        expected_relationships=["CALLS", "TESTS", "QUERIES"],
        evidence_requirements=["Direct callers: PaymentController.create; Tests: PaymentServiceTest"],
        acceptable_answer_characteristics=["Lists PaymentController as caller and PaymentServiceTest as affected test."],
    ),
    EvaluationItem(
        id="imp-02",
        category="impact",
        target_symbol="PaymentRepository",
        question="What components are affected by changes to PaymentRepository?",
        expected_entities=["PaymentService", "payments"],
        expected_relationships=["DEPENDS_ON", "QUERIES"],
        evidence_requirements=["PaymentService depends on PaymentRepository"],
        acceptable_answer_characteristics=["Mentions PaymentService and downstream payments table."],
    ),
    EvaluationItem(
        id="imp-03",
        category="impact",
        target_symbol="PaymentController",
        question="Which APIs are impacted if PaymentController is changed?",
        expected_entities=["/api/payment"],
        expected_relationships=["EXPOSES"],
        evidence_requirements=["Exposes /api/payment"],
        acceptable_answer_characteristics=["Lists POST /api/payment."],
    ),

    # -------------------------------------------------------------------------
    # 9. Risk (Items 30-32)
    # -------------------------------------------------------------------------
    EvaluationItem(
        id="risk-01",
        category="risk",
        question="What is the highest severity technical risk detected in payment-service?",
        expected_entities=["PaymentService", "NotificationService"],
        expected_relationships=["DEPENDS_ON"],
        evidence_requirements=["CIRCULAR_DEPENDENCY between PaymentService and NotificationService"],
        acceptable_answer_characteristics=["Identifies circular dependency cycle."],
    ),
    EvaluationItem(
        id="risk-02",
        category="risk",
        question="Which service has an automated testing gap?",
        expected_entities=["NotificationService"],
        expected_relationships=["TESTS"],
        evidence_requirements=["TESTING_GAP: NotificationService has no unit tests"],
        acceptable_answer_characteristics=["Identifies NotificationService."],
    ),
    EvaluationItem(
        id="risk-03",
        category="risk",
        question="Why is PaymentService flagged as a high dependency component?",
        expected_entities=["PaymentService"],
        expected_relationships=["DEPENDS_ON", "CALLS"],
        evidence_requirements=["incoming dependencies >= 3", "outgoing dependencies >= 3"],
        acceptable_answer_characteristics=["Explains high fan-in and fan-out coupling while clarifying it is not bad software."],
    ),

    # -------------------------------------------------------------------------
    # 10. Modernization (Items 33-35)
    # -------------------------------------------------------------------------
    EvaluationItem(
        id="mod-01",
        category="modernization",
        question="What is the recommended modernization direction for the circular dependency?",
        expected_entities=["PaymentService", "NotificationService"],
        expected_relationships=["DEPENDS_ON"],
        evidence_requirements=["Domain events or mediator pattern"],
        acceptable_answer_characteristics=["Recommends event-driven decoupling or mediator."],
    ),
    EvaluationItem(
        id="mod-02",
        category="modernization",
        question="What modernization candidate addresses central service coupling?",
        expected_entities=["PaymentService"],
        expected_relationships=["DEPENDS_ON"],
        evidence_requirements=["DECOMPOSITION_CANDIDATE: Partition PaymentService responsibilities"],
        acceptable_answer_characteristics=["Recommends decomposing PaymentService into cohesive domain services."],
    ),
    EvaluationItem(
        id="mod-03",
        category="modernization",
        question="What testing modernization should be prioritized first?",
        expected_entities=["NotificationService"],
        expected_relationships=["TESTS"],
        evidence_requirements=["Implement automated tests for NotificationService"],
        acceptable_answer_characteristics=["Prioritizes test suite implementation for NotificationService."],
    ),
]
