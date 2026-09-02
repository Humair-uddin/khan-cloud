from app.main import app


def _route_index(path: str, method: str) -> int:
    for index, route in enumerate(app.routes):
        methods = set(
            getattr(route, "methods", []) or []
        )

        if (
            getattr(route, "path", None) == path
            and method in methods
        ):
            return index

    raise AssertionError(
        f"Route not found: {method} {path}"
    )


def test_desired_state_static_route_precedes_dynamic_node_get():
    desired = _route_index(
        "/api/v1/nodes/desired-state",
        "GET",
    )

    dynamic = _route_index(
        "/api/v1/nodes/{node_id}",
        "GET",
    )

    assert desired < dynamic


def test_desired_state_is_node_authenticated():
    route = next(
        route
        for route in app.routes
        if getattr(route, "path", None)
        == "/api/v1/nodes/desired-state"
        and "GET"
        in set(
            getattr(route, "methods", []) or []
        )
    )

    dependency_names = {
        getattr(dep.call, "__name__", "")
        for dep in route.dependant.dependencies
        if getattr(dep, "call", None)
        is not None
    }

    assert (
        "get_authenticated_node"
        in dependency_names
    )
