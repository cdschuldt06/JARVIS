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

export type Memory = {
  conversations: Array<{ id: number; role: string; content: string; conversation_id: string; created_at: string }>;
  projects: Project[];
  decisions: Array<{ id: number; title: string; details: string; reasoning: string; project_id: number | null }>;
  knowledge: Array<{ id: number; title: string; body: string; kind: string; source: string; project_id: number | null }>;
};

export type Handoff = {
  id: number;
  project_id: number | null;
  user_request: string;
  brief: string;
  status: string;
  created_at: string;
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
  chat: (message: string, conversationId?: string) =>
    request<{ conversation_id: string; response: string }>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, conversation_id: conversationId, input_mode: "text" }),
    }),
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
  getMemory: () => request<Memory>("/memory"),
  listHandoffs: () => request<Handoff[]>("/handoffs"),
  createHandoff: (payload: { user_request: string; project_id: number | null }) =>
    request<Handoff>("/handoffs", { method: "POST", body: JSON.stringify(payload) }),
};
