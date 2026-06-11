# Jarvis Architecture

Jarvis separates the shared brain from future device agents and layers memory, awareness, voice, and tool routing into one assistant experience.

## Shared Brain

The FastAPI backend owns durable memory, projects, decisions, tasks, knowledge, and Codex handoffs. SQLite is used locally through SQLAlchemy so the storage layer can move to a networked database later without changing the application services.

## Model Configuration

Jarvis supports two configurable OpenAI model names. `OPENAI_MODEL` is the everyday chat model used for normal chat and memory-grounded responses. `OPENAI_RESEARCH_MODEL` is used for web search, research, and synthesis workflows.

## Awareness

Jarvis v0.2 adds a deterministic retrieval layer before chat responses. It retrieves relevant project goals, decisions, knowledge items, and tasks with keyword and metadata matching. This intentionally avoids embeddings, vector databases, and external RAG frameworks.

Research is a dedicated path that uses the OpenAI Responses API with hosted web search and `OPENAI_RESEARCH_MODEL`. Research results can be saved as `KnowledgeItem` rows with `kind="research"` and project association. Codex handoffs include stored research as implementation context.

## Unified Assistant Routing

Jarvis v0.4 routes `POST /chat` through `UnifiedAssistant` and `ToolRouter`. The frontend still sends one chat request, but the backend deterministically chooses the tools to use:

- normal chat uses `OPENAI_MODEL`
- project chat retrieves project-scoped memory before responding
- repository-intent chat retrieves project-scoped repository knowledge before responding
- research-intent chat uses `OPENAI_RESEARCH_MODEL` and the Responses API web search tool
- explicit Codex brief requests generate a project-scoped handoff
- explicit save-research requests store the most recent research-style assistant response as a `KnowledgeItem`

The router does not use an LLM. Rules are intentionally simple and based on phrases such as `research`, `latest`, `news`, `today`, `current`, `Codex brief`, and `implementation brief`.

Memory retrieval remains SQL and keyword based. Ranking weights title matches highest, includes decision details, saved research, tasks, and indexed repository knowledge, and never leaves the selected `project_id` scope. Research and handoff generation require a Current Project to avoid accidental global context.

## Repository Awareness

Jarvis v0.5 adds read-only repository awareness through `RepositoryService` and `ProjectAnalysisService`. Repositories can be registered with a name, local path, description, and optional project association. Indexing is intentionally lightweight and stores summaries in `RepositoryKnowledge` instead of pushing whole source files into prompts.

The indexer focuses on important files such as `README.md`, `package.json`, `requirements.txt`, Prisma schemas, entry points, configuration files, and obvious service/provider/importer components. It skips heavy generated folders such as `.git`, `.next`, `node_modules`, build outputs, virtual environments, and caches.

Repository retrieval is project-scoped and deterministic. When a chat request asks about architecture, importers, code structure, services, risks, or next engineering work, `ToolRouter` can include `REPOSITORY_RETRIEVAL`, and retrieved repository summaries are added to the same prompt context as tasks, decisions, and research.

The Repositories tab can register repositories, re-index them, display summaries, show indexed knowledge, and surface simple project analysis findings such as missing README coverage, missing indexed tests, or missing schema summaries.

## Agents

- `JarvisAgent` handles chat, planning, memory writes, and future knowledge extraction.
- `CodexAgent` is a non-executing stub that represents implementation handoffs.

Jarvis prepares context. Codex builds from explicit briefs.

## Memory And Knowledge

Conversation history is stored as raw messages. `conversation_id` groups a chat session or thread, so Jarvis can keep a back-and-forth together even when it is not tied to a project. `project_id` optionally scopes a message to a project, so project memory can include relevant chat history without losing session grouping.

The dashboard exposes this with a persistent Current Project selector. Chat messages, tasks, decisions, and Codex handoffs use the shared selected project. For chat, the selected project is sent to `POST /chat` as `project_id`; the current `conversation_id` still threads the chat session.

Project-scoped dashboard sections display records for the Current Project. The project list itself remains global because it is the user's project index.

Decisions are also written into the knowledge table so future retrieval can use distilled project facts instead of scanning every message.

## Voice

The backend voice layer defines provider abstractions for future speech-to-text and text-to-speech services. The v0.3 MVP is browser-only: the web Chat tab feature-detects `SpeechRecognition` for push-to-talk and uses `SpeechSynthesis` for spoken responses when enabled. Chat records voice-originated messages with `input_mode="voice"`.

Wake words, backend audio transcription, OpenAI audio APIs, and local computer control are intentionally out of scope.

## Safety

The safety registry records action names, descriptions, risk levels, and confirmation requirements. v0.1 only registers low-risk brief generation and does not implement high-risk actions.

## Multi-Device

Device agent descriptors model future Windows and Mac agents. Computer control should live in device agents, while the shared brain remains responsible for memory and planning.
