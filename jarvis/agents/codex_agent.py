from jarvis.agents.base import Agent


class CodexAgent(Agent):
    name = "CodexAgent"
    responsibilities = ("receive_implementation_requests", "generate_handoff_briefs")

    def describe(self) -> dict[str, object]:
        return {"name": self.name, "responsibilities": self.responsibilities, "execution_enabled": False}
