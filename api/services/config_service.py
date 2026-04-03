"""Config service for effective config endpoint."""

from __future__ import annotations

from api.schemas import EffectiveConfig
from nightfall_photo_ingress.config import AppConfig


class ConfigService:
    """Provides configuration data."""

    @staticmethod
    def get_effective_config(app_config: AppConfig) -> EffectiveConfig:
        """Return effective config with sensitive values redacted."""

        return EffectiveConfig(
            config_version=app_config.core.config_version,
            poll_interval_minutes=app_config.core.poll_interval_minutes,
            registry_path=str(app_config.core.registry_path),
            staging_path=str(app_config.core.staging_path),
            pending_path=str(app_config.core.pending_path),
            accepted_path=str(app_config.core.accepted_path),
            rejected_path=str(app_config.core.rejected_path),
            trash_path=str(app_config.core.trash_path),
            storage_template=app_config.core.storage_template,
            accepted_storage_template=app_config.core.accepted_storage_template,
            verify_sha256_on_first_download=app_config.core.verify_sha256_on_first_download,
            max_downloads_per_poll=app_config.core.max_downloads_per_poll,
            max_poll_runtime_seconds=app_config.core.max_poll_runtime_seconds,
            kpi_thresholds={
                "pending_warning": 100,
                "pending_error": 500,
                "disk_warning_percent": 80,
                "disk_error_percent": 95,
            },
            api_token="[redacted]",
        )
