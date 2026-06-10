# Jarvis v0.1 Architecture

Jarvis v0.1 separates the shared brain from future device agents.

## Shared Brain

The FastAPI backend owns durable memory, projects, decisions, tasks, knowledge, and Codex handoffs. SQLite is used locally through SQLAlchemy so the storage layer can move to a networked database later without changing the application services.

## Agents

- `JarvisAgent` handles chat, planning, memory writes, and future knowledge extraction.
- `CodexAgent` is a non-executing stub that represents implementation handoffs.

Jarvis prepares context. Codex builds from explicit briefs.

## Memory And Knowledge

Conversation history is stored as raw messages. Decisions are also written into the knowledge table so future retrieval can use distilled project facts instead of scanning every message.

## Voice

The voice layer is an interface-only abstraction in v0.1. Chat already records an `input_mode`, so typed and spoken messages can share the same downstream path.

## Safety

The safety registry records action names, descriptions, risk levels, and confirmation requirements. v0.1 only registers low-risk brief generation and does not implement high-risk actions.

## Multi-Device

Device agent descriptors model future Windows and Mac agents. Computer control should live in device agents, while the shared brain remains responsible for memory and planning.
