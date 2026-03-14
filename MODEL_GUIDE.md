# AI Model Guide — FreightScan AI

The app uses **one AI model at a time** through Ollama.
This guide explains all 4 supported models, who they are for, and what your computer needs to run them.

You only need to **pick one and install it.** You do not need all four.

---

## Quick Pick — Just tell me which one to use

| My computer | Use this |
|---|---|
| GTX 1050 Ti / any GPU with 4 GB VRAM, 8 GB RAM | `qwen2.5:3b` |
| GPU with 8 GB+ VRAM (RTX 3060, 3070, 4060, etc.) | `qwen2.5:7b` |
| No GPU, 16 GB+ RAM, modern CPU | `mistral:7b` |
| No GPU, only 8 GB RAM, older CPU | `llama3.2:3b` |
| Apple MacBook M1 / M2 / M3 / M4 / M5 | `mistral:7b` |

---

## The 4 Models

---

### 1. `mistral:7b`
**The most accurate. Best for powerful machines.**

Mistral 7B is the most reliable model for reading complex freight tables and outputting
correct structured data. It handles tricky layouts, mixed text/table pages, and unusual
surcharge formats better than the smaller models.

Use this if your computer can handle it.

**Download:**
```bash
ollama pull mistral:7b
```

**Set in `.env`:**
```
OLLAMA_MODEL=mistral:7b
```

**Download size:** ~4.4 GB (one-time)

#### System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| **RAM** | 16 GB | 32 GB |
| **GPU VRAM** | None needed (CPU mode) | 8 GB+ (RTX 3060 12GB, etc.) |
| **CPU** | Intel i7 / Ryzen 7 (any gen) | Intel i7-12th gen / Ryzen 7 5000+ |
| **Storage** | 5 GB free | 10 GB free |

#### Speed estimate (100-page PDF)

| Setup | Time |
|---|---|
| CPU only, Ryzen 7 / i7, 16 GB RAM | ~1.5–2 hours |
| GPU with 8 GB VRAM (RTX 3060) | ~20–30 min |
| GPU with 12 GB+ VRAM | ~15–25 min |
| Apple M1 | ~35–45 min |
| Apple M4 / M5 | ~15–25 min |

> ⚠️ **Do NOT use on 8 GB RAM machines without a GPU.** The model needs ~4.5 GB just for
> itself — leaving almost nothing for the OS, Docling, and everything else. It will crash or freeze.

---

### 2. `llama3.2:3b`
**The lightest. Best for low-spec machines.**

Llama 3.2 3B is the smallest model in this list. It uses the least RAM and runs the fastest
on CPU-only machines. Accuracy is slightly lower than the larger models on complex tables,
but it handles standard freight rate sheets well.

Use this if you have limited RAM (8 GB) and no GPU.

**Download:**
```bash
ollama pull llama3.2:3b
```

**Set in `.env`:**
```
OLLAMA_MODEL=llama3.2:3b
```

**Download size:** ~2.0 GB (one-time)

#### System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| **RAM** | 8 GB | 16 GB |
| **GPU VRAM** | None needed | 4 GB+ (fits fully in GPU) |
| **CPU** | Any modern CPU (4+ cores) | Intel i5 / Ryzen 5, 2019 or newer |
| **Storage** | 3 GB free | 5 GB free |

#### Speed estimate (100-page PDF)

| Setup | Time |
|---|---|
| CPU only, 8 GB RAM, Ryzen 3 3200G | ~3–5 hours |
| CPU only, 16 GB RAM, Ryzen 5 / i5 | ~1–1.5 hours |
| GPU with 4 GB VRAM (GTX 1050 Ti) | ~55–80 min |
| Apple M1 | ~25–35 min |

> ✅ **This is the safe choice for any machine.** When in doubt, use this model.

---

### 3. `qwen2.5:3b`
**Best accuracy at the 3B size. Best for GPUs with 4 GB VRAM.**

Qwen 2.5 3B is made by Alibaba and is specifically trained to be excellent at structured
data output — which is exactly what this app needs (extracting rates into JSON).
At the same file size as Llama 3.2 3B, it produces noticeably more consistent and
correctly formatted outputs for freight tables.

If you have a GPU with 4 GB VRAM (like a GTX 1050 Ti, GTX 1650, or RTX 3050),
this is the best model you can run fully on that GPU.

**Download:**
```bash
ollama pull qwen2.5:3b
```

**Set in `.env`:**
```
OLLAMA_MODEL=qwen2.5:3b
```

**Download size:** ~2.0 GB (one-time)

