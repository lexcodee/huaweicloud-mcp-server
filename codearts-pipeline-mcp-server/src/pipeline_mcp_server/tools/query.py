"""Read-only query tools: pipeline_list, pipeline_get_detail."""
from __future__ import annotations

import logging
from typing import List, Optional

from huaweicloudsdkcodeartspipeline.v2.model import (
    ListPipelineQuery,
    ListPipelinesRequest,
    ShowPipelineDetailRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ..client import get_client
from ..config import Settings, resolve_project_id
from ..errors import wrap_tool
from ..models import PipelineGetDetailInput, PipelineListInput
from ..serializers import pipeline_detail, pipeline_list_response

log = logging.getLogger("pipeline_mcp_server.tools.query")


def make_query_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    @wrap_tool
    def pipeline_list(
        project_id: Optional[str] = None,
        name: Optional[str] = None,
        status: Optional[List[str]] = None,
        component_id: Optional[str] = None,
        creator_id: Optional[str] = None,
        creator_ids: Optional[List[str]] = None,
        executor_ids: Optional[List[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        offset: int = 0,
        limit: int = 20,
        sort_key: Optional[str] = None,
        sort_dir: Optional[str] = None,
        is_banned: Optional[bool] = None,
    ) -> dict:
        """List CodeArts pipelines and their latest-run status.

        Use this tool to answer "show me pipelines in project X" or "did the
        last run of pipeline Y succeed?". The `latest_run` field on each
        item carries `status` and `stage_status_list` — i.e. the per-stage
        pass/fail snapshot.

        Required: none (uses CODEARTS_DEFAULT_PROJECT_ID when omitted).
        Optional filters:
          name           : fuzzy match on pipeline name
          status         : list, allowed values COMPLETED / RUNNING / FAILED /
                           CANCELED / PAUSED / SUSPEND / IGNORED
          component_id   : filter by component
          creator_id     : single creator id (equality)
          creator_ids    : list of creator ids (any-of)
          executor_ids   : list of executor ids (any-of)
          start_time/end_time : ISO-8601 strings, server-side time range
          offset/limit   : 0-based pagination, limit defaults to 20 (max 100)
          sort_key       : name / create_time / update_time
          sort_dir       : asc / desc
          is_banned      : true to include disabled pipelines

        Returns:
          {offset, limit, total, pipelines: [
              {pipeline_id, name, is_publish, create_time,
               latest_run: {status, stage_status_list, start_time, end_time, ...}}
          ]}

        To operate on pipelines in a different project, pass project_id
        explicitly.
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")
        params = PipelineListInput(
            project_id=project_id,
            name=name,
            status=status,
            component_id=component_id,
            creator_id=creator_id,
            creator_ids=creator_ids,
            executor_ids=executor_ids,
            start_time=start_time,
            end_time=end_time,
            offset=offset,
            limit=limit,
            sort_key=sort_key,
            sort_dir=sort_dir,
            is_banned=is_banned,
        )
        pid = resolve_project_id(settings, params.project_id)

        query = ListPipelineQuery()
        query.project_id = pid
        if params.name is not None:
            query.name = params.name
        if params.status is not None:
            query.status = params.status
        if params.component_id is not None:
            query.component_id = params.component_id
        if params.creator_id is not None:
            query.creator_id = params.creator_id
        if params.creator_ids is not None:
            query.creator_ids = params.creator_ids
        if params.executor_ids is not None:
            query.executor_ids = params.executor_ids
        if params.start_time is not None:
            query.start_time = params.start_time
        if params.end_time is not None:
            query.end_time = params.end_time
        query.offset = params.offset
        query.limit = params.limit
        if params.sort_key is not None:
            query.sort_key = params.sort_key
        if params.sort_dir is not None:
            query.sort_dir = params.sort_dir
        if params.is_banned is not None:
            query.is_banned = params.is_banned

        client = get_client(settings)
        request = ListPipelinesRequest(project_id=pid, body=query)
        response = client.list_pipelines(request)
        return pipeline_list_response(response)

    @wrap_tool
    def pipeline_get_detail(
        pipeline_id: str,
        project_id: Optional[str] = None,
    ) -> dict:
        """Return the full configuration of a single pipeline.

        Useful for inspecting the default branch, schedules, triggers,
        variables, and the parsed `definition` (stages / jobs / pre-hooks).

        Required:
          pipeline_id : pipeline UUID.
        Optional:
          project_id  : CodeArts project UUID. Defaults to
                        CODEARTS_DEFAULT_PROJECT_ID.

        Returns:
          {id, name, description, is_publish, sources, variables, schedules,
           triggers, definition: { stages: [...] }, ...}

        NOTE: the API returns `definition` as a JSON-encoded string. This
        tool decodes it for you — the returned `definition` is a real
        object you can index into directly.
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = PipelineGetDetailInput(
            project_id=project_id,
            pipeline_id=pipeline_id,
        )
        pid = resolve_project_id(settings, params.project_id)
        client = get_client(settings)
        request = ShowPipelineDetailRequest(project_id=pid, pipeline_id=params.pipeline_id)
        response = client.show_pipeline_detail(request)
        return pipeline_detail(response)

    return {
        "pipeline_list": pipeline_list,
        "pipeline_get_detail": pipeline_get_detail,
    }
