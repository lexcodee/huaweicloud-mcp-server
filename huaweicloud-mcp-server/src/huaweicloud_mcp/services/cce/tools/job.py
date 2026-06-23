"""CCE async-job inspection tool."""
from __future__ import annotations

import logging

from huaweicloudsdkcce.v3 import ShowJobRequest
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import wrap_tool
from ..models import GetJobInput
from ..serializers import job_summary

log = logging.getLogger("huaweicloud_mcp.services.cce.tools.job")


def make_job_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    @wrap_tool
    def cce_get_job(job_id: str) -> dict:
        """Poll the status of an asynchronous CCE job.

        Most CCE write operations (cluster create/delete/upgrade, node
        pool scale, node create/remove) are asynchronous and return a
        ``job_id``. Use this tool to learn whether the underlying work
        has completed.

        Polling guidance: 5–10 seconds between calls; give up after about
        60 polls (≈10 minutes) for long-running ops like cluster create.
        ``phase`` is one of:

          * ``Initializing`` / ``Running``  — in progress
          * ``Success``                     — completed
          * ``Failed``                      — completed with error
                                              (``reason`` is populated)

        Args:
            job_id: Job id from a previous async CCE call.

        Returns:
            {
              "job_id", "type", "cluster_id", "resource_id", "resource_name",
              "phase", "reason", "created", "updated",
              "sub_jobs_total", "sub_jobs": [...]
            }
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = GetJobInput(job_id=job_id)
        client = get_client("cce", settings)
        resp = client.show_job(ShowJobRequest(job_id=params.job_id))
        return job_summary(resp)

    return {"cce_get_job": cce_get_job}
