const API_BASE = "/api/v1";

function getToken(): string | null {
  return localStorage.getItem("token");
}

export function setToken(token: string) {
  localStorage.setItem("token", token);
}

export function clearToken() {
  localStorage.removeItem("token");
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (resp.status === 401 && !path.startsWith("/auth/")) {
    clearToken();
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }

  return resp.json() as Promise<T>;
}

// Auth
export async function login(username: string, password: string) {
  return apiFetch<{
    access_token: string;
    username: string;
    tenant_id: string;
    role: string;
  }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function register(username: string, password: string) {
  return apiFetch<{ message: string }>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

// Dashboard
export async function getStats() {
  return apiFetch<{
    total_sources: number;
    total_drafts: number;
    total_published: number;
    total_pipeline_runs: number;
  }>("/dashboard/stats");
}

// Pipeline
export interface PipelineRunConfig {
  sources: string[];
  target_platforms: string[];
  generate_video: boolean;
}

export async function runPipeline(config: PipelineRunConfig) {
  return apiFetch<{ success: boolean; pipeline_run_id: string }>(
    "/pipeline/run",
    { method: "POST", body: JSON.stringify(config) }
  );
}

export interface PipelineRun {
  id: string;
  trigger_type: string;
  status: string;
  items_scraped: number;
  items_published: number;
  started_at: string;
  finished_at: string | null;
}

export async function listPipelineRuns(limit = 10) {
  return apiFetch<PipelineRun[]>(`/pipeline/runs?limit=${limit}`);
}

export async function getPipelineRun(runId: string) {
  return apiFetch<PipelineRun>(`/pipeline/runs/${runId}`);
}

// Sources
export interface TrendSource {
  id: string;
  source_platform: string;
  source_id: string;
  source_url: string;
  title: string;
  description: string;
  author: string;
  language: string;
  engagement_score: number;
  normalized_heat_score: number;
  hashtags: string[];
  media_urls: string[];
  parse_status: string;
  scraped_at: string;
}

export async function listSources(
  platform?: string,
  limit = 50,
  offset = 0
) {
  let url = `/sources?limit=${limit}&offset=${offset}`;
  if (platform) url += `&platform=${platform}`;
  return apiFetch<TrendSource[]>(url);
}

// Content Drafts
export interface ContentDraft {
  id: string;
  source_id: string;
  target_platform: string;
  title: string;
  body: string;
  summary: string;
  hashtags: string[];
  media_urls: string[];
  video_url: string;
  video_provider: string;
  status: string;
  quality_score: number;
  quality_details: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
}

export async function listDrafts(
  status?: string,
  platform?: string,
  limit = 50,
  offset = 0
) {
  let url = `/content?limit=${limit}&offset=${offset}`;
  if (status) url += `&status=${status}`;
  if (platform) url += `&platform=${platform}`;
  return apiFetch<ContentDraft[]>(url);
}

export async function getDraft(draftId: string) {
  return apiFetch<ContentDraft>(`/content/${draftId}`);
}

export async function updateDraft(
  draftId: string,
  updates: {
    title?: string;
    body?: string;
    summary?: string;
    hashtags?: string[];
    status?: string;
  }
) {
  return apiFetch<{ success: boolean; draft_id: string }>(
    `/content/${draftId}`,
    { method: "PUT", body: JSON.stringify(updates) }
  );
}

export async function deleteDraft(draftId: string) {
  return apiFetch<{ success: boolean; draft_id: string }>(
    `/content/${draftId}`,
    { method: "DELETE" }
  );
}

// Publish
export async function publishDrafts(draftIds: string[], platforms: string[]) {
  return apiFetch<{ message: string; draft_ids: string[]; platforms: string[] }>(
    "/publish",
    {
      method: "POST",
      body: JSON.stringify({ draft_ids: draftIds, platforms }),
    }
  );
}

export interface PublishRecord {
  id: string;
  draft_id: string;
  platform: string;
  platform_post_id: string;
  platform_url: string;
  status: string;
  error_message: string;
  published_at: string | null;
  retry_count: number;
}

export async function listPublishHistory(limit = 50, offset = 0) {
  return apiFetch<PublishRecord[]>(
    `/publish/history?limit=${limit}&offset=${offset}`
  );
}
