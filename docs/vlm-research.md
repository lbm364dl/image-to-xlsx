# Open-Source VLMs for Table Extraction — Research (March 2025)

This document surveys the current landscape of open-source Vision Language Models
that could serve as extraction backends in this project. The use case: given a
scanned document page (image or PDF), detect tables and extract cell contents
(text + row/col positions).

All VRAM figures are for inference only. Training/fine-tuning requires
significantly more.

---

## What we already have

| Method | Params | VRAM | Approach | Notes |
|--------|--------|------|----------|-------|
| **Surya** | ~27M per component | 7-13 GB | Pipeline: layout detection → table structure → per-cell OCR | 90+ languages, dedicated table structure model with row/col IDs |
| **PaddleOCR-VL** | 0.9B | ~2.5 GB (GPU), feasible on CPU | Single-pass VLM outputting HTML/Markdown tables | Apache 2.0. 93.52 TEDS on OmniDocBench |
| **GLM-OCR** | 0.9B | needs separate vLLM backend | Layout detection + LLM OCR | Multi-token prediction for fast decoding |
| **pdf-text** | — | negligible | PyMuPDF text extraction | For digitally-born PDFs with embedded text |

---

## Tier 1 — High-value, easy to integrate

### PaddleOCR-VL 1.5 (drop-in upgrade)

- **Params**: 0.9B (same architecture as current)
- **VRAM**: ~2.5 GB GPU; CPU feasible
- **License**: Apache 2.0
- **What changed**: Better training data. Table-TEDS-S improves from 93.52 → 95.79. Cross-page table merging, better rare characters, multilingual tables.
- **Integration**: Update the pip package version in `services/paddleocr-vl/requirements.txt`. No code changes.
- **HuggingFace**: `PaddlePaddle/PaddleOCR-VL-1.5`

### GOT-OCR 2.0

- **Params**: 580M
- **VRAM**: ~2-3 GB (BF16). CPU feasible given the small size.
- **License**: Apache 2.0
- **Capabilities**: End-to-end OCR covering plain text, formatted text, tables, charts, math. Outputs Markdown/LaTeX. Supports region-specific OCR with bounding boxes.
- **Limitation**: No layout/table detection — it needs a separate model to find table bounding boxes first (e.g. Table Transformer, see below). Once you crop to a table, it can extract the content.
- **Integration**: New service, same pattern. Pair with Table Transformer for detection.
- **HuggingFace**: `stepfun-ai/GOT-OCR-2.0-hf` (integrated into HuggingFace Transformers)

### Qwen2.5-VL-7B (or 3B)

- **Params**: 3B or 7B
- **VRAM**: 3B → ~5.75 GB (BF16), ~3 GB (Q4). 7B → ~13 GB (BF16), ~5 GB (AWQ/Q4).
- **License**: Apache 2.0
- **Capabilities**: Multilingual OCR (32+ languages), structured output (JSON/CSV/Markdown), table parsing, chart understanding, 128K context. Can be prompted: "Extract all tables from this image as Markdown."
- **Quantized**: Official AWQ and GPTQ on HuggingFace. Community GGUF. Supported by vLLM, Ollama, llama.cpp.
- **Integration**: Serve via vLLM (reuse the pattern from GLM-OCR). New service that posts the image and a prompt, parses Markdown/HTML response.
- **HuggingFace**: `Qwen/Qwen2.5-VL-7B-Instruct-AWQ`, `Qwen/Qwen2.5-VL-3B-Instruct`

There is also **Qwen3-VL** (4B, 8B) — successor with improved multilingual OCR. Same integration pattern. Requires slightly more VRAM than Qwen2.5-VL at equivalent sizes.

---

## Tier 2 — Strong candidates

### Granite-Docling-258M / SmolDocling-256M

