"""Explainable, local hybrid scoring for existing rule-based anomaly alerts."""
from __future__ import annotations

from typing import Any
import networkx as nx
import numpy as np

from . import config


def _weights() -> tuple[float, float, float]:
    values = [max(0.0, config.HYBRID_RISK_RULE_WEIGHT), max(0.0, config.HYBRID_RISK_ML_WEIGHT), max(0.0, config.HYBRID_RISK_GRAPH_WEIGHT)]
    total = sum(values)
    return tuple(value / total for value in values) if total else (0.5, 0.25, 0.25)


def _ml_scores(feature_rows: list[list[float]]) -> tuple[list[float], str]:
    """Return normalized Isolation Forest outlier scores, or neutral scores for small data."""
    if len(feature_rows) < 5:
        return [50.0] * len(feature_rows), "Neutral: fewer than five anomaly records are available for unsupervised ML."
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        return [50.0] * len(feature_rows), "Neutral: scikit-learn is unavailable, so Isolation Forest did not run."
    values = np.asarray(feature_rows, dtype=float)
    if values.ndim != 2 or not np.isfinite(values).all():
        return [50.0] * len(feature_rows), "Neutral: ML features are incomplete or non-finite."
    scale = values.std(axis=0)
    scale[scale == 0] = 1.0
    normalized = (values - values.mean(axis=0)) / scale
    model = IsolationForest(n_estimators=100, contamination="auto", random_state=42)
    try:
        model.fit(normalized)
        raw = -model.decision_function(normalized)
    except ValueError:
        return [50.0] * len(feature_rows), "Neutral: Isolation Forest could not fit the available anomaly feature rows."
    spread = float(raw.max() - raw.min())
    if spread < 1e-9:
        return [50.0] * len(feature_rows), "Neutral: anomaly feature rows are materially identical."
    return [round(100 * float((score - raw.min()) / spread), 1) for score in raw], "Isolation Forest outlier score from the displayed rule, graph, and evidence features."


def _level(score: float) -> str:
    return "HIGH" if score >= 70 else "MEDIUM" if score >= 40 else "LOW"


def enrich_anomalies(alerts: list[dict[str, Any]], graph: nx.Graph, analytics: dict[str, Any]) -> list[dict[str, Any]]:
    """Add explainable ML, graph, and hybrid scores without changing rule alert detection."""
    if not alerts:
        return []
    degree = analytics.get("degree", {})
    betweenness = analytics.get("betweenness", {})
    relationship_counts = dict(graph.degree()) if len(graph) else {}
    max_relationships = max(relationship_counts.values(), default=1) or 1
    signal_entities = {entity for alert in alerts for entity in alert.get("entities", []) if entity in graph}
    rows: list[dict[str, Any]] = []
    for alert in alerts:
        entities = [entity for entity in alert.get("entities", []) if entity in graph]
        counts = [relationship_counts.get(entity, 0) for entity in entities] or [0]
        degrees = [degree.get(entity, 0.0) for entity in entities] or [0.0]
        between = [betweenness.get(entity, 0.0) for entity in entities] or [0.0]
        entity_set = set(entities)
        risk_neighbors = {neighbor for entity in entities for neighbor in graph.neighbors(entity) if neighbor in signal_entities - entity_set}
        other_signals = signal_entities - entity_set
        distances = [nx.shortest_path_length(graph, entity, signal) for entity in entities for signal in other_signals if nx.has_path(graph, entity, signal)]
        proximity = 100.0 if risk_neighbors else (round(100 / (1 + min(distances)), 1) if distances else 0.0)
        rule_score = round(min(100.0, max(0.0, float(alert.get("confidence", 0)) * 100)), 1)
        relationship_score = 100 * max(counts) / max_relationships
        graph_score = round(min(100.0, 0.35 * relationship_score + 0.25 * max(degrees) * 100 + 0.25 * max(between) * 100 + 0.15 * proximity), 1)
        rows.append({"alert": alert, "rule_score": rule_score, "relationship_count": max(counts), "degree_centrality": max(degrees), "betweenness_centrality": max(between), "risk_signal_connections": len(risk_neighbors), "risk_signal_proximity": proximity, "graph_score": graph_score})
    ml_rows = [[row["rule_score"], row["relationship_count"], row["degree_centrality"], row["betweenness_centrality"], row["risk_signal_connections"], len(row["alert"].get("evidence", []))] for row in rows]
    ml_scores, ml_note = _ml_scores(ml_rows)
    rule_weight, ml_weight, graph_weight = _weights()
    results = []
    for row, ml_score in zip(rows, ml_scores):
        hybrid_score = round(rule_weight * row["rule_score"] + ml_weight * ml_score + graph_weight * row["graph_score"], 1)
        factors = [f"Rule signal: {row['alert']['explanation']}", f"{row['relationship_count']} observed relationship(s); degree centrality {row['degree_centrality']:.3f}.", f"Betweenness centrality {row['betweenness_centrality']:.3f}."]
        if row["risk_signal_connections"]:
            factors.append(f"Directly connected to {row['risk_signal_connections']} entity/entities in other rule-based risk signals.")
        elif row["risk_signal_proximity"]:
            factors.append(f"Graph proximity to other rule-based risk signals contributes {row['risk_signal_proximity']:.1f}/100.")
        factors.append(f"ML: {ml_note}")
        result = dict(row["alert"])
        result.update({"rule_score": row["rule_score"], "ml_anomaly_score": ml_score, "graph_score": row["graph_score"], "hybrid_risk_score": hybrid_score, "risk_level": _level(hybrid_score), "top_factors": factors, "feature_values": {"relationship_count": row["relationship_count"], "degree_centrality": round(row["degree_centrality"], 4), "betweenness_centrality": round(row["betweenness_centrality"], 4), "risk_signal_connections": row["risk_signal_connections"], "risk_signal_proximity": row["risk_signal_proximity"]}, "scoring_weights": {"rule": round(rule_weight, 3), "ml": round(ml_weight, 3), "graph": round(graph_weight, 3)}})
        results.append(result)
    return sorted(results, key=lambda alert: alert["hybrid_risk_score"], reverse=True)