#### System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| **RAM** | 8 GB | 16 GB |
| **GPU VRAM** | None (runs on CPU too) | 4 GB — fits entirely in GPU |
| **CPU** | Any modern CPU (4+ cores) | Intel i5 / Ryzen 5, 2019 or newer |
| **Storage** | 3 GB free | 5 GB free |

#### Speed estimate (100-page PDF)

| Setup | Time |
|---|---|
| CPU only, 8 GB RAM, Ryzen 3 | ~3–5 hours |
| CPU only, 16 GB RAM, Ryzen 5 / i5 | ~1–1.5 hours |
| GTX 1050 Ti (4 GB VRAM) + Ryzen 3 3200G, 8 GB RAM | **~50–75 min** |
| RTX 3050 / GTX 1660 | ~35–55 min |
| Apple M2 / M3 | ~20–30 min |

> ✅ **Best choice for the GTX 1050 Ti + 8 GB RAM build.** The model fits entirely in
> the GPU's 4 GB VRAM, keeping system RAM free for Docling and the OS.

---

### 4. `qwen2.5:7b`
**Best overall accuracy. Best for GPUs with 8 GB+ VRAM.**

Qwen 2.5 7B is the largest model that still fits in most mid-range gaming GPUs.
It combines Qwen's excellent structured JSON output quality with a larger model size —
meaning it handles the most unusual freight contract layouts and edge cases best.

If you have an RTX 3060 12 GB, RTX 3070, RTX 4060 Ti, or anything with 8 GB+ VRAM,
this is the best model to use.

**Download:**
```bash
ollama pull qwen2.5:7b
```

**Set in `.env`:**
```
OLLAMA_MODEL=qwen2.5:7b
```

**Download size:** ~4.7 GB (one-time)

#### System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| **RAM** | 16 GB | 32 GB |
| **GPU VRAM** | 8 GB (to run fully on GPU) | 12 GB+ |
| **CPU** | Intel i5 / Ryzen 5 | Intel i7 / Ryzen 7 |
| **Storage** | 6 GB free | 10 GB free |

> ⚠️ On a 4 GB VRAM GPU (like GTX 1050 Ti), this model will **not** fully load onto the GPU.
> Ollama will split it between GPU and CPU, which is much slower. Use `qwen2.5:3b` instead.

#### Speed estimate (100-page PDF)

| Setup | Time |
|---|---|
| CPU only, 16 GB RAM, Ryzen 7 / i7 | ~1.5–2.5 hours |
| RTX 3060 12 GB | ~20–30 min |
| RTX 3070 / RTX 4060 Ti | ~15–22 min |
| RTX 4080 / 4090 | ~8–14 min |
| Apple M2 Pro / M3 Pro | ~18–25 min |
| Apple M4 / M5 | ~12–18 min |

> ✅ **The best model in this list for accuracy.** Recommended for the main demo machine
> at the hackathon if it has an 8 GB+ VRAM GPU.

---

## Side-by-side Comparison

| | `mistral:7b` | `llama3.2:3b` | `qwen2.5:3b` | `qwen2.5:7b` |
|---|---|---|---|---|
| **Size** | 4.4 GB | 2.0 GB | 2.0 GB | 4.7 GB |
| **Min RAM** | 16 GB | 8 GB | 8 GB | 16 GB |
| **Min VRAM (GPU)** | 8 GB | 4 GB | 4 GB | 8 GB |
| **JSON accuracy** | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Speed (CPU)** | Slow | Fast | Fast | Slow |
| **Speed (GPU)** | Fast | Very Fast | Very Fast | Fast |
| **Safe on 8 GB RAM** | ⚠️ Risky | ✅ Yes | ✅ Yes | ❌ No |

---

## How to switch models

1. Open your `.env` file in the project root
2. Change the `OLLAMA_MODEL` line to your chosen model name
3. Make sure you have pulled that model with `ollama pull <model-name>`
4. Restart the backend — the new model will be used automatically

Example:
```
OLLAMA_MODEL=qwen2.5:3b
```

---

## Checking how much VRAM your GPU has

**Windows:**
1. Right-click the desktop → Display Settings
2. Scroll down → Advanced display settings → Display adapter properties
3. Look for "Dedicated Video Memory"

Or open **Task Manager → Performance → GPU** and check "Dedicated GPU Memory"

**Mac:**
Apple Silicon Macs do not have separate VRAM — they use unified memory (shared with RAM).
A 16 GB M-series Mac effectively has 16 GB available for the model.

---

## Notes

- All models run **100% locally** — no internet needed after the initial download
- You only need **one model installed** — pick based on your hardware
- The `.env` file controls which model is active — changing it is instant
- Ollama must be running before you start the backend (`ollama serve` or open the Ollama app)
