"""Async job tracking tools."""
from __future__ import annotations

import logging

from huaweicloudsdkecs.v2 import ShowJobRequest
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import wrap_tool
from ..models import GetJobInput
from ..serializers import job_summary

log = logging.getLogger("huaweicloud_mcp.services.ecs.tools.job")


def make_job_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    @wrap_tool
    def ecs_get_job_status(job_id: str) -> dict:
        """Poll the status of an asynchronous ECS job.

        Most write tools (start, stop, reboot, delete, resize) return a job_id.
        Use this tool to learn whether the underlying operation has finished.

        Polling guidance: 3–5 seconds between calls, give up after ~60 polls
        (5 minutes) to avoid runaway loops. Return value status is one of:
          - INIT      : queued
          - RUNNING   : in progress
          - SUCCESS   : completed successfully
          - FAIL      : completed with error (see error_code/fail_reason)

        Args:
            job_id: Job id from a previous async tool call.

        Returns:
            {
              "job_id", "job_type", "status", "begin_time", "end_time",
              "error_code", "fail_reason", "message", "code",
              "sub_jobs_total", "sub_jobs": [...]
            }.
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = GetJobInput(job_id=job_id)
        client = get_client("ecs", settings)
        resp = client.show_job(ShowJobRequest(job_id=params.job_id))
        return job_summary(resp)

    return {"ecs_get_job_status": ecs_get_job_status}