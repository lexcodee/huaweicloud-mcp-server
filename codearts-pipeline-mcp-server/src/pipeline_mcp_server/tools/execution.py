"""pipeline_run — start a CodeArts pipeline."""
from __future__ import annotations

import logging
from typing import List, Optional

from huaweicloudsdkcodeartspipeline.v2.model import (
    RunPipelineDTO,
    RunPipelineDTOParams,
    RunPipelineDTOParamsBuildParams,
    RunPipelineDTOSources,
    RunPipelineDTOVariables,
    RunPipelineRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ..client import get_client
from ..config import Settings, resolve_project_id
from ..errors import wrap_tool
from ..models import PipelineRunInput, RunSource, RunVariable

log = logging.getLogger("pipeline_mcp_server.tools.execution")


def _build_sources(sources: Optional[List[RunSource]]) -> Optional[list]:
    if sources is None:
        return None
    out = []
    for src in sources:
        sdk_src = RunPipelineDTOSources()
        if src.type is not None:
            sdk_src.type = src.type
        if src.params is not None:
            sdk_params = RunPipelineDTOParams()
            if src.params.git_type is not None:
                sdk_params.git_type = src.params.git_type
            if src.params.default_branch is not None:
                sdk_params.default_branch = src.params.default_branch
            if src.params.alias is not None:
                sdk_params.alias = src.params.alias
            if src.params.codehub_id is not None:
                sdk_params.codehub_id = src.params.codehub_id
            if src.params.endpoint_id is not None:
                sdk_params.endpoint_id = src.params.endpoint_id
            if src.params.git_url is not None:
                sdk_params.git_url = src.params.git_url
            if src.params.build_params is not None:
                bp = RunPipelineDTOParamsBuildParams()
                for k, v in src.params.build_params.items():
                    if hasattr(bp, k):
                        setattr(bp, k, v)
                sdk_params.build_params = bp
            sdk_src.params = sdk_params
        out.append(sdk_src)
    return out


def _build_variables(variables: Optional[List[RunVariable]]) -> Optional[list]:
    if variables is None:
        return None
    out = []
    for v in variables:
        sdk_var = RunPipelineDTOVariables()
        sdk_var.name = v.name
        sdk_var.value = v.value
        out.append(sdk_var)
    return out


def make_execution_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    @wrap_tool
    def pipeline_run(
        pipeline_id: str,
        project_id: Optional[str] = None,
        sources: Optional[list] = None,
        variables: Optional[list] = None,
        description: Optional[str] = None,
        choose_jobs: Optional[List[str]] = None,
        choose_stages: Optional[List[str]] = None,
    ) -> dict:
        """Trigger a pipeline run.

        90% of callers want to "just run it with the default config" — leave
        sources/variables/choose_jobs empty and the pipeline runs with whatever
        was configured last (default branch, default variables).

        Required:
          pipeline_id : pipeline UUID.
        Optional:
          project_id    : defaults to CODEARTS_DEFAULT_PROJECT_ID.
          sources       : list of {type, params: {git_type, default_branch,
                          alias, codehub_id, endpoint_id, git_url,
                          build_params: {target_branch, commit_id, tag}}}.
                          Use this to override the branch for one run only;
                          the pipeline's stored default_branch is unchanged.
          variables     : [{name, value}] custom run variables.
          description   : human-readable description, ≤ 512 chars.
          choose_jobs   : restrict the run to these job ids.
          choose_stages : restrict the run to these stage ids.

        Returns:
          {pipeline_run_id: "..."}

        Typical use:
          pipeline_run(pipeline_id="abc")  # default branch
          pipeline_run(pipeline_id="abc",
                       sources=[{"params": {"default_branch": "release/2.0"}}])
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        # Re-validate via Pydantic (FastMCP -> our typed model).
        normalised_sources = None
        if sources is not None:
            normalised_sources = [RunSource.model_validate(s) for s in sources]
        normalised_variables = None
        if variables is not None:
            normalised_variables = [RunVariable.model_validate(v) for v in variables]

        params = PipelineRunInput(
            pipeline_id=pipeline_id,
            project_id=project_id,
            sources=normalised_sources,
            variables=normalised_variables,
            description=description,
            choose_jobs=choose_jobs,
            choose_stages=choose_stages,
        )
        pid = resolve_project_id(settings, params.project_id)

        dto = RunPipelineDTO()
        sdk_sources = _build_sources(params.sources)
        if sdk_sources is not None:
            dto.sources = sdk_sources
        sdk_vars = _build_variables(params.variables)
        if sdk_vars is not None:
            dto.variables = sdk_vars
        if params.description is not None:
            dto.description = params.description
        if params.choose_jobs is not None:
            dto.choose_jobs = params.choose_jobs
        if params.choose_stages is not None:
            dto.choose_stages = params.choose_stages

        client = get_client(settings)
        request = RunPipelineRequest(
            project_id=pid,
            pipeline_id=params.pipeline_id,
            body=dto,
        )
        response = client.run_pipeline(request)
        d = response.to_dict() if hasattr(response, "to_dict") else {}
        run_id = d.get("pipeline_run_id")
        log.info(
            "pipeline.run pipeline_id=%s project_id=%s run_id=%s",
            params.pipeline_id, pid, run_id,
        )
        return {"pipeline_run_id": run_id}

    return {"pipeline_run": pipeline_run}
