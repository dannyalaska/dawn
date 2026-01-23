export type ServiceState = 'online' | 'offline' | 'degraded';

export interface ServiceHealth {
  ok: boolean;
  service: string;
  env: string;
  redis: boolean;
  db: boolean;
  llm: {
    provider: string;
    ok: boolean;
    detail?: string | null;
  };
}

export interface DawnUser {
  id: number;
  email: string;
  full_name?: string | null;
  is_default?: boolean;
}

export interface FeedVersion {
  id: number;
  number: number;
  rows: number;
  columns: number;
  sha16: string;
  created_at: string | null;
  sheet?: string | null;
  sheet_names?: string[];
  summary?: Record<string, unknown>;
  profile?: Record<string, unknown>;
  schema?: Record<string, unknown>;
  manifest?: Record<string, unknown> | null;
}

export interface FeedRecord {
  identifier: string;
  name: string;
  owner?: string | null;
  source_type: string;
  format?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  favorite_sheet?: string | null;
  latest_version?: FeedVersion | null;
}

export interface ContextNote {
  id: string;
  text: string;
  source: string;
  row_index: number;
  type: string;
  tags: string[];
}

export interface MemoryPayload {
  sha16: string;
  sheet: string;
  relationships: Record<string, unknown>;
  analysis_plan: Array<Record<string, unknown>>;
  insights: Record<string, unknown>;
  aggregates: Array<Record<string, unknown>>;
  notes?: string[];
}

export interface RunnerMeta {
  jobs: {
    total: number;
    active: number;
    scheduled: number;
  };
  runs: {
    total: number;
    success: number;
    failed: number;
    last_run: {
      finished_at: string | null;
      status: string | null;
      duration_seconds: number | null;
    };
  };
}

export interface AgentRunLogEntry {
  agent: string;
  message: string;
  timestamp?: string | null;
  [key: string]: unknown;
}

export interface AgentRunSummary {
  status: string;
  feed_identifier: string;
  feed_name?: string | null;
  feed_version?: number | null;
  plan: Array<Record<string, unknown>>;
  completed: Array<Record<string, unknown>>;
  warnings: string[];
  context_updates: Array<Record<string, unknown>>;
  answer?: string | null;
  answer_sources: Array<Record<string, unknown>>;
  final_report?: string;
  run_log: AgentRunLogEntry[];
}

export interface JobRecord {
  id: number;
  name: string;
  schedule?: string | null;
  is_active: boolean;
  feed_identifier: string;
  feed_version?: number | null;
  transform_name?: string | null;
  transform_version?: number | null;
}

export interface SchedulerStatus {
  running: boolean;
  count: number;
  scheduled_jobs: Array<{
    job_id: number;
    next_run?: string | null;
    name?: string | null;
  }>;
}

export interface IndexExcelResponse {
  indexed_chunks: number;
  rows: number;
  source: string;
  sheet: string;
  sha16: string;
  summary: {
    text: string;
    columns: Array<{
      name: string;
      dtype: string;
      top_values: Array<[string, number]> | null;
      stats: Record<string, number> | null;
    }>;
    metrics: Array<Record<string, unknown>>;
    insights: Record<string, Array<{ label: string; count: number }>>;
    aggregates: Array<Record<string, unknown>>;
    relationships: Record<string, string>;
    analysis_plan: Array<Record<string, unknown>>;
    tags: string[];
  };
  chunk_config: {
    max_chars: number;
    overlap: number;
  };
}

export interface PreviewColumn {
  name: string;
  dtype: string;
  non_null: number;
  nulls: number;
  sample: string[];
}

export interface PreviewTable {
  sheet: string;
  shape: [number, number];
  columns: PreviewColumn[];
  rows: Array<Record<string, unknown>>;
  cached: boolean;
  sha16: string;
  sheet_names?: string[];
}

export interface BackendConnection {
  id: number;
  name: string;
  kind: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  schema_grants?: string[];
}

export type RagRole = 'user' | 'assistant';

export interface RagMessage {
  role: RagRole;
  content: string;
}

export interface RagChatResponse {
  answer: string;
  sources: Array<Record<string, unknown>>;
  messages: RagMessage[];
  direct_answer?: boolean;
}

export interface NL2SQLResponse {
  sql: string;
  validation: {
    ok: boolean;
    errors?: string[];
    warnings?: string[];
    tables?: string[];
    columns?: string[];
  };
  citations?: {
    tables?: string[];
    columns?: string[];
    context?: Array<Record<string, unknown>>;
  };
  explain?: string | null;
}

export interface LMStudioModel {
  id: string;
  publisher?: string | null;
  state?: string | null;
  type?: string | null;
  quantization?: string | null;
  max_context_length?: number | null;
  model_key: string;
  display_name?: string | null;
}

export interface LMStudioModelsResponse {
  models: LMStudioModel[];
  base_url: string;
  cli_available: boolean;
}
