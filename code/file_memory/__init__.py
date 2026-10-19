"""File-based memory (AGENT.md + MEMORY.md) for HW6 Part 4."""
from .commands import HELP_TEXT, FileMemorySession
from .consolidation import ConsolidationResult, audit_resolution, consolidate
from .memory_files import (
    AGENT_MD,
    MAX_MEMORY_LINES,
    MEMORY_MD,
    append_facts,
    build_system_prompt,
    count_memory_lines,
    load_memory_files,
    needs_consolidation,
    parse_facts,
    read_last_consolidated,
)

__all__ = [
    "AGENT_MD", "MAX_MEMORY_LINES", "MEMORY_MD", "HELP_TEXT", "ConsolidationResult", "FileMemorySession",
    "append_facts", "audit_resolution", "build_system_prompt", "consolidate", "count_memory_lines",
    "load_memory_files", "needs_consolidation", "parse_facts", "read_last_consolidated",
]
