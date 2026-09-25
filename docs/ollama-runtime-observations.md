# Ollama Runtime Observations

Issue #7, Ollama runtime path. Recorded 2026-09-20 by Skipl1 (Dimas).

## What this is, and what it is not

This is a technical observation of the runtime path on real hardware. It is
**not** a pilot run and **not** part of the research conclusions:

- the GPU is a GTX 1080, which is not in the research matrix;
- the run used three prompts and one repetition, not the frozen protocol;
- its artifacts were written outside the repository and are not committed.

Two findings below invalidate every measured request under the current rules,
so no run on any host can be called validated until they are resolved.

## Host

| Item | Value |
| --- | --- |
| OS | Windows 11 Pro 26200 |
| GPU | NVIDIA GeForce GTX 1080, 8 GiB, compute capability 6.1 |
| Driver | 582.66 |
| Ollama | 0.34.2 |
| Model | `llama3.2:3b-instruct-q4_K_M`, digest `a80c4f17acd5…`, pulled by hand |

## 1. The runtime path works end to end

`doctor --json` reports `ok: true` with the real runtime version (`0.34.2`),
the resolved digest, and placement (`size_vram == size`, `gpu_fraction 1.0`).
A three-prompt run completed in 10.5 s and produced every artifact, with
`energy_source: total_energy_counter` and per-request energy figures.

Measured on this host, for scale only: TTFT 52–122 ms, end-to-end latency
0.07–1.83 s, 2.45–4.59 J per output token.

## 2. `prompt_eval_cached_count` is real, and it is the prefix-cache signal

The open question from the Task 4 review is answered on a live server. Ollama
0.34.2 reports `prompt_eval_cached_count` in the final chunk. Repeating one
prompt against a loaded model:

| Request | `prompt_eval_cached_count` / `prompt_eval_count` | Prefill |
| --- | --- | --- |
| first after load | 0 / 35 | 565 ms |
| same prompt again | 34 / 35 | 75 ms |

The field means what its name says, and prefill time follows it. The field
already merged into `ollama.py` is therefore correct.

## 3. A structural cache floor required an explicit validity rule

At the time of this observation, `runner.py` marked a request invalid when
`prompt_eval_cached_count > 0`, and `results.py` repeats the rule in
validation. But Ollama always reuses the chat-template preamble, so the count
never reaches zero after the first request.

Five unrelated prompts, each with a fresh random 24-hex-character prefix:

| Prompt body | cached / total |
| --- | --- |
| `Name a colour.` | 20 / 46 |
| `Опиши погоду одним словом.` | 21 / 51 |
| `def f(x): return x*2 # explain` | 21 / 51 |
| `What is 17 plus 4?` | 20 / 50 |
| `Recite one line of Latin.` | 21 / 49 |
| pilot `long-01` (443 tokens) | 21 / 443 |

The floor is 20–21 tokens and does not grow with prompt length: it is the
template preamble, not contamination. In the observation run all three
measured requests were rejected with `cached_prompt_tokens`, so the run
produced zero requests eligible for primary analysis.

**Resolution in Issue #13.** At least two warm-up requests are required. The
cached count from the final warm-up is recorded with the model and digest as
the template baseline. A measured request is invalid only when the count is
missing or exceeds that baseline; counts at or below the floor remain valid.
The output stores both the applied baseline and excess, and semantic
validation recomputes the decision from raw fields. This policy is covered by
hardware-independent tests but still requires confirmation with Ollama on the
RTX 5060 host.

## 4. The cache buster now puts entropy first

`_cache_busted_prompt` prefixes the prompt with the request ID, but IDs share
a long run-specific prefix (`<run-id>-request-000NN`), and the shared part is
cached. Two prompt bodies, three requests per prefix style:

| Prefix style | Prompt body | cached / total | Prefill |
| --- | --- | --- | --- |
| shared run ID | short | 46 / 69 | 40–44 ms |
| random first | short | 20 / 50–56 | 34–39 ms |
| shared run ID | long | 34 / 440 | 250–253 ms |
| random first | long | 21 / 443 | 252–272 ms |

(The shared-ID rows carry more prompt tokens because the ID itself is long.)

Two thirds of a short prompt is served from cache, and prefill is measured on
a quarter of the tokens the prompt actually has. Short prompts are exactly the
decode-focused cases the protocol depends on. Putting a per-request random
nonce at the very start of the prompt brings contamination down to the floor.

Issue #13 implements a deterministic SHA-256 nonce derived from the request ID
as the literal first prompt line. The shared marker follows it, so no common
run-ID head precedes the entropy. Determinism preserves auditability without
giving Ollama a reusable leading prefix.

## 5. Placement can be silently CPU-only

The first load on this host reported `size_vram: 0`, i.e. 100% CPU, while the
server had started before CUDA discovery finished. The preflight caught it:
`fully_on_gpu` was `False` and the run would have been refused. After a clean
server start the same model loaded fully into VRAM.

Worth knowing for the measurement hosts: Ollama 0.34.2 ships a CUDA v13 build
compiled for architectures `[750 800 860 890 1000 1200]` and skips Pascal
(`cc 610`) there, falling back to its CUDA v12 build. The log line is
`skipping CUDA device — compute capability not in compiled architectures`.
A host whose GPU falls out of both builds would run on the CPU and the run
would be rejected rather than silently mismeasured.

## 6. For the NVML owner: Pascal does expose the energy counter

Contrary to the usual "Volta and newer" assumption,
`nvmlDeviceGetTotalEnergyConsumption` works on this GTX 1080 with driver
582.66, and it agrees with integrated power: 79.26 J over 5.03 s implies
15.76 W, against a 15.52 W mean of 49 legacy power samples, about 1.5% apart.
So `energy_source` is `total_energy_counter` here, not a fallback.

One caveat for @Qcsteeven: at idle, `NVML_FI_DEV_POWER_INSTANT` read 41.9 W
while the legacy average over the same period was 15.5 W. Instantaneous power
is a momentary sample and integrating it at 100 ms intervals may overestimate
energy. Where the counter exists it should stay the preferred source.

## Code changes made under this Issue

In `ollama.py` and `test_ollama.py` only:

- `AvailableModel.capabilities` and `max_context_length`, both taken from the
  real 0.34.2 `/api/tags` payload, with `is_thinking_model` derived from the
  first. A thinking model streams reasoning outside the `response` field, so
  the client would record it as having produced no text; now it can be
  detected before it is measured.
- Tests covering truncation by `num_predict`, trailing chunks after the final
  one, a reloaded model's load duration, an omitted `keep_alive`, a near-total
  cache hit, and a zero cache hit that is not an absent one.

Nothing in `runner.py`, `results.py`, or the frozen prompt and model protocol
was touched.

## Follow-up change under Issue #13

The runner and validator now implement the template-floor policy above, record
the baseline and excess in derived metrics, require two warm-ups, and abort
before measured requests when the baseline cannot be established. The prompt
nonce also moved ahead of every static character. These are methodology fixes
derived from this observation; they do not turn the GTX 1080 observation into
an experimental run.
