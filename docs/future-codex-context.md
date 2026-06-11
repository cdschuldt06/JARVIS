# Future Codex Context - Jarvis

Last updated: 2026-06-11
Primary workspace path: C:\Projects\jarvis
Old copied-from path: C:\Users\charl\OneDrive\Documents\jarvis
Remote: https://github.com/cdschuldt06/JARVIS.git
Current branch: main

Use this document to bootstrap a new Codex session. Inspect the repo before editing, but this captures the important project context, architecture, decisions, roadmap, and current work.

## Session Startup Notes

- Use `C:\Projects\jarvis` as the workspace. The OneDrive copy should be treated as stale.
- Run `git status -sb` first. At the time this document was generated, the new workspace had uncommitted voice formatter changes:
  - `apps/web/app/page.tsx`
  - `apps/web/lib/voice.ts`
  - `apps/web/package.json`
  - `apps/web/scripts/voice-formatter-sample.cjs`
- The most recent pushed commit is `5a8f544 Add repository awareness and usage dashboard`.
- The project was copied out of OneDrive because OneDrive was warning about generated file deletions. `.next` was intentionally not copied because it is disposable build cache.
- Do not expose or print `.env` values. The local `.env` contains the OpenAI API key.

## Product Summary

Jarvis is a local personal AI operating system foundation. It combines:

- Chat
- Project memory
- Tasks
- Decisions
- Saved knowledge/research
- Web research
- Voice input and spoken responses
- Codex implementation handoff briefs
- Repository awareness
- Estimated OpenAI usage/cost tracking

The UX goal is a single assistant experience: the user chats with Jarvis, and Jarvis decides whether to answer directly, retrieve memory, run research, use repository context, save explicit research, or generate a Codex brief.

## Architecture

### Frontend

Path: `apps/web`

- Next.js dashboard app.
- Main dashboard file: `apps/web/app/page.tsx`.
- API client/types: `apps/web/lib/api.ts`.
- Voice utilities and spoken response formatting: `apps/web/lib/voice.ts`.
- Voice formatter sample check: `apps/web/scripts/voice-formatter-sample.cjs`.

Major UI sections:

- Chat
- Research
- Tasks
- Memory
- Handoffs
- Repositories
- Usage

The dashboard has a persistent Current Project selector. Chat, tasks, decisions, handoffs, research, repository awareness, and usage filtering all use the selected project where applicable.

### Backend

Path: `jarvis`

- FastAPI app/routes: `jarvis/api/main.py`
- Pydantic schemas: `jarvis/api/schemas.py`
- SQLAlchemy models: `jarvis/database/models.py`
- DB/session/startup migration helpers: `jarvis/database/session.py`
- OpenAI chat wrapper: `jarvis/llm.py`
- Unified orchestration: `jarvis/agents/unified_assistant.py`
- Deterministic routing: `jarvis/tools/router.py`

Core services:

- `jarvis/memory/service.py` - projects, decisions, knowledge, conversation messages, chat sessions.
- `jarvis/memory/retrieval.py` - deterministic project-scoped retrieval/ranking.
- `jarvis/research/service.py` - OpenAI Responses API web search and saved research.
- `jarvis/handoffs/service.py` - Codex handoff brief generation.
- `jarvis/tasks/service.py` - task CRUD.
- `jarvis/repositories/service.py` - read-only repository registration, indexing, summaries, and retrieval.
- `jarvis/project_analysis/service.py` - deterministic repository/project analysis findings.
- `jarvis/usage/service.py` - OpenAI usage logging and estimated cost dashboard.
- `jarvis/voice/service.py` - backend voice abstraction placeholder for future providers.

### Database

Local SQLite database: `data/jarvis.db`

SQLAlchemy tables/models:

- `conversation_messages`
- `projects`
- `decisions`
- `knowledge_items`
- `tasks`
- `codex_handoffs`
- `repositories`
- `repository_knowledge`
- `usage_logs`

Startup uses `Base.metadata.create_all(bind=engine)` plus lightweight SQLite schema update helpers for local development.

