# Survey: Memory-Augmented LLM Architectures & Knowledge Injection Methods (2023-2026)

**Context**: Making an LLM "remember" a 6M-token Chinese novel without stuffing the context window.
**Hardware constraint**: 4x L40S (192GB VRAM total).

---

## 1. MemoryLLM — Self-Updatable Memory Pool

| Field | Detail |
|-------|--------|
| **Paper** | "MEMORYLLM: Towards Self-Updatable Large Language Models" |
| **Authors** | Yu Wang, Yifan Gao, Xiusi Chen, Haoming Jiang, Shiyang Li, Jingfeng Yang, Qingyu Yin, Zheng Li, Xian Li, Bing Yin, Jingbo Shang, Julian McAuley |
| **Venue/Date** | arXiv 2402.04624, Feb 2024 (revised May 2024) |
| **Code** | https://github.com/wangyu-ustc/MemoryLLM |
| **Base models** | Llama-2-7B, Llama-3-8B |
| **Max scale tested** | 16,384 tokens context; up to ~1M memory updates tested for retention stability |
| **Training req** | H100-80GB; RedPajama dataset; 1.67B additional memory parameters on top of 8B base |
| **GPU fit (4xL40S)** | Marginal. 8B base + 1.67B memory = ~10B params. Should fit in fp16 on 1-2 GPUs. But 6M tokens would require sequential injection of ~400+ chunks — untested at that scale. |

**Mechanism**: Pairs a frozen/trainable transformer with a fixed-size latent memory pool. New text is "injected" into the memory pool via a learned write operation, updating the pool in-place. At inference, the model attends to both the input and the memory pool. Memory pool size is fixed (not proportional to document length), so it's lossy compression.

**Key limitations**:
- Memory pool is fixed-size — cannot scale with document length; 6M tokens would be heavily compressed/lossy
- Minimum 16 tokens per injection (memory gets "disturbed" below this)
- Only Llama-family models supported
- No evidence of working on non-English (Chinese) text at scale
- MPlus-8B (improved version) has no chat variant yet

---

## 2. Larimar — Episodic Memory for LLMs

| Field | Detail |
|-------|--------|
| **Paper** | "Larimar: Large Language Models with Episodic Memory Control" |
| **Authors** | Payel Das, Subhajit Chaudhury, Elliot Nelson, Igor Melnyk, Sarath Swaminathan, Sihui Dai, Aurlie Lozano, Georgios Kollias, Vijil Chenthamarakshan, Jiri Navratil, Soham Dan, Pin-Yu Chen |
| **Venue/Date** | ICML 2024; arXiv 2403.11901, Mar 2024 |
| **Code** | https://github.com/IBM/larimar (Apache-2.0) |
| **Base models** | Custom 1.3B model only |
| **Max scale tested** | Not documented; appears small-scale (knowledge editing benchmarks) |
| **Training req** | Requires training from scratch or fine-tuning with their custom architecture; no pre-trained weights bundled |
| **GPU fit (4xL40S)** | Model is small (1.3B), but no path to scale to larger models or longer documents |

**Mechanism**: Brain-inspired distributed episodic memory module attached to an LLM. Uses a learned encoder to write facts into a key-value episodic memory, and a decoder to read them back. Supports one-shot knowledge updates (8-10x faster than fine-tuning competitors), selective forgetting, and information leakage prevention.

**Key limitations**:
- Only tested on 1.3B custom model — no support for standard open models
- Designed for knowledge editing (individual facts), not bulk document ingestion
- No pre-trained weights distributed; must train from scratch
- Not designed for 6M-token scale document memorization
- No Chinese language evaluation

---

## 3. Infini-attention (Leave No Context Behind)

| Field | Detail |
|-------|--------|
| **Paper** | "Leave No Context Behind: Efficient Infinite Context Transformers with Infini-attention" |
| **Authors** | Tsendsuren Munkhdalai, Manaal Faruqui, Siddharth Gopal (Google) |
| **Venue/Date** | arXiv 2404.07143, Apr 2024 |
| **Code** | No official release from Google |
| **Base models** | Tested on 1B and 8B parameter models (internal Google models) |
| **Max scale tested** | 1M tokens (passkey retrieval), 500K tokens (book summarization) |
| **Training req** | Requires continued training on the base model to add compressive memory; details not fully disclosed |
| **GPU fit (4xL40S)** | Architecture is efficient (bounded memory), but no public code to test. 8B model would fit. |

