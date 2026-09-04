'use client';
import { useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import ThemeToggle, { useTheme } from './components/ThemeToggle';

const NetworkGraph3D = dynamic(() => import('./components/NetworkGraph3D'), {
  ssr: false,
  loading: () => <div className="graph3d" style={{ display: 'grid', placeItems: 'center', color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>Rendering network…</div>,
});

const API = process.env.NEXT_PUBLIC_API_URL ?? '';
const nav = ['Command Center', 'Case Management', 'Intelligence Ingestion', 'Network Explorer', 'Entity Intelligence', 'Anomaly & Risk', 'Investigation Timeline', 'AI Investigation Assistant', 'Evidence & Reports', 'Case Workspace'];
type Any = any;
const get = (p: string) => fetch(API + p).then(async (r) => { if (!r.ok) throw new Error(`API ${r.status}: ${await r.text()}`); return r.json(); });

function Badge({ children }: { children: any }) { return <span className="badge">{children}</span>; }
function Card({ title, children }: { title: string; children: any }) { return <section className="card"><h3>{title}</h3>{children}</section>; }

function Dashboard({ d, graph, theme, error }: Any) {
  if (error) return <div className="loading">Unable to reach the ShadowIntel API. Start the backend at <code>http://127.0.0.1:8010</code> and refresh this page.<br /><small>{error}</small></div>;
  if (!d) return <div className="loading">Loading case intelligence…</div>;
  return (
    <>
      <header>
        <div><p className="eyebrow">ACTIVE CASE / {d.case.id}</p><h1>Command Center</h1><p>{d.case.name} · synthetic investigation workspace</p></div>
        <Badge>STATUS · {d.case.status}</Badge>
      </header>
      <div className="metrics">{Object.entries(d.metrics).map(([k, v]) => <div className="metric" key={k}><span>{k.replaceAll('_', ' ')}</span><strong>{String(v)}</strong></div>)}</div>
      <div className="grid two">
        <Card title="Network overview">
          <NetworkGraph3D
            nodes={graph?.nodes || []}
            edges={graph?.edges || []}
            theme={theme}
            height={260}
            maxNodes={22}
            legend={false}
            caption={`${graph?.nodes?.length || 0} entities · ${graph?.edges?.length || 0} observed relationships`}
          />
        </Card>
        <Card title="Priority entities">{d.high_priority_entities.map((x: Any) => <div className="row" key={x.id}><b>{x.label}</b><small>{x.type} · Community {x.community}</small><Badge>{x.priority} priority</Badge></div>)}</Card>
        <Card title="Suspicious activity feed">{d.anomaly_alerts.map((x: Any) => <div className="feed" key={x.id}><Badge>{x.severity}</Badge><b>{x.type}</b><p>{x.explanation}</p></div>)}</Card>
        <Card title="Recent activity">{d.recent_activity.map((x: Any) => <div className="row" key={x.id}><b>{x.title}</b><small>{new Date(x.timestamp).toLocaleString()} · {x.source}</small></div>)}</Card>
      </div>
    </>
  );
}

function CaseManagement({ onCaseChanged, onUploadCase }: { onCaseChanged?: () => void; onUploadCase?: (caseId: string) => void }) {
  const emptyForm = { name: '', investigator: '', priority: 'MEDIUM', stage: 'EVIDENCE_INGESTION', status: 'ACTIVE' };
  const [data, setData] = useState<Any>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<Any>(emptyForm);
  const [editingId, setEditingId] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');

  function load() {
    get('/api/cases').then(setData).catch((e) => setError(e instanceof Error ? e.message : 'Failed to load cases.'));
  }
  useEffect(load, []);

  function startEdit(item: Any) {
    setEditingId(item.id);
    setForm({ name: item.name, investigator: item.investigator || '', priority: item.priority, stage: item.stage, status: item.status });
    setShowForm(true);
  }
  function startCreate() {
    setEditingId('');
    setForm(emptyForm);
    setShowForm(true);
  }
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError('');
    try {
      const url = editingId ? `${API}/api/cases/${editingId}` : `${API}/api/cases`;
      const method = editingId ? 'PATCH' : 'POST';
      const response = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form) });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || `Case ${editingId ? 'update' : 'creation'} failed (HTTP ${response.status}).`);
      setShowForm(false); setEditingId(''); setForm(emptyForm);
      load(); onCaseChanged?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Case save failed.');
    } finally {
      setBusy(false);
    }
  }
  async function remove(id: string) {
    if (!window.confirm(`Delete case ${id}? This cannot be undone.`)) return;
    try {
      const response = await fetch(`${API}/api/cases/${id}`, { method: 'DELETE' });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || 'Case could not be deleted.');
      load(); onCaseChanged?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Case could not be deleted.');
    }
  }

  if (error) return <div className="loading">{error}</div>;
  if (!data) return <div className="loading">Loading case list…</div>;
  const cases = statusFilter === 'ALL' ? data.cases : data.cases.filter((x: Any) => x.status === statusFilter);

  return (
    <>
      <header>
        <div><p className="eyebrow">CASE MANAGEMENT</p><h1>Case Workspace</h1><p>Create, assign, and track every investigation by ID, status, priority, and stage.</p></div>
        <button onClick={startCreate}>+ New Case</button>
      </header>
      <div className="toolbar">
        <label>Status
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="ALL">All statuses</option>
            {data.statuses.map((s: string) => <option key={s} value={s}>{s.replaceAll('_', ' ')}</option>)}
          </select>
        </label>
      </div>
      {showForm && (
        <Card title={editingId ? `Edit ${editingId}` : 'Create new case'}>
          <form className="auth-form" onSubmit={submit}>
            <label>Case name<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></label>
            <label>Assigned investigator<input value={form.investigator} onChange={(e) => setForm({ ...form, investigator: e.target.value })} placeholder="e.g. Investigator A. Menon" /></label>
            <label>Priority
              <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                {data.priorities.map((p: string) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
            <label>Investigation stage
              <select value={form.stage} onChange={(e) => setForm({ ...form, stage: e.target.value })}>
                {data.stages.map((s: string) => <option key={s} value={s}>{s.replaceAll('_', ' ')}</option>)}
              </select>
            </label>
            <label>Status
              <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {data.statuses.map((s: string) => <option key={s} value={s}>{s.replaceAll('_', ' ')}</option>)}
              </select>
            </label>
            <div className="toolbar">
              <button type="submit" disabled={busy}>{busy ? 'Saving…' : editingId ? 'Save changes' : 'Create case'}</button>
              <button type="button" onClick={() => { setShowForm(false); setEditingId(''); }}>Cancel</button>
            </div>
          </form>
        </Card>
      )}
      <Card title={`Cases (${cases.length})`}>
        <div className="table">
          {cases.map((item: Any) => (
            <div className="row" key={item.id} style={{ alignItems: 'flex-start' }}>
              <div>
                <b>{item.name}</b>
                <small>{item.id} · {item.investigator || 'Unassigned'} · Opened {item.created_at?.slice(0, 10)}</small>
              </div>
              <Badge>{item.status.replaceAll('_', ' ')}</Badge>
              <Badge>{item.priority} priority</Badge>
              <Badge>{item.stage.replaceAll('_', ' ')}</Badge>
              <small>{item.entity_count} entities · {item.relationship_count} relationships · {item.evidence_count} evidence</small>
              <button onClick={() => onUploadCase?.(item.id)}>Upload documents</button>
              <button onClick={() => startEdit(item)}>Edit</button>
              <button onClick={() => remove(item.id)}>Delete</button>
            </div>
          ))}
          {!cases.length && <p>No cases match this filter.</p>}
        </div>
      </Card>
    </>
  );
}

function Ingest({ cases, selectedCaseId, onCaseChange }: { cases: Any[]; selectedCaseId: string; onCaseChange: (caseId: string) => void }) {
  const stages = ['UPLOAD', 'PARSING', 'ENTITY EXTRACTION', 'ENTITY RESOLUTION', 'GRAPH UPDATE', 'ANOMALY ANALYSIS'];
  const [result, setResult] = useState<Any>();
  const [history, setHistory] = useState<Any[]>([]);
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const [selectedFile, setSelectedFile] = useState<File>();
  const [status, setStatus] = useState('');
  const [stageState, setStageState] = useState<string[]>(stages.map(() => 'pending'));
  const loadHistory = () => get('/api/ingestion/jobs').then(setHistory).catch(() => {});
  const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
  const stageNumber = (index: number, data: Any) => [undefined, data?.records_processed, data?.entities_extracted, undefined, data?.relationships_created, data?.anomaly_count][index];
  useEffect(() => { loadHistory(); }, []);
  async function reveal(data: Any) {
    setStageState(['complete', 'active', 'pending', 'pending', 'pending', 'pending']);
    for (let i = 1; i < stages.length; i++) {
      await pause(190);
      setStageState((previous) => previous.map((state, index) => (index < i ? 'complete' : index === i ? 'active' : 'pending')));
    }
    await pause(190);
    setStageState(stages.map(() => 'complete'));
    setResult(data);
    loadHistory();
  }
  async function send(fd: FormData) {
    fd.append('case_id', selectedCaseId);
    setBusy(true); setError(''); setStatus('Uploading and processing selected source…'); setResult(undefined);
    setStageState(['active', ...stages.slice(1).map(() => 'pending')]);
    try {
      const r = await fetch(API + '/api/ingestion/upload', { method: 'POST', body: fd });
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail || 'Ingestion failed');
      await reveal(body);
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Ingestion failed';
      setError(message);
      setStageState((previous) => previous.map((state, index) => (index === previous.findIndex((x) => x !== 'complete') ? 'error' : state)));
    } finally {
      setBusy(false); setStatus('');
    }
  }
  async function upload(f: File) { const fd = new FormData(); fd.append('file', f); await send(fd); }
  async function ingestUrl() { if (!url.trim()) return; const fd = new FormData(); fd.append('url', url.trim()); await send(fd); }
  return (
    <>
      <header><div><p className="eyebrow">DATA OPERATIONS</p><h1>Intelligence Ingestion</h1><p>Import reports, CDRs, transactions, locations, or a captioned YouTube source.</p></div></header>
      <div className="toolbar"><label>Attach to case
        <select value={selectedCaseId} onChange={(e) => onCaseChange(e.target.value)}>{cases.map((item: Any) => <option key={item.id} value={item.id}>{item.name} · {item.id}</option>)}</select>
      </label></div>
      <div className="pipeline" aria-label="Ingestion pipeline">
        {stages.map((stage, index) => (
          <div className="pipeline-unit" key={stage}>
            <div className={'pipeline-stage ' + stageState[index]}>
              <span className="stage-icon">{stageState[index] === 'complete' ? '✓' : stageState[index] === 'error' ? '!' : index + 1}</span>
              <span>{stage}</span>
              {stageState[index] === 'complete' && stageNumber(index, result) !== undefined && <b>{stageNumber(index, result)}</b>}
            </div>
            {index < stages.length - 1 && <div className={'pipeline-link ' + (stageState[index] === 'complete' ? 'complete' : '')} />}
          </div>
        ))}
      </div>
      <label className="drop">
        <input type="file" accept=".txt,.csv,.pdf,.png,.jpg,.jpeg,.tiff,.bmp" onChange={(e) => setSelectedFile(e.target.files?.[0])} />
        <b>{selectedFile ? selectedFile.name : 'Drop a report, CSV, PDF, or image here'}</b>
        <small>{selectedFile ? `${selectedFile.type || 'Supported file'} · ${(selectedFile.size / 1024).toFixed(1)} KB selected` : 'Supported: TXT, CSV, PDF, PNG, JPG, TIFF, BMP'}</small>
      </label>
      <div className="toolbar">
        <button disabled={busy || !selectedFile} onClick={() => selectedFile && upload(selectedFile)}>{busy ? 'Processing…' : 'Process selected file'}</button>
        {status && <Badge>{status}</Badge>}
      </div>
      <div className="toolbar">
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=…" />
        <button disabled={busy || !url.trim()} onClick={ingestUrl}>Ingest YouTube transcript</button>
      </div>
      {error && <p className="notice">{error}</p>}
      {result && (
        <Card title="Completed ingestion">
          <div className="metrics compact">{['records_processed', 'entities_extracted', 'relationships_created', 'events_created', 'duration_ms'].map((k) => <div className="metric" key={k}><span>{k.replaceAll('_', ' ')}</span><strong>{result[k]}</strong></div>)}</div>
          <p>Source: <b>{result.source}</b> · Method: <Badge>{result.extraction_method}</Badge> · Status: <Badge>{result.status}</Badge> · Evidence: <Badge>{result.evidence_id}</Badge></p>
          <pre>{result.text_snippet}</pre>
          <pre>{JSON.stringify(result.extraction, null, 2)}</pre>
        </Card>
      )}
      <Card title="Ingestion history">{history.length ? history.slice(0, 8).map((x) => <div className="row" key={x.id}><b>{x.source}</b><small>{x.result?.extraction_method || 'processing'} · {x.status} · {x.created_at}</small></div>) : <p>No persisted ingestion jobs yet.</p>}</Card>
    </>
  );
}

