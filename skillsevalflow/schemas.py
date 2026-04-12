"""Pydantic models for skill submission metadata validation."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class GenerationMode(str, Enum):
    MANUAL = "manual"
    AI = "ai"


class SubmissionMetadata(BaseModel):
    """Schema for metadata.yaml in a skill submission directory.

    The schema_version field enables forward-compatible evolution
    of the metadata format without breaking existing submissions.
    """

    schema_version: str = Field(
        description="Schema version for forward compatibility (e.g. '1.0')",
    )
    name: str = Field(min_length=1, description="Skill name, must be non-empty")
    description: str = Field(min_length=1, description="Brief description of the skill")
    persona: str = Field(min_length=1, description="Target persona (e.g. rh-sre, rh-developer)")
    version: str = Field(min_length=1, description="Skill version string")
    author: str = Field(min_length=1, description="Author or team name")
    tags: Optional[list[str]] = Field(default=None, description="Optional classification tags")
    generation_mode: GenerationMode = Field(
        description="Whether the skill was created manually or AI-generated",
    )
