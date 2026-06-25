"""VPC EIP tools: list/describe, associate, disassociate.

disassociate_eip is DESTRUCTIVE (cuts public network access) and uses
two-phase commit:
  Phase 1: call → returns preview + approval_id (no execution)
  Phase 2: user approves → call vpc_confirm_destructive(approval_id)
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkeip.v2 import (
    ListPublicipsRequest,
    ShowPublicipRequest,
    UpdatePublicipRequest,
    UpdatePublicipsRequestBody,
    UpdatePublicipOption,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, pending_actions, wrap_tool
from ..models import (
    AssociateEipInput,
    DescribeEipsInput,
    DisassociateEipInput,
)
from ..serializers import eip_detail, eip_summary

log = logging.getLogger("huaweicloud_mcp.services.vpc.tools.eip")


def make_eip_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    # ------------------------------------------------------------------ #
    # describe_eips  (merged: list + describe)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_describe_eips(
        eip_id: Optional[str] = None,
        public_ip_address: Optional[str] = None,
        private_ip_address: Optional[str] = None,
        enterprise_project_id: Optional[str] = None,
        limit: int = 100,
        marker: Optional[str] = None,
    ) -> dict:
        """List elastic public IPs, or fetch one EIP's detail.

        Dispatches based on ``eip_id``:

          * ``eip_id`` is None/empty → LIST mode. Returns EIPs with
            public_ip_address, status, bandwidth info, bound port_id
            and private_ip_address.
          * ``eip_id`` is set → DETAIL mode. Returns full info for one EIP.

        EIP status values: DOWN (unbound), ACTIVE (bound), FREEZED, ERROR,
        BINDING, PENDING_CREATE, PENDING_DELETE, etc.

        Args:
            eip_id: EIP UUID; omit/empty to list.
            public_ip_address: List filter — public IP address.
            private_ip_address: List filter — bound private IP address.
            enterprise_project_id: List filter — enterprise project id.
            limit: List page size, default 100.
            marker: Pagination cursor.

        Returns:
            LIST mode:   {"eips": [...], "count": N}
            DETAIL mode: {id, public_ip_address, status, bandwidth_*, ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = DescribeEipsInput(
            eip_id=eip_id, public_ip_address=public_ip_address,
            private_ip_address=private_ip_address,
            enterprise_project_id=enterprise_project_id,
            limit=limit, marker=marker,
        )
        client = get_client("eip", settings)

        if params.eip_id:
            resp = client.show_publicip(ShowPublicipRequest(publicip_id=params.eip_id))
            if resp.publicip is None:
                raise ToolError(
                    code="NOT_FOUND",
                    message=f"EIP {params.eip_id} not found",
                )
            return eip_detail(resp.publicip)

        req = ListPublicipsRequest(
            limit=params.limit, marker=params.marker,
            enterprise_project_id=params.enterprise_project_id,
        )
        if params.public_ip_address:
            req.public_ip_address = [params.public_ip_address]
        if params.private_ip_address:
            req.private_ip_address = [params.private_ip_address]

        resp = client.list_publicips(req)
        eips = [eip_summary(e) for e in (resp.publicips or [])]
        return {"eips": eips, "count": len(eips)}

    # ------------------------------------------------------------------ #
    # associate_eip
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_associate_eip(publicip_id: str, port_id: str) -> dict:
        """Bind an EIP to a resource (ECS NIC, NAT gateway, ELB, etc.).

        Executes immediately. The EIP transitions from DOWN to ACTIVE.

        Args:
            publicip_id: EIP UUID to bind.
            port_id: Port UUID of the target resource's NIC.

        Returns:
            {id, public_ip_address, status, port_id, private_ip_address, ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        params = AssociateEipInput(publicip_id=publicip_id, port_id=port_id)
        client = get_client("eip", settings)

        opt = UpdatePublicipOption(port_id=params.port_id)
        resp = client.update_publicip(
            UpdatePublicipRequest(
                publicip_id=params.publicip_id,
                body=UpdatePublicipsRequestBody(publicip=opt),
            )
        )
        return eip_detail(resp.publicip)

    # ------------------------------------------------------------------ #
    # disassociate_eip  (DESTRUCTIVE — two-phase)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_disassociate_eip(publicip_id: str, confirm: bool = False) -> dict:
        """⚠ DESTRUCTIVE: unbind an EIP from its resource.

        Disassociating an EIP immediately cuts public network access for
        the bound resource. This is a TWO-PHASE operation: returns a
        preview + approval_id. Use vpc_confirm_destructive to execute
        after user approval.

        Args:
            publicip_id: EIP UUID to unbind.
            confirm: Must be True to initiate the two-phase flow.

        Returns:
            {"status": "pending_approval", "approval_id": "...", ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "admin")

        params = DisassociateEipInput(publicip_id=publicip_id, confirm=confirm)

        if not params.confirm:
            raise ToolError(
                code="CONFIRM_REQUIRED",
                message=(
                    "Disassociating an EIP cuts public network access for the "
                    "bound resource. Set confirm=True to proceed with the "
                    "two-phase approval flow."
                ),
            )

        client = get_client("eip", settings)

        # Fetch current state for the preview.
        show_resp = client.show_publicip(
            ShowPublicipRequest(publicip_id=params.publicip_id)
        )
        current = eip_detail(show_resp.publicip) if show_resp.publicip else {}

        action_label = f"vpc_disassociate_eip(publicip_id={params.publicip_id})"

        def _execute() -> dict:
            opt = UpdatePublicipOption(port_id="")
            client.update_publicip(
                UpdatePublicipRequest(
                    publicip_id=params.publicip_id,
                    body=UpdatePublicipsRequestBody(publicip=opt),
                )
            )
            return {"disassociated": True, "publicip_id": params.publicip_id}

        approval_id = pending_actions.put(
            action_label=action_label,
            preview={
                "action": "disassociate_eip",
                "publicip_id": params.publicip_id,
                "current": current,
            },
            execute_fn=_execute,
        )
        return {
            "status": "pending_approval",
            "approval_id": approval_id,
            "action": "disassociate_eip",
            "publicip_id": params.publicip_id,
            "current": current,
            "message": (
                f"⚠ Disassociating this EIP will cut public network access "
                f"for the bound resource. Present this preview to the user "
                f"and ask for explicit approval. If approved, call "
                f"vpc_confirm_destructive(approval_id='{approval_id}')."
            ),
        }

    return {
        "vpc_describe_eips": vpc_describe_eips,
        "vpc_associate_eip": vpc_associate_eip,
        "vpc_disassociate_eip": vpc_disassociate_eip,
    }