### Main API Routes

- `GET /health`
- `POST /chat`
- `GET /chat/sessions`
- `GET /chat/conversations/{conversation_id}`
- `GET /tasks`
- `POST /tasks`
- `PATCH /tasks/{task_id}`
- `DELETE /tasks/{task_id}`
- `GET /memory`
- `GET /projects`
- `POST /projects`
- `POST /decisions`
- `POST /research`
- `GET /research`
- `POST /research/save`
- `GET /repositories`
- `POST /repositories`
- `POST /repositories/{repository_id}/index`
- `GET /repositories/{repository_id}/knowledge`
- `GET /repositories/{repository_id}/summary`
- `GET /project-analysis`
- `GET /usage`
- `GET /handoffs`
- `POST /handoffs`

## Completed Versions

### v0.1 - Memory MVP

- Initial FastAPI backend and Next.js dashboard.
- SQLAlchemy models for conversations, projects, decisions, knowledge, tasks, and Codex handoffs.
- Project memory, decisions, tasks, and handoff generation.
- `conversation_id` groups chat sessions.
- `project_id` optionally scopes memory to a project.

Related commit: `6fbfc6b Initial Jarvis MVP`

### v0.2 - Awareness

- Added configurable model setup:
  - `OPENAI_MODEL` for everyday chat.
  - `OPENAI_RESEARCH_MODEL` for web research/synthesis.
- Added web research with OpenAI Responses API and web search.
- Saved research is stored as `KnowledgeItem(kind="research")` with JSON source metadata in `KnowledgeItem.source`.
- Memory retrieval improved with deterministic scoring across project goals, decisions, knowledge, and tasks.
- Research and handoff generation require a Current Project to prevent accidental global context use.

Related commits:

- `c05f170 Add research model config`
- `c65c169 Implement awareness v0.2`

### v0.3 - Voice MVP

- Browser push-to-talk in Chat using `SpeechRecognition` when available.
- Graceful fallback when browser speech recognition is unavailable.
- Browser `SpeechSynthesis` spoken responses behind a `Speak responses` toggle.
- No wake word, backend audio transcription, or OpenAI audio APIs yet.

Related commit: `639cacb Add browser voice MVP`

### v0.4 - Unified Assistant

- Added deterministic `ToolRouter`.
- Chat can automatically use memory, research, repository retrieval, and handoff generation depending on user request.
- Tool Activity panel shows memory retrieval, research, handoff generation, and repository context usage.
- Explicit data-changing actions remain explicit: save research, create tasks, generate handoffs.
- Chat history/session navigation added with New Chat, project-scoped sessions, search, Show More/Show Less/Reset.

Related commits:

- `35bf789 Implement unified assistant routing`
- `51ace0a Improve handoff research routing`

### v0.5 - Repository Awareness

- Added Repository and RepositoryKnowledge tables.
- Added read-only repository registration and lightweight indexing.
- Indexing focuses on important files, manifests, entry points, config, schema files, services, providers, and importers.
- Repositories tab can register repos, re-index, view status, summaries, and indexed knowledge.
- Repository retrieval participates in project-scoped memory for architecture/code questions.
- Repository answers were tightened to separate current implementation from memory, research, and future plans.

### v0.5.1 - Repository UX and Confidence

- Repository status/freshness metadata:
  - Up To Date
  - Re-index Recommended
  - Not Indexed
  - Index Failed
- Tracks last indexed timestamp, last known repository modification timestamp, files indexed, and knowledge count.
- Repository answer footer/Tool Activity includes repository context used, knowledge items used, last indexed, and confidence.
- Repository risk analysis prioritizes current implementation risks over research/future feature risks.

### v0.5.2 - Usage Dashboard

- Added UsageLog model/table.
- Logs OpenAI API usage for chat and research calls.
- Stores timestamp, model, operation type, token counts, estimated cost, project_id, and conversation_id when available.
- Centralized estimated pricing map in `jarvis/usage/service.py`.
- Added Usage tab with today/week/month/total estimated cost, cost by model, cost by operation, and recent events.

