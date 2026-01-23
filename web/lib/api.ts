import { DEFAULT_API_BASE } from '@/lib/config';
import type {
  AgentRunSummary,
  BackendConnection,
  ContextNote,
  DawnUser,
  FeedRecord,
  IndexExcelResponse,
  MemoryPayload,
  PreviewTable,
  RunnerMeta,
  SchedulerStatus,
  ServiceHealth,
  RagChatResponse,
  RagMessage,
  JobRecord,
  LMStudioModelsResponse,
  NL2SQLResponse
} from '@/lib/types';

export class DawnHttpError extends Error {
  status?: number;
  details?: unknown;

  constructor(message: string, status?: number, details?: unknown) {
    super(message);
    this.name = 'DawnHttpError';
    this.status = status;
    this.details = details;
  }
}

export interface DawnRequestOptions extends RequestInit {
  token?: string | null;
  apiBase?: string;
  json?: unknown;
  formData?: FormData;
}

const normalizePath = (path: string) => (path.startsWith('/') ? path : `/${path}`);

export async function dawnRequest<T>(path: string, options: DawnRequestOptions = {}): Promise<T> {
  const { token, apiBase = DEFAULT_API_BASE, json, formData, headers, ...rest } = options;
  const url = `${apiBase}${normalizePath(path)}`;
  const mergedHeaders = new Headers(headers ?? undefined);

  if (token) {
    mergedHeaders.set('Authorization', `Bearer ${token}`);
  }

  let body: BodyInit | undefined = rest.body as BodyInit | undefined;
  if (formData) {
    body = formData;
  } else if (json !== undefined) {
    mergedHeaders.set('Content-Type', 'application/json');
    body = JSON.stringify(json);
  }

  const response = await fetch(url, {
    ...rest,
    headers: mergedHeaders,
    body
  });

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    const detailMessage =
      typeof payload === 'object' && payload && 'detail' in (payload as Record<string, unknown>)
        ? String((payload as Record<string, unknown>).detail)
        : response.statusText || 'Request failed';
    throw new DawnHttpError(detailMessage, response.status, payload);
  }

  return payload as T;
}

export async function login(email: string, password: string, opts?: DawnRequestOptions) {
  return dawnRequest<{ token: string; user: DawnUser }>('/auth/login', {
    method: 'POST',
    json: { email, password },
    ...(opts || {})
  });
}

export async function register(payload: { email: string; password: string; full_name?: string }, opts?: DawnRequestOptions) {
  return dawnRequest<{ token: string; user: DawnUser }>('/auth/register', {
    method: 'POST',
    json: payload,
    ...(opts || {})
  });
}

export async function fetchHealth(opts?: DawnRequestOptions) {
  return dawnRequest<ServiceHealth>('/health', opts);
}

export async function fetchFeeds(opts?: DawnRequestOptions) {
  const result = await dawnRequest<{ feeds: FeedRecord[] }>('/feeds', opts);
  return result.feeds;
}

export async function fetchContext(source: string, limit = 100, opts?: DawnRequestOptions) {
  return dawnRequest<{ source: string; notes: ContextNote[] }>(`/rag/context?source=${encodeURIComponent(source)}&limit=${limit}`, opts);
}

export async function fetchMemory(sha16: string, sheet: string, opts?: DawnRequestOptions) {
  return dawnRequest<MemoryPayload>(`/rag/memory?sha16=${encodeURIComponent(sha16)}&sheet=${encodeURIComponent(sheet)}`, opts);
}

export async function updateMemory(
  payload: {
    sha16: string;
    sheet: string;
    relationships?: Record<string, string>;
    analysis_plan?: Array<Record<string, unknown>>;
    notes?: string[];
  },
  opts?: DawnRequestOptions
) {
  return dawnRequest<MemoryPayload>('/rag/memory', {
    method: 'PUT',
    json: payload,
    ...(opts || {})
  });
}

export async function fetchRunnerMeta(opts?: DawnRequestOptions) {
  return dawnRequest<RunnerMeta>('/jobs/runner/meta', opts);
}

export async function fetchSchedulerStatus(opts?: DawnRequestOptions) {
  return dawnRequest<SchedulerStatus>('/jobs/scheduler/status', opts);
}

export async function runAgents(payload: {
  feed_identifier: string;
  question?: string | null;
  refresh_context?: boolean;
  max_plan_steps?: number;
  retrieval_k?: number;
}, opts?: DawnRequestOptions) {
  return dawnRequest<AgentRunSummary>('/agents/analyze', {
    method: 'POST',
    json: payload,
    ...(opts || {})
  });
}

