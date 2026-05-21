from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from andino.config import AgentConfig, ObservabilityConfig
from andino.service import AgentService


@pytest.fixture
def base_config() -> AgentConfig:
    return AgentConfig(name="test-agent")


class TestSetupTelemetry:
    def test_otlp_exporter_when_enabled(self, base_config: AgentConfig):
        base_config.observability = ObservabilityConfig(enabled=True, otlp=True)
        service = AgentService(base_config)
        with patch("strands.telemetry.StrandsTelemetry") as mock_telemetry:
            instance = MagicMock()
            mock_telemetry.return_value = instance
            service._setup_telemetry()
        instance.setup_otlp_exporter.assert_called_once()
        instance.setup_console_exporter.assert_not_called()
        instance.setup_meter.assert_not_called()

    def test_console_and_metrics_chained(self, base_config: AgentConfig):
        base_config.observability = ObservabilityConfig(
            enabled=True, otlp=True, console=True, metrics=True
        )
        service = AgentService(base_config)
        with patch("strands.telemetry.StrandsTelemetry") as mock_telemetry:
            instance = MagicMock()
            mock_telemetry.return_value = instance
            service._setup_telemetry()
        instance.setup_console_exporter.assert_called_once()
        instance.setup_otlp_exporter.assert_called_once()
        instance.setup_meter.assert_called_once_with(
            enable_console_exporter=True, enable_otlp_exporter=True
        )

    def test_service_name_defaults_to_agent_name(self, base_config: AgentConfig):
        base_config.observability = ObservabilityConfig(enabled=True)
        service = AgentService(base_config)
        prev = os.environ.pop("OTEL_SERVICE_NAME", None)
        try:
            with patch("strands.telemetry.StrandsTelemetry"):
                service._setup_telemetry()
            assert os.environ["OTEL_SERVICE_NAME"] == "test-agent"
        finally:
            os.environ.pop("OTEL_SERVICE_NAME", None)
            if prev is not None:
                os.environ["OTEL_SERVICE_NAME"] = prev

    def test_service_name_override(self, base_config: AgentConfig):
        base_config.observability = ObservabilityConfig(enabled=True, service_name="custom-svc")
        service = AgentService(base_config)
        prev = os.environ.pop("OTEL_SERVICE_NAME", None)
        try:
            with patch("strands.telemetry.StrandsTelemetry"):
                service._setup_telemetry()
            assert os.environ["OTEL_SERVICE_NAME"] == "custom-svc"
        finally:
            os.environ.pop("OTEL_SERVICE_NAME", None)
            if prev is not None:
                os.environ["OTEL_SERVICE_NAME"] = prev


class TestAgentServiceFromYaml:
    def test_from_yaml(self, tmp_path):
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text("name: from-yaml-test\n", encoding="utf-8")
        service = AgentService.from_yaml(str(yaml_file))
        assert service.config.name == "from-yaml-test"