Related commit: `5a8f544 Add repository awareness and usage dashboard`

## Current Work In Progress

### Voice spoken response cleanup and generalization

Uncommitted at time of document creation.

Goal: Jarvis should not read screen text verbatim. Spoken responses should sound like a short assistant briefing.

Files touched:

- `apps/web/app/page.tsx`
- `apps/web/lib/voice.ts`
- `apps/web/package.json`
- `apps/web/scripts/voice-formatter-sample.cjs`

Implemented/being refined:

- Speech controls:
  - Stop Speaking
  - Pause
  - Resume
- Interrupt behavior:
  - New message cancels old speech.
  - New Chat cancels speech.
  - Switching away from Chat cancels speech.
  - Turning off Speak responses cancels speech.
- Voice speed setting:
  - Slow = 0.85
  - Normal = 1.0
  - Fast = 1.2
- Response-type aware speech formatting for:
  - news
  - markets
  - research
  - repository
  - codex_handoff
  - general
- Formatting rules:
  - Never speak raw URLs.
  - Never speak source lists.
  - Never speak markdown syntax.
  - Never speak code blocks.
  - Never speak long file paths.
  - Keep speech short and conversational.
- Added `npm run check:voice` sample script covering news, markets, research, repository, and Codex handoff examples.

Recent verification performed before moving/copying:

- `cmd /c npm run check:voice`
- `cmd /c npm run build`

A future Codex session should re-run those checks in `C:\Projects\jarvis\apps\web`.

## Important Product/Architecture Decisions

- `conversation_id` and `project_id` serve different purposes and both should remain:
  - `conversation_id` groups a chat session/thread.
  - `project_id` scopes memory and records to a project.
- Current Project is global shared React state at the dashboard level.
- Normal chat can work with `project_id = null`.
- Research and handoff generation require a selected Current Project to avoid accidental global context use.
- Handoff Goal should be derived deterministically from the user request, not broad `project.goals`.
- Broad project goals belong in Project Context/Background inside handoffs.
- Known Research in handoffs should render concise implementation takeaways, not full saved research bodies.
- Repository answers must clearly separate:
  - Current repository implementation
  - Project memory/decisions
  - Research/future plans
- General news/current-events questions should use web research only, not repository retrieval or project memory unless project relevance is explicitly requested.
- Repository access is read-only. Jarvis may read, index, and summarize repositories but must not edit, commit, push, branch, or create PRs.
- Deterministic rules are preferred for routing/retrieval/formatting for now. No LLM router yet.
- Usage costs are estimated locally from token usage and a configurable pricing map. Do not connect to OpenAI billing APIs.
- Full written assistant responses should remain unchanged; only spoken text should be shortened/formatted.

## Repository Structure

```text
C:\Projects\jarvis
  apps/
    web/
      app/page.tsx                 Main Next.js dashboard
      lib/api.ts                   Frontend API client and TypeScript types
      lib/voice.ts                 Browser voice utilities and spoken formatter
      scripts/voice-formatter-sample.cjs
      package.json
  data/
    jarvis.db                      Local SQLite app database
    test-jarvis.db                 Local test/dev database artifact
  docs/
    architecture.md                Architecture notes
    future-codex-context.md        This context document
  jarvis/
    agents/
      jarvis_agent.py              Older Jarvis agent path
      codex_agent.py               Codex agent stub
      unified_assistant.py         Main chat orchestration
    api/
      main.py                      FastAPI routes
      schemas.py                   API request/response schemas
    core/
      config.py                    Environment/settings
    database/
      models.py                    SQLAlchemy models
      session.py                   Engine/session/init/migrations
    devices/
      agents.py                    Future device agent descriptors
    handoffs/
      service.py                   Codex brief generation/rendering
    memory/
      service.py                   Memory CRUD/session helpers
      retrieval.py                 Deterministic memory/repo retrieval
    project_analysis/
      service.py                   Deterministic project/repository analysis
    repositories/
      service.py                   Repository registration/indexing/summaries
    research/
      service.py                   OpenAI Responses API web research
    safety/
      registry.py                  Safety registry for future tool risk levels
    tasks/
      service.py                   Task CRUD
    tools/
      router.py                    Deterministic ToolRouter
    usage/
      service.py                   Usage logging/cost dashboard
    voice/
      service.py                   Backend voice abstraction placeholder
    llm.py                         OpenAI chat wrapper with usage logging
```

