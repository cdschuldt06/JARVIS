# Jarvis v0.1

Jarvis is a personal AI operating system foundation. In v0.1, Jarvis is the planner and memory layer: it chats with an OpenAI model, stores durable project context, manages tasks and decisions, and generates structured implementation briefs for Codex.

## Architecture

```text
apps/web/          Next.js dashboard
jarvis/api/        FastAPI routes
jarvis/core/       Configuration and app setup
jarvis/agents/     Jarvis and Codex agent abstractions
jarvis/memory/     Conversation, project, decision, and knowledge services
jarvis/tasks/      Task service
jarvis/handoffs/   Codex handoff brief generation
jarvis/safety/     Tool/action safety framework
jarvis/voice/      Voice provider abstractions
jarvis/devices/    Future multi-device agent abstractions
jarvis/database/   SQLite and SQLAlchemy setup
data/              Local SQLite database location
docs/              Product and architecture notes
```

## Requirements

- Python 3.12+
- Node.js 20+
- OpenAI API key

## Backend Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Update `.env`:

```env
OPENAI_API_KEY=your_key_here
DATABASE_URL=sqlite:///./data/jarvis.db
APP_ENV=development
OPENAI_MODEL=gpt-4.1-mini
OPENAI_RESEARCH_MODEL=gpt-5.5
```

Run the API:

```powershell
uvicorn jarvis.api.main:app --reload
```

The API will create SQLite tables at startup.

## Frontend Setup

```powershell
cd apps/web
npm install
Copy-Item .env.example .env.local
npm run dev
```

The web app expects the backend at `http://localhost:8000` by default.

## Core API

- `POST /chat`
- `GET /tasks`
- `POST /tasks`
- `PATCH /tasks/{task_id}`
- `DELETE /tasks/{task_id}`
- `GET /memory`
- `GET /projects`
- `POST /projects`
- `GET /handoffs`
- `POST /handoffs`

## Memory Model Notes

`conversation_id` groups chat messages into a session. `project_id` is optional and scopes a chat message to a project. Keep both: a conversation can remain a coherent chat thread while also contributing memory to a specific project.

In the web UI, the dashboard has a persistent Current Project selector near the top of the app. Chat messages, tasks, decisions, and Codex handoffs use that shared selected project. When no project is selected, new records are stored with `project_id = null`.

The Memory, Tasks, and Handoffs views show records for the Current Project. The Projects list remains global so the user can see available project containers.

## Model Configuration

`OPENAI_MODEL` is the default everyday chat model used by Jarvis v0.1. `OPENAI_RESEARCH_MODEL` is reserved for v0.2 web search, research, and synthesis workflows. Current chat behavior still uses `OPENAI_MODEL`.

## Safety

Jarvis v0.1 does not execute computer-control actions, terminal commands, trading, email sending, GitHub writes, or local file edits. It only includes a safety registry so future tools can declare risk level and confirmation requirements before they are enabled.
