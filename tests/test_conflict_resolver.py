from scripts.resolve_app_conflict import resolve_conflicts


def test_resolve_conflicts_combines_and_dedupes():
    source = (
        "start\n"
        "<<<<<<< HEAD\n"
        "line_a\n"
        "line_dup\n"
        "=======\n"
        "line_b\n"
        "line_dup\n"
        ">>>>>>> main\n"
        "end\n"
    )
    resolved, count = resolve_conflicts(source)
    assert count == 1
    assert "<<<<<<<" not in resolved
    assert resolved == "start\nline_a\nline_dup\nline_b\nend\n"


def test_resolve_conflicts_no_markers():
    source = "alpha\nbeta\n"
    resolved, count = resolve_conflicts(source)
    assert count == 0
    assert resolved == source
