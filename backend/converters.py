"""Independent adapters: never substitute one engine's output for another."""
from pathlib import Path
import subprocess
import sys
import time
from pypdf import PdfReader

ENGINES = {'pdf2htmlEX', 'docling', 'opendataloader'}
MAX_PAGES = 40

def validate_pdf(source: Path):
    if source.stat().st_size > 20 * 1024 * 1024:
        raise ValueError('PDF must be 20 MB or smaller.')
    if not source.read_bytes()[:1024].lstrip().startswith(b'%PDF-'):
        raise ValueError('The uploaded file is not a PDF.')
    reader = PdfReader(source)
    if reader.is_encrypted:
        raise ValueError('Password-protected PDFs are not supported. Upload an unlocked copy.')
    pages = len(reader.pages)
    if not 1 <= pages <= MAX_PAGES:
        raise ValueError(f'Please upload a PDF with 1–{MAX_PAGES} pages.')
    return pages

def convert(source: Path, output: Path, engine: str):
    if engine not in ENGINES:
        raise ValueError('Unknown conversion engine.')
    pages = validate_pdf(source)
    start = time.monotonic()
    # A child process provides a real timeout and releases model memory after each job.
    run = subprocess.run([sys.executable, str(Path(__file__).with_name('run_engine.py')),
                          engine, str(source), str(output)],
                         capture_output=True, text=True, timeout=720)
    if run.returncode:
        print(f'{engine} failed: {run.stderr[-4000:]}')
        raise RuntimeError(f'{engine} could not convert this document. Try another engine.')
    if not output.exists() or not output.stat().st_size:
        raise RuntimeError('The converter returned no HTML.')
    if output.stat().st_size > 80 * 1024 * 1024:
        raise ValueError('Converted HTML exceeds the 80 MB output limit.')
    return {'pages': pages, 'seconds': round(time.monotonic()-start, 2), 'bytes': output.stat().st_size}
