from shiroe.policy.approvals import ApprovalStatus, scope_digest


def test_scope_digest_is_order_independent_for_dict_keys():
    assert scope_digest({"b": 2, "a": 1}) == scope_digest({"a": 1, "b": 2})


def test_scope_digest_changes_when_scope_changes():
    assert scope_digest({"files": ["a"]}) != scope_digest({"files": ["a", "b"]})


def test_approved_status_is_not_default():
    assert ApprovalStatus.pending.value == "pending"