function InvestigativeRelationshipMap({ route, entities, selectedEdge, onSelectEdge }: Any) {
  const ids: string[] = route?.path || [];
  const relationships: Any[] = route?.relationships || [];
  if (!ids.length) return <p className="notice">No observed relationship path exists for this selection.</p>;
  const width = Math.max(720, 180 * ids.length);
  const x = (index: number) => 90 + index * ((width - 180) / Math.max(ids.length - 1, 1));
  const label = (id: string) => entities.find((entity: Any) => entity.id === id)?.label || id;
  return <div className="investigative-map" aria-label="Investigative relationship map"><svg viewBox={`0 0 ${width} 260`} role="img" aria-label="Selected relationship path"> <defs><marker id="path-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path className="path-arrow" d="M 0 0 L 10 5 L 0 10 z" /></marker></defs>{relationships.map((relationship: Any, index: number) => <g className={'path-edge ' + (selectedEdge === index ? 'selected' : '')} key={relationship.id || index} onClick={() => onSelectEdge(index)}><line x1={x(index) + 35} y1="125" x2={x(index + 1) - 35} y2="125" markerEnd="url(#path-arrow)" /><text x={(x(index) + x(index + 1)) / 2} y="104" textAnchor="middle">{relationship.type || 'OBSERVED RELATIONSHIP'}</text></g>)}{ids.map((id, index) => <g className={'path-node ' + (index === 0 ? 'path-from' : index === ids.length - 1 ? 'path-to' : 'path-intermediate')} key={id}><circle cx={x(index)} cy="125" r="35" /><text x={x(index)} y="131" textAnchor="middle">{index === 0 ? 'FROM' : index === ids.length - 1 ? 'TO' : index}</text><text className="path-label" x={x(index)} y="190" textAnchor="middle">{label(id)}</text><text className="path-id" x={x(index)} y="210" textAnchor="middle">{id}</text></g>)}</svg></div>;
}

function Explorer({ entities, theme }: Any) {
  const people = entities.filter((x: Any) => x.type === 'Person');
  const [focus, setFocus] = useState(''), [target, setTarget] = useState(''), [graph, setGraph] = useState<Any>(), [path, setPath] = useState<Any>(), [pathIndex, setPathIndex] = useState(0), [selectedEdge, setSelectedEdge] = useState(0);
  useEffect(() => { if (!focus && people[0]) setFocus(people[0].id); if (!target && people[1]) setTarget(people[1].id); }, [people, focus, target]);
  useEffect(() => { if (focus) get('/api/graph/neighborhood?entity_id=' + focus + '&hops=2').then(setGraph); }, [focus]);
  return (
    <>
      <header><div><p className="eyebrow">KNOWLEDGE GRAPH</p><h1>Network Explorer</h1><p>Live graph records with confidence and provenance — drag to rotate, click a card to focus it.</p></div></header>
      <div className="toolbar">
        <select value={focus} onChange={(e) => setFocus(e.target.value)}>{people.map((x: Any) => <option value={x.id} key={x.id}>{x.label} ({x.id})</option>)}</select>
        <select value={target} onChange={(e) => setTarget(e.target.value)}>{people.map((x: Any) => <option value={x.id} key={x.id}>{x.label} ({x.id})</option>)}</select>
        <button disabled={!focus || !target} onClick={() => get('/api/graph/path?source=' + focus + '&target=' + target).then((result) => { setPath(result); setPathIndex(0); setSelectedEdge(0); })}>Find path</button>
        <Badge>2-hop exploration</Badge>
      </div>
      <div className="graph">
        <NetworkGraph3D nodes={graph?.nodes || []} edges={graph?.edges || []} focusId={focus} interactive theme={theme} height="100%" maxNodes={40} onSelectNode={setFocus} />
        <aside>
          <h3>Selected entity</h3>
          <b>{entities.find((x: Any) => x.id === focus)?.label}</b>
          <p>Community and centrality are calculated from the current relationship store.</p>
          <p>{graph?.nodes?.length || 0} stored nodes · {graph?.edges?.length || 0} observed relationships</p>
          {path && <><h3>Observed path</h3>{path.path.map((x: string) => <div className="row" key={x}>{x}</div>)}</>}
        </aside>
      </div>
      <section className="investigative-section">
        <p className="eyebrow">ROUTE ANALYSIS</p><h2>Investigative Relationship Map</h2><p>Path-only view of the selected entities, using observed relationships and provenance from the case store.</p>
        {!path && <p className="notice">Select FROM and TO, then choose Find path to inspect an observed relationship route.</p>}
        {path && !path.paths?.length && <p className="notice">{path.message || 'No observed relationship path exists for this selection.'}</p>}
        {path?.paths?.length > 0 && <>
          {path.paths.length > 1 && <div className="toolbar path-switch"><label>Observed shortest path<select value={pathIndex} onChange={(event) => { setPathIndex(Number(event.target.value)); setSelectedEdge(0); }}>{path.paths.map((candidate: Any, index: number) => <option value={index} key={index}>Path {index + 1} · {candidate.path.length - 1} relationship(s)</option>)}</select></label></div>}
          <InvestigativeRelationshipMap route={path.paths[pathIndex]} entities={entities} selectedEdge={selectedEdge} onSelectEdge={setSelectedEdge} />
          {path.paths[pathIndex].relationships[selectedEdge] && <Card title="Selected relationship"><div className="row"><b>{path.paths[pathIndex].relationships[selectedEdge].type}</b><small>{path.paths[pathIndex].relationships[selectedEdge].source} → {path.paths[pathIndex].relationships[selectedEdge].target} · {path.paths[pathIndex].relationships[selectedEdge].timestamp}</small><Badge>{Math.round(path.paths[pathIndex].relationships[selectedEdge].confidence * 100)}% confidence</Badge></div><p>Evidence: <b>{path.paths[pathIndex].relationships[selectedEdge].evidence_id || 'Not recorded'}</b></p><p>Source / provenance: <b>{path.paths[pathIndex].relationships[selectedEdge].provenance || path.paths[pathIndex].relationships[selectedEdge].source}</b></p></Card>}
        </>}
      </section>
    </>
  );
}

function Entity({ entities }: Any) {
  const people = entities.filter((x: Any) => x.type === 'Person');
  const [id, setId] = useState(''), [d, setD] = useState<Any>();
  useEffect(() => { if (!id && people[0]) setId(people[0].id); }, [id, people]);
  useEffect(() => { if (id) get('/api/entities/' + id).then(setD); }, [id]);
  return (
    <>
      <header><div><p className="eyebrow">ENTITY DOSSIER</p><h1>Entity Intelligence</h1></div><select value={id} onChange={(e) => setId(e.target.value)}>{people.map((x: Any) => <option key={x.id} value={x.id}>{x.label}</option>)}</select></header>
        {d && (
          <div className="grid two">
            <Card title="Identity & analytics">
              <h2>{d.entity.label}</h2><p>{d.entity.type} · Community {d.entity.community}</p>
              <div className="metrics compact">
                <div className="metric"><span>Priority</span><strong>{d.entity.priority}</strong></div>
                <div className="metric"><span>Centrality</span><strong>{d.entity.centrality}</strong></div>
                <div className="metric"><span>Confidence</span><strong>{d.entity.confidence}</strong></div>
              </div>
            </Card>
            <Card title="Connections">{d.connections.slice(0, 8).map((x: Any) => <div className="row" key={x.id}><b>{x.type}</b><small>{x.source} → {x.target} · {x.evidence_id}</small></div>)}</Card>
            <Card title="Timeline">{d.timeline.map((x: Any) => <div className="row" key={x.id}><b>{x.title}</b><small>{x.timestamp} · {x.source}</small></div>)}</Card>
            <Card title="Related anomaly indicators">{d.anomalies.length ? d.anomalies.map((x: Any) => <div className="feed" key={x.id}><Badge>{x.severity}</Badge> {x.explanation}</div>) : <p>No rule-based alert directly includes this entity.</p>}</Card>
          </div>
        )}
    </>
  );
}

function EnhancedEntity({ entities, selectedId }: Any) {
  const [id, setId] = useState(''), [d, setD] = useState<Any>(), [correlations, setCorrelations] = useState<Any[]>([]);
  useEffect(() => { if (selectedId) setId(selectedId); else if (!id && entities[0]) setId(entities[0].id); }, [id, entities, selectedId]);
  useEffect(() => { if (id) get('/api/entities/' + id).then(setD); }, [id]);
  useEffect(() => { if (id) get('/api/entities/' + id + '/correlations').then(setCorrelations).catch(() => setCorrelations([])); }, [id]);
  const ranked = entities.slice(0, 8);
  const uniqueCorrelations = correlations.filter((correlation: Any, index: number, all: Any[]) => all.findIndex((candidate) => {
    const related = candidate.entities.filter((entity: Any) => entity.id !== id).map((entity: Any) => entity.id).sort().join(',');
    const currentRelated = correlation.entities.filter((entity: Any) => entity.id !== id).map((entity: Any) => entity.id).sort().join(',');
    const records = candidate.records.map((record: Any) => `${record.kind}:${record.type}:${record.id}`).sort().join('|');
    const currentRecords = correlation.records.map((record: Any) => `${record.kind}:${record.type}:${record.id}`).sort().join('|');
    return related === currentRelated && records === currentRecords;
  }) === index);
  return <><header><div><p className="eyebrow">ENTITY DOSSIER</p><h1>Entity Intelligence</h1><p>Existing graph influence, connections, case indicators, and evidence links ranked for investigator review.</p></div><select value={id} onChange={(event) => setId(event.target.value)}>{entities.map((entity: Any) => <option key={entity.id} value={entity.id}>{entity.label} ({entity.id})</option>)}</select></header><div className="grid two"><Card title="Ranked key entities">{ranked.map((entity: Any, index: number) => <button className={'entity-rank ' + (entity.id === id ? 'active' : '')} key={entity.id} onClick={() => setId(entity.id)}><span>{index + 1}</span><b>{entity.label}</b><small>Influence {entity.influence_score} - Risk {entity.risk_score} - {entity.connection_count} connections</small></button>)}</Card>{d && <Card title="Importance profile"><h2>{d.entity.label}</h2><p>{d.entity.type} - Community {d.entity.community}</p><div className="metrics compact entity-metrics"><div className="metric"><span>Influence</span><strong>{d.entity.influence_score}</strong></div><div className="metric"><span>Centrality</span><strong>{d.entity.centrality}</strong></div><div className="metric"><span>Connections</span><strong>{d.entity.connection_count}</strong></div><div className="metric"><span>Risk score</span><strong>{d.entity.risk_score}</strong></div></div><h4>Why this entity is important</h4>{d.entity.importance_reasons.map((reason: string, index: number) => <p className="importance-reason" key={index}>{reason}</p>)}<h4>Linked case & evidence</h4><p>Case: <Badge>{d.case?.id || d.entity.case_id}</Badge> {d.case?.name}</p><p>Evidence links: {d.entity.evidence_ids.length ? d.entity.evidence_ids.map((evidenceId: string) => <Badge key={evidenceId}>{evidenceId}</Badge>) : 'No linked evidence recorded.'}</p></Card>}{d && <Card title="Connections">{d.connections.length ? d.connections.slice(0, 8).map((connection: Any) => <div className="row" key={connection.id}><b>{connection.type}</b><small>{connection.source} - {connection.target} - {connection.evidence_id || 'No evidence ID'}</small></div>) : <p>No observed relationships are recorded.</p>}</Card>}{d && <Card title="Cross-source correlations">{uniqueCorrelations.length ? uniqueCorrelations.map((correlation: Any) => <div className="correlation" key={correlation.id}><div className="event-heading"><Badge>Cross-source correlation detected</Badge>{correlation.source_types.map((type: string) => <Badge key={type}>{type}</Badge>)}</div><div className="correlation-field"><span>Primary entity</span><b>{entities.find((entity: Any) => entity.id === id)?.label || id} ({id})</b></div><div className="correlation-field"><span>Related entities</span><p>{correlation.entities.filter((entity: Any) => entity.id !== id).map((entity: Any) => <span className="entity-reference" key={entity.id}>{entity.label} ({entity.id})</span>)}</p></div><div className="correlation-field"><span>Observed records</span>{correlation.records.map((record: Any) => <div className="row" key={record.id}><b>{record.type}</b><small>{record.id} - {record.timestamp || 'Time not recorded'}</small></div>)}</div><div className="correlation-field"><span>Evidence IDs</span><p>{correlation.evidence_ids.map((evidenceId: string) => <Badge key={evidenceId}>{evidenceId}</Badge>)}</p></div><p className="correlation-why"><b>Why it matters</b> {correlation.explanation}</p></div>) : <p>No observed cross-source correlations for this entity.</p>}</Card>}{d && <Card title="Evidence & risk indicators">{d.evidence.length ? d.evidence.slice(0, 6).map((item: Any) => <div className="row" key={item.id}><b>{item.id}</b><small>{item.source} - {item.document_type}</small></div>) : <p>No evidence is directly linked to this entity.</p>}{d.anomalies.length ? d.anomalies.map((alert: Any) => <div className="feed" key={alert.id}><Badge>{alert.risk_level || alert.severity}</Badge> {alert.explanation}</div>) : <p>No current anomaly indicator directly includes this entity.</p>}</Card>}</div></>;
}

function TopSearch({ value, results, onChange, onSelect }: Any) {
  return <div className="top-search"><input value={value} onChange={(event) => onChange(event.target.value)} placeholder="Search entity name, ID, phone, or account..." aria-label="Search entities" />{value.trim().length >= 2 && <div className="search-results">{results.length ? results.map((entity: Any) => <button key={entity.id} onClick={() => onSelect(entity)}><b>{entity.label}</b><small>{entity.type} - {entity.id}</small></button>) : <p>No matching entities found.</p>}</div>}</div>;
}

function Anomalies({ data }: Any) {
  return (
    <>
      <header><div><p className="eyebrow">EXPLAINABLE ANALYSIS</p><h1>Anomaly & Risk Analysis</h1><p>Rule-based indicators with supporting evidence, not guilt determinations.</p></div></header>
      <div className="grid three">{data.map((x: Any) => <Card title={x.type} key={x.id}><Badge>{x.severity} · {Math.round(x.confidence * 100)}%</Badge><p>{x.explanation}</p><small>{x.timestamp}</small><p>Evidence: {x.evidence.join(', ')}</p></Card>)}</div>
    </>
  );
}

function HybridAnomalies({ data }: Any) {
  return <><header><div><p className="eyebrow">EXPLAINABLE ANALYSIS</p><h1>Anomaly & Risk Analysis</h1><p>Rule signals, local ML outlier detection, and NetworkX graph features are combined without making guilt determinations.</p></div></header><div className="grid three">{data.map((x: Any) => <Card title={x.type} key={x.id}><Badge>{x.risk_level || x.severity} RISK</Badge><div className="metrics compact risk-metrics"><div className="metric"><span>Rule score</span><strong>{x.rule_score ?? Math.round(x.confidence * 100)}</strong></div><div className="metric"><span>ML anomaly</span><strong>{x.ml_anomaly_score ?? '—'}</strong></div><div className="metric"><span>Graph score</span><strong>{x.graph_score ?? '—'}</strong></div><div className="metric"><span>Hybrid risk</span><strong>{x.hybrid_risk_score ?? '—'}</strong></div></div><p>{x.explanation}</p><small>{x.timestamp}</small><h4>Top explanation factors</h4>{(x.top_factors || []).map((factor: string, index: number) => <p className="risk-factor" key={index}>{factor}</p>)}<p>Evidence: {x.evidence.join(', ')}</p></Card>)}</div></>;
}

function Timeline({ data, entities, anomalies }: Any) {
  const [entityFilter, setEntityFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const entityLabel = (id: string) => entities.find((entity: Any) => entity.id === id)?.label || id;
  const types = Array.from(new Set(data.map((event: Any) => event.type))).sort() as string[];
  const filtered = data.filter((event: Any) => (!entityFilter || event.entities.includes(entityFilter)) && (!typeFilter || event.type === typeFilter));
  const indicatorsFor = (event: Any) => anomalies.filter((alert: Any) => alert.entities.some((id: string) => event.entities.includes(id)) || alert.evidence?.includes(event.source));
  return (
    <>
      <header><div><p className="eyebrow">CASE CHRONOLOGY</p><h1>Investigation Timeline</h1><p>Calls, transfers, and location observations in a unified evidence view.</p></div></header>
      <div className="toolbar timeline-filters">
        <label>Entity<select value={entityFilter} onChange={(event) => setEntityFilter(event.target.value)}><option value="">All entities</option>{entities.map((entity: Any) => <option value={entity.id} key={entity.id}>{entity.label} ({entity.id})</option>)}</select></label>
        <label>Event type<select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}><option value="">All event types</option>{types.map((type) => <option value={type} key={type}>{type}</option>)}</select></label>
        <Badge>{filtered.length} of {data.length} events</Badge>
      </div>
      <div className="timeline">{filtered.slice(0, 70).map((event: Any) => { const indicators = indicatorsFor(event); return <div className="event" key={event.id}><time>{new Date(event.timestamp).toLocaleString()}</time><div><div className="event-heading"><Badge>{event.type}</Badge><b>{event.title}</b>{indicators.map((alert: Any) => <Badge key={alert.id}>{alert.risk_level || alert.severity} risk</Badge>)}</div><p>Entities: {event.entities.map((id: string) => <span className="entity-reference" key={id}>{entityLabel(id)} ({id})</span>)}</p><p>Evidence: <Badge>{event.source || 'Not recorded'}</Badge> · confidence {event.confidence}</p>{indicators.map((alert: Any) => <p className="event-indicator" key={alert.id}>Indicator: {alert.type} · {alert.explanation}</p>)}</div></div>; })}</div>
      {!filtered.length && <p className="notice">No stored events match the selected filters.</p>}
    </>
  );
}

function Assistant({ selectedCaseId, onOpenEvidence }: { selectedCaseId: string; onOpenEvidence: (id: string) => void }) {
  const examples = ['How are P-017 and P-003 connected?', 'What does E-001 say about Aarav Sen?', 'What risk signals involve BA-003?', 'What is known about P-017?'];
  const [q, setQ] = useState(examples[0]), [a, setA] = useState<Any>(), [busy, setBusy] = useState(false), [error, setError] = useState(''), [showWhy, setShowWhy] = useState(false);
  function investigate() {
    if (!q.trim() || busy) return;
    setBusy(true); setError(''); setShowWhy(false);
    fetch(API + '/api/assistant/query', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: q, case_id: selectedCaseId }) })
      .then(async (response) => { const result = await response.json(); if (!response.ok) throw new Error(result.detail || 'Investigation failed'); return result; })
      .then(setA).catch((reason) => setError(reason instanceof Error ? reason.message : 'Investigation failed')).finally(() => setBusy(false));
  }
  const evidenceCites: string[] = a?.evidence_ids || a?.sources || [];
  return (
    <>
      <header><div><p className="eyebrow">EVIDENCE-BACKED COPILOT</p><h1>AI Investigation Assistant</h1><p>Every response is grounded in stored graph and evidence records{a ? (a.provider === 'groq-llm' ? ' and phrased by an LLM.' : '.') : '.'}</p></div></header>
      <div className="chat">
        <textarea value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') investigate(); }} aria-label="Investigation question" placeholder="Ask about the available case data..." />
        <div className="assistant-examples" aria-label="Example questions">{examples.map((example) => <button key={example} className="example-question" onClick={() => setQ(example)}>{example}</button>)}</div>
        <button onClick={investigate} disabled={busy || !q.trim()}>{busy ? 'Retrieving…' : 'Investigate'}</button>
        {error && <p className="notice">{error}</p>}
        {a && (
          <Card title="Finding">
            <Badge>{a.provider === 'groq-llm' ? 'LLM-ANSWERED' : 'DETERMINISTIC RETRIEVAL'}</Badge>
            <h2>{a.finding}</h2>
            <h4>SUPPORTING EVIDENCE</h4>{a.observed_evidence.map((x: string, i: number) => <p key={i}>{x}</p>)}
            <h4>SUPPORTING EVIDENCE IDS (click to open)</h4>
            <p>{evidenceCites.length ? evidenceCites.map((x: string) => <button key={x} className="example-question citation-chip" onClick={() => onOpenEvidence(x)}>{x}</button>) : 'No evidence IDs were retrieved.'}</p>
            <h4>SUPPORTING ENTITY IDS</h4><p>{a.entity_ids?.length ? a.entity_ids.map((x: string) => <Badge key={x}>{x}</Badge>) : 'No entity IDs were retrieved.'}</p>
            <h4>INFERENCE (labelled — not a fact)</h4><p>{a.inference}</p>
            <h4>CONFIDENCE</h4>
            <div className="row"><Badge>{a.confidence}</Badge>{typeof a.confidence_score === 'number' && <div className="confidence-bar" aria-label={`Confidence ${a.confidence_score} of 100`}><div className="confidence-bar-fill" style={{ width: `${a.confidence_score}%` }} /><small>{a.confidence_score}/100</small></div>}</div>
            {a.why?.length > 0 && (
              <>
                <button className="example-question" onClick={() => setShowWhy(!showWhy)}>{showWhy ? 'Hide' : 'Why did you say this?'}</button>
                {showWhy && <ul className="why-list">{a.why.map((line: string, i: number) => <li key={i}>{line}</li>)}</ul>}
              </>
            )}
            {a.evidence_gaps?.length > 0 && (<><h4>WHAT EVIDENCE IS MISSING</h4><ul className="why-list">{a.evidence_gaps.map((line: string, i: number) => <li key={i}>{line}</li>)}</ul></>)}
            {a.next_step && (<><h4>POSSIBLE NEXT STEP</h4><p>{a.next_step}</p></>)}
          </Card>
        )}
      </div>
    </>
  );
}
function Evidence({ data, focusId }: Any) {
  const [report, setReport] = useState<Any>();
  const [reportBusy, setReportBusy] = useState(false);
  const [reportError, setReportError] = useState('');
  const [selected, setSelected] = useState<Any>();
  const [selectedDetails, setSelectedDetails] = useState<Any[]>([]);
  const [selectedCase, setSelectedCase] = useState<Any>();
  useEffect(() => {
    if (!focusId) return;
    const item = data.find((x: Any) => x.id === focusId);
    if (item) selectEvidence(item);
  }, [focusId, data]);
  async function generateReport() {
    if (reportBusy) return;
    setReportBusy(true);
    setReportError('');
    try {
      const response = await fetch(API + '/api/reports/generate', { method: 'POST' });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || `Report generation failed (HTTP ${response.status}).`);
      setReport(result);
      const download = document.createElement('a');
      download.href = API + '/api/reports/' + result.id + '/export/docx';
      download.download = result.id + '.docx';
      document.body.appendChild(download);
      download.click();
      download.remove();
    } catch (reason) {
      setReportError(reason instanceof Error ? reason.message : 'Report generation failed.');
    } finally {
      setReportBusy(false);
    }
  }
  function selectEvidence(item: Any) {
    if (selected?.id === item.id) { setSelected(undefined); return; }
    setSelected(item);
    setSelectedDetails([]);
    Promise.all([
      get('/api/evidence/' + item.id),
      get('/api/cases/' + item.case_id),
      ...item.entities.map((entityId: string) => get('/api/entities/' + entityId)),
    ]).then(([detail, currentCase, ...entityDetails]) => {
      setSelected(detail);
      setSelectedCase(currentCase);
      setSelectedDetails(entityDetails);
    });
  }
  return (
    <>
      <header>
        <div><p className="eyebrow">PROVENANCE & OUTPUTS</p><h1>Evidence & Reports</h1><p>SHA-256 integrity, case audit trail, and report generation.</p></div>
        <button onClick={generateReport} disabled={reportBusy}>{reportBusy ? 'Generating…' : 'Generate Report'}</button>
      </header>
      {reportError && <p className="notice">{reportError}</p>}
      <Card title="Evidence repository">
        <div className="table">{data.slice(0, 16).map((x: Any) => <div key={x.id}>
          <div className={'row evidence-row ' + (selected?.id === x.id ? 'active' : '')} onClick={() => selectEvidence(x)} role="button" tabIndex={0} onKeyDown={(event) => event.key === 'Enter' && selectEvidence(x)}>
            <b>{x.id}</b><small>{x.source} · {x.document_type} · SHA-256 {x.hash.slice(0, 14)}…</small><button onClick={(event) => { event.stopPropagation(); generateReport(); }} disabled={reportBusy}>{reportBusy ? 'Generating…' : 'Generate Report'}</button>
          </div>
          {selected?.id === x.id && <div className="evidence-details">
            <div className="evidence-detail-heading"><b>{selected.id}</b><span>{selected.source} · {selected.document_type}</span></div>
            <p>{selected.extracted_text || selected.preview || 'No stored evidence summary.'}</p>
            <div className="evidence-detail-grid">
              <div><h4>Linked entities</h4>{selectedDetails.length ? selectedDetails.map((entity: Any) => <div className="row" key={entity.entity.id}><b>{entity.entity.label}</b><small>{entity.entity.type} · {entity.entity.id}</small></div>) : <p>No linked entities recorded.</p>}</div>
              <div><h4>Linked relationships & case</h4><p>Case: <Badge>{selectedCase?.id || 'Not recorded'}</Badge> {selectedCase?.name}</p>{selectedDetails.flatMap((entity: Any) => entity.connections || []).filter((connection: Any, index: number, connections: Any[]) => connections.findIndex((candidate) => candidate.id === connection.id) === index).slice(0, 8).map((connection: Any) => <div className="row" key={connection.id}><b>{connection.type}</b><small>{connection.source} → {connection.target}</small></div>)}</div>
              <div><h4>Related risk signals</h4>{selectedDetails.flatMap((entity: Any) => entity.anomalies || []).filter((alert: Any, index: number, alerts: Any[]) => alerts.findIndex((candidate) => candidate.id === alert.id) === index).map((alert: Any) => <div className="feed" key={alert.id}><Badge>{alert.risk_level || alert.severity}</Badge> {alert.explanation}</div>)}{!selectedDetails.some((entity: Any) => entity.anomalies?.length) && <p>No related anomaly signals recorded.</p>}</div>
              <div><h4>Provenance & audit</h4><p>SHA-256: <span className="hash">{selected.hash}</span></p><p>Created: {selected.created_at}</p><p>Audit: {selected.audit?.length ? selected.audit.join(' · ') : 'No audit entries recorded.'}</p></div>
            </div>
          </div>}
        </div>)}</div>
      </Card>
      {report && (
        <Card title={report.title}>
          <div className="toolbar">
            <a href={API + '/api/reports/' + report.id + '/export/docx'}><button type="button">Download Word (.docx)</button></a>
            <a href={API + '/api/reports/' + report.id + '/export/pdf'}><button type="button">Download PDF</button></a>
          </div>
          <p>{report.executive_summary}</p>
          <h4>System findings</h4>
          <p>Key entities: {report.system_findings.key_entities.map((x: Any) => <Badge key={x.id}>{x.label} · {x.id}</Badge>)}</p>
          <p>Risk/anomaly findings: {report.system_findings.risk_anomalies.length ? report.system_findings.risk_anomalies.map((x: Any) => <Badge key={x.id}>{x.id} · {x.risk_level || x.severity}</Badge>) : 'None recorded.'}</p>
          <h4>Important relationships</h4>{report.system_findings.important_relationships.slice(0, 8).map((x: Any) => <div className="row" key={x.id}><b>{x.type}</b><small>{x.id} · {x.source} → {x.target} · {x.timestamp}</small></div>)}
          <h4>Cross-source correlations</h4>{report.system_findings.cross_source_correlations.length ? report.system_findings.cross_source_correlations.slice(0, 8).map((x: Any) => <div className="feed" key={x.id}>{x.explanation} Evidence: {x.evidence_ids.join(', ')}</div>) : <p>No observed cross-source correlations recorded.</p>}
          <h4>Timeline highlights</h4>{report.system_findings.timeline_highlights.map((x: Any) => <div className="row" key={x.id}><b>{x.type}</b><small>{x.timestamp} · {x.title} · Evidence {x.source || 'Not recorded'}</small></div>)}
          <h4>Source evidence</h4><p>Supporting Evidence IDs: {report.source_evidence.evidence_ids.length ? report.source_evidence.evidence_ids.map((x: string) => <Badge key={x}>{x}</Badge>) : 'None recorded.'}</p><p>SHA-256 integrity: <Badge>{report.source_evidence.verified_count} verified</Badge> <Badge>{report.source_evidence.issue_count} issues</Badge></p>
          <h4>Responsible-AI notice</h4><p>{report.disclaimer}</p>
        </Card>
      )}
    </>
  );
}

