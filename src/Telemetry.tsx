import { useEffect, useMemo, useRef, useState } from 'react';
import { Download, FileText, Save, X } from 'lucide-react';
import { request, type Config, type Job, type Session, type TelemetryEvent } from './api';

type SavedLog = { id: string; created: number; engine: string; status: string; filename: string; text?: string };
type Props = { config: Config; session: Session; job?: Job; events: TelemetryEvent[]; error: string; close: () => void; logged: (id: string) => void };
export default function Telemetry({ config, session, job, events, error: operationError, close, logged }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const consoleView = useRef<HTMLPreElement>(null);
  const [logs, setLogs] = useState<SavedLog[]>([]);
  const [selected, setSelected] = useState('live');
  const [saved, setSaved] = useState<SavedLog>();
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [follow, setFollow] = useState(true);
  const [notice, setNotice] = useState('');
  function dismiss() { dialog.current?.close(); close(); }
  useEffect(() => {
    const node = dialog.current!; node.showModal();
    return () => node.close();
  }, []);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const result = await request<{logs: SavedLog[]}>(config, session, '/logs');
        if (!stopped) setLogs(result.logs);
      } catch (e) { if (!stopped) setError(e instanceof Error ? e.message : 'Could not load saved logs.'); }
      finally { if (!stopped) timer = setTimeout(refresh, 5000); }
    }
    void refresh();
    return () => { stopped = true; clearTimeout(timer); };
  }, [config, session]);
  useEffect(() => {
    if (selected !== 'live' && !logs.some(item => item.id === selected)) {
      setSelected('live'); setSaved(undefined);
      setNotice('The selected log was removed by the three-operation retention limit.');
    }
  }, [logs, selected]);
  useEffect(() => {
    setSaved(undefined);
    if (selected === 'live') return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const result = await request<SavedLog>(config, session, '/logs/'+selected);
        if (!stopped) { setSaved(result); setError(''); }
        if (!stopped && ['running','queued'].includes(result.status)) timer = setTimeout(refresh, 3000);
      } catch (e) { if (!stopped) { setSaved(undefined); setError(e instanceof Error ? e.message : 'Could not read log.'); } }
    }
    void refresh();
    return () => { stopped = true; clearTimeout(timer); };
  }, [selected, config, session]);
  const text = useMemo(() => selected !== 'live' ? saved?.text || 'Loading saved log…' : [
    ...events.map(item => `${item.time}  ${item.message}`),
    ...(job?.droppedEvents ? [`[Earlier converter output omitted: ${job.droppedEvents} events]`] : []),
    ...(job?.events || []).map(item => `${item.time}  ${item.message}`),
    ...(operationError ? [`ERROR: ${operationError}`] : [])
  ].join('\n') || 'Start a conversion to see its execution here.', [selected, saved, events, job, operationError]);
  useEffect(() => {
    if (follow && consoleView.current) consoleView.current.scrollTop = consoleView.current.scrollHeight;
  }, [text, follow]);
  const recorded = !job?.logError && logs.some(item => item.id === job?.id);
  async function log() {
    if (!job) return;
    setSaving(true); setError('');
    try {
      const result = await request<{saved:boolean}>(config, session, `/jobs/${job.id}/log`, {});
      if (!result.saved) throw new Error('This operation is older than your three retained logs.');
      logged(job.id);
      setLogs((await request<{logs: SavedLog[]}>(config, session, '/logs')).logs);
      setNotice('Log saved. Recording continues until the conversion finishes, even if this window is closed.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not save log.'); }
    finally { setSaving(false); }
  }
  async function download() {
    const id = selected === 'live' ? job?.id : selected;
    if (!id) return;
    try {
      const result = await request<SavedLog>(config, session, '/logs/'+id);
      const url = URL.createObjectURL(new Blob([result.text || ''], {type:'text/plain;charset=utf-8'}));
      const a = document.createElement('a'); a.href = url; a.download = result.filename; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not download log.'); }
  }
  return <dialog className="telemetry-dialog" ref={dialog} aria-labelledby="telemetry-title" onCancel={e=>{e.preventDefault();dismiss();}}>
    <div className="telemetry-heading"><div><h2 id="telemetry-title">Telemetry</h2><p>Live execution and saved operation logs</p></div><button onClick={dismiss}><X size={16}/>Close</button></div>
    <div className="telemetry-layout"><aside aria-label="Operation logs"><button aria-pressed={selected==='live'} onClick={()=>{setSelected('live');setError('');}}>Current operation<span>{job ? `${job.engine} · ${job.status}` : 'Waiting for a conversion'}</span></button><h3>Saved logs ({logs.length}/3)</h3>{logs.map(item=><button key={item.id} aria-pressed={selected===item.id} onClick={()=>{setSelected(item.id);setError('');}}><FileText size={14}/>{item.engine}<span>{new Date(item.created*1000).toLocaleString()} · {item.status}</span></button>)}{!logs.length && <p>No saved logs yet. Select Log during or after a conversion.</p>}<p>Only the latest three saved operations are retained. Older logs are deleted automatically.</p></aside>
    <section className="telemetry-main" aria-label="Execution console"><div className="telemetry-toolbar"><span role="status">{selected==='live' ? job ? `${job.engine} · ${job.status}` : 'Ready' : saved ? `${saved.engine} · ${saved.status}` : 'Loading…'}</span><label><input type="checkbox" checked={follow} onChange={e=>setFollow(e.target.checked)}/>Follow output</label></div><pre ref={consoleView} tabIndex={0} aria-label="Execution log">{text}</pre><p className="telemetry-hint">Updates about every 2 seconds. Quiet processes show an elapsed-time heartbeat. Logs retain up to 500 events, with long lines shortened.</p></section></div>
    {(error || job?.logError) && <p className="error" role="alert">{error || job?.logError}</p>}{notice && <p className="telemetry-notice" role="status">{notice}</p>}
    <div className="telemetry-actions"><span>{!job ? 'Log becomes available once the upload is queued.' : recorded ? 'Current operation is logged.' : 'Log saves the full server operation, including earlier events.'}</span><button onClick={download} disabled={selected==='live' ? !recorded : !saved}><Download size={16}/>Download log</button><button className="primary" onClick={log} disabled={!job || saving || recorded || selected!=='live'}><Save size={16}/>{saving ? 'Saving…' : recorded ? 'Logged' : 'Log'}</button></div>
  </dialog>;
}
