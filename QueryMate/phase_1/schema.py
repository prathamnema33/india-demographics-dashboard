
from typing import Optional, Literal
from pydantic import BaseModel, Field


class SortDetails(BaseModel):
    field: Optional[str] = None
    order: Optional[
        Literal["ascending", "descending", "random"]
    ] = None


class FilterCondition(BaseModel):
    field: str
    operator: str
    value: Optional[str] = None


class DateFilterDetails(BaseModel):
    """Represents date-based analysis without generating SQL expressions."""

    field: str
    period: Literal[
        "year",
        "month",
        "day",
        "before",
        "after",
        "between"
    ]
    value: Optional[str] = None
    end_value: Optional[str] = None


class AggregationDetails(BaseModel):
    function: Literal[
        "COUNT",
        "SUM",
        "AVG",
        "MIN",
        "MAX"
    ]

    field: str
    alias: Optional[str] = None


class PercentageDetails(BaseModel):
    """Describes the requested percentage while leaving denominator SQL to Phase 3."""

    enabled: bool = False
    scope: Literal[
        "overall",
        "by_group",
        "within_group",
        "filtered_population"
    ] = "overall"
    denominator_field: Optional[str] = None
    denominator_group: list[str] = Field(default_factory=list)


class WindowDetails(BaseModel):
    """Reserved for future window operations; unsupported operations must not be generated."""

    function: Literal[
        "LAG",
        "LEAD",
        "RUNNING_TOTAL",
        "MOVING_AVERAGE",
        "WINDOW_PERCENTAGE"
    ]
    field: Optional[str] = None
    partition_by: list[str] = Field(default_factory=list)
    order_by: Optional[str] = None
    order: Literal["ascending", "descending"] = "ascending"


class RankingDetails(BaseModel):
    function: Literal[
        "ROW_NUMBER",
        "RANK",
        "DENSE_RANK",
        "NTILE"
    ]

    order_by: str
    order: Literal["ascending", "descending"] = "descending"

    partition_by: list[str] = Field(
        default_factory=list
    )

    buckets: Optional[int] = Field(
        default=None,
        ge=2,
        le=100
    )


class QuestionAnalysis(BaseModel):

    intent: Literal[
        "retrieve_records",
        "count_records",
        "aggregate_records",
        "rank_records",
        "clarification_required"
    ]

    entity: list[str] = Field(min_length=1)

    filters: list[FilterCondition] = Field(
        default_factory=list
    )

    aggregations: list[AggregationDetails] = Field(
        default_factory=list
    )

    group_by: list[str] = Field(
        default_factory=list
    )

    having: list[FilterCondition] = Field(
        default_factory=list
    )

    percentage: bool = False

    percentage_details: Optional[PercentageDetails] = None

    date_filters: list[DateFilterDetails] = Field(
        default_factory=list
    )

    ranking: Optional[RankingDetails] = None

    window: Optional[WindowDetails] = None

    distinct: bool = False

    sort: SortDetails = Field(
        default_factory=SortDetails
    )

    limit: Optional[int] = Field(
        default=None,
        ge=1
    )

    offset: Optional[int] = Field(
        default=None,
        ge=0
    )

    clarification_question: Optional[str] = None

    clarification_reason: Optional[
        Literal[
            "ambiguous_entity",
            "missing_sort_criteria",
            "missing_filter_value",
            "ambiguous_filter",
            "ambiguous_percentage_denominator",
            "unsupported_request",
            "insufficient_information"
        ]
    ] = None
