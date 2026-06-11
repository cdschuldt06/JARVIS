from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from jarvis.database.models import UsageLog


# Estimated USD prices per 1M tokens. Keep pricing centralized here so it is easy to update.
MODEL_PRICING_USD_PER_1M: dict[str, dict[str, float | bool]] = {
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60, "estimated": True},
    "gpt-4.1": {"input": 2.00, "output": 8.00, "estimated": True},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "estimated": True},
    "gpt-5.5": {"input": 1.00, "output": 4.00, "estimated": True},
}
DEFAULT_PRICING_USD_PER_1M = {"input": 1.00, "output": 4.00, "estimated": True}


class UsageService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def log_openai_usage(
        self,
        model: str,
        operation_type: str,
        usage: Any,
        project_id: int | None = None,
        conversation_id: str | None = None,
    ) -> UsageLog:
        input_tokens, output_tokens, total_tokens = self._tokens_from_usage(usage)
        estimated_cost = self.estimate_cost(model, input_tokens, output_tokens)
        row = UsageLog(
            model=model,
            operation_type=operation_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost=estimated_cost,
            project_id=project_id,
            conversation_id=conversation_id,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = MODEL_PRICING_USD_PER_1M.get(model, DEFAULT_PRICING_USD_PER_1M)
        input_cost = (input_tokens / 1_000_000) * float(pricing["input"])
        output_cost = (output_tokens / 1_000_000) * float(pricing["output"])
        return round(input_cost + output_cost, 8)

    def pricing_is_estimated(self, model: str) -> bool:
        return bool(MODEL_PRICING_USD_PER_1M.get(model, DEFAULT_PRICING_USD_PER_1M)["estimated"])

    def dashboard(self, project_id: int | None = None) -> dict[str, object]:
        now = datetime.utcnow()
        start_today = datetime(now.year, now.month, now.day)
        start_week = start_today - timedelta(days=start_today.weekday())
        start_month = datetime(now.year, now.month, 1)
        rows = self._rows(project_id)

        return {
            "estimated": True,
            "totals": {
                "today": self._sum_since(rows, start_today),
                "week": self._sum_since(rows, start_week),
                "month": self._sum_since(rows, start_month),
                "all_time": round(sum(row.estimated_cost for row in rows), 8),
            },
            "by_model": self._group_cost(rows, "model"),
            "by_operation": self._group_cost(rows, "operation_type"),
            "recent": rows[:25],
        }

    def _rows(self, project_id: int | None = None) -> list[UsageLog]:
        stmt = select(UsageLog)
        if project_id is not None:
            stmt = stmt.where(UsageLog.project_id == project_id)
        return self.db.scalars(stmt.order_by(UsageLog.created_at.desc())).all()

    def _sum_since(self, rows: list[UsageLog], since: datetime) -> float:
        return round(sum(row.estimated_cost for row in rows if row.created_at >= since), 8)

    def _group_cost(self, rows: list[UsageLog], field: str) -> list[dict[str, object]]:
        grouped: dict[str, dict[str, object]] = defaultdict(lambda: {"cost": 0.0, "tokens": 0, "calls": 0})
        for row in rows:
            key = str(getattr(row, field))
            grouped[key]["cost"] = round(float(grouped[key]["cost"]) + row.estimated_cost, 8)
            grouped[key]["tokens"] = int(grouped[key]["tokens"]) + row.total_tokens
            grouped[key]["calls"] = int(grouped[key]["calls"]) + 1
        return [{"name": key, **value} for key, value in sorted(grouped.items())]

    def _tokens_from_usage(self, usage: Any) -> tuple[int, int, int]:
        if usage is None:
            return 0, 0, 0
        input_tokens = self._usage_value(usage, ("prompt_tokens", "input_tokens"))
        output_tokens = self._usage_value(usage, ("completion_tokens", "output_tokens"))
        total_tokens = self._usage_value(usage, ("total_tokens",))
        if total_tokens == 0:
            total_tokens = input_tokens + output_tokens
        return input_tokens, output_tokens, total_tokens

    def _usage_value(self, usage: Any, names: tuple[str, ...]) -> int:
        for name in names:
            if isinstance(usage, dict) and name in usage:
                return int(usage[name] or 0)
            value = getattr(usage, name, None)
            if value is not None:
                return int(value or 0)
        return 0
