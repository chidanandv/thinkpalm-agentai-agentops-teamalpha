from fleet_health.agents.graph import run_pipeline


def test_run_pipeline_deterministic(
    sample_voyage_reports,
    sample_port_calls,
    sample_bunker_logs,
    sample_maintenance_alerts,
):
    result = run_pipeline(
        voyage_reports=sample_voyage_reports,
        port_calls=sample_port_calls,
        bunker_logs=sample_bunker_logs,
        maintenance_alerts=sample_maintenance_alerts,
        fleet_name="Test Fleet",
        report_period="2026-06-04",
    )

    assert result["thread_id"]
    assert result["anomalies_count"] >= 1
    assert result["escalations_count"] >= 1
    assert result["report"]["fleet_name"] == "Test Fleet"
    assert len(result["report"]["vessel_summaries"]) == 3
