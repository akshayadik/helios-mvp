# .claude/governance/agent_registry.py
from dataclasses import dataclass


@dataclass
class AgentSpec:
    name: str
    owned_paths: list[str]
    allowed_flags: list[str]
    forbidden_paths: list[str]
    requires_approval: bool = True


AGENTS = {
    "StatisticalPipelineAgent": AgentSpec(
        name="StatisticalPipelineAgent",
        owned_paths=["src/stats/", "src/dpipe/"],
        allowed_flags=["HELIOS_ENABLE_STATS"],
        forbidden_paths=["src/graph/", "src/llm/"],
    ),
    # ... similar for others
}


def validate_agent_action(agent_name: str, file_path: str, flags: dict) -> bool:
    spec = AGENTS.get(agent_name)
    if not spec:
        return False
    # flag check etc.
    return all(p not in file_path for p in spec.forbidden_paths)
