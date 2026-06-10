"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import type { ComponentType } from "react";
import { Brain, ClipboardList, FileText, MessageSquare, Plus, RefreshCw, Send } from "lucide-react";
import { Handoff, Memory, Project, Task, api } from "@/lib/api";

type View = "chat" | "tasks" | "memory" | "handoffs";
type ChatLine = { role: "user" | "assistant"; content: string };

const views: Array<{ id: View; label: string; icon: ComponentType<{ size?: number }> }> = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "tasks", label: "Tasks", icon: ClipboardList },
  { id: "memory", label: "Memory", icon: Brain },
  { id: "handoffs", label: "Handoffs", icon: FileText },
];

export default function Home() {
  const [activeView, setActiveView] = useState<View>("chat");
  const [projects, setProjects] = useState<Project[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [memory, setMemory] = useState<Memory | null>(null);
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(false);

  async function refreshAll() {
    setError("");
    try {
      const [projectData, taskData, memoryData, handoffData] = await Promise.all([
        api.listProjects(),
        api.listTasks(),
        api.getMemory(),
        api.listHandoffs(),
      ]);
      setProjects(projectData);
      setTasks(taskData);
      setMemory(memoryData);
      setHandoffs(handoffData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to reach Jarvis API.");
    }
  }

  useEffect(() => {
    refreshAll();
  }, []);

  const counts = useMemo(
    () => ({
      projects: projects.length,
      tasks: tasks.length,
      decisions: memory?.decisions.length ?? 0,
      handoffs: handoffs.length,
    }),
    [handoffs.length, memory?.decisions.length, projects.length, tasks.length],
  );

  return (
    <main className="min-h-screen bg-field">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 py-4 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 border-b border-line pb-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal text-ink">Jarvis</h1>
            <p className="mt-1 text-sm text-ink/65">Planner, memory, tasks, and Codex handoffs.</p>
          </div>
          <button
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-line bg-white px-3 text-sm font-medium text-ink shadow-sm transition hover:border-pine"
            onClick={refreshAll}
            title="Refresh workspace"
          >
            <RefreshCw size={16} />
            Refresh
          </button>
        </header>

        <section className="grid gap-3 border-b border-line py-4 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Projects" value={counts.projects} />
          <Metric label="Tasks" value={counts.tasks} />
          <Metric label="Decisions" value={counts.decisions} />
          <Metric label="Handoffs" value={counts.handoffs} />
        </section>

        {error ? <div className="my-4 rounded-md border border-signal/40 bg-white px-3 py-2 text-sm text-signal">{error}</div> : null}

        <div className="grid flex-1 gap-5 py-5 lg:grid-cols-[220px_1fr]">
          <nav className="flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible">
            {views.map((view) => {
              const Icon = view.icon;
              const selected = activeView === view.id;
              return (
                <button
                  key={view.id}
                  className={`inline-flex h-11 min-w-32 items-center gap-2 rounded-md px-3 text-sm font-medium transition lg:min-w-0 ${
                    selected ? "bg-pine text-white" : "bg-white text-ink hover:bg-line/40"
                  }`}
                  onClick={() => setActiveView(view.id)}
                  title={view.label}
                >
                  <Icon size={17} />
                  {view.label}
                </button>
              );
            })}
          </nav>

          <section className="min-w-0">
            {activeView === "chat" ? <ChatPanel loading={loading} setLoading={setLoading} refreshAll={refreshAll} /> : null}
            {activeView === "tasks" ? <TasksPanel projects={projects} tasks={tasks} refreshAll={refreshAll} /> : null}
            {activeView === "memory" ? <MemoryPanel projects={projects} memory={memory} refreshAll={refreshAll} /> : null}
            {activeView === "handoffs" ? <HandoffsPanel projects={projects} handoffs={handoffs} refreshAll={refreshAll} /> : null}
          </section>
        </div>
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-line bg-white p-3">
      <div className="text-xs font-medium uppercase text-ink/55">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-ink">{value}</div>
    </div>
  );
}

function ChatPanel({ loading, setLoading, refreshAll }: { loading: boolean; setLoading: (value: boolean) => void; refreshAll: () => Promise<void> }) {
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [message, setMessage] = useState("");
  const [lines, setLines] = useState<ChatLine[]>([]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!message.trim() || loading) return;
    const outgoing = message.trim();
    setMessage("");
    setLines((current) => [...current, { role: "user", content: outgoing }]);
    setLoading(true);
    try {
      const result = await api.chat(outgoing, conversationId);
      setConversationId(result.conversation_id);
      setLines((current) => [...current, { role: "assistant", content: result.response }]);
      await refreshAll();
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid min-h-[620px] grid-rows-[1fr_auto] rounded-md border border-line bg-white">
      <div className="space-y-3 overflow-y-auto p-4">
        {lines.length === 0 ? <div className="text-sm text-ink/55">No messages yet.</div> : null}
        {lines.map((line, index) => (
          <div key={`${line.role}-${index}`} className={`max-w-3xl rounded-md px-3 py-2 text-sm ${line.role === "user" ? "ml-auto bg-pine text-white" : "bg-field text-ink"}`}>
            {line.content}
          </div>
        ))}
      </div>
      <form onSubmit={submit} className="flex gap-2 border-t border-line p-3">
        <textarea
          className="min-h-11 flex-1 resize-none rounded-md border border-line px-3 py-2 text-sm outline-none focus:border-pine"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="Message Jarvis"
        />
        <button className="inline-flex h-11 w-11 items-center justify-center rounded-md bg-pine text-white transition hover:bg-pine/90" title="Send" disabled={loading}>
          <Send size={18} />
        </button>
      </form>
    </div>
  );
}

function TasksPanel({ projects, tasks, refreshAll }: { projects: Project[]; tasks: Task[]; refreshAll: () => Promise<void> }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<Task["priority"]>("medium");
  const [projectId, setProjectId] = useState("");

  async function createTask(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    await api.createTask({
      title,
      description,
      priority,
      project_id: projectId ? Number(projectId) : null,
      assigned_agent: "JarvisAgent",
    });
    setTitle("");
    setDescription("");
    await refreshAll();
  }

  async function setStatus(task: Task, status: Task["status"]) {
    await api.updateTask(task.id, { status });
    await refreshAll();
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
      <form onSubmit={createTask} className="rounded-md border border-line bg-white p-4">
        <h2 className="text-base font-semibold text-ink">Create Task</h2>
        <Field label="Title" value={title} onChange={setTitle} />
        <Field label="Description" value={description} onChange={setDescription} multiline />
        <label className="mt-3 block text-sm font-medium text-ink/70">Priority</label>
        <select className="mt-1 h-10 w-full rounded-md border border-line bg-white px-2 text-sm" value={priority} onChange={(event) => setPriority(event.target.value as Task["priority"])}>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
          <option value="critical">Critical</option>
        </select>
        <ProjectSelect projects={projects} value={projectId} onChange={setProjectId} />
        <button className="mt-4 inline-flex h-10 items-center gap-2 rounded-md bg-pine px-3 text-sm font-medium text-white" title="Create task">
          <Plus size={16} />
          Create
        </button>
      </form>

      <div className="space-y-3">
        {tasks.map((task) => (
          <article key={task.id} className="rounded-md border border-line bg-white p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h3 className="font-semibold text-ink">{task.title}</h3>
                <p className="mt-1 text-sm text-ink/65">{task.description || "No description."}</p>
                <p className="mt-2 text-xs uppercase text-ink/50">{task.priority} priority · {task.assigned_agent}</p>
              </div>
              <select className="h-10 rounded-md border border-line bg-white px-2 text-sm" value={task.status} onChange={(event) => setStatus(task, event.target.value as Task["status"])}>
                <option value="pending">Pending</option>
                <option value="in_progress">In progress</option>
                <option value="completed">Completed</option>
                <option value="blocked">Blocked</option>
              </select>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function MemoryPanel({ projects, memory, refreshAll }: { projects: Project[]; memory: Memory | null; refreshAll: () => Promise<void> }) {
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [projectGoals, setProjectGoals] = useState("");
  const [decisionTitle, setDecisionTitle] = useState("");
  const [decisionDetails, setDecisionDetails] = useState("");
  const [decisionReasoning, setDecisionReasoning] = useState("");
  const [decisionProjectId, setDecisionProjectId] = useState("");

  async function createProject(event: FormEvent) {
    event.preventDefault();
    if (!projectName.trim()) return;
    await api.createProject({ name: projectName, description: projectDescription, goals: projectGoals });
    setProjectName("");
    setProjectDescription("");
    setProjectGoals("");
    await refreshAll();
  }

  async function createDecision(event: FormEvent) {
    event.preventDefault();
    if (!decisionTitle.trim() || !decisionDetails.trim()) return;
    await api.createDecision({
      title: decisionTitle,
      details: decisionDetails,
      reasoning: decisionReasoning,
      project_id: decisionProjectId ? Number(decisionProjectId) : null,
    });
    setDecisionTitle("");
    setDecisionDetails("");
    setDecisionReasoning("");
    await refreshAll();
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
      <div className="space-y-4">
        <form onSubmit={createProject} className="rounded-md border border-line bg-white p-4">
          <h2 className="text-base font-semibold text-ink">Project</h2>
          <Field label="Name" value={projectName} onChange={setProjectName} />
          <Field label="Description" value={projectDescription} onChange={setProjectDescription} multiline />
          <Field label="Goals" value={projectGoals} onChange={setProjectGoals} multiline />
          <button className="mt-4 inline-flex h-10 items-center gap-2 rounded-md bg-pine px-3 text-sm font-medium text-white" title="Create project">
            <Plus size={16} />
            Create
          </button>
        </form>
        <form onSubmit={createDecision} className="rounded-md border border-line bg-white p-4">
          <h2 className="text-base font-semibold text-ink">Decision</h2>
          <Field label="Title" value={decisionTitle} onChange={setDecisionTitle} />
          <Field label="Details" value={decisionDetails} onChange={setDecisionDetails} multiline />
          <Field label="Reasoning" value={decisionReasoning} onChange={setDecisionReasoning} multiline />
          <ProjectSelect projects={projects} value={decisionProjectId} onChange={setDecisionProjectId} />
          <button className="mt-4 inline-flex h-10 items-center gap-2 rounded-md bg-pine px-3 text-sm font-medium text-white" title="Store decision">
            <Plus size={16} />
            Store
          </button>
        </form>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <MemoryList title="Projects" items={memory?.projects.map((item) => [item.name, item.goals || item.description]) ?? []} />
        <MemoryList title="Decisions" items={memory?.decisions.map((item) => [item.title, item.details]) ?? []} />
        <MemoryList title="Knowledge" items={memory?.knowledge.map((item) => [item.title, item.body]) ?? []} />
        <MemoryList title="Conversations" items={memory?.conversations.map((item) => [item.role, item.content]) ?? []} />
      </div>
    </div>
  );
}

function HandoffsPanel({ projects, handoffs, refreshAll }: { projects: Project[]; handoffs: Handoff[]; refreshAll: () => Promise<void> }) {
  const [request, setRequest] = useState("");
  const [projectId, setProjectId] = useState("");

  async function createHandoff(event: FormEvent) {
    event.preventDefault();
    if (!request.trim()) return;
    await api.createHandoff({ user_request: request, project_id: projectId ? Number(projectId) : null });
    setRequest("");
    await refreshAll();
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
      <form onSubmit={createHandoff} className="rounded-md border border-line bg-white p-4">
        <h2 className="text-base font-semibold text-ink">Codex Brief</h2>
        <Field label="Request" value={request} onChange={setRequest} multiline />
        <ProjectSelect projects={projects} value={projectId} onChange={setProjectId} />
        <button className="mt-4 inline-flex h-10 items-center gap-2 rounded-md bg-pine px-3 text-sm font-medium text-white" title="Generate brief">
          <FileText size={16} />
          Generate
        </button>
      </form>

      <div className="space-y-3">
        {handoffs.map((handoff) => (
          <article key={handoff.id} className="rounded-md border border-line bg-white p-4">
            <div className="mb-3 text-xs uppercase text-ink/50">{handoff.status}</div>
            <pre className="whitespace-pre-wrap text-sm leading-6 text-ink">{handoff.brief}</pre>
          </article>
        ))}
      </div>
    </div>
  );
}

function Field({ label, value, onChange, multiline = false }: { label: string; value: string; onChange: (value: string) => void; multiline?: boolean }) {
  return (
    <label className="mt-3 block text-sm font-medium text-ink/70">
      {label}
      {multiline ? (
        <textarea className="mt-1 min-h-20 w-full resize-y rounded-md border border-line px-3 py-2 text-sm outline-none focus:border-pine" value={value} onChange={(event) => onChange(event.target.value)} />
      ) : (
        <input className="mt-1 h-10 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-pine" value={value} onChange={(event) => onChange(event.target.value)} />
      )}
    </label>
  );
}

function ProjectSelect({ projects, value, onChange }: { projects: Project[]; value: string; onChange: (value: string) => void }) {
  return (
    <label className="mt-3 block text-sm font-medium text-ink/70">
      Project
      <select className="mt-1 h-10 w-full rounded-md border border-line bg-white px-2 text-sm" value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">None</option>
        {projects.map((project) => (
          <option key={project.id} value={project.id}>
            {project.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function MemoryList({ title, items }: { title: string; items: Array<[string, string]> }) {
  return (
    <section className="rounded-md border border-line bg-white p-4">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      <div className="mt-3 space-y-3">
        {items.length === 0 ? <p className="text-sm text-ink/55">Empty.</p> : null}
        {items.map(([heading, body], index) => (
          <article key={`${heading}-${index}`} className="border-t border-line pt-3 first:border-t-0 first:pt-0">
            <h3 className="text-sm font-semibold text-ink">{heading}</h3>
            <p className="mt-1 whitespace-pre-wrap text-sm text-ink/65">{body || "No details."}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
