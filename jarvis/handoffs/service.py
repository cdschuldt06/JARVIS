import json
import re

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from jarvis.core.config import get_settings
from jarvis.database.models import CodexHandoff, Decision, KnowledgeItem, Project, Task
from jarvis.memory.retrieval import MemoryRetrievalService, RetrievedMemory
from jarvis.memory.service import MemoryService
from jarvis.usage.service import UsageService


class HandoffService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.memory = MemoryService(db)
        self.retrieval = MemoryRetrievalService(db)
        self.settings = get_settings()
        self.client = OpenAI(api_key=self.settings.openai_api_key)

    def list_handoffs(self) -> list[CodexHandoff]:
        return self.db.scalars(select(CodexHandoff).order_by(CodexHandoff.created_at.desc())).all()

    def create_handoff(self, user_request: str, project_id: int | None = None) -> CodexHandoff:
        brief = self.generate_brief(user_request, project_id)
        handoff = CodexHandoff(project_id=project_id, user_request=user_request, brief=brief)
        self.db.add(handoff)
        self.db.commit()
        self.db.refresh(handoff)
        return handoff

    def generate_brief(self, user_request: str, project_id: int | None = None) -> str:
        retrieved = self.retrieval.retrieve(user_request, project_id=project_id, limit=8)
        return self._plan_brief(user_request, retrieved, project_id)

    def _plan_brief(self, user_request: str, retrieved: RetrievedMemory, project_id: int | None) -> str:
        prompt = self._planner_prompt(user_request, retrieved)
        try:
            response = self.client.responses.create(
                model=self.settings.openai_research_model,
                input=prompt,
            )
        except Exception:
            return self._render_brief(
                user_request,
                retrieved.project,
                retrieved.decisions,
                retrieved.tasks,
                [item for item in retrieved.knowledge if item.kind == "research"],
            )

        payload = response.model_dump()
        UsageService(self.db).log_openai_usage(
            model=self.settings.openai_research_model,
            operation_type="codex_brief",
            usage=payload.get("usage"),
            project_id=project_id,
        )
        planned = self._normalize_planned_brief(response.output_text or "")
        if planned:
            return planned
        return self._render_brief(
            user_request,
            retrieved.project,
            retrieved.decisions,
            retrieved.tasks,
            [item for item in retrieved.knowledge if item.kind == "research"],
        )

    def _planner_prompt(self, user_request: str, retrieved: RetrievedMemory) -> str:
        return f"""You are Jarvis's engineering planner. Generate a concise Codex task brief for another senior engineer.

You may only generate text. Do not modify data, call tools, or ask follow-up questions.

Select only context that directly helps this implementation task. Discard unrelated project memory, decisions, research, repository summaries, tasks, providers, and future plans. If a context type has nothing relevant, omit it entirely. Do not write "none".

Use exactly this Markdown structure, omitting only empty context subsections inside Relevant Context:

# Codex Task

## Objective
One concise sentence.

## Problem
Short explanation of the current issue or need.

## Relevant Context
Include only directly relevant context. Prefer likely affected files/areas from repository context. Include research only when it directly supports this task. Include decisions only when they constrain the requested work.

## Requirements
Concrete implementation requirements for this task only.

## Acceptance Criteria
Checklist for done/not done.

## Out Of Scope
Things Codex should not touch.

## Verification
Commands and manual checks.

## Deliverable
What Codex should return when finished.

Rules:
- Do not include unrelated pending project tasks.
- Do not include unrelated research.
- Do not include unrelated decisions.
- Do not include broad project goals unless directly relevant.
- Do not duplicate the full user request in multiple sections.
- Do not include an Open Questions section.
- Keep the brief concise and executable.

User request:
{user_request}

Retrieved context candidate set:
{self._planner_context(retrieved)}
"""

    def _planner_context(self, retrieved: RetrievedMemory) -> str:
        sections: list[str] = []
        if retrieved.project:
            sections.append(
                "Project:\n"
                f"- Name: {retrieved.project.name}\n"
                f"- Description: {retrieved.project.description or ''}\n"
                f"- Goals: {retrieved.project.goals or ''}"
            )
        if retrieved.repository_knowledge:
            sections.append(
                "Repository context candidates:\n"
                + "\n".join(f"- {item.file_path} [{item.kind}]: {item.summary}" for item in retrieved.repository_knowledge)
            )
        if retrieved.decisions:
            sections.append(
                "Decision candidates:\n"
                + "\n".join(f"- {item.title}: {item.details} Reasoning: {item.reasoning}" for item in retrieved.decisions)
            )
        research_items = [item for item in retrieved.knowledge if item.kind == "research"]
        if research_items:
            sections.append(
                "Research candidates:\n"
                + "\n".join(f"- {item.title}: {self._truncate(item.body, 1200)}" for item in research_items)
            )
        other_knowledge = [item for item in retrieved.knowledge if item.kind != "research"]
        if other_knowledge:
            sections.append(
                "Other knowledge candidates:\n"
                + "\n".join(f"- [{item.kind}] {item.title}: {self._truncate(item.body, 800)}" for item in other_knowledge)
            )
        if retrieved.tasks:
            sections.append(
                "Task candidates:\n"
                + "\n".join(f"- [{item.status.value}] {item.title}: {item.description}" for item in retrieved.tasks)
            )
        return "\n\n".join(sections) if sections else "No stored context candidates were retrieved."

    def _normalize_planned_brief(self, brief: str) -> str:
        brief = brief.strip()
        if not brief:
            return ""
        if not brief.startswith("# Codex Task"):
            brief = f"# Codex Task\n\n{brief}"
        return f"{brief}\n"

    def _truncate(self, text: str, limit: int) -> str:
        cleaned = " ".join(text.split())
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[: limit - 3].rstrip()}..."

    def _project_decisions(self, project_id: int | None) -> list[Decision]:
        stmt = select(Decision)
        if project_id is not None:
            stmt = stmt.where(Decision.project_id == project_id)
        return self.db.scalars(stmt.order_by(Decision.created_at.desc())).all()

    def _project_tasks(self, project_id: int | None) -> list[Task]:
        stmt = select(Task)
        if project_id is not None:
            stmt = stmt.where(Task.project_id == project_id)
        return self.db.scalars(stmt.order_by(Task.created_at.desc())).all()

    def _project_research(self, project_id: int | None) -> list[KnowledgeItem]:
        stmt = select(KnowledgeItem).where(KnowledgeItem.kind == "research")
        if project_id is not None:
            stmt = stmt.where(KnowledgeItem.project_id == project_id)
        return self.db.scalars(stmt.order_by(KnowledgeItem.created_at.desc())).all()

    def _render_brief(self, user_request: str, project: Project | None, decisions: list[Decision], tasks: list[Task], research: list[KnowledgeItem]) -> str:
        task_text = self._task_relevant_text(user_request)
        objective = self._goal_from_request(self._headline_request(user_request))
        problem = self._problem_from_request(user_request, objective)
        relevant_context = self._relevant_context(task_text, project, decisions, research)
        requirements = self._requirements_from_request(user_request)
        acceptance = self._acceptance_criteria(user_request, requirements)
        out_of_scope = self._out_of_scope(user_request)
        verification = self._verification(user_request)

        sections = [
            ("Objective", objective),
            ("Problem", problem),
            ("Relevant Context", relevant_context),
            ("Requirements", requirements),
            ("Acceptance Criteria", acceptance),
            ("Out Of Scope", out_of_scope),
            ("Verification", verification),
            ("Deliverable", "Provide a concise summary of what changed, files modified, verification run, and any blockers."),
        ]
        rendered = ["# Codex Task"]
        for title, body in sections:
            body = body.strip()
            if not body:
                continue
            rendered.append(f"## {title}\n{body}")
        return "\n\n".join(rendered) + "\n"

    def _goal_from_request(self, user_request: str) -> str:
        request = " ".join(user_request.strip().split())
        if not request:
            return user_request

        lowered = request.lower()
        prefixes = (
            "create an implementation plan for ",
            "create a plan for ",
            "create implementation plan for ",
            "create a codex brief for ",
            "create codex brief for ",
            "create a codex task for ",
            "create codex task for ",
            "generate an implementation plan for ",
            "generate a plan for ",
            "generate a codex brief for ",
            "make an implementation plan for ",
            "make a codex task for ",
            "implement ",
            "add ",
            "build ",
            "create ",
        )
        for prefix in prefixes:
            if lowered.startswith(prefix):
                goal = request[len(prefix) :].strip()
                return self._sentence_case_goal(goal) if goal else request
        return self._ensure_period(request)

    def _sentence_case_goal(self, goal: str) -> str:
        goal = goal.strip()
        if not goal:
            return goal
        replacements = {
            "adding ": "add ",
            "building ": "build ",
            "creating ": "create ",
            "implementing ": "implement ",
            "updating ": "update ",
        }
        lowered = goal.lower()
        for source, target in replacements.items():
            if lowered.startswith(source):
                goal = f"{target}{goal[len(source):]}"
                break
        return self._ensure_period(goal[0].upper() + goal[1:])

    def _ensure_period(self, text: str) -> str:
        text = text.strip()
        if not text:
            return text
        return text if text[-1] in ".!?" else f"{text}."

    def _problem_from_request(self, user_request: str, objective: str) -> str:
        problem_section = self._section_text(user_request, ("problem", "current problem", "observed behavior"))
        if problem_section:
            return self._first_sentences(problem_section, 2)
        lowered = user_request.lower()
        if any(term in lowered for term in ("fix", "bug", "error", "failed", "stuck", "broken", "issue", "problem")):
            return "The current behavior is unreliable or confusing for this specific workflow and needs a focused fix."
        if any(term in lowered for term in ("simplify", "refactor", "improve", "update")):
            return "The current implementation works, but the workflow or code path needs to be made clearer and more focused."
        return f"Jarvis needs this focused implementation completed: {objective}"

    def _relevant_context(
        self,
        user_request: str,
        project: Project | None,
        decisions: list[Decision],
        research: list[KnowledgeItem],
    ) -> str:
        lines: list[str] = []
        areas = self._likely_affected_areas(user_request)
        if areas:
            lines.append("Likely affected areas:")
            lines.extend(f"- {area}" for area in areas)

        notes = self._context_notes(user_request)
        if notes:
            if lines:
                lines.append("")
            lines.extend(notes)

        relevant_decisions = self._relevant_decisions(user_request, decisions)
        if relevant_decisions:
            lines.append("")
            lines.append("Relevant decisions:")
            lines.extend(f"- {decision.title}: {self._first_sentences(decision.details, 1)}" for decision in relevant_decisions)

        relevant_research = self._relevant_research(user_request, research)
        if relevant_research:
            lines.append("")
            lines.append("Relevant research:")
            lines.extend(self._render_research_item(item) for item in relevant_research)

        return "\n".join(lines)

    def _context_notes(self, user_request: str) -> list[str]:
        lowered = user_request.lower()
        notes = []
        if "codex tab" in lowered:
            notes.append("This is a frontend UI task for the Codex task panel.")
        if "wake word" in lowered:
            notes.append("This is a voice activation task; use browser voice code and backend voice abstractions as context, not unrelated providers.")
        if "market" in lowered or "alpha vantage" in lowered:
            notes.append("This is a market data provider task; keep news and research providers separate unless explicitly needed.")
        return notes

    def _requirements_from_request(self, user_request: str) -> str:
        explicit = self._section_items(user_request, ("requirements", "implementation requirements", "desired behavior", "workflow"))
        if explicit:
            return "\n".join(f"- {item}" for item in explicit[:12])

        sentences = self._important_request_sentences(user_request)
        if sentences:
            return "\n".join(f"- {self._ensure_period(sentence)}" for sentence in sentences[:8])
        return "- Implement the requested change with the smallest safe code change.\n- Preserve existing behavior that is not directly related to this task."

    def _acceptance_criteria(self, user_request: str, requirements: str) -> str:
        explicit = self._section_items(user_request, ("acceptance criteria", "verification", "done"))
        if explicit:
            return "\n".join(f"- {item}" for item in explicit[:10])

        criteria = [
            "The requested behavior is implemented.",
            "Existing related behavior still works.",
            "No unrelated systems are refactored or removed.",
        ]
        if "ui" in user_request.lower() or "tab" in user_request.lower() or "frontend" in user_request.lower():
            criteria.append("The UI remains clear and usable at common desktop widths.")
        if "api" in user_request.lower() or "backend" in user_request.lower():
            criteria.append("The API returns clear success and error states.")
        if "test" in user_request.lower() or "verification" in user_request.lower():
            criteria.append("Requested verification commands pass.")
        return "\n".join(f"- {criterion}" for criterion in criteria)

    def _out_of_scope(self, user_request: str) -> str:
        explicit = self._section_items(user_request, ("out of scope", "do not refactor unrelated systems", "do not touch"))
        if explicit:
            return "\n".join(f"- {item}" for item in explicit[:12])

        lowered = user_request.lower()
        items = ["Unrelated refactors", "Unrequested new features"]
        protected_areas = {
            "voice": "Voice behavior",
            "news": "News providers",
            "market": "Market providers",
            "markets": "Market providers",
            "repository indexing": "Repository indexing",
            "usage": "Usage dashboard",
            "research": "OpenAI research behavior",
        }
        for term, label in protected_areas.items():
            if f"do not" in lowered and term in lowered:
                items.append(label)
        return "\n".join(f"- {item}" for item in dict.fromkeys(items))

    def _verification(self, user_request: str) -> str:
        commands = self._verification_commands(user_request)
        manual_checks = self._section_items(user_request, ("manual checks", "manual test", "manual tests"))

        lines: list[str] = []
        if commands:
            lines.append("Run:")
            lines.extend(f"- `{command}`" for command in commands)
        else:
            lines.append("Run:")
            lines.append("- `python -m compileall jarvis`")

        if manual_checks:
            lines.append("")
            lines.append("Manual checks:")
            lines.extend(f"- {check}" for check in manual_checks[:8])
        return "\n".join(lines)

    def _likely_affected_areas(self, user_request: str) -> list[str]:
        lowered = user_request.lower()
        area_terms = (
            (("codex tab", "ui", "frontend", "responsive", "button", "layout"), "apps/web/app/page.tsx"),
            (("api client", "fetch", "frontend api"), "apps/web/lib/api.ts"),
            (("codex task", "task execution", "approve", "approval", "run task", "timeout", "subprocess", "auth"), "jarvis/codex_tasks/service.py"),
            (("brief", "handoff", "assignment"), "jarvis/handoffs/service.py"),
            (("chat", "router", "route", "create a codex task"), "jarvis/tools/router.py"),
            (("assistant", "chat integration"), "jarvis/agents/unified_assistant.py"),
            (("endpoint", "api", "schema", "request model"), "jarvis/api/main.py / jarvis/api/schemas.py"),
            (("database", "model", "table"), "jarvis/database/models.py"),
            (("news", "rss"), "jarvis/news/service.py"),
            (("market", "alpha vantage", "ticker"), "jarvis/markets/service.py"),
            (("usage", "cost", "dashboard"), "jarvis/usage/service.py"),
            (("repository indexing", "index repository"), "jarvis/repositories/service.py"),
            (("wake word", "voice", "speech", "tts", "transcription"), "jarvis/voice/"),
            (("wake word", "browser voice", "speech recognition"), "apps/web/lib/voice.ts"),
        )
        areas = [area for terms, area in area_terms if any(term in lowered for term in terms)]
        return list(dict.fromkeys(areas))[:8]

    def _relevant_decisions(self, user_request: str, decisions: list[Decision]) -> list[Decision]:
        request_terms = self._keywords(user_request)
        relevant = []
        for decision in decisions:
            haystack = f"{decision.title} {decision.details} {decision.reasoning}"
            if len(request_terms & self._keywords(haystack)) >= 3:
                relevant.append(decision)
            if len(relevant) == 3:
                break
        return relevant

    def _relevant_research(self, user_request: str, research: list[KnowledgeItem]) -> list[KnowledgeItem]:
        request_terms = self._keywords(user_request)
        relevant = []
        for item in research:
            if len(request_terms & self._keywords(f"{item.title} {item.body}")) >= 3:
                relevant.append(item)
            if len(relevant) == 2:
                break
        return relevant

    def _headline_request(self, user_request: str) -> str:
        for line in user_request.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.strip("#:").lower() in self._known_section_names():
                break
            return stripped
        objective_section = self._section_text(user_request, ("objective", "goal"))
        return objective_section or user_request

    def _task_relevant_text(self, user_request: str) -> str:
        lines = user_request.splitlines()
        excluded_sections = {"out of scope", "do not refactor unrelated systems", "do not touch", "verification", "manual checks", "manual test", "manual tests", "run"}
        kept: list[str] = []
        skipping = False
        for line in lines:
            normalized = line.strip().strip("#:").lower()
            if normalized in excluded_sections:
                skipping = True
                continue
            if skipping and normalized in self._known_section_names() and normalized not in excluded_sections:
                skipping = False
            if not skipping:
                kept.append(line)
        return "\n".join(kept)

    def _section_text(self, text: str, names: tuple[str, ...]) -> str:
        lines = text.splitlines()
        capture = False
        captured: list[str] = []
        for line in lines:
            normalized = line.strip().strip("#:").lower()
            if capture and normalized in self._known_section_names():
                break
            if normalized in names:
                capture = True
                continue
            if capture:
                captured.append(line)
        return "\n".join(captured).strip()

    def _section_items(self, text: str, names: tuple[str, ...]) -> list[str]:
        section = self._section_text(text, names)
        if not section:
            return []
        items = []
        for line in section.splitlines():
            stripped = line.strip().lstrip("-*0123456789. ").strip()
            if stripped:
                items.append(self._ensure_period(stripped))
        return items

    def _verification_commands(self, user_request: str) -> list[str]:
        commands = []
        in_run_block = False
        for line in user_request.splitlines():
            stripped = line.strip()
            lowered = stripped.lower().rstrip(":")
            if lowered == "run":
                in_run_block = True
                continue
            if in_run_block and stripped.startswith("-"):
                command = stripped.lstrip("- ").strip("` ")
                if command:
                    commands.append(command)
                continue
            if in_run_block and stripped and not stripped.startswith("-"):
                in_run_block = False

        if not commands and "npm run build" in user_request:
            commands.append("cmd /c npm run build")
        if not commands or "compileall" in user_request:
            if "python -m compileall jarvis" in user_request or not commands:
                commands.insert(0, "python -m compileall jarvis")
        return list(dict.fromkeys(commands))

    def _important_request_sentences(self, user_request: str) -> list[str]:
        sentences = self._research_sentences(user_request)
        implementation_terms = (
            "add",
            "allow",
            "create",
            "fix",
            "implement",
            "keep",
            "preserve",
            "remove",
            "require",
            "run",
            "show",
            "update",
        )
        return [sentence for sentence in sentences if any(term in sentence.lower() for term in implementation_terms)]

    def _first_sentences(self, text: str, count: int) -> str:
        sentences = self._research_sentences(text)
        if not sentences:
            return self._ensure_period(" ".join(text.strip().split())[:240])
        return " ".join(self._ensure_period(sentence) for sentence in sentences[:count])

    def _keywords(self, text: str) -> set[str]:
        stopwords = {
            "about",
            "after",
            "again",
            "also",
            "and",
            "are",
            "before",
            "brief",
            "briefs",
            "build",
            "codex",
            "codextask",
            "could",
            "create",
            "creates",
            "current",
            "existing",
            "from",
            "generated",
            "generation",
            "have",
            "implement",
            "implementation",
            "implementing",
            "into",
            "its",
            "jarvis",
            "not",
            "own",
            "preserve",
            "problem",
            "project",
            "requirements",
            "service",
            "should",
            "status",
            "task",
            "tasks",
            "that",
            "their",
            "there",
            "the",
            "this",
            "too",
            "used",
            "with",
            "work",
        }
        keywords = set()
        for raw_word in re.findall(r"[a-z0-9_./-]{3,}", text.lower()):
            word = raw_word.strip(".,:;!?()[]`'\"")
            if word and word not in stopwords:
                keywords.add(word)
        return keywords

    def _known_section_names(self) -> set[str]:
        return {
            "acceptance criteria",
            "current problem",
            "desired behavior",
            "do not refactor unrelated systems",
            "do not touch",
            "done",
            "goal",
            "implementation requirements",
            "manual checks",
            "manual test",
            "manual tests",
            "objective",
            "out of scope",
            "problem",
            "requirements",
            "run",
            "verification",
            "workflow",
        }

    def _render_research_item(self, item: KnowledgeItem) -> str:
        takeaways = self._research_takeaways(item.body)
        sources = self._research_sources(item.source)
        lines = [f"- {item.title}"]
        lines.extend(f"  - {takeaway}" for takeaway in takeaways)
        if sources:
            lines.append(f"  - Sources: {', '.join(sources)}")
        rendered = "\n".join(lines)
        if len(rendered) <= 800:
            return rendered
        return f"{rendered[:797].rstrip()}..."

    def _research_takeaways(self, body: str) -> list[str]:
        sentences = self._research_sentences(body)
        implementation_terms = (
            "api",
            "backend",
            "browser",
            "fallback",
            "feature",
            "implement",
            "integration",
            "prototype",
            "speech",
            "start",
            "support",
            "use",
        )
        selected: list[str] = []
        for sentence in sentences:
            lowered = sentence.lower()
            if any(term in lowered for term in implementation_terms):
                selected.append(self._ensure_period(sentence))
            if len(selected) == 4:
                break
        if not selected:
            selected = [self._ensure_period(sentence) for sentence in sentences[:4]]
        return selected

    def _research_sentences(self, body: str) -> list[str]:
        cleaned_lines = []
        skip_prefixes = ("concise summary", "key findings", "recommendation", "summary")
        for line in body.splitlines():
            stripped = line.strip().lstrip("-*#0123456789. ")
            if not stripped:
                continue
            if stripped.lower().rstrip(":") in skip_prefixes:
                continue
            cleaned_lines.append(stripped)
        cleaned = " ".join(cleaned_lines)
        parts = re.split(r"(?<=[.!?])\s+", cleaned)
        return [part.strip() for part in parts if len(part.strip()) > 20]

    def _research_sources(self, source: str) -> list[str]:
        if not source:
            return []
        try:
            parsed = json.loads(source)
        except json.JSONDecodeError:
            return []
        urls = parsed.get("urls") if isinstance(parsed, dict) else None
        if not isinstance(urls, list):
            return []
        return [url for url in urls if isinstance(url, str) and url.startswith(("http://", "https://"))][:4]
