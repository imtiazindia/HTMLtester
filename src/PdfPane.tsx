import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, FileText } from 'lucide-react';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

export default function PdfPane({ file }: { file: File | null }) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState('');
  const [width, setWidth] = useState(600);
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const observer = new ResizeObserver(entries => setWidth(entries[0].contentRect.width));
    if (host.current) observer.observe(host.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    let gone = false;
    let task: ReturnType<typeof import('pdfjs-dist')['getDocument']> | undefined;
    setDoc(null); setPage(1); setError('');
    if (file) (async () => {
      const pdf = await import('pdfjs-dist');
      pdf.GlobalWorkerOptions.workerSrc = workerUrl;
      const data = new Uint8Array(await file.arrayBuffer());
      if (gone) return;
      task = pdf.getDocument({ data });
      const loaded = await task.promise;
      if (!gone) setDoc(loaded);
    })().catch(error => { if (!gone) setError(error.name === 'PasswordException' ? 'Please use an unlocked PDF.' : 'This PDF could not be displayed.'); });
    return () => { gone = true; void task?.destroy(); };
  }, [file]);
  useEffect(() => {
    if (!doc || !canvas.current) return;
    let gone = false;
    let render: ReturnType<Awaited<ReturnType<PDFDocumentProxy['getPage']>>['render']> | undefined;
    (async () => {
      const pdfPage = await doc.getPage(page);
      if (gone || !canvas.current) return;
      const base = pdfPage.getViewport({ scale: 1 });
      const scale = Math.max(0.15, (width - 32) / base.width) * zoom;
      const viewport = pdfPage.getViewport({ scale });
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      const element = canvas.current;
      element.width = viewport.width * pixelRatio; element.height = viewport.height * pixelRatio;
      element.style.width = viewport.width + 'px'; element.style.height = viewport.height + 'px';
      render = pdfPage.render({ canvas: element, viewport, transform: [pixelRatio,0,0,pixelRatio,0,0] });
      await render.promise;
    })().catch(error => { if (!gone && error.name !== 'RenderingCancelledException') setError('Unable to render this page.'); });
    return () => { gone = true; render?.cancel(); };
  }, [doc, page, zoom, width]);
  return <section className="pane" aria-label="Source PDF"><div className="pane-title"><h2>Source PDF</h2><span>PDF.js</span></div>
    <div className="pane-toolbar"><button className="icon-button" aria-label="Previous PDF page" disabled={!doc || page === 1} onClick={() => setPage(p => p-1)}><ChevronLeft size={18}/></button>
    <span className="page-number">{doc ? page : '—'}</span><span className="muted">/ {doc?.numPages ?? '—'}</span>
    <button className="icon-button" aria-label="Next PDF page" disabled={!doc || page === doc.numPages} onClick={() => setPage(p => p+1)}><ChevronRight size={18}/></button>
    <select aria-label="PDF zoom" value={zoom} onChange={e => setZoom(Number(e.target.value))}><option value={1}>Fit width</option><option value={1.25}>125%</option><option value={1.5}>150%</option><option value={2}>200%</option></select></div>
    <div className="pdf-scroll" ref={host}>{error ? <p role="alert" className="empty">{error}</p> : !file ? <div className="empty"><FileText size={36}/><h3>Your original document</h3><p>Upload a PDF to start comparing.</p></div> : <><canvas ref={canvas} aria-label={`PDF page ${page}`}/>{!doc && <p className="empty">Opening PDF…</p>}</>}</div>
  </section>;
}
