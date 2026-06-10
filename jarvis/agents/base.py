from abc import ABC, abstractmethod


class Agent(ABC):
    name: str
    responsibilities: tuple[str, ...]

    @abstractmethod
    def describe(self) -> dict[str, object]:
        """Return metadata about this agent."""
