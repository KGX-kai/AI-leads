from datetime import date, datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResearchInput(Input):
    region: str = Field(min_length=1, max_length=100)
    scene: str = Field(min_length=1, max_length=300)
    target: int = Field(default=10, ge=1, le=30)


class CandidateInput(Input):
    company: str = Field(min_length=1, max_length=200)
    project: str = Field(min_length=1, max_length=200)
    region: str = Field(min_length=1, max_length=100)
    address: str = Field(default="", max_length=300)
    source_url: str = Field(default="", max_length=2000)
    source_type: Literal["公开网络", "公开招标公告", "抖音", "已有关系"] = "公开网络"
    evidence: str = Field(min_length=3, max_length=4000)
    reason: str = Field(default="", max_length=1000)
    demand_evidence: str = Field(default="", max_length=2000)
    discovered_at: date = Field(default_factory=date.today)
    publisher: str = Field(default="未知", max_length=200)
    published_at: date | None = None
    location_kind: Literal["项目位置", "公司注册地址", "供应商或代理地址", "未知"] = "未知"
    project_state: str = Field(default="未知", max_length=100)
    org_phone: str = Field(default="", max_length=50)
    unknowns: list[str] = Field(default_factory=list, max_length=12)
    source_channel: str = Field(default="", max_length=50)
    bid_deadline: date | None = None

    @field_validator("source_url")
    @classmethod
    def public_url(cls, v):
        if v:
            p = urlparse(v)
            if p.scheme not in {"https", "http"} or not p.hostname or p.username or p.password:
                raise ValueError("来源链接须为不含凭证的 http(s) 地址")
        return v

    @field_validator("unknowns")
    @classmethod
    def valid_unknowns(cls, values):
        if any(not value.strip() or len(value) > 100 for value in values):
            raise ValueError("未知项须为1至100字的说明")
        return values

    @field_validator("org_phone")
    @classmethod
    def valid_org_phone(cls, value):
        if value and (sum(char.isdigit() for char in value) < 7 or any(char not in "0123456789-+() " for char in value)):
            raise ValueError("公开单位电话格式不正确")
        return value


class FollowupInput(Input):
    summary: str = Field(min_length=1, max_length=4000)
    result: Literal[
        "待跟进", "有效沟通", "无需求", "无采购权", "时间不合适", "报价未接受", "试样反馈", "已采购", "补货"
    ] = "待跟进"
    next_action: str = Field(default="", max_length=300)
    due_date: date | None = None
    minutes: int | None = Field(default=None, ge=0, le=1440)
    draft: str = Field(default="", max_length=4000)


class RequirementsInput(Input):
    version: int = Field(ge=1)
    role: str = Field(default="未知", max_length=100)
    authority: str = Field(default="未知", max_length=100)
    lamps: str = Field(default="未知", max_length=500)
    demand: str = Field(default="未知", max_length=500)
    purchase_time: str = Field(default="未知", max_length=100)
    business_mode: Literal["EMC", "买断", "两种都要", "未定"] = "未定"
    annual_power_cost: Literal["≥30万", "5–30万", "<5万", "未知"] = "未知"
    managed_projects: int | None = Field(default=None, ge=0, le=100000)
    confirmed: bool = False


class ContactInput(Input):
    name: str = Field(min_length=1, max_length=100)
    channel: str = Field(min_length=1, max_length=200)
    role: str = Field(default="未知", max_length=100)


class OfferInput(Input):
    kind: Literal["报价", "试样"]
    product: str = Field(min_length=1, max_length=300)
    quantity: int = Field(ge=1, le=1000000)
    amount_cents: int | None = Field(default=None, ge=0, le=10000000000)
    due_date: date | None = None
    feedback: str = Field(default="", max_length=2000)
    status: Literal["待确认", "已确认", "已寄样", "已收到", "已反馈", "已采购", "未接受"] = "待确认"


class InquiryInput(Input):
    platform: Literal["抖音", "企业微信", "手工"] = "抖音"
    account_id: str = Field(min_length=1, max_length=200)
    source_channel: str = Field(default="", max_length=50)
    message_id: str = Field(default="", max_length=300)
    comment_id: str = Field(default="", max_length=300)
    video_id: str = Field(default="", max_length=300)
    event_type: Literal["comment", "private_message", "manual"] = "manual"
    user_id: str = Field(default="", max_length=300)
    nickname: str = Field(default="", max_length=200)
    body: str = Field(min_length=1, max_length=8000)
    source_url: str = Field(default="", max_length=2000)
    occurred_at: datetime

    _url = field_validator("source_url")(CandidateInput.public_url.__func__)

    @field_validator("occurred_at")
    @classmethod
    def zoned(cls, value):
        if value.tzinfo is None:
            raise ValueError("时间必须包含时区，如 +08:00")
        return value


INQUIRY_SUGGESTION_FIELDS = (
    "company", "project_name", "region", "scene", "lamps", "demand", "purchase_time", "annual_power_cost",
)
BUSINESS_MODES = ("EMC", "买断", "两种都要", "未定")
POWER_COST_BANDS = ("≥30万", "5–30万", "<5万", "未知")
REJECT_REASON_CODES = {
    "other": "其他",
    "not_target": "非目标客户",
    "channel_dealer": "渠道商/批发",
    "peer_inquiry": "同行询价",
    "under_contract": "改造合同期内",
    "too_small": "需求过小",
    "no_capacity": "无支付能力",
    "duplicate": "重复",
}


class InquiryFieldsSuggestion(Input):
    fields: dict[str, str] = Field(min_length=1, max_length=len(INQUIRY_SUGGESTION_FIELDS))
    evidence: str = Field(min_length=3, max_length=2000)

    @field_validator("fields")
    @classmethod
    def supported_fields(cls, value):
        if set(value) - set(INQUIRY_SUGGESTION_FIELDS) or any(not v.strip() or len(v) > 500 for v in value.values()):
            raise ValueError("咨询建议只能填写八项已知字段，每项1至500字；未知值请省略")
        if "annual_power_cost" in value and value["annual_power_cost"] not in POWER_COST_BANDS:
            raise ValueError("年照明电费区间须为 ≥30万、5–30万、<5万 或 未知")
        return value


class QualificationInput(Input):
    fit: Literal["符合", "待核实", "不符合"] = "待核实"
    need: Literal["明确需求", "有问题但采购未定", "未知", "明确暂无计划"] = "未知"
    role: Literal["已核实采购角色", "可影响/可引荐", "未知", "明确无权限"] = "未知"
    timing: Literal["已明确日期/窗口", "未知", "明确延期"] = "未知"
    confidence: Literal["原文已核对", "待核对", "存在冲突"] = "待核对"
    priority: Literal["优先核实", "常规核实", "暂缓", "建议排除"] = "常规核实"
    evidence: str = Field(min_length=3, max_length=4000)
    tag_ids: list[str] = Field(default_factory=list, max_length=20)


class OpportunityUpdate(FollowupInput):
    stage: Literal["", "待核实", "确认需求", "报价或试样", "采购", "补货跟进", "暂缓", "关闭"] = ""
    tag_ids: list[str] = Field(default_factory=list, max_length=20)
    evidence: str = Field(default="", max_length=4000)
    business_mode: Literal["", "EMC", "买断", "两种都要", "未定"] = ""
    annual_power_cost: Literal["", "≥30万", "5–30万", "<5万", "未知"] = ""
    managed_projects: int | None = Field(default=None, ge=0, le=100000)
    bid_deadline: date | None = None
