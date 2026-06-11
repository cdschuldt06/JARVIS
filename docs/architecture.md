# Jarvis v0.2 Architecture

Jarvis v0.2 separates the shared brain from future device agents and adds Awareness through memory retrieval and web research.

## Shared Brain

The FastAPI backend owns durable memory, projects, decisions, tasks, knowledge, and Codex handoffs. SQLite is used locally through SQLAlchemy so the storage layer can move to a networked database later without changing the application services.

## Model Configuration

Jarvis supports two configurable OpenAI model names. `OPENAI_MODEL` is the everyday chat model used by the current chat path. `OPENAI_RESEARCH_MODEL` is reserved for v0.2 workflows that need web search, research, or deeper synthesis. The current chat behavior does not use the research model yet.

## Awareness

Jarvis v0.2 adds a deterministic retrieval layer before chat responses. It retrieves relevant project goals, decisions, knowledge items, and tasks with keyword and metadata matching. This intentionally avoids embeddings, vector databases, and external RAG frameworks.

Research is a dedicated path that uses the OpenAI Responses API with hosted web search and `OPENAI_RESEARCH_MODEL`. Research results can be saved as `KnowledgeItem` rows with `kind="research"` and project association. Codex handoffs include stored research as implementation context.

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

The voice layer is an interface-only abstraction in v0.1. Chat already records an `input_mode`, so typed and spoken messages can share the same downstream path.

## Safety

The safety registry records action names, descriptions, risk levels, and confirmation requirements. v0.1 only registers low-risk brief generation and does not implement high-risk actions.

## Multi-Device

Device agent descriptors model future Windows and Mac agents. Computer control should live in device agents, while the shared brain remains responsible for memory and planning.
