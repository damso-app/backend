from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.v1.answers import get_clip_service
from app.db.session import get_db
from app.models.user import User
from app.schemas.clips import ClipGridGroup, ClipGridItem, ClipGridResponse
from app.services.clip_service import ActiveFamilyRequiredError, ClipService

router = APIRouter(prefix="/clips", tags=["clips"])


@router.get("", response_model=ClipGridResponse)
def get_clip_grid(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[ClipService, Depends(get_clip_service)],
) -> ClipGridResponse:
    try:
        grouped = service.get_grid(db, user=current_user)
    except ActiveFamilyRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ClipGridResponse(
        groups=[
            ClipGridGroup(
                date=day,
                clips=[
                    ClipGridItem(
                        answerId=answer.id,
                        status=answer.status,
                        thumbnailUrl=service.resolve_thumbnail_url(answer),
                    )
                    for answer in answers
                ],
            )
            for day, answers in grouped
        ]
    )