- **Params**: 256-258M
- **VRAM**: <1 GB
- **License**: Apache 2.0
- **Capabilities**: Full document conversion including tables (with row/col headers), formulas, code blocks. Uses DocTags format (convertible to Markdown/HTML). Architecture: SigLIP2 vision encoder + Granite 165M LLM.
- **Table accuracy**: Lower than larger models (TEDS 0.52 on FinTabNet, 0.65 on PubTables-1M), but remarkable for 258M params.
- **CPU**: Yes, easily. Available on Ollama (`ibm/granite-docling:258m`).
- **Best for**: CPU-only environments, ultra-fast preliminary passes.
- **HuggingFace**: `ibm-granite/granite-docling-258M`

### dots.ocr

- **Params**: 3B (1.2B vision encoder + 1.7B LM)
- **VRAM**: ~6-8 GB (BF16). 4-bit quantized version available.
- **License**: MIT
- **Capabilities**: Document layout parsing in a single VLM. Layout detection includes tables. Outputs Markdown/JSON.
- **Benchmark**: 79.1 on olmOCR-Bench. SOTA on text, tables, and reading order on OmniDocBench.
- **HuggingFace**: `rednote-hilab/dots.ocr`, `helizac/dots.ocr-4bit`

### FireRed-OCR

- **Params**: 2B (Qwen3-VL architecture)
- **VRAM**: ~5-8 GB estimated
- **License**: Not clearly specified — needs verification before use
- **Capabilities**: Uses GRPO reinforcement learning specifically for table integrity and formula syntax. 92.94% on OmniDocBench v1.5 (current SOTA as of early 2025).
- **Table focus**: Explicit RL rewards for "table structure preserved" and "hierarchical closure."
- **HuggingFace**: `FireRedTeam/FireRed-OCR`

### olmOCR-2

- **Params**: 7B (fine-tuned Qwen2.5-VL-7B)
- **VRAM**: ~14 GB (BF16), ~7 GB (FP8). GGUF versions exist.
- **License**: Apache 2.0
- **Capabilities**: GRPO RL-trained specifically to boost math equations, tables, and tricky OCR.
- **Benchmark**: 82.3 on olmOCR-Bench.
- **Comparison**: Same base as Qwen2.5-VL-7B but table-focused RL training. Serve via vLLM.
- **HuggingFace**: `allenai/olmOCR-2-7B-1025`, `allenai/olmOCR-2-7B-1025-FP8`

### Table Transformer (component, not standalone)

- **Params**: ~20-30M (DETR-based)
- **VRAM**: <1 GB. Runs easily on CPU.
- **License**: MIT
- **Purpose**: Two separate models — one detects table bounding boxes, the other recognizes table structure (rows, columns, spanning cells). Does NOT do OCR.
- **Use case**: Pair with GOT-OCR or any lightweight OCR model for a two-stage pipeline.
- **HuggingFace**: `microsoft/table-transformer-detection`, `microsoft/table-transformer-structure-recognition-v1.1-all`

---

## Tier 3 — Alternatives worth knowing

### DeepSeek-OCR / DeepSeek-OCR-2

- **Params**: ~950M (v1, MoE), 3B (v2)
- **VRAM**: 8-10 GB min, 16-24 GB recommended for high-res
- **License**: Apache 2.0
- **HuggingFace**: `deepseek-ai/DeepSeek-OCR`, `deepseek-ai/DeepSeek-OCR-2`

### Chandra-OCR

- **Params**: 9B (fine-tuned Qwen3-VL)
- **VRAM**: ~8 GB min (batch 8)
- **Benchmark**: 83.1 on olmOCR-Bench
- **Note**: From the Surya team (Datalab). 40+ languages.
- **GitHub**: `datalab-to/chandra`

### LightOnOCR-2

- **Params**: 1B (Pixtral ViT encoder + Qwen3 decoder)
- **Speed**: 5.71 pages/sec on H100, 3.3x faster than Chandra
- **Benchmark**: 83.2 on olmOCR-Bench
- **VRAM**: Documentation says ~44 GB on A6000 (seems high for 1B; may include vision processing overhead) — needs verification on consumer hardware.
- **License**: Apache 2.0
- **HuggingFace**: `lightonai/LightOnOCR-2-1B`

