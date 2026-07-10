from datetime import UTC, datetime, timedelta

import google.auth
import google.auth.credentials
from google.auth.transport.requests import Request
from google.cloud import storage

from app.core.config import Settings, get_settings


class StorageServiceError(Exception):
    pass


class StorageNotConfiguredError(StorageServiceError):
    pass


class StorageService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: storage.Client | None = None
        self._credentials: google.auth.credentials.Credentials | None = None

    @property
    def client(self) -> storage.Client:
        if self._client is None:
            self._client = storage.Client()
        return self._client

    def _access_token(self) -> str:
        if self._credentials is None:
            self._credentials, _ = google.auth.default()
        if not self._credentials.valid:
            self._credentials.refresh(Request())
        return self._credentials.token

    def generate_upload_url(
        self,
        *,
        object_path: str,
        content_type: str,
        expire_minutes: int | None = None,
    ) -> tuple[str, datetime]:
        if not self._settings.gcs_bucket_name:
            raise StorageNotConfiguredError("GCS_BUCKET_NAME is not configured")

        expire_delta = timedelta(
            minutes=expire_minutes
            if expire_minutes is not None
            else self._settings.gcs_signed_url_expire_minutes
        )
        bucket = self.client.bucket(self._settings.gcs_bucket_name)
        blob = bucket.blob(object_path)
        # V4 signed URLs need a private key. Neither user ADC nor a GCE/Cloud Run
        # metadata identity carries one, so signing goes through the IAM signBlob
        # API instead: the caller's access token authenticates the signBlob call,
        # and service_account_email names who the URL is signed as. In Cloud Run
        # that's the runtime service account signing for itself, which is why it
        # needs roles/iam.serviceAccountTokenCreator on its own identity.
        upload_url = blob.generate_signed_url(
            version="v4",
            expiration=expire_delta,
            method="PUT",
            content_type=content_type,
            service_account_email=self._settings.gcs_signer_service_account,
            access_token=self._access_token(),
        )
        expires_at = datetime.now(UTC) + expire_delta
        return upload_url, expires_at

    def generate_read_url(self, *, gs_uri: str, expire_minutes: int | None = None) -> str:
        if not self._settings.gcs_bucket_name:
            raise StorageNotConfiguredError("GCS_BUCKET_NAME is not configured")

        prefix = f"gs://{self._settings.gcs_bucket_name}/"
        if not gs_uri.startswith(prefix):
            raise StorageServiceError(f"Unexpected GCS URI for this bucket: {gs_uri}")
        object_path = gs_uri.removeprefix(prefix)

        expire_delta = timedelta(
            minutes=expire_minutes
            if expire_minutes is not None
            else self._settings.gcs_signed_url_expire_minutes
        )
        bucket = self.client.bucket(self._settings.gcs_bucket_name)
        blob = bucket.blob(object_path)
        return blob.generate_signed_url(
            version="v4",
            expiration=expire_delta,
            method="GET",
            service_account_email=self._settings.gcs_signer_service_account,
            access_token=self._access_token(),
        )

    def download_to_file(self, *, gs_uri: str, destination_path: str) -> None:
        """Download an object directly (server-side, via the GCS client
        library) rather than through a signed URL — used when this backend
        itself needs the bytes, not a caller we're delegating access to."""
        if not self._settings.gcs_bucket_name:
            raise StorageNotConfiguredError("GCS_BUCKET_NAME is not configured")

        prefix = f"gs://{self._settings.gcs_bucket_name}/"
        if not gs_uri.startswith(prefix):
            raise StorageServiceError(f"Unexpected GCS URI for this bucket: {gs_uri}")
        object_path = gs_uri.removeprefix(prefix)

        bucket = self.client.bucket(self._settings.gcs_bucket_name)
        bucket.blob(object_path).download_to_filename(destination_path)

    def upload_file(self, *, object_path: str, source_path: str, content_type: str) -> str:
        """Upload a local file directly (server-side) and return its gs:// URI."""
        if not self._settings.gcs_bucket_name:
            raise StorageNotConfiguredError("GCS_BUCKET_NAME is not configured")

        bucket = self.client.bucket(self._settings.gcs_bucket_name)
        blob = bucket.blob(object_path)
        blob.upload_from_filename(source_path, content_type=content_type)
        return f"gs://{self._settings.gcs_bucket_name}/{object_path}"
