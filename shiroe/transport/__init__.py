"""Transport adapters for Shiroe worker reachability."""

from shiroe.transport.base import ProbeResult, TailnetIdentity, TailnetPeer, TailnetStatus
from shiroe.transport.tailscale import TailscaleTransport, TransportError
from shiroe.transport.tailscale_ssh import RemoteExecutionError, execute_remote_package

__all__ = [
    "ProbeResult",
    "TailnetIdentity",
    "TailnetPeer",
    "TailnetStatus",
    "TailscaleTransport",
    "TransportError",
    "RemoteExecutionError",
    "execute_remote_package",
]