**Mechanism**: Replaces standard attention with a hybrid that combines (1) masked local attention for nearby tokens and (2) a compressive memory using linear attention for long-range context. The compressive memory is updated incrementally as new segments are processed, using an associative matrix that stores key-value bindings. This gives bounded memory cost regardless of sequence length.

**Key limitations**:
- No public code or model weights released by Google
- Only evaluated on internal Google models
- Compressive memory is inherently lossy — fine-grained detail retrieval may degrade
- No Chinese language benchmarks
- Community reimplementations exist but are unofficial and unvalidated

---

## 4. ICAE (In-Context Autoencoder)

| Field | Detail |
|-------|--------|
| **Paper** | "In-context Autoencoder for Context Compression in a Large Language Model" |
| **Authors** | Tao Ge, Jing Hu, Lei Wang, Xun Wang, Si-Qing Chen, Furu Wei (Microsoft) |
| **Venue/Date** | ICLR 2024; arXiv 2307.06945, Jul 2023 |
| **Code** | https://github.com/getao/icae (CC0-1.0) |
| **Base models** | Llama-2-7b-chat (V1), Mistral-7B (V2) |
| **Max scale tested** | 5,120 tokens input (V2); ~4x compression ratio |
| **Training req** | Pretrain with autoencoding + LM objectives on large text; fine-tune on instruction data; adds ~1% parameters |
| **GPU fit (4xL40S)** | 7B model fits easily. But 6M tokens / 4x compression = 1.5M memory tokens — far beyond what's been tested. |

**Mechanism**: Trains a small encoder on top of an LLM to compress long contexts into a small number of "memory slot" tokens. The LLM then conditions on these memory tokens instead of the full context. Uses autoencoding loss (reconstruct original from compressed) plus language modeling loss. V2 supports multi-span concatenation for longer inputs.

**Key limitations**:
- Maximum tested input is only 5,120 tokens — 1000x short of our 6M target
- 4x compression is modest; would still need ~1.5M memory tokens for 6M input
- Only 7B-class models supported
- Compression is lossy — fine-grained QA accuracy degrades
- No evidence of Chinese language support

---

## 5. AutoCompressor — Recursive Summary Vectors

| Field | Detail |
|-------|--------|
| **Paper** | "Adapting Language Models to Compress Contexts" |
| **Authors** | Alexis Chevalier, Alexander Wettig, Anirudh Ajith, Danqi Chen (Princeton) |
| **Venue/Date** | EMNLP 2023; arXiv 2305.14788, May 2023 |
| **Code** | https://github.com/princeton-nlp/AutoCompressors |
| **Base models** | OPT-1.3B, OPT-2.7B, Llama-2-7B |
| **Max scale tested** | 30,720 tokens (20 compression steps) |
| **Training req** | 2B-15B tokens (Pile/RedPajama); Flash Attention; CUDA + bfloat16 |
| **GPU fit (4xL40S)** | 7B model fits. But recursive compression over 6M tokens = ~200 compression steps — untested, likely unstable. |

**Mechanism**: Segments long documents and recursively compresses each segment into 50 "summary vectors" (soft prompts). These summary vectors are passed forward to the next segment, accumulating information. The model is trained with unsupervised language modeling loss over the segmented documents. Achieves ~13:1 compression ratio (660 tokens to 50 summary vectors).

**Key limitations**:
- Max tested at 30K tokens — 200x short of target
- Recursive compression over hundreds of steps likely loses information catastrophically
- Flash Attention on OPT is "experimental"
- Only OPT and Llama-2 supported
- Summary vectors are opaque — no way to verify what information is retained

---

## 6. Gisting / Gist Tokens

