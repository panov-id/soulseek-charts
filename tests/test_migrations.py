from soulseek_charts.storage.migrations import discover_migrations, split_statements


def test_split_statements_separates_on_semicolons():
    sql_text = "CREATE TABLE first (a UInt8) ENGINE = Memory;\n\nCREATE TABLE second (b UInt8);"

    statements = split_statements(sql_text)

    assert len(statements) == 2
    assert statements[0].startswith("CREATE TABLE first")
    assert statements[1].startswith("CREATE TABLE second")


def test_split_statements_drops_comment_only_fragments():
    sql_text = "-- a leading comment\nCREATE TABLE first (a UInt8);\n-- a trailing comment\n"

    statements = split_statements(sql_text)

    assert len(statements) == 1
    assert "CREATE TABLE first" in statements[0]


def test_split_statements_ignores_a_semicolon_inside_a_comment():
    """A semicolon in prose once cut a CREATE TABLE in half."""
    sql_text = (
        "-- stability is the point; the TTL is the mitigation\n"
        "CREATE TABLE first (a UInt8) ENGINE = Memory;\n"
    )

    statements = split_statements(sql_text)

    assert len(statements) == 1
    assert "CREATE TABLE first" in statements[0]


def test_discovered_migrations_are_ordered_and_non_empty():
    migrations = discover_migrations()

    assert [migration.identifier for migration in migrations] == [
        "0001",
        "0002",
        "0003",
        "0004",
        "0005",
        "0006",
    ]
    assert all(migration.statements for migration in migrations)


def test_migrations_never_store_a_raw_username():
    """Privacy decision 5: usernames must not appear in the schema itself.

    Comments are stripped first — they are allowed to explain the decision.
    """
    for migration in discover_migrations():
        declaration_lines = [
            line
            for statement in migration.statements
            for line in statement.splitlines()
            if not line.strip().startswith("--")
        ]
        combined_declarations = " ".join(declaration_lines)
        assert "username" not in combined_declarations