function CaseWorkspace({ caseId, cases, entities, evidence, user }: Any) {
  const [board, setBoard] = useState<Any>(); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [kind, setKind] = useState('NOTE'); const [refId, setRefId] = useState(''); const [title, setTitle] = useState(''); const [content, setContent] = useState(''); const [status, setStatus] = useState('OPEN');
  const [fromId, setFromId] = useState(''); const [toId, setToId] = useState(''); const [connectionLabel, setConnectionLabel] = useState('');
  const boardRef = useRef<HTMLElement>(null); const drag = useRef<Any>(undefined); const currentCase = cases.find((item: Any) => item.id === caseId); const items = board?.items || [];
  const isImage = (item: Any) => /\.(png|jpe?g|gif|webp|bmp)$/i.test(item?.source || '');
  function load() { setError(''); get('/api/blackboard?case_id=' + encodeURIComponent(caseId)).then(setBoard).catch((reason) => setError(reason instanceof Error ? reason.message : 'Unable to load this case workspace.')); }
  useEffect(load, [caseId]);
  useEffect(() => { setRefId(''); setFromId(''); setToId(''); }, [caseId]);
  useEffect(() => { if (kind === 'ENTITY' && entities[0]) setRefId(entities[0].id); if (kind === 'EVIDENCE' && evidence[0]) setRefId(evidence[0].id); if (kind === 'NOTE' || kind === 'HYPOTHESIS') setRefId(''); }, [kind, entities, evidence]);
  async function request(path: string, method: string, body?: Any) { const response = await fetch(API + path, { method, headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined }); const result = await response.json().catch(() => ({})); if (!response.ok) throw new Error(result.detail || `Workspace request failed (HTTP ${response.status}).`); return result; }
  async function addItem(event: React.FormEvent<HTMLFormElement>) { event.preventDefault(); if (!title.trim() || busy) return; setBusy(true); setError(''); try { const offset = items.length * 24; await request('/api/blackboard/items', 'POST', { case_id: caseId, kind, ref_id: refId || null, title: title.trim(), content: content.trim(), status: kind === 'HYPOTHESIS' ? status : '', x: 36 + (offset % 480), y: 36 + (offset % 300), created_by: user?.name || '' }); setTitle(''); setContent(''); load(); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to add card.'); } finally { setBusy(false); } }
  async function addConnection() { if (!fromId || !toId || fromId === toId || busy) return; setBusy(true); setError(''); try { await request('/api/blackboard/connections', 'POST', { case_id: caseId, from_id: fromId, to_id: toId, label: connectionLabel.trim() }); setConnectionLabel(''); load(); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to add connection.'); } finally { setBusy(false); } }
  async function updateItem(id: string, patch: Any) { try { const updated = await request('/api/blackboard/items/' + id, 'PATCH', patch); setBoard((value: Any) => ({ ...value, items: value.items.map((item: Any) => item.id === id ? updated : item) })); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to save card.'); } }
  async function removeItem(id: string) { try { await request('/api/blackboard/items/' + id, 'DELETE'); load(); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to remove card.'); } }
  function startDrag(event: React.PointerEvent<HTMLElement>, item: Any) { if ((event.target as HTMLElement).closest('button,select,a')) return; drag.current = { id: item.id, startX: event.clientX, startY: event.clientY, x: item.x, y: item.y }; event.currentTarget.setPointerCapture(event.pointerId); }
  function moveDrag(event: React.PointerEvent<HTMLElement>) { if (!drag.current) return; const state = drag.current; const x = Math.max(12, Math.min(1160, state.x + event.clientX - state.startX)); const y = Math.max(12, Math.min(660, state.y + event.clientY - state.startY)); setBoard((value: Any) => ({ ...value, items: value.items.map((item: Any) => item.id === state.id ? { ...item, x, y } : item) })); }
  function stopDrag() { if (!drag.current) return; const item = items.find((candidate: Any) => candidate.id === drag.current.id); drag.current = undefined; if (item) updateItem(item.id, { x: item.x, y: item.y }); }
  if (!board && !error) return <div className="loading">Loading live case workspace…</div>;
  return <><header><div><p className="eyebrow">LIVE INVESTIGATION BLACKBOARD / {caseId}</p><h1>Case Workspace</h1><p>Pin observed evidence and entities alongside investigator notes and testable hypotheses.</p></div><Badge>{currentCase?.status || 'CASE'}</Badge></header>{error && <p className="notice" role="alert">{error}</p>}
    <section className="workspace-metadata" aria-label="Case metadata"><div><span>Case</span><b>{currentCase?.name || caseId}</b></div><div><span>Investigator</span><b>{currentCase?.investigator || 'Unassigned'}</b></div><div><span>Priority</span><b>{currentCase?.priority || 'Not recorded'}</b></div><div><span>Stage</span><b>{currentCase?.stage?.replaceAll('_', ' ') || 'Not recorded'}</b></div></section>
    <Card title="Add to case board"><form className="blackboard-toolbar" onSubmit={addItem}><select value={kind} onChange={(event) => setKind(event.target.value)} aria-label="Card type"><option value="EVIDENCE">Evidence</option><option value="ENTITY">Entity</option><option value="NOTE">Investigator note</option><option value="HYPOTHESIS">Hypothesis</option></select>{(kind === 'ENTITY' || kind === 'EVIDENCE') && <select value={refId} onChange={(event) => setRefId(event.target.value)} aria-label="Source record"><option value="">Select existing {kind.toLowerCase()}</option>{(kind === 'ENTITY' ? entities : evidence).map((item: Any) => <option key={item.id} value={item.id}>{item.id} · {item.label || item.source}</option>)}</select>}<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder={kind === 'NOTE' ? 'Note title' : kind === 'HYPOTHESIS' ? 'Hypothesis statement' : 'Card label'} required />{kind === 'HYPOTHESIS' && <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Hypothesis status"><option value="OPEN">Open</option><option value="SUPPORTED">Supported</option><option value="CHALLENGED">Challenged</option><option value="REJECTED">Rejected</option></select>}<button type="submit" disabled={busy || ((kind === 'ENTITY' || kind === 'EVIDENCE') && !refId)}>{busy ? 'Adding…' : 'Add card'}</button><textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="Context, observation, or rationale (optional)" aria-label="Card details" /></form><div className="blackboard-picker"><b>Connect cards</b><select value={fromId} onChange={(event) => setFromId(event.target.value)} aria-label="Connection source"><option value="">From card</option>{items.map((item: Any) => <option key={item.id} value={item.id}>{item.kind}: {item.title}</option>)}</select><select value={toId} onChange={(event) => setToId(event.target.value)} aria-label="Connection target"><option value="">To card</option>{items.map((item: Any) => <option key={item.id} value={item.id}>{item.kind}: {item.title}</option>)}</select><input value={connectionLabel} onChange={(event) => setConnectionLabel(event.target.value)} placeholder="Relationship label (optional)" /><button type="button" onClick={addConnection} disabled={busy || !fromId || !toId || fromId === toId}>Connect</button></div></Card>
    <section className="blackboard-board" ref={boardRef} aria-label="Investigation case board">{!items.length && <div className="blackboard-empty"><b>Your board is ready.</b><p>Add existing evidence or entities, then capture notes and hypotheses to connect the investigation.</p></div>}<svg className="blackboard-strings" viewBox="0 0 1400 760" aria-label="Card relationships">{(board?.connections || []).map((connection: Any) => { const source = items.find((item: Any) => item.id === connection.from_id); const target = items.find((item: Any) => item.id === connection.to_id); if (!source || !target) return null; return <g key={connection.id}><line className="blackboard-string" x1={source.x + 108} y1={source.y + 70} x2={target.x + 108} y2={target.y + 70} /><text className="blackboard-string-label" x={(source.x + target.x) / 2 + 108} y={(source.y + target.y) / 2 + 64}>{connection.label}</text></g>; })}</svg>{items.map((item: Any) => { const reference = item.kind === 'ENTITY' ? entities.find((value: Any) => value.id === item.ref_id) : evidence.find((value: Any) => value.id === item.ref_id); return <article key={item.id} className={'blackboard-card kind-' + item.kind.toLowerCase()} style={{ left: item.x, top: item.y }} onPointerDown={(event) => startDrag(event, item)} onPointerMove={moveDrag} onPointerUp={stopDrag} onPointerCancel={stopDrag}><div className="blackboard-card-head"><Badge>{item.kind === 'NOTE' ? 'NOTE' : item.kind}</Badge><button className="blackboard-card-x" onClick={() => removeItem(item.id)} aria-label={'Remove ' + item.title}>×</button></div>{item.kind === 'EVIDENCE' && isImage(reference) && <img className="blackboard-image" src={API + '/api/evidence/' + item.ref_id + '/file'} alt={'Evidence preview: ' + item.title} />}<b className="blackboard-card-title">{item.title}</b>{item.ref_id && <small className="blackboard-ref">{item.ref_id} · {reference?.type || reference?.document_type || 'source record'}</small>}<p className="blackboard-card-content">{item.content || reference?.extracted_text?.slice(0, 150) || reference?.label || 'No additional context recorded.'}</p>{item.kind === 'HYPOTHESIS' && <select value={item.status || 'OPEN'} onChange={(event) => updateItem(item.id, { status: event.target.value })} aria-label={'Status for ' + item.title}><option value="OPEN">Open</option><option value="SUPPORTED">Supported</option><option value="CHALLENGED">Challenged</option><option value="REJECTED">Rejected</option></select>}<button className="blackboard-connect" onClick={() => { setFromId(item.id); if (toId === item.id) setToId(''); }}>Use as connection source</button></article>; })}</section>
  </>;
}

function Settings({ theme, onChange, user }: Any) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function changePassword(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setStatus(''); setError('');
    if (newPassword !== confirmPassword) { setError('New passwords do not match.'); return; }
    setBusy(true);
    try {
      const token = localStorage.getItem('shadowintel-token');
      const response = await fetch(API + '/api/auth/change-password', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || 'Unable to change password.');
      setCurrentPassword(''); setNewPassword(''); setConfirmPassword(''); setStatus(result.message);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to change password.'); }
    finally { setBusy(false); }
  }
  return <>
    <header><div><p className="eyebrow">WORKSPACE PREFERENCES</p><h1>Settings</h1><p>Manage your account and investigation workspace.</p></div></header>
    <div className="settings-grid">
      <Card title="Appearance"><p>Interface mode</p><ThemeToggle theme={theme} onChange={onChange} /></Card>
      <Card title="Account"><p><b>{user?.name || 'Investigator'}</b></p><p>{user?.email}</p></Card>
      <Card title="Change password"><form className="auth-form" onSubmit={changePassword}>
        <label>Current password<input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} autoComplete="current-password" required /></label>
        <label>New password<input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" minLength={8} required /></label>
        <label>Confirm new password<input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} autoComplete="new-password" minLength={8} required /></label>
        {error && <p className="notice auth-error" role="alert">{error}</p>}
        {status && <p className="notice" role="status">{status}</p>}
        <button type="submit" disabled={busy}>{busy ? 'Changing…' : 'Change password'}</button>
      </form></Card>
    </div>
  </>;
}

function DashboardApp() {
  const router = useRouter();
  const [theme, setTheme] = useTheme();
  const [page, setPage] = useState(nav[0]);
  const [dash, setDash] = useState<Any>();
  const [entities, setEntities] = useState<Any[]>([]);
  const [graph, setGraph] = useState<Any>();
  const [anoms, setAnoms] = useState<Any[]>([]);
  const [timeline, setTimeline] = useState<Any[]>([]);
  const [evidence, setEvidence] = useState<Any[]>([]);
  const [error, setError] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [search, setSearch] = useState('');
  const [searchResults, setSearchResults] = useState<Any[]>([]);
  const [selectedEntityId, setSelectedEntityId] = useState('');
  const [focusEvidenceId, setFocusEvidenceId] = useState('');
  const [user, setUser] = useState<Any>();
  const [cases, setCases] = useState<Any[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState('CASE-SL-01');
  useEffect(() => {
    const token = localStorage.getItem('shadowintel-token');
    if (!token) { router.replace('/login'); return; }
    fetch(API + '/api/auth/me', { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        if (!response.ok) throw new Error('Session is no longer valid');
        return response.json();
      })
      .then((account) => {
        setUser(account);
        setAuthenticated(true);
      })
      .catch(() => { localStorage.removeItem('shadowintel-token'); router.replace('/login'); });
  }, [router]);
  useEffect(() => {
    if (!authenticated) return;
    get('/api/cases').then((result) => { setCases(result.cases); if (result.cases.some((item: Any) => item.id === selectedCaseId)) return; if (result.cases[0]) setSelectedCaseId(result.cases[0].id); }).catch((e) => setError(e instanceof Error ? e.message : 'Failed to load cases'));
  }, [authenticated, selectedCaseId]);
  useEffect(() => {
    if (!authenticated) return;
    const scope = `?case_id=${encodeURIComponent(selectedCaseId)}`;
    Promise.all([get('/api/dashboard/summary' + scope), get('/api/entities' + scope), get('/api/graph' + scope), get('/api/anomalies' + scope), get('/api/timeline' + scope), get('/api/evidence' + scope)])
      .then(([d, e, g, a, t, v]) => { setDash(d); setEntities(e); setGraph(g); setAnoms(a); setTimeline(t); setEvidence(v); })
      .catch((e) => setError(e instanceof Error ? e.message : 'Backend request failed'));
  }, [authenticated, selectedCaseId]);
  useEffect(() => {
    const term = search.trim();
    if (term.length < 2) { setSearchResults([]); return; }
    const timer = window.setTimeout(() => { get('/api/entities?q=' + encodeURIComponent(term)).then((results) => setSearchResults(results.slice(0, 8))).catch(() => setSearchResults([])); }, 180);
    return () => window.clearTimeout(timer);
  }, [search]);
  function signOut() { localStorage.removeItem('shadowintel-token'); router.replace('/login'); }
  function openEntity(entity: Any) { setSelectedEntityId(entity.id); setPage(nav[4]); setSearch(''); setSearchResults([]); }
  function openEvidence(id: string) { setFocusEvidenceId(id); setPage(nav[8]); }
  const body =
    page === nav[0] ? <Dashboard d={dash} graph={graph} theme={theme} error={error} /> :
    page === nav[1] ? <CaseManagement onCaseChanged={() => get('/api/cases').then((result) => setCases(result.cases)).catch(() => {})} onUploadCase={(caseId) => { setSelectedCaseId(caseId); setPage(nav[2]); }} /> :
    page === nav[2] ? <Ingest cases={cases} selectedCaseId={selectedCaseId} onCaseChange={setSelectedCaseId} /> :
    page === nav[3] ? <Explorer entities={entities} theme={theme} /> :
    page === nav[4] ? <EnhancedEntity entities={entities} selectedId={selectedEntityId} /> :
    page === nav[5] ? <HybridAnomalies data={anoms} /> :
    page === nav[6] ? <Timeline data={timeline} entities={entities} anomalies={anoms} /> :
    page === nav[7] ? <Assistant selectedCaseId={selectedCaseId} onOpenEvidence={openEvidence} /> :
    page === nav[9] ? <CaseWorkspace caseId={selectedCaseId} cases={cases} entities={entities} evidence={evidence} user={user} /> :
    page === 'Settings' ? <Settings theme={theme} onChange={setTheme} user={user} /> :
    <Evidence data={evidence} focusId={focusEvidenceId} />;
  if (!authenticated) return <div className="loading">Verifying secure workspace access…</div>;
  return (
    <main className={sidebarOpen ? '' : 'sidebar-hidden'}>
      <aside className="side">
        <div className="brand"><span className="mark">SHADOW<span>INTEL</span></span><small>INVESTIGATION WORKSPACE</small></div>
        <nav>{nav.map((x) => <button className={page === x ? 'active' : ''} onClick={() => setPage(x)} key={x}>{x}</button>)}</nav>
        <div className="disclaimer">ShadowIntel assists investigation and evidence analysis. It does not determine guilt, criminality, or legal responsibility.</div>
        <div className="account-footer">
          <div className="account-details"><b>{user?.name || 'Investigator'}</b><small>{user?.email || 'Account'}</small></div>
          <button className={page === 'Settings' ? 'account-action active' : 'account-action'} onClick={() => setPage('Settings')}>Settings</button>
          <button className="account-action" onClick={signOut}>Sign out</button>
        </div>
      </aside>
      <section className="content">
        <div className="top">
          <TopSearch value={search} results={searchResults} onChange={setSearch} onSelect={openEntity} />
          <label className="workspace-case-picker">Case
            <select value={selectedCaseId} onChange={(event) => setSelectedCaseId(event.target.value)}>{cases.map((item: Any) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
          </label>
          <button className="sidebar-toggle" onClick={() => setSidebarOpen((v) => !v)} aria-label="Toggle sidebar">☰</button>
          <div className="spacer" />
        </div>
        {body}
      </section>
    </main>
  );
}

function LandingPage() {
  return <main className="landing-shell">
    <nav className="landing-nav"><div className="brand landing-brand"><span className="mark">SHADOW<span>INTEL</span></span><small>INVESTIGATION WORKSPACE</small></div><div className="landing-nav-links"><a href="#capabilities">Capabilities</a><a href="#workflow">Workflow</a><Link className="landing-signin" href="/signup">Create Account</Link></div></nav>
    <section className="landing-hero"><div className="hero-copy"><p className="eyebrow">NETWORK INTELLIGENCE / 01</p><h1>AI-Powered Criminal Network Analysis</h1><p className="hero-lede">Connect fragmented intelligence, surface meaningful risk signals, and move from raw evidence to an explainable investigation.</p><div className="hero-actions"><Link className="landing-primary" href="/dashboard">Start Investigation <span>→</span></Link><Link className="landing-secondary" href="/signup">Create Account</Link></div><p className="hero-note">Evidence-backed analysis for investigators, analysts, and intelligence teams.</p></div><div className="hero-console" aria-label="Network intelligence preview"><div className="console-bar"><span>LIVE CASE GRAPH</span><i /> <b>OPERATIONAL</b></div><div className="console-map"><span className="map-line line-a" /><span className="map-line line-b" /><span className="map-line line-c" /><span className="map-node node-a" /><span className="map-node node-b" /><span className="map-node node-c" /><span className="map-node node-d" /><strong>128</strong><small>linked entities</small></div><div className="console-footer"><span>42 evidence sources</span><span>08 active signals</span></div></div></section>
    <section className="landing-section" id="capabilities"><div className="section-intro"><p className="eyebrow">CORE CAPABILITIES</p><h2>See the network behind the record.</h2></div><div className="feature-grid"><article><span className="feature-index">01</span><h3>Network Intelligence</h3><p>Map entities, relationships, communities, and influence from the live investigation graph.</p></article><article><span className="feature-index">02</span><h3>Multi-Source Correlation</h3><p>Connect observed signals across calls, transactions, locations, and evidence records.</p></article><article><span className="feature-index">03</span><h3>Risk & Anomaly Detection</h3><p>Prioritize explainable risk indicators with transparent rule and graph signals.</p></article><article><span className="feature-index">04</span><h3>Evidence & Reports</h3><p>Trace findings back to source evidence, provenance, and integrity verification.</p></article></div></section>
    <section className="landing-section workflow-section" id="workflow"><div className="section-intro"><p className="eyebrow">INVESTIGATION FLOW</p><h2>From signal to supported finding.</h2></div><div className="workflow"><div><b>01</b><span>Ingest</span><small>Bring in source material</small></div><div><b>02</b><span>Extract</span><small>Resolve useful entities</small></div><div><b>03</b><span>Correlate</span><small>Connect observed signals</small></div><div><b>04</b><span>Investigate</span><small>Explore the network</small></div><div><b>05</b><span>Report</span><small>Preserve the evidence trail</small></div></div></section>
    <footer className="landing-footer" id="future-access"><div className="brand"><span className="mark">SHADOW<span>INTEL</span></span></div><p>ShadowIntel supports investigation and evidence analysis. It does not determine guilt, criminality, or legal responsibility.</p><span className="footer-status">SYSTEM / EVIDENCE-FIRST</span></footer>
  </main>;
}

export default function AppRouter() {
  const pathname = usePathname();
  return pathname === '/' ? <LandingPage /> : <DashboardApp />;
}
