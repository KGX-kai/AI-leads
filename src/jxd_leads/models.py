from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(UTC).isoformat()


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[str] = mapped_column(String, default=now)


class Research(Record, Base):
    __tablename__ = "research"
    region: Mapped[str]
    scene: Mapped[str]
    target: Mapped[int] = mapped_column(default=10)
    status: Mapped[str] = mapped_column(default="pending")
    note: Mapped[str] = mapped_column(Text, default="")


class Candidate(Record, Base):
    __tablename__ = "candidates"
    research_id: Mapped[str | None] = mapped_column(ForeignKey("research.id"))
    company: Mapped[str]
    project: Mapped[str]
    region: Mapped[str]
    address: Mapped[str] = mapped_column(default="")
    source_url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(default="公开网络")
    evidence: Mapped[str] = mapped_column(Text)
    discovered_at: Mapped[str]
    reason: Mapped[str] = mapped_column(Text, default="")
    demand_evidence: Mapped[str] = mapped_column(Text, default="")
    identity_key: Mapped[str] = mapped_column(index=True)
    submission_key: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="pending")
    review_reason: Mapped[str] = mapped_column(Text, default="")
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    org_phone: Mapped[str] = mapped_column(default="")
    unknowns: Mapped[list] = mapped_column(JSON, default=list)
    next_review_at: Mapped[str | None]
    review_reason_code: Mapped[str] = mapped_column(default="")
    source_channel: Mapped[str] = mapped_column(default="")
    bid_deadline: Mapped[str | None]


class CandidateReviewEvent(Record, Base):
    __tablename__ = "candidate_review_events"
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    decision: Mapped[str]
    reason: Mapped[str] = mapped_column(Text, default="")
    reason_code: Mapped[str] = mapped_column(default="")
    next_review_at: Mapped[str | None]
    actor: Mapped[str] = mapped_column(default="owner")


class Company(Record, Base):
    __tablename__ = "companies"
    name: Mapped[str]
    region: Mapped[str]
    identity_key: Mapped[str] = mapped_column(unique=True)


class Project(Record, Base):
    __tablename__ = "projects"
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"))
    name: Mapped[str]
    region: Mapped[str]
    address: Mapped[str]
    identity_key: Mapped[str] = mapped_column(unique=True)
    stage: Mapped[str] = mapped_column(default="待核实")
    requirements: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(default=1)
    merged_into_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))


class Contact(Record, Base):
    __tablename__ = "contacts"
    fingerprint: Mapped[str] = mapped_column(unique=True)
    encrypted: Mapped[str] = mapped_column(Text)
    blocked: Mapped[bool] = mapped_column(default=False)


class ProjectContact(Base):
    __tablename__ = "project_contacts"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), primary_key=True)
    role: Mapped[str] = mapped_column(default="未知")


class Followup(Record, Base):
    __tablename__ = "followups"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"), index=True)
    summary: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(default="待跟进")
    minutes: Mapped[int | None]
    minutes_quality: Mapped[str] = mapped_column(default="recorded")


class Todo(Record, Base):
    __tablename__ = "todos"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"), index=True)
    action: Mapped[str]
    due_date: Mapped[str]
    status: Mapped[str] = mapped_column(default="open")


class Proposal(Record, Base):
    __tablename__ = "proposals"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    request_id: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="pending")


class Offer(Record, Base):
    __tablename__ = "offers"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"), index=True)
    kind: Mapped[str]
    product: Mapped[str]
    quantity: Mapped[int]
    amount_cents: Mapped[int | None]
    due_date: Mapped[str] = mapped_column(default="")
    feedback: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(default="待确认")


class Suppression(Record, Base):
    __tablename__ = "suppressions"
    __table_args__ = (UniqueConstraint("kind", "identity_key"),)
    kind: Mapped[str]
    identity_key: Mapped[str]
    reason: Mapped[str]


class Audit(Record, Base):
    __tablename__ = "audit"
    actor: Mapped[str]
    action: Mapped[str]
    entity_id: Mapped[str]
    detail: Mapped[str] = mapped_column(default="")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]


class KeyMetadata(Base):
    __tablename__ = "key_metadata"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(default=1)
    key_ref: Mapped[str]
    sentinel: Mapped[str]


class OperationReceipt(Record, Base):
    __tablename__ = "operation_receipts"
    __table_args__ = (UniqueConstraint("actor", "action", "request_id"),)
    actor: Mapped[str]
    action: Mapped[str]
    request_id: Mapped[str]
    payload_hash: Mapped[str]
    result: Mapped[dict] = mapped_column(JSON)


