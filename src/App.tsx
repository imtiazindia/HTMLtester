import { useEffect, useRef, useState } from 'react';
import { Download, FileText, LoaderCircle, LogOut, Upload } from 'lucide-react';
import PdfPane from './PdfPane';
import HtmlPane from './HtmlPane';
import Telemetry from './Telemetry';
import { request, signIn, uploadFile, type Config, type Job, type Session, type TelemetryEvent } from './api';

const engines = [
  { id:'pdf2htmlEX', label:'pdf2htmlEX', detail:'Fixed page layout · Embedded fonts · GPLv3+' },
  { id:'docling', label:'Docling', detail:'Layout and table models · CPU, OCR off · MIT code' },
  { id:'opendataloader', label:'OpenDataLoader PDF', detail:'Deterministic local mode · CPU, no hybrid AI · Apache 2.0' }
];
export default function App() {
  const [config,setConfig] = useState<Config | null>(null);
  const [session,setSession] = useState<Session | null>(null);
  const [file,setFile] = useState<File | null>(null);
  const [uploadId,setUploadId] = useState('');
  const [engine,setEngine] = useState('pdf2htmlEX');
  const [results,setResults] = useState<Record<string,{job:Job;html:string}>>({});
  const [telemetryOpen,setTelemetryOpen] = useState(false);
  const [currentJob,setCurrentJob] = useState<Job>();
  const [clientEvents,setClientEvents] = useState<TelemetryEvent[]>([]);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [username,setUsername] = useState('upSkillAir');
  const [password,setPassword] = useState('');
  const [authBusy,setAuthBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const generation = useRef(0);
  const active = results[engine];
  useEffect(() => { fetch('/config.json').then(r=>r.json()).then(setConfig).catch(()=>setError('Could not load app configuration. Please refresh.')); }, []);
  useEffect(() => () => { generation.current++; }, []);
  function choose(next?:File) {
    if (!next || busy) return;
    if (!next.name.toLowerCase().endsWith('.pdf') || next.size > 20*1024*1024 || !next.size) { setError('Choose a non-empty PDF of at most 20 MB.'); return; }
    generation.current++; setFile(next); setUploadId(''); setResults({}); setError('');
  }
  async function convert() {
    if (!config || !session || !file || busy) return;
    setBusy(true); setError(''); setCurrentJob(undefined);
    setClientEvents([{time:new Date().toISOString(),message:uploadId ? 'Reusing the uploaded PDF.' : 'Uploading PDF to private storage.'}]);
    const run = generation.current;
    const chosen = engine;
    try {
      const id = uploadId || await uploadFile(config,session,file);
      if (run!==generation.current) return;
      setUploadId(id);
      let job = await request<Job>(config,session,'/jobs',{ uploadId:id, engine:chosen });
      setCurrentJob(job);
      setResults(r=>({...r,[chosen]:{job,html:''}}));
      const deadline = Date.now()+17*60*1000;
      while (job.status==='running' || job.status==='queued') {
        if (Date.now()>deadline) throw new Error('Conversion timed out. Try a smaller document.');
        await new Promise(resolve=>setTimeout(resolve,2500));
        if (run!==generation.current) return;
        job = {...await request<Job>(config,session,`/jobs/${job.id}`),id:job.id};
        setCurrentJob(job);
      setResults(r=>({...r,[chosen]:{job,html:''}}));
      }
      if (job.status==='failed') throw new Error(job.error || 'Conversion failed.');
      const response = await fetch(job.url!);
      if (!response.ok) throw new Error('Could not retrieve the converted HTML. Please retry.');
      const html = await response.text();
      if (run===generation.current) setResults(r=>({...r,[chosen]:{job,html}}));
    } catch(error) { if(run===generation.current) setError(error instanceof Error ? error.message : 'Conversion failed.'); }
    finally { if(run===generation.current) setBusy(false); }
  }
  function download() {
    if (!active?.html) return;
    const url=URL.createObjectURL(new Blob([active.html],{type:'text/html;charset=utf-8'}));
    const a=document.createElement('a'); a.href=url; a.download=`${file?.name.replace(/\.pdf$/i,'')}-${engine}.html`; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function logout() { setTelemetryOpen(false);setCurrentJob(undefined);setClientEvents([]);generation.current++; setSession(null); setFile(null); setResults({}); setBusy(false);setUploadId('');setError(''); }
  return <><header className="header"><a className="brand" href="/"><span className="brand-mark"><FileText size={22}/></span>HTMLtester</a><div className="header-actions"><button className="telemetry-launch" disabled={!session} onClick={()=>setTelemetryOpen(true)}>Telemetry</button>{session && <button className="quiet" onClick={logout}><LogOut size={16}/>Sign out</button>}<button className="primary" disabled={busy} onClick={()=>input.current?.click()}><Upload size={17}/>Upload PDF</button></div><input ref={input} className="sr-only" type="file" accept="application/pdf,.pdf" aria-label="Choose PDF file" onChange={e=>{choose(e.target.files?.[0]);e.target.value='';}}/></header>
    <main onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();choose(e.dataTransfer.files[0]);}}>
      <div className="intro"><h1>Compare your PDF, side by side.</h1><p>Explore how different engines preserve layout and structure.</p></div>
      {config && !session && <form className="login" onSubmit={async e=>{e.preventDefault();setAuthBusy(true);setError('');try {setSession(await signIn(config,username,password));setPassword('');} catch(error) {setError(error instanceof Error?error.message:'Sign-in failed.');} finally {setAuthBusy(false);}}}><div><strong>Your private workspace</strong><p>Sign in to run conversions. PDF preview works locally.</p></div><label>Username<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required/></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/></label><button className="primary" disabled={authBusy || !config.clientId}>{authBusy?'Signing in…':'Sign in'}</button></form>}
      <div className="conversion-bar"><label className="file-label">File<button className="file-choice" onClick={()=>input.current?.click()} disabled={busy}><FileText size={18}/><span>{file?.name || 'Choose or drop a PDF'}</span></button></label><label className="engine-label">Converter<select value={engine} onChange={e=>setEngine(e.target.value)}>{engines.map(item=><option key={item.id} value={item.id}>{item.label}{results[item.id]?.job.status==='complete'?' ✓':''}</option>)}</select></label><button className="primary" disabled={!file || !session || busy} onClick={convert}>{busy?<LoaderCircle size={17} className="spin"/>:<span aria-hidden="true">↻</span>}{busy?'Converting…':'Convert'}</button><button className="download" disabled={!active?.html} onClick={download}><Download size={17}/>Download HTML</button></div>
      <div className="context-row"><span>{engines.find(item=>item.id===engine)?.detail}</span><span>Digital PDFs · Up to 20 MB / 40 pages</span></div>
      {error && <div className="error" role="alert">{error}</div>}
      <div className="comparison"><PdfPane file={file}/><HtmlPane html={active?.html||''} job={active?.job} engine={engine}/></div>
      <footer><span className="status" role="status"><i className={busy?'working':''}/>{busy?'Conversion in progress':active?.job.status==='complete'?'Conversion complete':file?'Ready to convert':'Ready to compare'}</span><span>Preview is isolated · Temporary uploads expire automatically</span></footer>
      <details className="notes"><summary>About the comparison</summary><p>pdf2htmlEX aims to preserve page appearance. Docling and OpenDataLoader reconstruct content structure and may reflow text. OpenDataLoader uses its deterministic CPU mode, not the hybrid mode used for its strongest published benchmark scores. OCR is disabled in Docling. Mathematical notation and complex tables may need review.</p><p>The preview removes scripts and blocks external resources. Download HTML exports the original converter output. Preview page layout may differ from opening the downloaded file. Files are private and eligible for automatic S3 deletion after one day; deletion is asynchronous.</p><p><a href="https://github.com/imtiazindia/HTMLtester" target="_blank" rel="noreferrer">Source and research notes</a></p></details>
    </main>{telemetryOpen && config && session && <Telemetry config={config} session={session} job={currentJob} events={clientEvents} error={error} close={()=>setTelemetryOpen(false)} logged={id=>setCurrentJob(current=>current?.id===id ? {...current,logError:undefined} : current)}/>}</>;
}
