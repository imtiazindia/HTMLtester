import { useMemo, useState } from 'react';
import DOMPurify from 'dompurify';
import { Code2 } from 'lucide-react';
import type { Job } from './api';

export default function HtmlPane({ html, job, engine }: { html: string; job?: Job; engine: string }) {
  const [mode, setMode] = useState('preview');
  const preview = useMemo(() => {
    if (!html) return '';
    const clean = DOMPurify.sanitize(html, { WHOLE_DOCUMENT: true, ADD_TAGS: ['style'], FORBID_TAGS: ['script','iframe','object','embed','form','base','meta','link'], FORBID_ATTR: ['srcset'] });
    const policy = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; font-src data:;">`;
    const fix = engine === 'pdf2htmlEX' ? '<style>#sidebar{display:none!important}#page-container{position:static!important;overflow:visible!important;background:#fff!important}.pf,.pc{display:block!important}.pf{margin:12px auto!important}</style>' : '<style>body{margin:24px;color:#182036;font-family:Georgia,serif;line-height:1.55}img{max-width:100%;height:auto}table{border-collapse:collapse;max-width:100%}td,th{border:1px solid #ccd0da;padding:6px}pre{white-space:pre-wrap}</style>';
    return clean.replace(/<head[^>]*>/i, '<head>'+policy+fix);
  }, [html, engine]);
  return <section className="pane" aria-label="Converted HTML"><div className="pane-title"><h2>Converted HTML</h2><span>{engine === 'opendataloader' ? 'OpenDataLoader' : engine === 'docling' ? 'Docling' : engine}</span></div>
    <div className="pane-toolbar"><div className="view-toggle" aria-label="HTML view"><button aria-pressed={mode==='preview'} onClick={() => setMode('preview')}>Preview</button><button aria-pressed={mode==='source'} onClick={() => setMode('source')}>HTML source</button></div><span className="muted output-meta">{job?.status==='complete' ? `${job.seconds}s · ${((job.bytes||0)/1024).toFixed(0)} KB` : 'Output'}</span></div>
    <div className="html-content">{html ? mode==='preview' ? <iframe title="Converted HTML preview" sandbox="" srcDoc={preview}/> : <pre tabIndex={0} aria-label="HTML source code">{html}</pre> : <div className="empty"><Code2 size={36}/><h3>{job?.status==='running' || job?.status==='queued' ? 'Converting your document…' : job?.status==='failed' ? 'Conversion couldn’t finish' : 'A new perspective on your PDF'}</h3><p>{job?.status==='running' || job?.status==='queued' ? 'The first run can take a few minutes. You can keep viewing the original.' : job?.error || 'Choose an engine, then select Convert.'}</p></div>}</div>
  </section>;
}
