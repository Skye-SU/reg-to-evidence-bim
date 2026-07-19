"""Typed domain objects for the reg-to-check pipeline.

Everything that flows through the pipeline is an explicit, validated object so that
`None` never has to mean three different things at once. States and reason codes are
enums, not free strings.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SourceMode(str, Enum):
    """Where a value actually came from. Never blur these together."""

    PINNED_IFC = "pinned_ifc"          # read from the exact pinned IFC fixture
    CONTROLLED_IFC = "controlled_ifc"  # read from a controlled IFC fixture
    CONSTRUCTED_CASE = "constructed_case"  # hand-authored value, not from any model
    EXTERNAL_PRECOMPUTED = "external_precomputed"  # supplied scalar, not computed here


class Applicability(str, Enum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"
    NOT_APPLICABLE = "not_applicable"


class ReasonCode(str, Enum):
    """Only codes this pipeline can actually detect or fault-inject."""

    SOURCE_INTEGRITY_FAILURE = "SOURCE_INTEGRITY_FAILURE"
    RULE_SCOPE_UNKNOWN = "RULE_SCOPE_UNKNOWN"
    MISSING_DATA = "MISSING_DATA"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    DEFINITION_MISMATCH = "DEFINITION_MISMATCH"
    RELATIONSHIP_UNVERIFIED = "RELATIONSHIP_UNVERIFIED"  # window cannot be tied to space (R1)


class SourceRecord(BaseModel):
    """One clause as registered in the independent source manifest."""

    source_id: str
    clause_id: str
    title: str
    version_date: str
    retrieved_date: str
    url: str
    excerpt: str
    excerpt_sha256: str


class RuleObject(BaseModel):
    """Normalized rule. References the manifest by source_id + source_span_hash;
    it never carries its own copy of the legal text to self-verify against."""

    rule_id: str
    applies_to_legal_use: list[str]
    check_type: str
    operands: list[str]
    threshold: float
    unit_si: str
    evidence_required: list[str]
    source_id: str
    source_clause_id: str
    source_span_hash: str
    simplification_note: str
    rule_schema_version: str = "1.0"


class Provenance(BaseModel):
    source_mode: SourceMode
    raw_value: float | None = None
    raw_unit: str | None = None
    value_si: float | None = None
    unit_si: str | None = None
    model_sha256: str | None = None
    ifc_schema: str | None = None
    element_global_id: str | None = None
    property_path: str | None = None
    extraction_method: str | None = None
    data_quality_flags: list[str] = Field(default_factory=list)


class Observation(BaseModel):
    """A single value read (or constructed) for one element, with provenance."""

    field_name: str
    provenance: Provenance


class CheckInput(BaseModel):
    """What the checker needs for one (element) before it can judge a rule."""

    element_id: str
    element_name: str | None = None
    element_source_mode: SourceMode
    legal_space_use: str | None = None
    legal_space_use_source_mode: SourceMode | None = None
    observations: dict[str, Observation] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    data_quality_flags: list[str] = Field(default_factory=list)
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    review_details: list[str] = Field(default_factory=list)


class EvidenceRecord(BaseModel):
    """Machine-readable record per (rule_id, element_id). Capability sample format;
    not a claim of conformance to any regulatory standard."""

    element_id: str
    element_name: str | None = None
    rule_id: str
    applicability: Applicability
    status: CheckStatus
    observed: dict = Field(default_factory=dict)
    required: dict = Field(default_factory=dict)
    gap: float | None = None
    source_clause_id: str
    source_id: str
    source_span_hash: str
    source_integrity_verified: bool
    input_provenance: dict = Field(default_factory=dict)
    # Observations that were SEEN but deliberately NOT used for judgment (e.g. a
    # slab-to-slab height that is not substitutable). Kept for a complete audit trail;
    # never fed into a pass/fail decision.
    rejected_observations: list[dict] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)
    data_quality_flags: list[str] = Field(default_factory=list)
    human_review_flag: bool = False
    decision_path: list[str] = Field(default_factory=list)
    simplification_note: str | None = None
    rule_schema_version: str = "1.0"
    run_id: str = "demo-r2-001"
