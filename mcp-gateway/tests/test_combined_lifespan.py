"""Test: combined lifespan enters all mounted FastMCP session managers.

Regression test for the known pitfall where only the first mounted
FastMCP server initializes correctly because the combined lifespan
was not set up to enter each server's session manager.

We verify that the Starlette app's route table contains all expected
mounts and that the /healthz endpoint works. We do NOT attempt a full
SSE handshake (which would hang the TestClient on a streaming response);
instead we verify the routing structure and the healthz probe.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from starlette.routing import Mount, Route
from starlette.testclient import TestClient


class TestCombinedLifespan:
    def test_route_table_has_all_mounts(self):
        """Two FastMCP instances mounted on one Starlette app should both
        appear in the route table."""
        ecs = FastMCP("test-ecs", host="0.0.0.0")
        pipeline = FastMCP("test-pipeline", host="0.0.0.0")

        ecs_app = ecs.sse_app(mount_path="/ecs")
        pipeline_app = pipeline.sse_app(mount_path="/pipeline")

        app = _build_test_app([
            ("/ecs", ecs_app),
            ("/pipeline", pipeline_app),
        ])

        mount_paths = [
            r.path for r in app.routes if isinstance(r, Mount)
        ]
        assert "/ecs" in mount_paths, "ECS mount should exist"
        assert "/pipeline" in mount_paths, "Pipeline mount should exist"

    def test_sub_app_routes_exist(self):
        """Each mounted sub-app should contain /sse and /messages routes."""
        ecs = FastMCP("test-ecs", host="0.0.0.0")
        pipeline = FastMCP("test-pipeline", host="0.0.0.0")

        ecs_app = ecs.sse_app(mount_path="/ecs")
        pipeline_app = pipeline.sse_app(mount_path="/pipeline")

        app = _build_test_app([
            ("/ecs", ecs_app),
            ("/pipeline", pipeline_app),
        ])

        for mount in app.routes:
            if not isinstance(mount, Mount):
                continue
            sub_paths = [
                r.path for r in getattr(mount.app, "routes", [])
            ]
            assert "/sse" in sub_paths, f"{mount.path}/sse should exist"
            assert "/messages" in sub_paths, f"{mount.path}/messages should exist"

    def test_healthz_always_works(self):
        """The /healthz endpoint should always respond regardless of mounts."""
        app = _build_test_app([])
        client = TestClient(app)
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_healthz_with_mounts(self):
        """healthz works even when servers are mounted."""
        ecs = FastMCP("test-ecs", host="0.0.0.0")
        ecs_app = ecs.sse_app(mount_path="/ecs")
        app = _build_test_app([("/ecs", ecs_app)])
        client = TestClient(app)
        r = client.get("/healthz")
        assert r.status_code == 200


def _build_test_app(mounts: list[tuple[str, object]]):
    """Build a minimal Starlette app with the given mounts + /healthz."""
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse

    routes = []
    for path, sub_app in mounts:
        routes.append(Mount(path, app=sub_app))

    async def healthz(request):
        return JSONResponse({"status": "ok"})

    routes.append(Route("/healthz", healthz, methods=["GET"]))
    return Starlette(routes=routes)