| Field | Detail |
|-------|--------|
| **Paper** | "Learning to Compress Prompts with Gist Tokens" |
| **Authors** | Jesse Mu, Xiang Lisa Li, Noah Goodman (Stanford) |
| **Venue/Date** | NeurIPS 2023; arXiv 2304.08467, Apr 2023 |
| **Code** | https://github.com/jayelm/gisting (Apache-2.0) |
| **Base models** | LLaMA-7B, FLAN-T5-XXL |
| **Max scale tested** | Instruction-length prompts (hundreds of tokens); up to 26x compression |
| **Training req** | 4x A100-80GB, ~400GB CPU RAM; DeepSpeed; specific transformers commit required |
| **GPU fit (4xL40S)** | 7B model fits. But designed for short prompts, not document-scale compression. |

**Mechanism**: Modifies attention masks during instruction fine-tuning to learn special "gist" tokens that compress arbitrary prompts. A full instruction can be distilled into as few as 1 gist token. The gist tokens are cached and reused, saving both compute and storage. Training cost is essentially zero beyond standard instruction tuning.

**Key limitations**:
- Designed for prompt compression (hundreds of tokens), NOT document-scale (millions of tokens)
- Only batch_size=1 supported for gist compression
- Wall-clock speedups are "small or even non-existent" in practice
- Requires specific old transformers version
- Fundamentally wrong tool for 6M-token document memorization

---

## 7. CaMeLS — Context-Aware Meta-Learned Loss Scaling

| Field | Detail |
|-------|--------|
| **Paper** | "Meta-Learning Online Adaptation of Language Models" |
| **Authors** | Nathan Hu, Eric Mitchell, Christopher Manning, Chelsea Finn (Stanford) |
| **Venue/Date** | EMNLP 2023; ACL Anthology 2023.emnlp-main.268 |
| **Code** | No public repository found |
| **Base models** | GPT-2 family tested; method is model-agnostic |
| **Max scale tested** | Streams of thousands of documents |
| **Training req** | Meta-trains a small autoregressive model to reweight per-token loss; requires meta-learning loop with QA evaluation |
| **GPU fit (4xL40S)** | Meta-training is lightweight. Applying to 6M tokens would require chunking into documents + QA pairs for meta-learning. |

**Mechanism**: Addresses the problem that naive fine-tuning on documents is inefficient because gradient signals from important factual tokens get "drowned out" by noise from common tokens. CaMeLS meta-trains a small model to predict per-token loss weights that maximize downstream QA performance after a single gradient step on a new document. This is applied during online adaptation.

**Key limitations**:
- Requires QA pairs for meta-training (needs existing QA supervision)
- Single gradient step adaptation — unclear if it scales to 6M tokens
- No public code released
- Tested only on GPT-2 scale models
- Meta-learning loop adds complexity

---

## 8. Reading Comprehension Fine-Tuning

| Field | Detail |
|-------|--------|
| **Paper** | "Fine-Tuning or Retrieval? Comparing Knowledge Injection in LLMs" |
| **Authors** | Oded Ovadia, Menachem Brief, Moshik Mishaeli, Oren Elisha |
| **Venue/Date** | arXiv 2312.05934, Dec 2023 |
| **Also relevant** | "Penrose Tiled Low-Rank Compression and Section-Wise Q&A Fine-Tuning" (arXiv 2503.22074, Mar 2025) |
| **Code** | No standard implementation |
| **Base models** | Any LLM (method-agnostic) |
| **Max scale tested** | Document collections (not specified in tokens) |
| **Training req** | Standard fine-tuning compute; needs synthetic QA pair generation |
| **GPU fit (4xL40S)** | Easily fits for 7-8B models. The bottleneck is QA pair quality, not compute. |

**Mechanism**: Generate QA pairs from the target document (manually or via another LLM), then fine-tune the target model on these pairs. The section-wise variant (2503.22074) processes documents section-by-section, generating structured QA routines. Key finding from Ovadia et al.: RAG consistently outperforms unsupervised fine-tuning; models struggle to absorb new facts via fine-tuning alone unless exposed to "numerous variations of the same fact."

**Key limitations**:
- RAG outperforms fine-tuning for knowledge injection in controlled experiments
- Models struggle to internalize new facts via fine-tuning without many paraphrases
- QA pair quality is critical — garbage in, garbage out
- Catastrophic forgetting risk on general capabilities
- For 6M tokens: would need thousands of QA pairs covering the entire novel
- No guarantee the model "understands" vs. memorizes specific QA patterns

