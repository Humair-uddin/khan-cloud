from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.services import operations_dashboard_service as svc


NOW = datetime.now(UTC)


class FakeScalars:
    def __init__(self, items):
        self.items = items
    def unique(self):
        return self
    def __iter__(self):
        return iter(self.items)


class FakeDB:
    def __init__(self, profiles, nodes, cases):
        self.profiles = profiles
        self.nodes = nodes
        self.cases = cases
    def scalars(self, statement):
        text = str(statement)
        if "FROM deployment_profiles" in text:
            return FakeScalars(self.profiles)
        if "FROM nodes" in text:
            return FakeScalars(self.nodes)
        if "FROM support_cases" in text:
            return FakeScalars(self.cases)
        raise AssertionError(text)


def user():
    return SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])


def profile(org_id, name="Deployment"):
    return SimpleNamespace(
        id=uuid4(), organization_id=org_id, name=name, purpose="gpu_compute"
    )


def node(profile_id, *, name="gpu-1", age=0, install="success", category=""):
    return SimpleNamespace(
        id=uuid4(), deployment_profile_id=profile_id, name=name,
        lifecycle_state="approved", connectivity_state="online",
        last_seen_at=NOW - timedelta(seconds=age),
        installation_status=install, installation_stage="health_checks",
        installation_failure_category=category,
        installation_message="sanitized",
        installation_updated_at=NOW,
    )


def support_case(org_id, profile_id, *, priority="normal", status="open"):
    return SimpleNamespace(
        id=uuid4(), organization_id=org_id, deployment_profile_id=profile_id,
        node_id=None, priority=priority, status=status, category="installation",
        summary="Deployment needs help", created_at=NOW,
    )


def patch_visibility(monkeypatch, org_id, allowed_profiles):
    monkeypatch.setattr(
        svc, "visible_organizations",
        lambda db, actor: [SimpleNamespace(id=org_id, name="Customer")],
    )
    monkeypatch.setattr(
        svc, "user_can_access_deployment_profile",
        lambda db, actor, p: p.id in allowed_profiles,
    )
    monkeypatch.setattr(
        svc, "user_can_access_organization",
        lambda db, actor, oid: oid == org_id,
    )


def test_dashboard_aggregates_visible_deployment(monkeypatch):
    org_id = uuid4(); p = profile(org_id)
    patch_visibility(monkeypatch, org_id, {p.id})
    db = FakeDB([p], [node(p.id)], [])
    result = svc.build_operations_dashboard(db, user())
    assert result.counts.organizations == 1
    assert result.counts.deployments == 1
    assert result.counts.nodes == 1
    assert result.counts.online_nodes == 1
    assert result.counts.successful_nodes == 1
    assert result.deployments[0].health == "healthy"


def test_dashboard_excludes_inaccessible_deployments(monkeypatch):
    org_id = uuid4(); allowed = profile(org_id, "Allowed"); hidden = profile(uuid4(), "Hidden")
    patch_visibility(monkeypatch, org_id, {allowed.id})
    db = FakeDB([allowed, hidden], [node(allowed.id), node(hidden.id)], [])
    result = svc.build_operations_dashboard(db, user())
    assert result.counts.deployments == 1
    assert result.counts.nodes == 1
    assert [d.profile_name for d in result.deployments] == ["Allowed"]


def test_failed_node_enters_attention_queue(monkeypatch):
    org_id = uuid4(); p = profile(org_id)
    patch_visibility(monkeypatch, org_id, {p.id})
    db = FakeDB([p], [node(p.id, install="failed", category="health_check_failed")], [])
    result = svc.build_operations_dashboard(db, user())
    assert result.counts.failed_nodes == 1
    assert result.counts.attention_nodes == 1
    item = result.attention_queue[0]
    assert item.kind == "node"
    assert item.reason == "health_check_failed"


def test_stale_node_is_counted(monkeypatch):
    org_id = uuid4(); p = profile(org_id)
    patch_visibility(monkeypatch, org_id, {p.id})
    db = FakeDB([p], [node(p.id, age=600)], [])
    result = svc.build_operations_dashboard(db, user(), stale_after_seconds=300)
    assert result.counts.stale_nodes == 1
    assert result.counts.attention_nodes == 1


def test_open_support_case_enters_queue(monkeypatch):
    org_id = uuid4(); p = profile(org_id)
    patch_visibility(monkeypatch, org_id, {p.id})
    case = support_case(org_id, p.id, priority="urgent")
    db = FakeDB([p], [node(p.id)], [case])
    result = svc.build_operations_dashboard(db, user())
    assert result.counts.open_support_cases == 1
    assert result.counts.urgent_support_cases == 1
    assert result.attention_queue[0].support_case_id == case.id


def test_resolved_support_case_not_in_attention_queue(monkeypatch):
    org_id = uuid4(); p = profile(org_id)
    patch_visibility(monkeypatch, org_id, {p.id})
    case = support_case(org_id, p.id, status="resolved")
    db = FakeDB([p], [node(p.id)], [case])
    result = svc.build_operations_dashboard(db, user())
    assert result.counts.open_support_cases == 0
    assert not any(i.kind == "support_case" for i in result.attention_queue)


def test_attention_queue_prioritizes_urgent_cases(monkeypatch):
    org_id = uuid4(); p = profile(org_id)
    patch_visibility(monkeypatch, org_id, {p.id})
    failing = node(p.id, install="failed")
    case = support_case(org_id, p.id, priority="critical")
    db = FakeDB([p], [failing], [case])
    result = svc.build_operations_dashboard(db, user())
    assert result.attention_queue[0].kind == "support_case"
    assert result.attention_queue[0].priority == "critical"


def test_invalid_stale_window_rejected(monkeypatch):
    org_id = uuid4()
    patch_visibility(monkeypatch, org_id, set())
    db = FakeDB([], [], [])
    try:
        svc.build_operations_dashboard(db, user(), stale_after_seconds=5)
    except ValueError as exc:
        assert "between 30 and 86400" in str(exc)
    else:
        raise AssertionError("expected ValueError")
