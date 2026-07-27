"""Shared prompts, constants, and helpers for edge case cache operations.

Used by generate_edge_case_evals.py, test_edge_case_cache.py, and
build_edge_case_library.py.
"""

from __future__ import annotations

import json
import logging

import yaml

logger = logging.getLogger(__name__)

CACHE_TAG_THRESHOLD = 3
CACHE_MAX_EDGE_CASES = 2
CACHE_MAX_ASSERTIONS = 2
CACHE_MIN_RELEVANCE_SCORE = 7

CLASSIFY_PROMPT = """\
You are classifying an AI agent skill into domain tags for cache lookup.

Given the skill description below, output a JSON object with:
- "tags": 5-8 tags following these rules:
  - PREFER tags from the existing list below when they match the skill
  - MUST include the specific library, tool, or framework name (e.g., "pymupdf", \
"scapy", "openpyxl", "suricata", "pyscipopt")
  - MUST include the specific technique or algorithm (e.g., "pid-algorithm", \
"levenshtein", "subtour-elimination")
  - AVOID broad field-level terms that match many unrelated skills (e.g., "chart", \
"etl", "ocr", "data-pipeline", "file-management", "security")
  - Each tag should be specific enough that a skill from a DIFFERENT sub-field \
would NOT share it
  - Only create NEW tags if none of the existing ones fit

## Existing Tags in Cache
{existing_tags}

## Skill Description
{skill_description}

## Skill Content (first 500 chars)
{skill_preview}

Output ONLY valid JSON — no markdown fences, no commentary."""

BUILD_CLASSIFY_PROMPT = """\
You are classifying AI agent skills into domains for an edge case reuse library.

Given the skill description below, output a JSON object with:
- "domain": a short kebab-case domain name (e.g., "control-systems", \
"pdf-processing", "network-security", "fuzzy-text-matching")
- "tags": 5-8 tags following these rules:
  - MUST include the specific library, tool, or framework name (e.g., "pymupdf", \
"scapy", "openpyxl", "suricata", "pyscipopt")
  - MUST include the specific technique or algorithm (e.g., "pid-algorithm", \
"levenshtein", "subtour-elimination")
  - AVOID broad field-level terms that match many unrelated skills (e.g., "chart", \
"etl", "ocr", "data-pipeline", "file-management", "security")
  - Each tag should be specific enough that a skill from a DIFFERENT sub-field \
would NOT share it

If the skill clearly belongs to one of these existing domains, use that exact \
domain name:
{existing_domains}

Otherwise, create a new domain name.

## Skill Description
{skill_description}

## Skill Content (first 500 chars)
{skill_preview}

Output ONLY valid JSON — no markdown fences, no commentary."""

VERIFY_PROMPT = """\
You are verifying whether cached edge cases are relevant for a new AI agent skill.

The edge cases were generated for a DIFFERENT skill in the same domain. \
For each edge case, score how relevant it is to THIS new skill on a scale \
of 0-10. Consider BOTH the scenario AND the assertions — if the scenario \
is relevant but the assertions expect behavior the skill contradicts, \
score low.

Scoring guide:
- 0: irrelevant scenario OR assertions contradict/don't match the skill's approach
- 5: scenario and assertions are somewhat relevant but not a strong fit
- 10: scenario and assertions directly test a gap in the skill's instructions

## New Skill Description
{skill_description}

## New Skill Content
{skill_content}

## Cached Edge Cases
{edge_cases_text}

Output ONLY a valid JSON object with exactly {num_edge_cases} integer scores:
{{"scores": [8, 2, 10]}}"""


def parse_llm_json(raw: str) -> dict:
    """Parse JSON from LLM response, handling markdown fences."""
    text = raw.strip()
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence) :]
            break
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except ValueError as exc:
            raise json.JSONDecodeError(
                f"No JSON object found in LLM response: {text[:100]}",
                text,
                0,
            ) from exc


def _parse_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from SKILL.md content."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                meta = yaml.safe_load(parts[1])
                if isinstance(meta, dict):
                    return meta
            except Exception:
                pass
    return {}


def extract_skill_description(content: str) -> str:
    """Extract description from SKILL.md YAML frontmatter."""
    return _parse_frontmatter(content).get("description", "")


def extract_skill_name(content: str, fallback: str = "unknown-skill") -> str:
    """Extract skill name from SKILL.md YAML frontmatter."""
    return _parse_frontmatter(content).get("name", fallback)


def collect_library_tags(library: dict) -> str:
    """Collect all unique tags from a library dict, return as comma-separated string."""
    all_tags: set[str] = set()
    for domain_data in library.get("domains", {}).values():
        for tag in domain_data.get("tags", []):
            all_tags.add(tag)
    return ", ".join(sorted(all_tags))


def build_edge_cases_text(evals_list: list[dict]) -> str:
    """Format edge cases with prompts and assertions for the verification prompt."""
    text = ""
    for i, ev in enumerate(evals_list, 1):
        text += f"\n{i}. {ev.get('name', 'unnamed')}\n"
        text += f"   Prompt: {ev.get('prompt', '')}\n"
        for a in ev.get("assertions", []):
            text += f"   Assertion: {a}\n"
    return text


def match_tags_against_library(
    tags: list[str],
    library: dict,
    threshold: int = CACHE_TAG_THRESHOLD,
) -> list[tuple[str, int, list[str]]]:
    """Match tags against library domains.

    Returns list of (domain_name, overlap_count, overlapping_tags) sorted
    by overlap count descending, then alphabetically for tiebreaking.
    Only returns matches >= threshold.
    """
    tag_set = set(t.lower() for t in tags)
    matches = []

    for domain_name, domain_data in library.get("domains", {}).items():
        cached_tags = set(t.lower() for t in domain_data.get("tags", []))
        overlap = tag_set & cached_tags
        if len(overlap) >= threshold:
            matches.append((domain_name, len(overlap), sorted(overlap)))

    matches.sort(key=lambda x: (-x[1], x[0]))
    return matches