---

## 9. LoRA-Based Knowledge Injection

| Field | Detail |
|-------|--------|
| **Key paper** | "LoRA Learns Less and Forgets Less" |
| **Authors** | Dan Biderman, Jacob Portes, Jose Javier Gonzalez Ortiz, Mansheej Paul, Philip Greengard, et al. |
| **Venue/Date** | TMLR Aug 2024 (Featured); arXiv 2405.09673, May 2024 |
| **Also relevant** | "Neurosymbolic LoRA" (arXiv 2601.12711, Jan 2026); LLaMA Pro block expansion (ACL 2024, arXiv 2401.02415) |
| **Code** | Standard LoRA via PEFT/Hugging Face |
| **Base models** | Any transformer (method-agnostic) |
| **Max scale tested** | 20B tokens continued pretraining; ~100K instruction pairs |
| **Training req** | Single A100 for 7B QLoRA; multiple GPUs for full LoRA on larger models |
| **GPU fit (4xL40S)** | Excellent. 4xL40S can LoRA-train any model up to ~30B. |

**Mechanism**: Low-Rank Adaptation adds small trainable low-rank matrices to frozen model weights. For knowledge injection, you either (a) continue pretraining on the target corpus with LoRA, or (b) fine-tune on QA pairs generated from the corpus. Key finding: LoRA "substantially underperforms full fine-tuning" for knowledge injection but "better preserves base model capabilities." Full fine-tuning produces weight perturbations 10-100x higher rank than typical LoRA configurations.

**Related approach — LLaMA Pro**: Instead of LoRA, add entirely new transformer blocks and train only those on new data. Avoids catastrophic forgetting by isolating new knowledge in new parameters.

**Key limitations**:
- LoRA underperforms full fine-tuning for knowledge absorption
- Low rank fundamentally limits how much new knowledge can be injected
- Continued pretraining on raw text is less effective than QA-formatted training
- For 6M Chinese tokens: would need significant compute for continued pretraining (days on 4xL40S)
- Risk of "hallucinated knowledge" — model may confuse injected facts with training priors
- Chinese text may need Chinese-dominant base model for best results

---

## 10. RMT (Recurrent Memory Transformer)

| Field | Detail |
|-------|--------|
| **Paper (original)** | "Recurrent Memory Transformer" |
| **Authors** | Aydar Bulatov, Yuri Kuratov, Mikhail S. Burtsev |
| **Venue/Date** | NeurIPS 2022; arXiv 2207.06881, Jul 2022 |
| **Paper (scaling)** | "In Search of Needles in a 11M Haystack: Recurrent Memory Finds What LLMs Miss" |
| **Authors** | Yuri Kuratov, Aydar Bulatov, Petr Anokhin, Dmitry Sorokin, Artyom Sorokin, Mikhail Burtsev |
| **Venue/Date** | arXiv 2402.10790, Feb 2024 |
| **Code** | https://github.com/booydar/babilong (BABILong benchmark + RMT code) |
| **Base models** | GPT-2 (137M) for the 11M experiment; method is architecture-agnostic in principle |
| **Max scale tested** | 11 million tokens (GPT-2 + RMT) |
| **Training req** | Fine-tuning required on segmented sequences; training notebook provided |
| **GPU fit (4xL40S)** | GPT-2-137M easily fits. Scaling to larger models (7B+) at 6M tokens is uncharted territory. |

**Mechanism**: Adds special memory tokens to the input sequence. The model processes text in segments; memory tokens are passed between segments via recurrence, carrying information forward. No architectural changes to the base transformer — just prepend/append memory tokens and train the model to use them. The 11M-token result used GPT-2 fine-tuned on BABILong synthetic tasks.

**Key limitations**:
- 11M result is on synthetic needle-in-haystack tasks with a tiny (137M) model
- Real-world QA over natural text at 6M tokens is completely untested
- Requires task-specific fine-tuning for the recurrent memory to work
- Unclear how well it handles complex reasoning over compressed memory
- Only demonstrated on English synthetic tasks
- Scaling to 7B+ models at 6M tokens would require significant engineering

