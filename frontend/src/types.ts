export interface Project {
  id: number;
  name: string;
  description?: string | null;
  created_at?: string | null;
}

export interface DashboardMetrics {
  total_files: number;
  java_classes: number;
  methods: number;
  dependencies: number;
  apis: number;
  database_references: number;
}

export interface ArchitectureData {
  packages: Array<{ id: string; name: string; classes: string[] }>;
  modules: Array<{ name: string; package_count: number; packages: string[] }>;
  controllers: Array<{ id: string; name: string; file_path: string; endpoints: string[] }>;
  services: Array<{ id: string; name: string; file_path: string; repositories_used: string[] }>;
  repositories: Array<{ id: string; name: string; file_path: string; tables_queried: string[] }>;
  databases: Array<{ id: string; name: string; queried_by: string[] }>;
  apis: Array<{ id: string; name: string; http_method: string; path: string; controller: string }>;
  external_integrations: Array<{ id: string; name: string; type: string }>;
  tests: Array<{ id: string; name: string; targets_tested: string[] }>;
  chains: Array<{
    endpoint: string;
    controller: string;
    service: string;
    repository: string;
    database_table: string;
    verified: boolean;
  }>;
}

export interface GraphNodeData {
  id: string;
  label: string;
  kind: string;
  category: string;
  file_path?: string | null;
  metadata?: Record<string, any>;
}

export interface GraphEdgeData {
  source: string;
  target: string;
  relationship: string;
  label: string;
  resolved: boolean;
}

export interface GraphData {
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
  categories: Record<string, number>;
  total_nodes: number;
  total_edges: number;
}

export interface AskResult {
  question: string;
  answer: string;
  evidence: Array<{
    type?: string;
    symbol?: string;
    file_path?: string;
    details?: string;
  }>;
  flow?: Array<{
    step_number: number;
    node_kind: string;
    node_name: string;
    relationship?: string;
  }>;
  limitations: string[];
}

export interface ImpactResult {
  target: string;
  target_kind: string;
  target_file?: string | null;
  direct_impact: Array<{
    id: string;
    name: string;
    kind: string;
    file_path?: string;
    relationship?: string;
  }>;
  indirect_impact: Array<{
    id: string;
    name: string;
    kind: string;
    depth: number;
  }>;
  affected_apis: Array<{ id: string; name: string; file_path?: string }>;
  affected_database_objects: Array<{ id: string; name: string; kind: string; relationship?: string }>;
  affected_tests: Array<{ id: string; name: string; file_path?: string }>;
  evidence: Array<Record<string, any>>;
  limitations: string[];
}

export interface RiskFinding {
  finding_type: string;
  severity: "HIGH" | "MEDIUM" | "LOW" | "INFO";
  subject: string;
  summary: string;
  metrics: Record<string, any>;
  evidence: string[];
}

export interface RiskReport {
  total_findings: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  findings: RiskFinding[];
}

export interface ModernizationFinding {
  category: string;
  finding: string;
  evidence: string[];
  reason: string;
  possible_direction: string;
  dependencies: string[];
  risk_considerations: string[];
  suggested_investigation_order: number;
  limitations: string[];
}

export interface ModernizationReport {
  total_findings: number;
  findings: ModernizationFinding[];
}

export interface FileItem {
  id: number;
  relative_path: string;
  size_bytes: number;
  categories: string[];
}

export interface ClassItem {
  id: number;
  name: string;
  qualified_name: string;
  kind: string;
  start_line?: number | null;
  end_line?: number | null;
  modifiers: string[];
  annotations: Array<{ name: string }>;
}

export interface MethodItem {
  id: number;
  class_id: number;
  name: string;
  signature: string;
  return_type?: string | null;
  is_constructor: boolean;
  start_line?: number | null;
  end_line?: number | null;
}
