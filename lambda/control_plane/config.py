from __future__ import annotations

import json
from functools import cache
from typing import Any, List

import boto3
from botocore.config import Config as BotoConfig
from pydantic_settings import BaseSettings, SettingsConfigDict, EnvSettingsSource
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Environment configuration loaded from variables."""

    cluster: str = Field(..., env="CLUSTER")
    subnets: List[str] = Field(..., env="SUBNETS")
    security_groups: List[str] = Field(..., env="SECURITY_GROUPS")
    github_pat: str = Field(..., env="GITHUB_PAT")
    github_repo: str = Field(..., env="GITHUB_REPO")
    github_webhook_secret: str = Field(..., env="GITHUB_WEBHOOK_SECRET")
    runner_table: str = Field(..., env="RUNNER_TABLE")
    class_sizes_param: str | None = Field(None, env="CLASS_SIZES_PARAM")
    execution_role_arn: str = Field(..., env="EXECUTION_ROLE_ARN")
    task_role_arn: str = Field(..., env="TASK_ROLE_ARN")
    log_group_name: str = Field(..., env="LOG_GROUP_NAME")
    event_bus_name: str = Field(..., env="EVENT_BUS_NAME")
    runner_repository_url: str = Field(..., env="RUNNER_REPOSITORY_URL")
    runner_image_tag: str = Field("latest", env="RUNNER_IMAGE_TAG")
    image_build_project: str | None = Field(None, env="IMAGE_BUILD_PROJECT")

    @field_validator("subnets", "security_groups", mode="before")
    @classmethod
    def _split_csv(cls, v: str | List[str]) -> List[str]:
        if isinstance(v, str):
            return [p for p in v.split(",") if p]
        return v

    model_config = SettingsConfigDict(case_sensitive=False, env_file=".env", enable_decoding=False)

_session = boto3.Session()
_retry_cfg = BotoConfig(retries={"max_attempts": 5, "mode": "standard"})


def client(service: str):
    """Create a boto3 client with retry config."""
    return _session.client(service, config=_retry_cfg)


def resource(service: str):
    """Create a boto3 resource with retry config."""
    return _session.resource(service, config=_retry_cfg)


@cache
def get_class_sizes(class_sizes_param: str | None) -> dict[str, Any]:
    """Fetch and cache runner class size definitions from SSM."""
    if not class_sizes_param:
        return {}
    ssm_client = client("ssm")
    resp = ssm_client.get_parameter(Name=class_sizes_param)
    return json.loads(resp["Parameter"]["Value"])