---

## 11. Titans — Neural Long-Term Memory

| Field | Detail |
|-------|--------|
| **Paper** | "Titans: Learning to Memorize at Test Time" |
| **Authors** | Ali Behrouz, Peilin Zhong, Vahab Mirrokni (Google DeepMind) |
| **Venue/Date** | arXiv 2501.00663, Dec 2024 |
| **Code** | Not released (authors state "intend to make code available soon") |
| **Base models** | New architecture from scratch — NOT a plug-in for existing models |
| **Max scale tested** | Claims >2M tokens; tested on BABILong, RULER (up to 16K explicitly benchmarked) |
| **Training req** | Trained from scratch on FineWeb-Edu (15-30B tokens); AdamW; FlashAttention-2; tested at 170M-760M params |
| **GPU fit (4xL40S)** | Small models (760M) fit easily, but there are NO pretrained large models to use |

**Mechanism**: New architecture family combining attention (as "short-term memory") with a neural long-term memory module. The long-term memory is a learned module that stores and retrieves information persistently, trained via a surprise-based learning signal (memorize things that are unexpected). Three variants: MAC (Memory as Context), MAG (Memory as Gate), MAL (Memory as Layer). Supports parallelizable training.

**Key limitations**:
- No public code or pretrained models
- Only tested at small scale (170M-760M) — not competitive with 7B+ models on general tasks
- New architecture means no transfer from existing pretrained models
- Training from scratch on 6M Chinese tokens is completely infeasible — would need full pretraining
- Purely a research architecture; not production-ready

---

## 12. Memory Layers at Scale (Meta)

| Field | Detail |
|-------|--------|
| **Paper** | "Memory Layers at Scale" |
| **Authors** | Vincent-Pierre Berges, Barlas Oguz, Daniel Haziza, Wen-tau Yih, Luke Zettlemoyer, Gargi Ghosh (Meta) |
| **Venue/Date** | arXiv 2412.09764, Dec 2024 |
| **Code** | https://github.com/facebookresearch/memory (CC-BY-NC) |
| **Base models** | LLaMA-style architecture; configs for 373M and 7B |
| **Max scale tested** | 128B memory parameters; pretrained to 1T tokens |
| **Training req** | SLURM cluster; multi-GPU; FineWeb-Edu dataset; HuggingFace tokenizer |
| **GPU fit (4xL40S)** | 7B base + 128B sparse memory params — memory params are sparse (not all activated), but storage is massive. Unlikely to fit 128B params on 192GB. Smaller configs may work. |

**Mechanism**: Replaces some feed-forward layers with sparse key-value lookup "memory layers." These add massive parameter counts without increasing FLOPs — only a small subset of memory entries are activated per token. The memory stores factual associations learned during pretraining. Models with memory layers outperform dense models using >2x the compute, especially on factual tasks.

**Key limitations**:
- Requires training from scratch (or at minimum extensive continued pretraining)
- 128B memory params need massive storage even if sparse
- Designed for pretraining-time factual storage, not post-hoc document injection
- CC-BY-NC license (non-commercial)
- No mechanism to inject a specific document post-training
- Not designed for the "memorize this specific novel" use case

---

## 13. Memory^3 — Explicit Memory

| Field | Detail |
|-------|--------|
| **Paper** | "Memory^3: Language Modeling with Explicit Memory" |
| **Authors** | Hongkang Yang, Zehao Lin, Wenjin Wang, Hao Wu, Zhiyu Li, Bo Tang, et al. |
| **Venue/Date** | arXiv 2407.01178, Jul 2024 |
| **Code** | Not found |
| **Base models** | Custom 2.4B model trained from scratch |
| **Max scale tested** | Claims to outperform larger LLMs and RAG; scale not specified |
| **Training req** | Two-stage pretraining from scratch |
| **GPU fit (4xL40S)** | 2.4B fits easily, but requires training from scratch |

**Mechanism**: Defines three memory types: implicit (parameters), working (context KV cache), and explicit (a new learned memory format "cheaper than parameters and RAG"). Uses a sparsification mechanism and memory circuitry theory to route information. The explicit memory sits between parameter storage cost and RAG retrieval cost.

