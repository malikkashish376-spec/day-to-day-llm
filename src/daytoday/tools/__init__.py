"""Tool package. ``build_registry`` is the only public entry point."""
from __future__ import annotations

from . import expenses, journal, notes, planner, tasks
from .registry import Tool, ToolError, ToolRegistry

MODULES = (tasks, expenses, journal, notes, planner)


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for module in MODULES:
        for tool in module.TOOLS:
            registry.register(tool)
    return registry


__all__ = ["build_registry", "Tool", "ToolError", "ToolRegistry"]
