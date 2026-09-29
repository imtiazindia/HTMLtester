# Converter selection — 29 September 2026

The test app compares different goals, not a universal quality score. Validate on your own documents, especially equations, merged cells, reading order and multi-column pages.

| Engine | Mode in this app | License | What to inspect |
|---|---|---|---|
| pdf2htmlEX | Native fixed-layout conversion, embedded assets | GPLv3+; some resources have permissive exceptions | Page geometry, fonts, graphics; usually not semantic tables |
| Docling | Standard CPU layout/table pipeline; OCR off | MIT code; bundled models have their own licenses | Reading order, headings, table structure; visual reflow expected |
| OpenDataLoader PDF | Deterministic local CPU mode; no hybrid service | Apache 2.0 in v2 | Headings, lists, simple tables, reading order; challenging equations/tables can require hybrid mode |
| PDF.js | Reference PDF renderer only | Apache 2.0 | Original appearance; not counted as a conversion engine |

## Primary sources

- [Docling technical report](https://arxiv.org/abs/2408.09869) describes the layout analysis and table reconstruction pipeline.
- [Docling source and licensing](https://github.com/docling-project/docling).
- [OpenDataLoader source](https://github.com/opendataloader-project/opendataloader-pdf) documents HTML export, Java runtime, deterministic and hybrid modes.
- [OpenDataLoader reproducible benchmark](https://github.com/opendataloader-project/opendataloader-bench) includes scientific and multi-column documents. It is maintained by the project, not an independent universal evaluation. Its strongest advertised hybrid score does not describe the CPU-only configuration deployed here.
- [OpenDataLoader licensing](https://www.opendataloader.org/docs/license).
- [pdf2htmlEX source and license](https://github.com/pdf2htmlEX/pdf2htmlEX). The available release binary is old (0.18.8.rc1, 2020); compatibility and maintenance are material limitations. It runs in a bounded worker, not the API process.
- [PDF.js](https://github.com/mozilla/pdf.js).

## Other research options considered

- [olmOCR / olmOCR 2](https://github.com/allenai/olmocr): Apache-2.0 project from Allen AI, with research and benchmark links; model inference adds GPU or provider cost. Promising for future comparison, but unnecessary for this small CPU-focused app.
- [Nougat](https://github.com/facebookresearch/nougat): academic-document model; MIT code but CC-BY-NC model weights, so not an unrestricted commercial option.
- [MinerU](https://github.com/opendatalab/MinerU): modern document extraction; additional conditions apply to its current license. Not included under a simple permissive-license assumption.
- [GROBID](https://github.com/grobidOrg/grobid): strong scholarly-document/TEI extraction. Its purpose differs from faithful HTML conversion.
- [arXiv HTML paper](https://arxiv.org/abs/2402.08954): source-LaTeX conversion is a different problem from converting arbitrary PDFs.

No engine guarantees both exact pixels and accurate semantic HTML. This app records time, page count and output size, not fabricated accuracy percentages. No paid AI API is used and uploaded PDFs are not sent to third-party inference services.