**Key limitations**:
- Custom architecture, trained from scratch
- No public code or pretrained models found
- 2.4B model is too small for complex reasoning
- No mechanism for post-hoc document injection

---

## 14. MemGPT / Letta — Training-Free Virtual Context Management

| Field | Detail |
|-------|--------|
| **Paper** | "MemGPT: Towards LLMs as Operating Systems" |
| **Authors** | Charles Packer, Sarah Wooders, Kevin Lin, Vivian Fang, Shishir G. Patil, Ion Stoica, Joseph E. Gonzalez (UC Berkeley) |
| **Venue/Date** | arXiv 2310.08560, Oct 2023 |
| **Code** | https://github.com/cpacker/MemGPT (now "Letta"); Apache-2.0; 22.3k stars |
| **Base models** | Model-agnostic (works with any LLM API) |
| **Max scale tested** | Large document analysis and multi-session chat |
| **Training req** | **NONE** — entirely training-free, works via prompting |
| **GPU fit (4xL40S)** | N/A — works with any model you can already run |

**Mechanism**: OS-inspired hierarchical memory management. Implements virtual context by paging data between "main memory" (context window) and "disk" (external storage). Uses function calls/tool use to let the LLM manage its own memory — reading, writing, searching, and archiving. Interrupts control flow between memory operations.

**Key limitations**:
- Relies entirely on the LLM's ability to manage its own memory via tool calls
- Heavy LLM call overhead — every memory operation is an LLM inference
- For 6M tokens: the LLM would need to search/retrieve relevant passages from external storage
- Essentially becomes a sophisticated RAG system with LLM-controlled retrieval
- Quality depends heavily on the underlying LLM's tool-use ability
- No compression — just pagination of the original text

---

## 15. StreamingLLM — Attention Sinks (Training-Free)

| Field | Detail |
|-------|--------|
| **Paper** | "Efficient Streaming Language Models with Attention Sinks" |
| **Authors** | Guangxuan Xiao, Yuandong Tian, Beidi Chen, Song Han, Mike Lewis |
| **Venue/Date** | ICLR 2024; arXiv 2309.17453, Sep 2023 |
| **Code** | https://github.com/mit-han-lab/streaming-llm |
| **Base models** | Llama-2, MPT, Falcon, Pythia |
| **Max scale tested** | Up to 4 million tokens streaming |
| **Training req** | **NONE** — training-free; modifies KV cache eviction strategy |
| **GPU fit (4xL40S)** | Works on any model that fits; just changes cache management |

**Mechanism**: Discovers that initial "sink" tokens receive disproportionate attention regardless of content. Keeps these sink tokens plus a sliding window of recent tokens in the KV cache, evicting middle tokens. This allows infinite-length streaming without fine-tuning, with 22.2x speedup over sliding-window recomputation.

**Key limitations**:
- Only retains recent context + attention sinks — middle content is LOST
- NOT suitable for document QA — cannot access content outside the sliding window
- Designed for streaming chat, not document comprehension
- Completely unsuitable for "remembering" a 6M-token novel

---

## 16. Unlimiformer — kNN Attention for Unlimited Input

| Field | Detail |
|-------|--------|
| **Paper** | "Unlimiformer: Long-Range Transformers with Unlimited Length Input" |
| **Authors** | Amanda Bertsch, Uri Alon, Graham Neubig, Matthew R. Gormley |
| **Venue/Date** | NeurIPS 2023; arXiv 2305.01625, May 2023 |
| **Code** | https://github.com/abertsch72/unlimiformer |
| **Base models** | BART, Longformer (encoder-decoder models) |
| **Max scale tested** | 500K tokens (BookSum) |
| **Training req** | **NONE** for inference; optional fine-tuning improves quality |
| **GPU fit (4xL40S)** | Fits easily; uses kNN index for attention |

**Mechanism**: Wraps encoder-decoder transformers, offloading cross-attention computation to a kNN index. Encodes the full input, stores all hidden states in a FAISS index, then at each decoding step retrieves the top-k most relevant encoded states via kNN search. No learned weights added.