### InternVL3.5

- **Sizes**: 1B, 2B, 4B, 8B
- **VRAM (Q4)**: 1B → ~2 GB, 4B → ~4 GB, 8B → ~6-7 GB
- **License**: MIT
- **Capabilities**: Strong document understanding, OCR, table comprehension.
- **Quantized**: GGUF available from bartowski.
- **HuggingFace**: `OpenGVLab/InternVL3_5-8B`

### MiniCPM-V 4.5

- **Params**: 9B
- **VRAM**: ~7 GB (int4)
- **Capabilities**: SOTA on OCRBench, table-to-markdown, full-text OCR. Leading PDF parsing on OmniDocBench.
- **Quantized**: int4 + GGUF in 16 sizes. Ollama supported.
- **HuggingFace**: `openbmb/MiniCPM-V-4_5`

### Moondream 2

- **Params**: 1.8B
- **VRAM**: 2.5 GB (4-bit)
- **License**: Apache 2.0
- **Best for**: Edge/CPU deployments. Limited table structure understanding vs. specialized models.
- **HuggingFace**: `vikhyatk/moondream2`

### General VLMs (less table-specialized)

These *can* extract tables via prompting but don't excel at it compared to the options above:

- **Phi-4 multimodal** (5.6B, MIT) — decent OCR, not table-specialized
- **Llama 3.2 Vision** (11B) — struggles with complex OCR/tables in benchmarks
- **Gemma 3** (4B+, vision from 4B) — competent OCR, PaddleOCR-VL outperforms it for tables
- **DeepSeek-VL2** (27B total, 1-4.5B active MoE, MIT) — strong but DeepSeek-OCR is more relevant
- **Molmo** (1B-72B, Apache 2.0) — less document-specialized

---

## Models NOT recommended

| Model | Why |
|-------|-----|
| **Donut / Nougat** | 2022-2023 architecture, superseded by everything above |
| **mPLUG-DocOwl2** | 8B, interesting research but limited deployment tooling |
| **Nanonets-OCR2-3B** | Fine-tuned Qwen2.5-VL-3B — use Qwen directly instead |
| **UniTable** | Good table structure accuracy, but niche focus and limited community |

---

## Hardware reference

Typical consumer/prosumer GPU VRAM:

| GPU | VRAM | Can run |
|-----|------|---------|
| RTX 3060 / 4060 | 8 GB | PaddleOCR-VL, GOT-OCR, Granite-Docling, Table Transformer, Moondream, Qwen2.5-VL-3B (Q4) |
| RTX 3070 Ti / 4070 | 12 GB | Above + Qwen2.5-VL-7B (AWQ), dots.ocr, InternVL3.5-8B (Q4) |
| RTX 3090 / 4090 | 24 GB | Above + olmOCR-2, Chandra, MiniCPM-V 4.5, most 7-9B models at BF16 |
| CPU only | — | Granite-Docling-258M, GOT-OCR (slow), PaddleOCR-VL (slow), Table Transformer |

---

## Integration pattern

All VLM-based methods follow the same pattern already established in this project:

1. Send image to service endpoint
2. Get back Markdown/HTML table(s)
3. Parse into `{"row", "col", "text", "confidence"}` cell format

The existing `_parse_html_table()` and `_parse_markdown_table()` helpers in `services/paddleocr-vl/server.py` can be extracted to a shared utility and reused for any new VLM service.

For vLLM-served models (Qwen, olmOCR, etc.), the GLM-OCR service's vLLM backend pattern already works — the new service just needs a different model ID and prompt template.

---

## Recommended next steps

1. **Quick win**: Upgrade PaddleOCR-VL to 1.5 (no code changes, better accuracy)
2. **Add GOT-OCR 2.0**: 580M, Apache 2.0, very lightweight, HuggingFace native
3. **Add Qwen2.5-VL-7B-AWQ via vLLM**: Strong general document understanding, reuse GLM-OCR deployment pattern
4. **Add Granite-Docling-258M**: CPU-only option, < 1 GB, available via Ollama
