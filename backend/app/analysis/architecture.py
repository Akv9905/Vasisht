"""Architecture analysis and visualization data models (P14).

Exposes:
- packages
- modules
- controllers
- services
- repositories
- databases
- APIs
- external integrations
- tests
- graph data suitable for frontend visualization
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.graph.models import DependencyGraph, RelationshipType
from app.graph.traversal import verify_controller_service_repository
from app.parser.models import ParseResult


@dataclass
class ArchitectureView:
    packages: list[dict[str, Any]] = field(default_factory=list)
    modules: list[dict[str, Any]] = field(default_factory=list)
    controllers: list[dict[str, Any]] = field(default_factory=list)
    services: list[dict[str, Any]] = field(default_factory=list)
    repositories: list[dict[str, Any]] = field(default_factory=list)
    databases: list[dict[str, Any]] = field(default_factory=list)
    apis: list[dict[str, Any]] = field(default_factory=list)
    external_integrations: list[dict[str, Any]] = field(default_factory=list)
    tests: list[dict[str, Any]] = field(default_factory=list)
    chains: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def categorize_node(node_id: str, kind: str, name: str) -> str:
    """Categorize graph node into high-level architectural role."""
    id_lower = node_id.lower()
    name_lower = name.lower()

    if kind == "endpoint" or id_lower.startswith("endpoint:"):
        return "api"
    if kind == "package" or id_lower.startswith("package:"):
        return "package"
    if kind in ("database_table", "database_reference", "table") or id_lower.startswith("table:") or id_lower.startswith("database:"):
        return "database"
    if "test" in name_lower or "test" in id_lower or kind == "test_class":
        return "test"
    if "controller" in name_lower or "controller" in id_lower:
        return "controller"
    if "repository" in name_lower or "repo" in id_lower or "dao" in id_lower:
        return "repository"
    if "service" in name_lower or "service" in id_lower or "facade" in id_lower:
        return "service"
    if "client" in name_lower or "feign" in id_lower or "kafka" in id_lower or "http" in id_lower:
        return "external"
    if kind in ("class", "interface", "entity"):
        if "entity" in id_lower or "entity" in name_lower:
            return "database"
        return "class"
    return "other"


def build_architecture_view(
    graph: DependencyGraph,
    parse_result: ParseResult | None = None,
) -> ArchitectureView:
    """Construct structured architectural inventory from dependency graph."""
    packages_map: dict[str, dict[str, Any]] = {}
    controllers: list[dict[str, Any]] = []
    services: list[dict[str, Any]] = []
    repositories: list[dict[str, Any]] = []
    databases_map: dict[str, dict[str, Any]] = {}
    apis: list[dict[str, Any]] = []
    external_integrations: list[dict[str, Any]] = []
    tests_list: list[dict[str, Any]] = []

    # 1. Packages & Classes
    for node in graph.nodes:
        if node.kind == "package" or node.id.startswith("package:"):
            pkg_name = node.name
            if pkg_name not in packages_map:
                packages_map[pkg_name] = {
                    "id": node.id,
                    "name": pkg_name,
                    "classes": [],
                }

    for node in graph.nodes:
        if node.kind in ("class", "interface"):
            name_lower = node.name.lower()
            meta = dict(node.metadata or {})

            # Skip framework annotations / imported external types
            if node.file_path is None or node.name in ("RestController", "Controller", "Service", "Repository", "Test", "SpringBootTest", "Component"):
                continue

            # Package grouping
            pkg = meta.get("package")
            if not pkg and node.qualified_name and "." in node.qualified_name:
                pkg = node.qualified_name.rsplit(".", 1)[0]
            if pkg:
                if pkg not in packages_map:
                    packages_map[pkg] = {"id": f"package:{pkg}", "name": pkg, "classes": []}
                packages_map[pkg]["classes"].append(node.name)

            # Controllers
            if "controller" in name_lower:
                endpoints_exposed = [
                    e.target_id for e in graph.outgoing_edges(node.id, RelationshipType.EXPOSES)
                ]
                services_dep = [
                    e.target_id.replace("type:", "")
                    for e in graph.outgoing_edges(node.id)
                    if e.relationship in (RelationshipType.DEPENDS_ON, RelationshipType.USES)
                    and "service" in e.target_id.lower()
                ]
                controllers.append({
                    "id": node.id,
                    "name": node.name,
                    "qualified_name": node.qualified_name or node.name,
                    "file_path": node.file_path,
                    "endpoints": endpoints_exposed,
                    "services_used": services_dep,
                })

            # Repositories
            elif "repository" in name_lower or "repo" in name_lower:
                tables_queried = [
                    e.target_id.replace("table:", "")
                    for e in graph.outgoing_edges(node.id)
                    if e.relationship in (RelationshipType.QUERIES, RelationshipType.REFERENCES)
                ]
                repositories.append({
                    "id": node.id,
                    "name": node.name,
                    "qualified_name": node.qualified_name or node.name,
                    "file_path": node.file_path,
                    "tables_queried": tables_queried,
                })

            # Services
            elif ("service" in name_lower or "facade" in name_lower) and not name_lower.endswith("test"):
                repos_dep = [
                    e.target_id.replace("type:", "")
                    for e in graph.outgoing_edges(node.id)
                    if e.relationship in (RelationshipType.DEPENDS_ON, RelationshipType.USES)
                    and ("repository" in e.target_id.lower() or "repo" in e.target_id.lower())
                ]
                services_dep = [
                    e.target_id.replace("type:", "")
                    for e in graph.outgoing_edges(node.id)
                    if e.relationship in (RelationshipType.DEPENDS_ON, RelationshipType.USES)
                    and "service" in e.target_id.lower()
                    and e.target_id != node.id
                ]
                services.append({
                    "id": node.id,
                    "name": node.name,
                    "qualified_name": node.qualified_name or node.name,
                    "file_path": node.file_path,
                    "repositories_used": repos_dep,
                    "services_used": services_dep,
                })

            # Tests
            elif name_lower.endswith("test") or "test" in name_lower:
                targets = [
                    e.target_id.replace("type:", "")
                    for e in graph.outgoing_edges(node.id, RelationshipType.TESTS)
                ]
                if not targets:
                    targets = [
                        e.target_id.replace("type:", "")
                        for e in graph.outgoing_edges(node.id)
                        if e.relationship in (RelationshipType.DEPENDS_ON, RelationshipType.USES)
                        and not e.target_id.lower().endswith("test")
                    ]
                tests_list.append({
                    "id": node.id,
                    "name": node.name,
                    "qualified_name": node.qualified_name or node.name,
                    "file_path": node.file_path,
                    "targets_tested": targets,
                })

            # External Integrations (clients, templates, messaging)
            if any(term in name_lower for term in ("client", "facade", "remote", "integration", "producer", "consumer")):
                external_integrations.append({
                    "id": node.id,
                    "name": node.name,
                    "type": "Client/Facade",
                    "file_path": node.file_path,
                    "evidence": [f"Component {node.name} provides external integration/facade capabilities"],
                })

        # APIs / Endpoints
        elif node.kind == "endpoint" or node.id.startswith("endpoint:"):
            meta = dict(node.metadata or {})
            path = meta.get("path") or node.name
            http_method = meta.get("http_method") or (node.id.split(":")[1] if ":" in node.id else "GET")
            ctrl = meta.get("handler_class") or "UnknownController"
            apis.append({
                "id": node.id,
                "name": f"{http_method} {path}",
                "http_method": http_method,
                "path": path,
                "controller": ctrl,
                "file_path": node.file_path,
            })

        # Databases (tables)
        elif node.kind in ("database_table", "table") or node.id.startswith("table:"):
            table_name = node.name or node.id.replace("table:", "")
            if table_name not in databases_map:
                queried_by = [
                    e.source_id.replace("type:", "")
                    for e in graph.incoming_edges(node.id)
                    if e.relationship in (RelationshipType.QUERIES, RelationshipType.REFERENCES, RelationshipType.DEPENDS_ON)
                ]
                databases_map[table_name] = {
                    "id": node.id,
                    "name": table_name,
                    "queried_by": queried_by,
                }

    # 2. Modules
    modules = [
        {
            "name": "root-module",
            "package_count": len(packages_map),
            "packages": list(packages_map.keys()),
        }
    ]

    # 3. Architecture Chains (Controller -> Service -> Repository -> Database)
    raw_chains = verify_controller_service_repository(graph)
    chains = [
        {
            "endpoint": c.endpoint_node.name if c.endpoint_node else "N/A",
            "controller": c.controller_node.name,
            "service": c.service_node.name,
            "repository": c.repository_node.name,
            "database_table": c.table_node.name if c.table_node else "N/A",
            "verified": c.verified,
        }
        for c in raw_chains
    ]

    return ArchitectureView(
        packages=list(packages_map.values()),
        modules=modules,
        controllers=controllers,
        services=services,
        repositories=repositories,
        databases=list(databases_map.values()),
        apis=apis,
        external_integrations=external_integrations,
        tests=tests_list,
        chains=chains,
    )


def build_graph_visualization(
    graph: DependencyGraph,
    category_filter: list[str] | None = None,
) -> dict[str, Any]:
    """Provide graph data formatted for frontend visualization (e.g. React Flow, Cytoscape)."""
    filter_set = set(category_filter) if category_filter else None

    nodes_out: list[dict[str, Any]] = []
    edges_out: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {}
    included_node_ids: set[str] = set()

    for node in graph.nodes:
        category = categorize_node(node.id, node.kind, node.name)
        category_counts[category] = category_counts.get(category, 0) + 1

        if filter_set and category not in filter_set:
            continue

        included_node_ids.add(node.id)
        nodes_out.append({
            "id": node.id,
            "label": node.name,
            "kind": node.kind,
            "category": category,
            "file_path": node.file_path,
            "metadata": dict(node.metadata or {}),
        })

    for edge in graph.edges:
        if edge.source_id in included_node_ids and edge.target_id in included_node_ids:
            rel_str = edge.relationship.value if hasattr(edge.relationship, "value") else str(edge.relationship)
            edges_out.append({
                "source": edge.source_id,
                "target": edge.target_id,
                "relationship": rel_str,
                "label": rel_str,
                "resolved": edge.resolved,
            })

    return {
        "nodes": nodes_out,
        "edges": edges_out,
        "categories": category_counts,
        "total_nodes": len(nodes_out),
        "total_edges": len(edges_out),
    }
