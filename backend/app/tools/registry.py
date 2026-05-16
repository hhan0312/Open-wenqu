from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolRegistry:
    tools: dict[str, Callable[..., Any]] = field(default_factory=dict)

    def register(self, name: str, fn: Callable[..., Any]) -> None:
        self.tools[name] = fn

    def require(self, name: str) -> Callable[..., Any]:
        if name not in self.tools:
            raise KeyError(name)
        return self.tools[name]

    def has(self, name: str) -> bool:
        return name in self.tools


def build_tool_registry(
    *,
    llm_generate_json: Callable[..., Any] | None = None,
) -> ToolRegistry:
    reg = ToolRegistry()
    # Placeholders wired in agent service; names must exist for skill validation.
    if llm_generate_json:
        reg.register("llm.generate_json", llm_generate_json)
    reg.register("evidence.locate", lambda **kwargs: kwargs)
    reg.register("docx.export", lambda **kwargs: kwargs)
    return reg
