import json
from config import load_config
from models import StudioProfile, LessonPlan, Affordances, Tool, CourseworkMapping
from .base import AIProvider

def get_provider() -> AIProvider:
    """Factory to get the configured AI Provider."""
    cfg = load_config()
    provider_name = cfg.get("ai_provider", "anthropic")
    
    if provider_name == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider()
    elif provider_name == "local":
        from .local_provider import LocalProvider
        return LocalProvider()
    else:
        # Default to anthropic
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider()


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API (Mirroring old ai.py behavior)
# ══════════════════════════════════════════════════════════════════════════════

def pdf_to_profiles(pdf_bytes: bytes) -> list[StudioProfile]:
    """
    Extract one or more StudioProfiles from a PDF via the configured AI provider.
    A single PDF may describe multiple studios — this returns all of them.
    """
    provider = get_provider()
    studios_data = provider.extract_json_from_pdf(pdf_bytes)  # always a list[dict]

    profiles = []
    for data in studios_data:
        affordances = Affordances(**data.pop("affordances", {}))
        tools       = [Tool(**t) for t in data.pop("tools", [])]
        coursework  = [CourseworkMapping(**c) for c in data.pop("coursework", [])]
        profiles.append(StudioProfile(
            affordances=affordances,
            tools=tools,
            coursework=coursework,
            **data
        ))
    return profiles


def pdf_to_profile(pdf_bytes: bytes) -> StudioProfile:
    """Backward-compat wrapper — returns the first extracted studio."""
    return pdf_to_profiles(pdf_bytes)[0]


def generate_plan(
    topic:        str,
    subject:      str,
    grade:        str,
    board:        str,
    sessions:     int,
    studios:      list[StudioProfile],
    similar_plans: list[LessonPlan] = []
) -> str:
    """
    Generate a lesson plan grounded in the actual studios of this school.
    Returns markdown string — the full lesson plan.
    """
    # Build studio context — only the fields the AI needs for planning
    studios_ctx = []
    for s in studios:
        studios_ctx.append({
            "name":         s.name,
            "description":  s.description,
            "affordances":  s.affordances.summary,
            "tools":        [{"name": t.name, "description": t.description,
                              "quantity": t.quantity, "interaction": t.interaction}
                             for t in s.tools],
            "capacity":     s.capacity,
            "sample_ideas": [{"topic": c.topic, "plan": c.teaching_plan}
                             for c in s.coursework[:3]]
        })

    # Add existing plans as few-shot examples if available
    examples_ctx = ""
    if similar_plans:
        examples = [{"topic": p.topic, "grade": p.grade,
                     "subject": p.subject, "plan": p.plan_text[:500]}
                    for p in similar_plans[:2]]
        examples_ctx = f"""
EXAMPLES OF PLANS THAT WORKED WELL IN THIS SCHOOL (use as style reference):
{json.dumps(examples, indent=2)}
"""

    system_prompt = f"""You are a curriculum planning assistant for an experiential learning school.
The school has specially designed studios with physical tools for hands-on learning.
Your job is to create lesson plans that GENUINELY USE the specific tools in these studios."""

    user_prompt = f"""
LESSON REQUEST:
- Topic:    {topic}
- Subject:  {subject}
- Grade:    {grade}
- Board:    {board}
- Sessions: {sessions}

STUDIOS AVAILABLE FOR THIS LESSON:
{json.dumps(studios_ctx, indent=2)}

{examples_ctx}

Generate a detailed, practical lesson plan. Requirements:
- Reference SPECIFIC TOOLS by their exact names from the studio
- Describe exactly what students DO at each stage (not just what the teacher does)
- Match cognitive complexity to Grade {grade}
- If multiple sessions: break down session by session
- Be specific — avoid generic advice that could apply to any classroom

Format exactly as:

## Overview
[2-3 sentences — what students will do and achieve]

## Learning Objectives
By the end of this lesson, students will be able to:
- [objective 1 — use an action verb]
- [objective 2]
- [objective 3]

## Session Plan
[Session-by-session breakdown with timing]

## Tools & How They're Used
[Each studio tool referenced, and exactly how it's used in this lesson]

## Setup Instructions
[What the teacher prepares before students arrive]

## Assessment
[How the teacher knows objectives were met — specific and practical]
"""

    provider = get_provider()
    return provider.generate_text(system_prompt, user_prompt)


def extract_objectives(plan_text: str) -> list[str]:
    """Pull learning objectives out of a generated plan."""
    objectives = []
    in_objectives = False
    for line in plan_text.split("\\n"):
        if "Learning Objectives" in line:
            in_objectives = True
            continue
        if in_objectives:
            if line.startswith("##"):
                break
            line = line.strip().lstrip("-•* ")
            if line:
                objectives.append(line)
    return objectives


def check_api_key() -> tuple[bool, str]:
    """Verify the configured API key is set and works."""
    provider = get_provider()
    return provider.test_connection()