**Key limitations**:
- Only works with encoder-decoder models (BART, Longformer) — NOT decoder-only LLMs
- Not applicable to modern decoder-only models (Llama, Qwen, etc.)
- 500K tested, but kNN index for 6M tokens would be very large
- Encoding 6M tokens through the encoder is itself a bottleneck

---

## 17. LongMem — Decoupled Memory Architecture

| Field | Detail |
|-------|--------|
| **Paper** | "Augmenting Language Models with Long-Term Memory" |
| **Authors** | Weizhi Wang, Li Dong, Hao Cheng, Xiaodong Liu, Xifeng Yan, Jianfeng Gao, Furu Wei (Microsoft) |
| **Venue/Date** | arXiv 2306.07174, Jun 2023 |
| **Code** | Not found |
| **Base models** | Internal models |
| **Max scale tested** | 65K tokens in memory bank |
| **Training req** | Trains a side network for retrieval; original LLM stays frozen |
| **GPU fit (4xL40S)** | Should fit, but no public code |

**Mechanism**: Uses a decoupled architecture: the original LLM is frozen as a "memory encoder," while a separate trainable side-network handles retrieval and reading from a memory bank. Avoids memory staleness because the encoder is frozen. Supports unlimited-length memory bank in principle.

**Key limitations**:
- No public code
- Only tested at 65K tokens — 100x short of target
- Requires training the side network
- Internal Microsoft models only

---

## Comparative Analysis for 6M Chinese Novel

### Feasibility Ranking (most to least promising for our use case)

| Rank | Method | Feasibility | Why |
|------|--------|-------------|-----|
| 1 | **LoRA continued pretraining** | HIGH | Standard tooling, fits on 4xL40S, can process 6M tokens. Main question: does it actually work? |
| 2 | **Reading comprehension FT** | HIGH | Generate QA pairs from novel, fine-tune. Better than raw pretraining per literature. |
| 3 | **CaMeLS + QA FT** | MEDIUM | If we can implement the meta-learned loss scaling, should improve over naive QA FT. No code though. |
| 4 | **MemGPT/Letta** | MEDIUM | Training-free, works today, but is essentially RAG with LLM-controlled retrieval. |
| 5 | **RMT** | MEDIUM-LOW | Proven at 11M tokens but only on synthetic tasks with tiny models. |
| 6 | **MemoryLLM** | LOW | Fixed-size memory pool can't faithfully represent 6M tokens of novel detail. |
| 7 | **ICAE** | LOW | 4x compression still leaves 1.5M tokens; only tested at 5K. |
| 8 | **AutoCompressor** | LOW | Recursive compression over 200 steps = information loss. |
| 9 | **Infini-attention** | LOW | No public code; lossy compressive memory. |
| 10 | **Titans** | VERY LOW | No code, no pretrained models, train from scratch only. |
| 11 | **Memory Layers** | VERY LOW | Pretraining-time approach; can't inject post-hoc. |
| 12 | **Larimar** | VERY LOW | 1.3B only; fact-editing focus. |
| 13 | **Gisting** | N/A | Designed for prompt compression, not documents. |
| 14 | **StreamingLLM** | N/A | Loses all middle content. |

### Key Insight from Literature

The most consistent finding across papers is that **RAG outperforms fine-tuning for knowledge injection** (Ovadia et al., 2023). LoRA further underperforms full fine-tuning. This aligns with our experiment 013 findings where RAG beat MSA.

For a 6M-token Chinese novel, the realistic options are:

1. **RAG** (already tested in 013 — scored 2.152-2.287 vs MSA's 1.574)
2. **LoRA/QLoRA continued pretraining** on raw novel text + QA pairs
3. **LLaMA Pro-style block expansion** — add new transformer blocks, train only those
4. **Hybrid: LoRA pretraining + RAG** — inject general knowledge via LoRA, use RAG for specific details

### What's Missing from the Literature

- No paper tests memory augmentation at 6M+ tokens on **natural language QA** (as opposed to synthetic needle tasks)
- No paper tests these methods on **Chinese literary text** specifically
- No paper compares all these approaches head-to-head on the same task
- The gap between "works on synthetic tasks" and "works on real novel QA" is unknown
