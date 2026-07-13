from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import require_internal_trigger
from app.db.session import get_db
from app.services.reconciliation_service import ReconciliationService

router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    dependencies=[Depends(require_internal_trigger)],
)


def get_reconciliation_service() -> ReconciliationService:
    return ReconciliationService()


class ReconciliationSummaryResponse(BaseModel):
    checked: int
    completed: int
    failed: int
    skipped: int
    redispatched: int


@router.post(
    "/answers/reconcile",
    response_model=ReconciliationSummaryResponse,
    summary="유실된 콜백 복구 (스케줄러 트리거용)",
    description=(
        "processing 상태로 일정 시간 이상 머물러 있는 answers를 찾아 AI 서버에 job 상태를 "
        "직접 폴링해서 콜백 유실을 복구한다. submitted 상태로 일정 시간 이상 머물러 있는 "
        "answers(AI 서버로의 최초 dispatch 자체가 실패해 processing으로도 못 넘어간 경우)는 "
        "dispatch를 재시도한다. Cloud Scheduler 등 외부 스케줄러가 주기적으로 호출하도록 "
        "설계됐다. INTERNAL_TRIGGER_TOKEN으로 인증한다."
    ),
)
def reconcile_stuck_answers(
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
) -> ReconciliationSummaryResponse:
    summary = service.reconcile_stuck_answers(db)
    return ReconciliationSummaryResponse(
        checked=summary.checked,
        completed=summary.completed,
        failed=summary.failed,
        skipped=summary.skipped,
        redispatched=summary.redispatched,
    )
