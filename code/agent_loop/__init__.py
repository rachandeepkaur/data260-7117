"""Hand-written tool-calling agent (HW7 Part 2) and bounded Reflexion (Part 3).

    loop.run_agent          the loop: tool calls -> tool-role messages -> final answer / ceiling
    toolsets                validation + execution of the domain (and file) tools
    tasks                   fixed cases A/B/C, strict verifier, independent oracle
    grounding               unsupported-claim detection
    reflexion.run_reflexion bounded retries with isolated, untrusted reflections
"""
from .loop import OllamaChatModel, ScriptedModel, run_agent
from .toolsets import ToolDef, Toolset, make_domain_toolset

__all__ = ["run_agent", "OllamaChatModel", "ScriptedModel", "Toolset", "ToolDef", "make_domain_toolset"]
