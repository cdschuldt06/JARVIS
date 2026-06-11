const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Project = {
  id: number;
  name: string;
  description: string;
  status: string;
  goals: string;
};

export type Task = {
  id: number;
  title: string;
  description: string;
  assigned_agent: string;
  status: "pending" | "in_progress" | "completed" | "blocked";
  priority: "low" | "medium" | "high" | "critical";
  project_id: number | null;
};

export type Repository = {
  id: number;
  name: string;
  path: string;
  description: string;
  project_id: number | null;
  last_indexed_at: string | null;
  last_known_modified_at: string | null;
  files_indexed: number;
  index_status: string;
  index_error: string;
  knowledge_items_count: number;
  status: string;
  created_at: string;
  updated_at: string;
};

export type RepositoryKnowledge = {
  id: number;
  repository_id: number;
  file_path: string;
  summary: string;
  kind: string;
  created_at: string;
};

export type Memory = {
  conversations: Array<{ id: number; role: string; content: string; conversation_id: string; project_id: number | null; created_at: string }>;
  projects: Project[];
  decisions: Array<{ id: number; title: string; details: string; reasoning: string; project_id: number | null }>;
  knowledge: Array<{ id: number; title: string; body: string; kind: string; source: string; project_id: number | null; created_at?: string }>;
};

export type ChatMessage = {
  id: number;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  input_mode: string;
  project_id: number | null;
  created_at: string;
};

export type ChatSession = {
  conversation_id: string;
  project_id: number | null;
  label: string;
  last_activity_at: string;
};

export type Handoff = {
  id: number;
  project_id: number | null;
  user_request: string;
  brief: string;
  status: string;
  created_at: string;
};

export type ResearchResult = {
  query: string;
  model: string;
  summary: string;
  sources: string[];
};

export type UsageEvent = {
  id: number;
  created_at: string;
  model: string;
  operation_type: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost: number;
  project_id: number | null;
  conversation_id: string | null;
};

export type UsageGroup = {
  name: string;
  cost: number;
  tokens: number;
  calls: number;
};

export type UsageDashboard = {
  estimated: boolean;
  totals: { today: number; week: number; month: number; all_time: number };
  by_model: UsageGroup[];
  by_operation: UsageGroup[];
  recent: UsageEvent[];
};

export type ToolActivity = {
  actions: string[];
  model: string;
  memory_retrieved: boolean;
  research_performed: boolean;
  handoff_generated: boolean;
  research_saved: boolean;
  repository_retrieved: boolean;
  news_provider_used: string | null;
  market_provider_used: string | null;
  research_fallback_used: boolean;
  market_context: { requested_symbols: string[]; returned_symbols: string[]; failed_symbols: string[] } | null;
  memory_counts: { decisions: number; research: number; tasks: number; repositories?: number } | null;
  repository_context: { files_used: number; knowledge_items_used: number; last_indexed_at: string | null; confidence: string } | null;
  sources: string[] | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed: ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const api = {
  chat: (message: string, conversationId?: string, projectId?: number | null, inputMode: "text" | "voice" = "text") =>
    request<{ conversation_id: string; response: string; activity: ToolActivity | null }>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, conversation_id: conversationId, project_id: projectId ?? null, input_mode: inputMode }),
    }),
  listChatSessions: (projectId?: number | null) =>
    request<ChatSession[]>(projectId == null ? "/chat/sessions" : `/chat/sessions?project_id=${projectId}`),
  getChatConversation: (conversationId: string, projectId?: number | null) =>
    request<ChatMessage[]>(projectId == null ? `/chat/conversations/${conversationId}` : `/chat/conversations/${conversationId}?project_id=${projectId}`),
  listTasks: () => request<Task[]>("/tasks"),
  createTask: (task: Partial<Task> & { title: string }) =>
    request<Task>("/tasks", { method: "POST", body: JSON.stringify(task) }),
  updateTask: (id: number, task: Partial<Task>) =>
    request<Task>(`/tasks/${id}`, { method: "PATCH", body: JSON.stringify(task) }),
  listProjects: () => request<Project[]>("/projects"),
  createProject: (project: { name: string; description: string; goals: string }) =>
    request<Project>("/projects", { method: "POST", body: JSON.stringify(project) }),
  createDecision: (decision: { title: string; details: string; reasoning: string; project_id: number | null }) =>
    request("/decisions", { method: "POST", body: JSON.stringify(decision) }),
  runResearch: (payload: { query: string; project_id: number | null }) =>
    request<ResearchResult>("/research", { method: "POST", body: JSON.stringify(payload) }),
  saveResearch: (payload: { title: string; summary: string; sources: string[]; project_id: number | null }) =>
    request<Memory["knowledge"][number]>("/research/save", { method: "POST", body: JSON.stringify(payload) }),
  listResearch: (projectId?: number | null) =>
    request<Memory["knowledge"]>(projectId == null ? "/research" : `/research?project_id=${projectId}`),
  getMemory: () => request<Memory>("/memory"),
  listHandoffs: () => request<Handoff[]>("/handoffs"),
  createHandoff: (payload: { user_request: string; project_id: number | null }) =>
    request<Handoff>("/handoffs", { method: "POST", body: JSON.stringify(payload) }),
  listRepositories: (projectId?: number | null) =>
    request<Repository[]>(projectId == null ? "/repositories" : `/repositories?project_id=${projectId}`),
  registerRepository: (payload: { name: string; path: string; description: string; project_id: number | null }) =>
    request<Repository>("/repositories", { method: "POST", body: JSON.stringify(payload) }),
  indexRepository: (repositoryId: number) =>
    request<{ repository: Repository; indexed_files: number }>(`/repositories/${repositoryId}/index`, { method: "POST" }),
  repositoryKnowledge: (repositoryId: number) =>
    request<RepositoryKnowledge[]>(`/repositories/${repositoryId}/knowledge`),
  repositorySummary: (repositoryId: number) =>
    request<{ summary: string }>(`/repositories/${repositoryId}/summary`),
  projectAnalysis: (projectId?: number | null) =>
    request<{ findings: string[] }>(projectId == null ? "/project-analysis" : `/project-analysis?project_id=${projectId}`),
  usage: (projectId?: number | null) =>
    request<UsageDashboard>(projectId == null ? "/usage" : `/usage?project_id=${projectId}`),
};
