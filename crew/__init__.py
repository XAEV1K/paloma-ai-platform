"""CrewAI orchestration layer.

The ONLY package that imports CrewAI orchestration primitives. Everything
here is wiring: agents get prompts + tools, tasks get contracts, the crew
gets a sequential process. Zero business logic by design.
"""

from crew.agents import AgentFactory
from crew.crew import PalomaPipeline, PipelineResult
from crew.prompts import PromptRepository
from crew.tasks import TaskFactory

__all__ = ["AgentFactory", "PalomaPipeline", "PipelineResult", "PromptRepository", "TaskFactory"]
