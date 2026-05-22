"""Tests for offline producer ingest fixture validation."""

from pcs_bench.producer_fixtures import (
    FIXTURE_ROOT,
    all_fixtures_valid,
    fixture_ingest_path,
    validate_all_producer_fixtures,
)


def test_fixture_root_exists() -> None:
    assert FIXTURE_ROOT.is_dir()
    assert fixture_ingest_path("certifyedge").is_file()


def test_all_producer_fixtures_validate() -> None:
    results = validate_all_producer_fixtures(None)
    assert len(results) >= 4
    producers = {r.producer.split(":")[0] for r in results}
    assert producers == {
        "certifyedge",
        "provability-fabric",
        "scientific-memory",
        "labtrust-gym",
    }
    assert all(r.valid for r in results), [r.errors for r in results if not r.valid]


def test_all_fixtures_valid_helper() -> None:
    assert all_fixtures_valid(None)