export async function ingestWorkbook(form: FormData, opts?: DawnRequestOptions) {
  return dawnRequest<IndexExcelResponse>('/rag/index_excel', {
    method: 'POST',
    formData: form,
    ...(opts || {})
  });
}

export async function previewWorkbook(form: FormData, opts?: DawnRequestOptions) {
  return dawnRequest<PreviewTable>('/ingest/preview', {
    method: 'POST',
    formData: form,
    ...(opts || {})
  });
}

export async function fetchBackends(opts?: DawnRequestOptions) {
  const result = await dawnRequest<{ connections: BackendConnection[] }>('/backends', opts);
  return result.connections;
}

export async function createBackend(
  payload: { name: string; kind: string; config: Record<string, unknown>; schema_grants?: string[] },
  opts?: DawnRequestOptions
) {
  return dawnRequest('/backends', {
    method: 'POST',
    json: payload,
    ...(opts || {})
  });
}

export async function queryContext(
  question: string,
  opts?: DawnRequestOptions,
  params?: { k?: number }
) {
  const url = `/rag/query?q=${encodeURIComponent(question)}&k=${params?.k ?? 5}`;
  return dawnRequest<{ query: string; answer: string; sources: ContextNote[] }>(url, opts);
}

export async function chatRag(messages: RagMessage[], opts?: DawnRequestOptions) {
  return dawnRequest<RagChatResponse>('/rag/chat', {
    method: 'POST',
    json: { messages },
    ...(opts || {})
  });
}

export async function addContextNote(payload: { source: string; text: string }, opts?: DawnRequestOptions) {
  return dawnRequest('/rag/context/note', {
    method: 'POST',
    json: payload,
    ...(opts || {})
  });
}

export async function generateSql(
  payload: {
    question: string;
    feed_identifiers?: string[];
    allow_writes?: boolean;
    dialect?: string;
    explain?: boolean;
  },
  opts?: DawnRequestOptions
) {
  return dawnRequest<NL2SQLResponse>('/nl/sql', {
    method: 'POST',
    json: payload,
    ...(opts || {})
  });
}

export async function updateContextNote(chunkId: string, text: string, opts?: DawnRequestOptions) {
  return dawnRequest(`/rag/context/${encodeURIComponent(chunkId)}`, {
    method: 'PUT',
    json: { text },
    ...(opts || {})
  });
}

export async function fetchJobs(opts?: DawnRequestOptions) {
  const result = await dawnRequest<{ jobs: JobRecord[] }>('/jobs', opts);
  return result.jobs;
}

export async function runJob(jobId: number, opts?: DawnRequestOptions) {
  return dawnRequest(`/jobs/${jobId}/run`, {
    method: 'POST',
    ...(opts || {})
  });
}

export async function pauseJob(jobId: number, opts?: DawnRequestOptions) {
  return dawnRequest(`/jobs/${jobId}/pause`, {
    method: 'POST',
    ...(opts || {})
  });
}

export async function resumeJob(jobId: number, opts?: DawnRequestOptions) {
  return dawnRequest(`/jobs/${jobId}/resume`, {
    method: 'POST',
    ...(opts || {})
  });
}

export async function ingestFeed(form: FormData, opts?: DawnRequestOptions) {
  return dawnRequest('/feeds/ingest', {
    method: 'POST',
    formData: form,
    ...(opts || {})
  });
}

export async function fetchLmStudioModels(
  opts?: DawnRequestOptions & { baseUrl?: string }
) {
  const { baseUrl, ...requestOpts } = opts || {};
  const query = baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : '';
  return dawnRequest<LMStudioModelsResponse>(`/lmstudio/models${query}`, requestOpts);
}

export async function loadLmStudioModel(
  payload: {
    model_key: string;
    base_url?: string;
    identifier?: string;
    context_length?: number;
    gpu?: string;
    ttl_seconds?: number;
  },
  opts?: DawnRequestOptions
) {
  return dawnRequest('/lmstudio/load', {
    method: 'POST',
    json: payload,
    ...(opts || {})
  });
}

export async function unloadLmStudioModel(
  payload: { model_key?: string; base_url?: string; unload_all?: boolean },
  opts?: DawnRequestOptions
) {
  return dawnRequest('/lmstudio/unload', {
    method: 'POST',
    json: payload,
    ...(opts || {})
  });
}

export async function useLmStudioModel(
  payload: { model: string; base_url?: string; provider?: string },
  opts?: DawnRequestOptions
) {
  return dawnRequest('/lmstudio/use', {
    method: 'POST',
    json: payload,
    ...(opts || {})
  });
}
