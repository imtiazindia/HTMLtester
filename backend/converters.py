"""Independent adapters: never substitute one engine's output for another."""
from pathlib import Path
import subprocess
import sys
import time
import queue
import threading
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

def stream_process(command, emit, timeout=720):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding='utf-8', errors='replace', bufsize=1)
    lines = queue.Queue(maxsize=200)
    stopped = threading.Event()
    def read():
        try:
            for line in process.stdout:
                while not stopped.is_set():
                    try: lines.put(line, timeout=.1); break
                    except queue.Full: pass
                if stopped.is_set(): break
        finally: process.stdout.close()
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    start = heartbeat = time.monotonic()
    try:
        while process.poll() is None or reader.is_alive() or not lines.empty():
            now = time.monotonic()
            if now-start > timeout: raise TimeoutError('Converter exceeded its 12-minute limit.')
            try:
                line = lines.get(timeout=.2).strip()
                if line: emit(line)
            except queue.Empty: pass
            if now-heartbeat >= 10:
                emit(f'Converter is running ({int(now-start)} seconds elapsed).')
                heartbeat = now
        return process.wait()
    finally:
        stopped.set()
        if process.poll() is None: process.kill()
        process.wait()
        reader.join(timeout=2)

def convert(source: Path, output: Path, engine: str, emit=lambda message: None):
    if engine not in ENGINES:
        raise ValueError('Unknown conversion engine.')
    pages = validate_pdf(source)
    emit(f'PDF validated: {pages} pages, {source.stat().st_size} bytes.')
    start = time.monotonic()
    # A child process provides a real timeout and releases model memory after each job.
    emit(f'Starting {engine}.')
    code = stream_process([sys.executable, '-u', str(Path(__file__).with_name('run_engine.py')),
                           engine, str(source), str(output)], emit)
    if code:
        emit(f'Converter exited with code {code}.')
        raise RuntimeError(f'{engine} could not convert this document. Try another engine.')
    if not output.exists() or not output.stat().st_size:
        raise RuntimeError('The converter returned no HTML.')
    if output.stat().st_size > 80 * 1024 * 1024:
        raise ValueError('Converted HTML exceeds the 80 MB output limit.')
    emit(f'HTML generated: {output.stat().st_size} bytes.')
    return {'pages': pages, 'seconds': round(time.monotonic()-start, 2), 'bytes': output.stat().st_size}
