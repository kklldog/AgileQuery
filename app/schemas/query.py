from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    database_id: str
    question: str = Field(min_length=1)
    space_id: str | None = None
    max_rows: int | None = Field(default=None, ge=1, le=1000)


class LLMTrace(BaseModel):
    stage: str
    prompt: str
    response: str


class QueryResponse(BaseModel):
    database_id: str
    space_id: str
    sql: str
    status: str
    summary: str
    table_markdown: str
    row_count: int
    is_truncated: bool
    diagnostics: list[str]
    llm_traces: list[LLMTrace] = Field(default_factory=list)