class BackupRun(Record, Base):
    __tablename__ = "backup_runs"
    status: Mapped[str]
    message: Mapped[str]
    filename: Mapped[str] = mapped_column(default="")


class Opportunity(Record, Base):
    __tablename__ = "opportunities"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str]
    kind: Mapped[str] = mapped_column(default="类型待确认")
    stage: Mapped[str] = mapped_column(default="待核实", index=True)
    requirements: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(default=1)
    historical: Mapped[bool] = mapped_column(default=False)
    stage_entered_at: Mapped[str] = mapped_column(default=now)
    bid_deadline: Mapped[str | None]
    source_channel: Mapped[str] = mapped_column(default="")


class Inquiry(Record, Base):
    __tablename__ = "inquiries"
    platform: Mapped[str]
    event_key: Mapped[str] = mapped_column(unique=True)
    payload_hash: Mapped[str]
    encrypted: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, default="")
    occurred_at: Mapped[str]
    status: Mapped[str] = mapped_column(default="new", index=True)
    intent: Mapped[str] = mapped_column(default="待判断")
    company: Mapped[str | None]
    project_name: Mapped[str | None]
    region: Mapped[str | None]
    scene: Mapped[str | None]
    lamps: Mapped[str | None]
    demand: Mapped[str | None]
    purchase_time: Mapped[str | None]
    annual_power_cost: Mapped[str | None]
    source_channel: Mapped[str] = mapped_column(default="")
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"))
    version: Mapped[int] = mapped_column(default=1)


class ReviewSuggestion(Record, Base):
    __tablename__ = "review_suggestions"
    kind: Mapped[str]
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"), index=True)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id"), index=True)
    inquiry_id: Mapped[str | None] = mapped_column(ForeignKey("inquiries.id"), index=True)
    encrypted: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="pending", index=True)
    request_id: Mapped[str] = mapped_column(unique=True)
    payload_hash: Mapped[str]
    target_version: Mapped[int | None]


class Qualification(Record, Base):
    __tablename__ = "qualifications"
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id"), unique=True)
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"), unique=True)
    dimensions: Mapped[dict] = mapped_column(JSON)
    evidence: Mapped[str] = mapped_column(Text)
    rule_version: Mapped[str] = mapped_column(default="1")
    version: Mapped[int] = mapped_column(default=1)
    confirmed_at: Mapped[str]


class SourceEvidence(Record, Base):
    __tablename__ = "source_evidence"
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    publisher: Mapped[str] = mapped_column(default="未知")
    published_at: Mapped[str | None]
    location_kind: Mapped[str] = mapped_column(default="未知")
    project_state: Mapped[str] = mapped_column(default="未知")
    status: Mapped[str] = mapped_column(default="未复核")
    note: Mapped[str] = mapped_column(Text, default="")
    verified_at: Mapped[str | None]
    actor: Mapped[str] = mapped_column(default="owner")
    source_url: Mapped[str] = mapped_column(Text, default="")
    claim: Mapped[str] = mapped_column(Text, default="")


class Tag(Record, Base):
    __tablename__ = "tags"
    name: Mapped[str] = mapped_column(unique=True)


class TagLink(Record, Base):
    __tablename__ = "tag_links"
    __table_args__ = (
        UniqueConstraint("tag_id", "candidate_id"),
        UniqueConstraint("tag_id", "project_id"),
        UniqueConstraint("tag_id", "opportunity_id"),
    )
    tag_id: Mapped[str] = mapped_column(ForeignKey("tags.id"))
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id"))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"))


class SuppressionEvent(Record, Base):
    __tablename__ = "suppression_events"
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"))
    inquiry_id: Mapped[str | None] = mapped_column(ForeignKey("inquiries.id"))
    encrypted: Mapped[str] = mapped_column(Text)
    source: Mapped[str]
    occurred_at: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending", index=True)
    review_note: Mapped[str] = mapped_column(default="")


class Notification(Record, Base):
    __tablename__ = "notifications"
    event_key: Mapped[str] = mapped_column(unique=True)
    kind: Mapped[str]
    title: Mapped[str]
    count: Mapped[int]
    target: Mapped[str] = mapped_column(default="/")
    read_at: Mapped[str | None]
    desktop_status: Mapped[str] = mapped_column(default="pending")
    desktop_attempted_at: Mapped[str | None]
    desktop_error: Mapped[str] = mapped_column(default="")


class EntityChange(Record, Base):
    __tablename__ = "entity_changes"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    merged_into_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    encrypted: Mapped[str] = mapped_column(Text)
    reason: Mapped[str]


class ProjectAlias(Record, Base):
    __tablename__ = "project_aliases"
    identity_key: Mapped[str] = mapped_column(unique=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
