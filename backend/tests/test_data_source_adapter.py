import json

from app.data_sources import FixtureDataSourceAdapter
from app.prediction_engine import WeightVersion, run_match_prediction


def write_fixture(path):
    path.write_text(
        json.dumps(
            {
                "match": {
                    "home_team": "Brazil",
                    "away_team": "Croatia",
                    "home_advantage": 1.08,
                },
                "team_form": {
                    "Brazil": {
                        "avg_goals_for": 2.2,
                        "avg_goals_against": 0.7,
                    },
                    "Croatia": {
                        "avg_goals_for": 1.4,
                        "avg_goals_against": 1.1,
                    },
                },
                "rankings": {
                    "Brazil": {"strength": 1.12},
                    "Croatia": {"strength": 0.96},
                },
            }
        ),
        encoding="utf-8",
    )


def test_adapter_saves_source_snapshot(tmp_path):
    fixture_path = tmp_path / "match.json"
    snapshot_dir = tmp_path / "snapshots"
    write_fixture(fixture_path)

    adapter = FixtureDataSourceAdapter(
        source_name="fixture-schedule",
        fixture_path=fixture_path,
        snapshot_dir=snapshot_dir,
    )

    snapshot = adapter.fetch_snapshot()

    assert snapshot.source_name == "fixture-schedule"
    assert snapshot.path.exists()
    assert snapshot.content_hash
    assert snapshot.path.read_text(encoding="utf-8") == fixture_path.read_text(
        encoding="utf-8"
    )


def test_adapter_normalizes_fixture_to_prediction_dataset(tmp_path):
    fixture_path = tmp_path / "match.json"
    snapshot_dir = tmp_path / "snapshots"
    write_fixture(fixture_path)

    adapter = FixtureDataSourceAdapter(
        source_name="fixture-schedule",
        fixture_path=fixture_path,
        snapshot_dir=snapshot_dir,
    )

    dataset = adapter.build_prediction_dataset()

    assert dataset.home_team == "Brazil"
    assert dataset.away_team == "Croatia"
    assert dataset.home.attack_index > dataset.away.attack_index
    assert dataset.away.defense_weakness > dataset.home.defense_weakness


def test_adapter_dataset_can_feed_prediction_engine(tmp_path):
    fixture_path = tmp_path / "match.json"
    snapshot_dir = tmp_path / "snapshots"
    write_fixture(fixture_path)
    adapter = FixtureDataSourceAdapter(
        source_name="fixture-schedule",
        fixture_path=fixture_path,
        snapshot_dir=snapshot_dir,
    )

    prediction = run_match_prediction(
        adapter.build_prediction_dataset(),
        WeightVersion(name="baseline", factors={}),
        simulation_count=1_000,
        seed=1,
    )

    assert prediction.home_team == "Brazil"
    assert prediction.away_team == "Croatia"
    assert prediction.probabilities["home_win"] > prediction.probabilities["away_win"]
