"""Experiment strategies for A/B evaluation variants.

Each strategy determines which directories to copy and how to customize
the template context for treatment and control variants. The scaffold
module delegates to these strategies rather than hardcoding skilled/unskilled
logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from abevalflow.schemas import CopySpec, ExperimentConfig, ExperimentType


class ExperimentStrategy(Protocol):
    """Protocol for experiment variant strategies."""

    def variant_copy_specs(
        self, submission_dir: Path, variant: str,
    ) -> list[CopySpec]:
        """Return copy specs for this variant ('control' or 'treatment')."""
        ...

    def customize_context(self, base_context: dict, variant: str) -> dict:
        """Adjust template context per variant.

        Must set 'skills_dir' when skills/ is in the copy spec, and
        'copy_pairs' as a list of (src, dest) tuples for Dockerfile.j2.
        """
        ...


def _skills_dir_from_specs(specs: list[CopySpec]) -> str | None:
    """Return the dest path if 'skills' is in the copy spec src list."""
    for spec in specs:
        if spec.src == "skills":
            return spec.dest
    return None


class SkillExperimentStrategy:
    """Default strategy: treatment includes skills/docs, control excludes them.

    Common dirs (tests, supportive, scripts) are handled by the scaffold
    module and are not part of the strategy's copy specs.
    """

    def __init__(self, config: ExperimentConfig) -> None:
        self._config = config

    def variant_copy_specs(
        self, submission_dir: Path, variant: str,
    ) -> list[CopySpec]:
        if variant == "treatment":
            return [
                spec
                for spec in self._config.treatment.copy_dirs
                if (submission_dir / spec.src).is_dir()
            ]
        return [
            spec
            for spec in self._config.control.copy_dirs
            if (submission_dir / spec.src).is_dir()
        ]

    def customize_context(self, base_context: dict, variant: str) -> dict:
        specs = (
            self._config.treatment.copy_dirs
            if variant == "treatment"
            else self._config.control.copy_dirs
        )
        ctx = {**base_context}
        ctx["skills_dir"] = _skills_dir_from_specs(specs)
        ctx["copy_pairs"] = [(s.src, s.dest) for s in specs]
        return ctx


class ModelExperimentStrategy:
    """Same files for both variants, different env vars.

    Both variants get identical copy specs from their respective
    VariantSpec. The difference is in env_from_secrets — e.g.,
    treatment uses model A, control uses model B. Env vars are
    injected via Harbor's persistent_env at runtime, not baked
    into the Dockerfile.
    """

    def __init__(self, config: ExperimentConfig) -> None:
        self._config = config

    def variant_copy_specs(
        self, submission_dir: Path, variant: str,
    ) -> list[CopySpec]:
        variant_spec = (
            self._config.treatment if variant == "treatment" else self._config.control
        )
        return [
            spec
            for spec in variant_spec.copy_dirs
            if (submission_dir / spec.src).is_dir()
        ]

    def customize_context(self, base_context: dict, variant: str) -> dict:
        variant_spec = (
            self._config.treatment if variant == "treatment" else self._config.control
        )
        ctx = {**base_context}
        ctx["skills_dir"] = _skills_dir_from_specs(variant_spec.copy_dirs)
        ctx["copy_pairs"] = [(s.src, s.dest) for s in variant_spec.copy_dirs]
        ctx["env_from_secrets"] = variant_spec.env_from_secrets
        return ctx


class ConfigDrivenStrategy:
    """Reads copy/env directly from ExperimentConfig for 'custom' type.

    Sets skills_dir when 'skills' is in the copy spec src list.
    """

    def __init__(self, config: ExperimentConfig) -> None:
        self._config = config

    def variant_copy_specs(
        self, submission_dir: Path, variant: str,
    ) -> list[CopySpec]:
        variant_spec = (
            self._config.treatment if variant == "treatment" else self._config.control
        )
        return [
            spec
            for spec in variant_spec.copy_dirs
            if (submission_dir / spec.src).is_dir()
        ]

    def customize_context(self, base_context: dict, variant: str) -> dict:
        variant_spec = (
            self._config.treatment if variant == "treatment" else self._config.control
        )
        ctx = {**base_context}
        ctx["skills_dir"] = _skills_dir_from_specs(variant_spec.copy_dirs)
        ctx["copy_pairs"] = [(s.src, s.dest) for s in variant_spec.copy_dirs]
        ctx["env_from_secrets"] = variant_spec.env_from_secrets
        return ctx


_STRATEGY_MAP: dict[ExperimentType, type] = {
    ExperimentType.SKILL: SkillExperimentStrategy,
    ExperimentType.MODEL: ModelExperimentStrategy,
    ExperimentType.PROMPT: SkillExperimentStrategy,
    ExperimentType.CUSTOM: ConfigDrivenStrategy,
}


def get_strategy(config: ExperimentConfig) -> ExperimentStrategy:
    """Return the appropriate strategy for the given experiment config."""
    cls = _STRATEGY_MAP[config.type]
    return cls(config)
