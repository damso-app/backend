from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timezone import to_kst_date
from app.models.answer import Answer
from app.models.family import Family, FamilyStatus
from app.models.family_member import FamilyMember, FamilyMemberStatus
from app.models.user import User
from app.models.video_clip import VideoClip
from app.services.storage_service import StorageService


class ClipServiceError(Exception):
    pass


class ActiveFamilyRequiredError(ClipServiceError):
    pass


class AnswerNotFoundError(ClipServiceError):
    pass


class ClipNotReadyError(ClipServiceError):
    pass


class ClipService:
    def __init__(self, storage_service: StorageService | None = None) -> None:
        self._storage_service = storage_service or StorageService()

    def get_grid(self, db: Session, *, user: User) -> list[tuple[date, list[Answer]]]:
        membership = self._require_active_membership(db, user_id=user.id)

        answers = list(
            db.scalars(
                select(Answer)
                .where(
                    Answer.family_id == membership.family_id,
                    Answer.deleted_at.is_(None),
                )
                .order_by(Answer.created_at.desc())
            )
        )

        grouped: dict[date, list[Answer]] = defaultdict(list)
        for answer in answers:
            grouped[to_kst_date(answer.created_at)].append(answer)

        return sorted(grouped.items(), key=lambda item: item[0], reverse=True)

    def get_clip_detail(
        self,
        db: Session,
        *,
        user: User,
        answer_id: int,
    ) -> tuple[Answer, VideoClip]:
        membership = self._require_active_membership(db, user_id=user.id)

        answer = db.scalar(
            select(Answer)
            .where(
                Answer.id == answer_id,
                Answer.family_id == membership.family_id,
                Answer.deleted_at.is_(None),
            )
            .limit(1)
        )
        if answer is None:
            raise AnswerNotFoundError("Answer was not found")

        video_clip = db.scalar(select(VideoClip).where(VideoClip.answer_id == answer_id).limit(1))
        if video_clip is None:
            raise ClipNotReadyError("Clip is not ready yet")

        return answer, video_clip

    def resolve_thumbnail_url(self, answer: Answer) -> str | None:
        if answer.thumbnail_url is None:
            return None
        return self._storage_service.generate_read_url(gs_uri=answer.thumbnail_url)

    def resolve_video_url(self, video_clip: VideoClip) -> str | None:
        if video_clip.video_url is None:
            return None
        return self._storage_service.generate_read_url(gs_uri=video_clip.video_url)

    def _require_active_membership(self, db: Session, *, user_id: int) -> FamilyMember:
        membership = db.scalar(
            select(FamilyMember)
            .join(Family, Family.id == FamilyMember.family_id)
            .where(
                FamilyMember.user_id == user_id,
                FamilyMember.status == FamilyMemberStatus.ACTIVE,
                Family.status == FamilyStatus.ACTIVE,
                Family.deleted_at.is_(None),
            )
            .limit(1)
        )
        if membership is None:
            raise ActiveFamilyRequiredError("Active family is required")
        return membership
