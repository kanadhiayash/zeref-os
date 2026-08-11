"""Operational first-party agents.

Only approval_advisor is allowed in vNext, and it writes advice rather than
authorization.
"""

from shiroe.agents.approval_advisor import ApprovalAdvice, ApprovalAdvisor

__all__ = ["ApprovalAdvice", "ApprovalAdvisor"]
