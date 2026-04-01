"""
StudioMap — Data Models
========================
Pydantic models for all data structures.
These are the single source of truth for what a Studio and Plan look like.
Validation happens automatically on load — bad data raises clear errors.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any
from datetime import datetime
import uuid


# ══════════════════════════════════════════════════════════════════════════════
# STUDIO MODELS
# ══════════════════════════════════════════════════════════════════════════════

class Tool(BaseModel):
    """A physical tool or installation in a studio."""
    model_config = {"extra": "ignore"}  # ignore any LLM fields not in schema
    name:        Optional[str]  = ""
    description: Optional[str]  = ""
    quantity:    Optional[int]  = 1
    dimensions:  Optional[str]  = ""
    interaction: Optional[str]  = ""     # how students physically use this
    movable:     bool = False
    images:      list[str] = []   # relative paths

    @field_validator("name", "description", "dimensions", "interaction", mode="before")
    @classmethod
    def handle_none(cls, v: Any) -> Any:
        return v if v is not None else ""


class Affordances(BaseModel):
    """
    What the space physically enables — not just what's in it.
    This is the most important field for AI matching quality.
    The summary field is what gets embedded into ChromaDB.
    """
    model_config = {"extra": "ignore"}  # ignore any LLM fields not in schema
    individual_work:  bool = False
    pair_work:        bool = False
    group_work:       bool = False
    movement:         bool = False   # students can move around
    digital_practice: bool = False
    physical_making:  bool = False   # building, crafting, constructing
    presentation:     bool = False   # students can present to class
    self_assessment:  bool = False   # rotation/quiz formats
    max_students:     Optional[int] = None
    summary: str = ""   # plain English — focus on what students CAN DO here


class CourseworkMapping(BaseModel):
    """A sample teaching idea for this studio — the training signal for the AI."""
    topic:          Optional[str] = ""
    subject:        Optional[str] = ""
    grades:         list[str] = []
    sessions:       Optional[int] = 1
    teaching_plan:  Optional[str] = ""
    other_studios:  list[str] = []   # other studios involved
    teacher_notes:  Optional[str] = ""
    rating:         Optional[int] = None    # 1-5, filled in after use
    use_count:      int = 0
    added_by:       str = ""
    added_date:     str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    @field_validator("topic", "subject", "teaching_plan", "teacher_notes", mode="before")
    @classmethod
    def handle_none(cls, v: Any) -> Any:
        return v if v is not None else ""


class StudioProfile(BaseModel):
    """Complete profile for a single studio."""
    model_config = {"extra": "ignore"}  # ignore any LLM fields not in schema
    studio_id:    str = Field(default_factory=lambda: f"S{str(uuid.uuid4())[:4].upper()}")
    name:         Optional[str] = ""
    tagline:      Optional[str] = ""
    description:  Optional[str] = ""
    affordances:  Affordances = Field(default_factory=Affordances)
    tools:        list[Tool] = []
    grades:       list[str] = []
    subjects:     list[str] = []
    board:        str = "Both"
    area_sqft:    Optional[int] = None
    capacity:     Optional[int] = None
    lighting:     Optional[str] = ""
    ventilation:  Optional[str] = ""
    source_pdf:   str = ""    # relative path to original PDF
    images:       list[str] = []
    coursework:   list[CourseworkMapping] = []
    raw_notes:    Optional[str] = ""    # extra observations from AI (photos, diagrams, etc.)
    validated:    bool = False
    reviewed_by:  str = ""
    reviewed_date: Optional[str] = None
    created_date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    @field_validator("name", "tagline", "description", "lighting", "ventilation", "raw_notes", mode="before")
    @classmethod
    def handle_none(cls, v: Any) -> Any:
        return v if v is not None else ""

    # Drive sync metadata — ignored by app logic, used by storage layer
    _drive_file_id:   str = ""
    _drive_filename:  str = ""

    def filename(self) -> str:
        """Generate a safe filename from studio name."""
        name = self.name or "unnamed_studio"
        safe = name.lower().strip().replace(" ", "_")
        safe = "".join(c for c in safe if c.isalnum() or c == "_")
        return f"{safe}.json"

    def grade_label(self) -> str:
        if not self.grades:
            return "All grades"
        return f"Grade {', '.join(sorted(self.grades, key=lambda g: int(g)))}"


# ══════════════════════════════════════════════════════════════════════════════
# LESSON PLAN MODEL
# ══════════════════════════════════════════════════════════════════════════════

class LessonPlan(BaseModel):
    """A generated (and optionally saved) lesson plan."""
    plan_id:      str = Field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:8]}")
    topic:        str
    subject:      str
    grade:        str
    board:        str = "CBSE"
    sessions:     int = 1
    studio_ids:   list[str] = []      # studio IDs used
    studio_names: list[str] = []      # studio display names
    plan_text:    str = ""            # full markdown plan from Claude
    tools_used:   list[str] = []      # specific tools referenced
    objectives:   list[str] = []      # extracted learning objectives
    generated_date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    generated_by:   str = ""
    created_by:     str = ""              # email of the teacher who generated this plan
    ratings:        dict[str, int] = {}   # email → 1-5 stars (per-user)
    rating_notes:   dict[str, str] = {}   # email → note text  (per-user)
    saved:          bool = False

    def user_rating(self, email: str) -> Optional[int]:
        return self.ratings.get(email)

    def average_rating(self) -> Optional[float]:
        if not self.ratings:
            return None
        return sum(self.ratings.values()) / len(self.ratings)

    def set_rating(self, email: str, stars: int, note: str = ""):
        self.ratings[email]      = stars
        self.rating_notes[email] = note

    def filename(self) -> str:
        return f"{self.plan_id}.json"

    def display_title(self) -> str:
        return f"{self.topic} · Grade {self.grade} · {self.subject}"