## Runtime Commands

Backend:

```powershell
cd C:\Projects\jarvis
C:\Users\charl\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m uvicorn jarvis.api.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd C:\Projects\jarvis\apps\web
npm run dev
```

Verification:

```powershell
cd C:\Projects\jarvis
C:\Users\charl\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m compileall jarvis
cd C:\Projects\jarvis\apps\web
cmd /c npm run check:voice
cmd /c npm run build
```

## Roadmap

Near-term:

- Finish and commit generalized spoken response formatting.
- Re-open Codex from `C:\Projects\jarvis` and stop editing the OneDrive copy.
- Add `.next`, `node_modules`, Python caches, backend logs, and local DB artifacts to appropriate ignore/sync-exclusion practices if needed.
- Re-test backend and frontend from the new C drive path.

Voice:

- Improve speech formatter heuristics with more real response samples.
- Add optional preview/debug display for spoken text if useful.
- Add backend audio transcription later using a provider abstraction.
- Add OpenAI audio API integration later, not in the browser-only MVP.
- Wake word detection remains future work.

Memory/Retrieval:

- Keep deterministic retrieval for now.
- Consider embeddings/vector search later once the memory model stabilizes.
- Add tests around project scoping, chat session history, and retrieval ranking.

Research:

- Keep research project-scoped unless explicitly general/current-events.
- Improve saved research metadata/source rendering without adding new tables yet.
- Add better summarization/selection for saved research in handoffs.

Repository Awareness:

- Improve index freshness checks.
- Add more focused repository component summaries.
- Add tests for repository indexing skip rules.
- Consider GitHub read-only import later.
- Keep repository writes out of scope.

Usage Dashboard:

- Keep cost estimates clearly labeled.
- Update pricing map as model pricing changes.
- Add tests for token extraction from Chat Completions and Responses API usage objects.

Safety:

- Do not add computer control, trading, email sending, GitHub writes, or filesystem mutation tools without explicit safety design and confirmations.

## Known Issues And Rough Edges

- The old OneDrive folder still exists and may be stale. Use `C:\Projects\jarvis` going forward.
- The project was copied, not moved, because Windows/Codex had the OneDrive folder in use.
- `node_modules` exists in the new copy; `.next` was not copied and will be regenerated by `npm run build` or `npm run dev`.
- The current official workspace for this existing Codex chat may still point at the OneDrive path even though commands can use `C:\Projects\jarvis` with elevated permissions.
- The voice formatter is heuristic. It should be tested against real Jarvis responses whenever a new response style is introduced.
- Current speech formatter detection can misclassify edge cases if answers contain overlapping keywords, though ordering now prioritizes Codex handoff, markets, news, repository, research, then general.
- Research relies on OpenAI Responses API web search and can be slow. No streaming/background jobs yet.
- Usage costs are estimates only and do not match actual billing dashboard data.
- SQLite/local migration helpers are suitable for local development but not a production migration strategy.
- Authentication/encryption are not implemented.
- Automated test coverage is still thin. Existing verification is mostly `compileall`, `npm run build`, and targeted scripts such as `check:voice`.
- Repository indexing is lightweight and heuristic. It does not parse every file or index full source into prompts.
- Tool routing is deterministic and intentionally simple; it does not use an LLM router yet.

## Suggested First Prompt For A New Codex Session

```text
Use C:\Projects\jarvis as the workspace. Read docs/future-codex-context.md, README.md, docs/architecture.md, then run git status -sb. This is my Jarvis project. Continue from the current uncommitted voice formatter work unless I say otherwise. Do not edit the old OneDrive copy.
```
