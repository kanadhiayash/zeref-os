"""Runtime enforcement for the documentary policy layer.

PRIVACY.md and SHARING_POLICY.md are typed runtime inputs. Network and
filesystem authorization uses the canonical JSON policy stack under
.shiroe/policy/.
"""
from shiroe.security.policy import (
    SecurityPolicy,
    NetworkDeniedError,
    ConnectorDisabledError,
    load_policy,
    require_connector,
    require_network,
)

__all__ = [
    "SecurityPolicy",
    "NetworkDeniedError",
    "ConnectorDisabledError",
    "load_policy",
    "require_connector",
    "require_network",
]
