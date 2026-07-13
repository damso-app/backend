import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from app.services.storage_service import StorageService
from app.services.thumbnail_service import ThumbnailService

_FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


class FakeAnswer(SimpleNamespace):
    id: int
    family_id: int
    question_send_id: int
    video_origin_url: str
    thumbnail_url: str | None = None


class FakeStorageService(StorageService):
    """Records what was uploaded and serves a fixed local file as the
    "download" for any gs:// URI, so tests don't touch real GCS."""

    def __init__(self, *, source_video_path: str) -> None:  # no super().__init__
        self._source_video_path = source_video_path
        self.uploaded: dict[str, str] = {}

    def download_to_file(self, *, gs_uri: str, destination_path: str) -> None:
        Path(destination_path).write_bytes(Path(self._source_video_path).read_bytes())

    def upload_file(self, *, object_path: str, source_path: str, content_type: str) -> str:
        self.uploaded[object_path] = content_type
        return f"gs://test-bucket/{object_path}"


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    """A tiny synthetic 2-second video generated with ffmpeg itself, so the
    fixture doesn't need a committed binary file."""
    video_path = tmp_path / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x64:d=2",
            str(video_path),
        ],
        check=True,
        capture_output=True,
    )
    return video_path


@pytest.mark.skipif(not _FFMPEG_AVAILABLE, reason="ffmpeg not installed")
def test_generate_thumbnail_happy_path(sample_video: Path) -> None:
    storage = FakeStorageService(source_video_path=str(sample_video))
    service = ThumbnailService(storage_service=storage)
    answer = FakeAnswer(
        id=1,
        family_id=2,
        question_send_id=3,
        video_origin_url="gs://test-bucket/answers/2/3/original.mp4",
        thumbnail_url=None,
    )
    db = mock.MagicMock()

    service.generate_thumbnail(db, answer=answer)

    assert answer.thumbnail_url == "gs://test-bucket/answers/2/3/thumbnail.jpg"
    assert "answers/2/3/thumbnail.jpg" in storage.uploaded
    assert storage.uploaded["answers/2/3/thumbnail.jpg"] == "image/jpeg"
    db.commit.assert_called_once()


@pytest.mark.skipif(not _FFMPEG_AVAILABLE, reason="ffmpeg not installed")
def test_generate_thumbnail_leaves_url_null_on_ffmpeg_failure(tmp_path: Path) -> None:
    """A corrupt/empty "video" makes ffmpeg fail — thumbnail_url must stay
    null and the failure must not raise (this runs as a fire-and-forget
    background task, an exception here must never propagate)."""
    broken_video = tmp_path / "broken.mp4"
    broken_video.write_bytes(b"not a real video")

    storage = FakeStorageService(source_video_path=str(broken_video))
    service = ThumbnailService(storage_service=storage)
    answer = FakeAnswer(
        id=1,
        family_id=2,
        question_send_id=3,
        video_origin_url="gs://test-bucket/answers/2/3/original.mp4",
        thumbnail_url=None,
    )
    db = mock.MagicMock()

    service.generate_thumbnail(db, answer=answer)

    assert answer.thumbnail_url is None
    assert storage.uploaded == {}
    db.commit.assert_not_called()


def test_generate_thumbnail_swallows_storage_download_failure() -> None:
    """A storage-layer failure (e.g. GCS unreachable, object missing) must
    also be swallowed, not just ffmpeg failures."""

    class FailingStorageService(StorageService):
        def __init__(self) -> None:  # no super().__init__
            pass

        def download_to_file(self, *, gs_uri: str, destination_path: str) -> None:
            raise RuntimeError("simulated GCS outage")

    service = ThumbnailService(storage_service=FailingStorageService())
    answer = FakeAnswer(
        id=1,
        family_id=2,
        question_send_id=3,
        video_origin_url="gs://test-bucket/answers/2/3/original.mp4",
        thumbnail_url=None,
    )
    db = mock.MagicMock()

    service.generate_thumbnail(db, answer=answer)

    assert answer.thumbnail_url is None
    db.commit.assert_not_called()
