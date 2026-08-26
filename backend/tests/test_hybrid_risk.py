import networkx as nx

try:
    from app.risk import enrich_anomalies
except ModuleNotFoundError:
    from backend.app.risk import enrich_anomalies


def _analytics(graph):
    return {"degree": nx.degree_centrality(graph), "betweenness": nx.betweenness_centrality(graph)}


def test_hybrid_risk_handles_empty_alerts():
    assert enrich_anomalies([], nx.Graph(), {}) == []


def test_hybrid_risk_uses_neutral_ml_for_small_dataset_and_explains_scores():
    graph = nx.Graph()
    graph.add_edges_from([("P-1", "P-2"), ("P-2", "P-3")])
    alerts = [{"id": "AN-1", "type": "Test signal", "severity": "MEDIUM", "confidence": 0.8, "timestamp": "2026-01-01", "entities": ["P-1"], "explanation": "Observed test rule signal.", "evidence": ["E-1"]}]
    result = enrich_anomalies(alerts, graph, _analytics(graph))[0]
    assert result["rule_score"] == 80.0
    assert result["ml_anomaly_score"] == 50.0
    assert 0 <= result["graph_score"] <= 100
    assert 0 <= result["hybrid_risk_score"] <= 100
    assert result["risk_level"] in {"LOW", "MEDIUM", "HIGH"}
    assert result["feature_values"]["relationship_count"] == 1
    assert any("fewer than five" in factor for factor in result["top_factors"])


def test_hybrid_risk_api_exposes_score_breakdown():
    try:
        from app.main import app
    except ModuleNotFoundError:
        from backend.app.main import app
    from fastapi.testclient import TestClient
    response = TestClient(app).get("/api/anomalies")
    assert response.status_code == 200
    if response.json():
        alert = response.json()[0]
        assert {"rule_score", "ml_anomaly_score", "graph_score", "hybrid_risk_score", "risk_level", "top_factors"} <= alert.keys()
