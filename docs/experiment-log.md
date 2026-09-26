# Experiment Log

This file is the append-only human index of hardware runs committed under
`experiments/runs/`. Raw artifacts and their manifest hashes remain the source
of truth. Do not rewrite earlier entries when analysis changes; append a dated
correction that references the original run ID.

Each completed entry records:

- date, contributor, host role, GPU, driver, and power limit;
- Git commit, runtime version, model tag and digest, and config/prompt hashes;
- run ID, validation outcome, valid/request counts, and energy source;
- material anomalies, exclusions, and links to the committed run directory.

Environment probes that do not execute an LLM request belong in the separate
section below and are never counted as experimental runs.

## Validated Experimental Runs

None yet. The first publishable entry will be the RTX 5060 Laptop `pilot-v1`
run repeated from the reviewed, merged implementation.

## Environment Probes

### 2026-09-26 — RTX 4060 Ti desktop benchmark-v1 observation

- Contributor: Qcsteeven
- Scope: one local `benchmark-v1` run and three calibration launches on the
  unmerged stabilization branch (`a683a57`, PR #17). This is **not** a
  publishable dataset: the code is untagged, and every run contains requests
  rejected by the validity rule. It used a local copy of
  `configs/benchmark-v1.toml` that differs only by
  `host_id = "rtx4060-desktop"`. Calibration used the same prompts and
  controls with `llama3.2:3b-instruct-q4_K_M` only. Artifacts stay local.
- GPU and runtime: RTX 4060 Ti 8 GiB, driver 560.94, 160 W limit, Ollama
  0.34.2. Digests: `qwen3:4b-instruct-2507-q4_K_M` `0edcdef34593…`,
  `qwen3:4b-instruct-2507-q8_0` `aa7252f68dda…`, `llama3.2:3b-instruct-q4_K_M`
  `a80c4f17acd5…`, `llama3.2:3b-instruct-q8_0` `e410b836fe61…`. All four loaded
  fully on the GPU.
- Conditions: the wallpaper renderer was closed first, and idle power was
  8.8 W before the benchmark. Idle readings taken immediately after a run were
  17–28 W because the GPU had not yet settled.
- Validity: 456/480 benchmark requests valid; calibration 110, 114 and 116 of
  120. Every rejection has the same cause, one cached prompt token above the
  template baseline (4 vs 3 for qwen3, 21 vs 20 for llama3.2). For qwen3 the
  first UUID character matched the previous request's, and qwen3 tokenizes
  digits individually. For llama3.2 the extra token appears mostly when a
  letter-led marker follows a digit-led one. The excess is a tokenization
  boundary effect of `uuid_prefix_v1`, not reuse of prompt content, but it
  makes an all-valid 480-request run practically unreachable (about 0.95^480).
- Calibration CV (`max(CV_speed, CV_energy)` over three runs): short 1.0%,
  long 1.3%, scored 3.9%. The resulting thresholds are 5.0%, 5.0% and 11.8%.
- Rank-inversion evaluation (PR #18 analysis, valid requests only): speed
  and energy produced the **same full ordering** in all three blocks.
  `llama3.2:3b-instruct-q4_K_M` led every block, ahead of the runner-up by
  26–52% in tok/s and 23–27% in tok/J. No inversion exists, so on this single
  host the hypothesis would be reported as unsupported. The pre-registered
  verdict still needs both hosts and publishable runs.
- Mechanism: mean GPU power was 109.9 W for both Q4 models and 93.6–95.1 W for
  the Q8 models. Q8 saved 13–15% power but lost 35–36% throughput, so
  energy per token (1.09, 1.38, 1.45, 1.85 J/token) followed speed.
- Quality: qwen3 Q4 and Q8 scored 1.0, `llama3.2` Q4 0.8125, and `llama3.2` Q8
  0.75, exactly at the inclusive floor.

### 2026-09-26 — RTX 4060 Ti desktop pilot-v1 observation

- Contributor: Qcsteeven
- Scope: three independently launched `pilot-v1` runs on the unmerged
  stabilization branch (`a683a57`, PR #17). They are **not** publishable runs:
  the code is not yet tagged `pilot-v1-code`. The runs used a local copy of
  `configs/pilot-rtx4060.toml` that differs only by
  `host_id = "rtx4060ti-desktop"`; the frozen `rtx4060-desktop` ID names this
  same machine. Artifacts stay local and are not committed.
- GPU: NVIDIA GeForce RTX 4060 Ti, 8 GiB; driver 560.94; enforced power limit
  160 W. This is the intended desktop host of Issue #5; earlier documents
  named it "RTX 4060", a 115 W part that is not interchangeable with it.
- Runtime: Ollama 0.34.2 (portable build); model
  `llama3.2:3b-instruct-q4_K_M`, digest `a80c4f17acd5…`, pulled by hand.
- Preflight: `doctor --json` returned `ok: true` with the frozen version and
  digest, `fully_on_gpu: true`, `gpu_fraction: 1.0`, and
  `energy_source: total_energy_counter`.
- Result: 54/54 measured requests valid across the three runs, every
  `validation.json` reports `ok: true`, quality 1.0 in every run, template
  cache baseline 20, 21 and 20 tokens, excess cache 0 on every request.
- Energy source: 48 requests used the total-energy counter; 6 fell back to
  instantaneous-power integration because the counter produced no positive
  delta. All six fallbacks record their reason.
- Run-level repeatability (ratio of sums per run, three runs):

  | Category | tok/s per run | CV | tok/J per run | CV | Threshold |
  | --- | --- | ---: | --- | ---: | ---: |
  | short | 99.9, 101.8, 98.7 | 1.5% | 0.940, 0.928, 0.918 | 1.1% | 5.0% |
  | long | 90.3, 89.7, 87.9 | 1.4% | 0.836, 0.832, 0.819 | 1.0% | 5.0% |
  | scored | 46.0, 42.4, 40.5 | 6.6% | 0.291, 0.334, 0.454 | 23.5% | 70.4% |

- Finding: scored utility requests produce two output tokens in about 40–50
  ms, which spans only two 100 ms telemetry samples. Their energy is therefore
  at the resolution limit of the sampler, the energy CV reaches 23.5%, and
  single requests imply average power up to 184 W against the 160 W limit. The
  `scored` block can gate quality, but its energy ranking cannot support a
  material-inversion claim. Decode-heavy `short` and prefill-heavy `long`
  blocks are stable to about 1–1.5%.
- Background load: a desktop wallpaper renderer kept about 21% GPU 3D
  utilization during the session, and the idle GPU drew a median 22.8 W in
  P0–P3 instead of settling in a low-power state. NVML reports whole-GPU
  power, so these energies include that background share, and the renderer
  also competes for the GPU. The publishable run must close GPU-active
  desktop applications first and record idle power before starting.
- Finding: output length varies between repetitions of the same prompt at
  temperature 0 and seed 42 (for example 122, 105 and 135 tokens), consistent
  with the per-repetition UUID marker changing the prompt. Ratio-of-sums
  metrics absorb this, but per-request comparisons across repetitions do not.

### 2026-09-25 — RTX 5060 Laptop NVML reliability check

- Contributor: Quirence/Codex
- GPU: NVIDIA GeForce RTX 5060 Laptop GPU, 8 GiB
- Driver: 591.66; reported power limit 80 W
- Capability result: all requested NVML fields are exposed.
- Initial observation: the total-energy counter implied hundreds of watts at
  idle and was rejected by the existing physical-consistency check. A stress
  probe also found equal consecutive monotonic timestamps in 6 of 20 short
  windows and one transient 4666 W instantaneous-power sample. The former made
  otherwise usable integrations unavailable; the latter could dominate an
  energy result.
- Corrective check: equal timestamps now retain the latest reading while a
  decreasing timestamp remains invalid. A power stream containing a reading
  above 120% of the enforced limit is rejected rather than clipped, with
  fallback from instantaneous to legacy power.
- Verification: 20 consecutive 0.25 s windows at a 50 ms sampling interval
  all selected `power_instant_integration`; none was unavailable. Observed
  average and peak power stayed within approximately 8.71–9.21 W.
- Scope: telemetry reliability validation at idle only. Ollama was not
  installed during the initial probe, no model was loaded, and no inference
  run was produced.

#### Follow-up after Ollama installation

- Runtime: Ollama 0.34.2, installed from the pinned `winget` package with a
  verified installer hash.
- Model: `llama3.2:3b-instruct-q4_K_M`, digest
  `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`,
  quantization Q4_K_M, parameter size 3.2B.
- Placement preflight: context 4096, `size_vram == size == 2,554,708,622`
  bytes, GPU fraction 1.0.
- Cache probe: the first excluded request paid 43.85 s of one-time startup;
  the second completed in 0.58 s and reported a 20-token template floor. A
  long-prompt probe then reported 20 cached of 468 prompt tokens, so the PR #16
  policy recorded zero excess.
- Loaded telemetry probe: a 256-output-token request completed in 2.47 s with
  51 samples and a 63 ms maximum gap. The total-energy counter reported a
  physically impossible 299.26 J delta. PR #15 rejected it and integrated
  instantaneous power instead: 152.55 J, 61.79 W average, and 91.90 W observed
  peak.
- Scope: component-level hardware acceptance only. This was not the frozen
  18-request pilot, no run directory was created, and no research comparison
  is inferred from these values.

#### Provisional combined integration run

- Scope: local acceptance of the combined, still-unmerged PR #14, PR #15, and
  PR #16 changes. The run directory is intentionally ignored by Git and must
  not be treated as a frozen or published research artifact.
- Workload: the six `pilot-v1` prompts, three measured repetitions, two
  excluded warm-ups, one model, concurrency 1, and 18 measured requests.
- Runtime and placement: Ollama 0.34.2; the same model digest listed above;
  context 4096; GPU fraction 1.0 on the RTX 5060 Laptop.
- Cache result: the final warm-up established a 20-token template baseline.
  All 18 measured requests reported 20 raw cached tokens and zero excess, so
  none was rejected as prompt-cache contamination.
- Telemetry result: semantic validation accepted all 18 requests. Seventeen
  requests used the total-energy counter after its per-request sanity check;
  one short request produced no positive counter delta and fell back to
  instantaneous-power integration. For requests that retained the counter,
  its energy was approximately 0.73--1.29 times the independently integrated
  instantaneous-power estimate. The mixed source is recorded explicitly in
  the derived summary rather than hidden.
- Coverage: the largest observed telemetry gap was 125 ms, below the 500 ms
  rejection threshold. The maximum observed power sample was 91.70 W; this is
  an observed sample, not a claim about wall power or sustained TGP.
- Analysis result: the report generated successfully, but no comparative rank
  is possible with one model configuration. The scored prompts averaged 0.5,
  below the frozen 0.75 quality floor, so the configuration was correctly
  excluded from ranking. A follow-up A/B check showed that the current leading
  raw SHA-256 cache-buster changed the arithmetic answer from `391` to a safety
  refusal. Therefore the observed score is a measurement-instrument confound,
  not evidence about the model's arithmetic quality. PR #16 records the
  proposed UUID-form marker design and must be updated before the repeated run.
- Decision: the acceptance run supports the implementation path only. It
  makes no speed-versus-energy research claim and will be repeated from the
  reviewed, merged commit before publication.

### 2026-09-20 — RTX 3050 Laptop NVML smoke check

- Contributor: Quirence/Codex
- GPU: NVIDIA GeForce RTX 3050 Laptop GPU, 4 GiB
- Driver: 572.83
- Reported power limit: approximately 74–75 W
- Capability result: temperature, clocks, utilization, memory, instantaneous
  power, legacy power, total-energy counter, and power limit are available.
- Observation: over two idle samples the total-energy delta was about
  171–205 J for roughly 2 s, while instantaneous-power integration measured
  about 23–24 J at 11.6–11.9 W average power.
- Decision: treat the counter as physically inconsistent on this host/driver.
  The implemented per-request sanity check falls back to
  `power_instant_integration` and records the rejection reason.
- Scope: telemetry smoke validation only. Ollama was unavailable, no model was
  loaded, and no inference run was produced.

### 2026-09-20 — GTX 1080 Ollama runtime observation

- Contributor: Skipl1 (Dimas)
- Scope: Issue #7 runtime validation. This entry executed real inference
  requests, but it is **not** an experimental run: the GPU is outside the
  research matrix and the workload was three ad-hoc prompts at one
  repetition, not the frozen protocol. Its artifacts were written outside the
  repository and are not committed.
- GPU: NVIDIA GeForce GTX 1080, 8 GiB, compute capability 6.1
- Driver: 582.66; reported power limit 200 W
- Runtime: Ollama 0.34.2; model `llama3.2:3b-instruct-q4_K_M`, digest
  `a80c4f17acd5…`, pulled by hand
- Result: `doctor --json` reported `ok: true` with the live version, the
  resolved digest and `gpu_fraction 1.0`; the run completed in 10.5 s and
  wrote every artifact with `energy_source: total_energy_counter`.
- Findings that block measurement everywhere: the chat-template prompt-cache
  floor of 20–21 tokens against a rule that rejects any cached token, and a
  cache buster whose shared run-ID head is itself cached. See
  `docs/ollama-runtime-observations.md`.
- Telemetry note: unlike the RTX 3050 host, this driver's total-energy counter
  is self-consistent, matching integrated power to about 1.5%.

## Methodology Decisions

### 2026-09-25 — Ollama template-cache baseline

- Source observation: the 2026-09-20 GTX 1080 runtime check above found a
  stable 20–21 token chat-template floor and additional contamination from a
  shared cache-buster prefix.
- Decision: require at least two warm-ups for every model and use the final
  warm-up's cached count as the recorded per-model, per-digest baseline.
- Validity rule: a measured cached count must be present and no larger than the
  baseline. The raw count, applied baseline, and excess are persisted and
  independently checked by semantic validation.
- Prompt construction: a deterministic SHA-256 request nonce is the literal
  first line, before the shared marker and prompt body.
- Metric rule: prefill throughput excludes all cached tokens, including the
  accepted template floor.
- Scope: code and synthetic-test validation only. The policy is not considered
  hardware-validated until it passes against Ollama on the RTX 5060 host.

### 2026-09-25 — UUID cache-marker correction and acceptance

- Correction: the raw SHA-256 first-line marker above is retained as historical
  context but is superseded. A live A/B check found that it changed the
  arithmetic utility answer from `391` to a safety refusal.
- Decision: encode the first 16 SHA-256 bytes as a deterministic UUID v4 and
  follow it with an explicit instruction that the benchmark marker is metadata
  to ignore. A logical prompt and repetition share a marker across model
  configurations in the same run.
- Diagnostic evidence: 10/10 arithmetic requests returned `391` with the UUID
  marker and all 10 reported the 20-token template floor.
- Stabilization acceptance: the complete six-prompt workload then produced
  18/18 valid measured requests on the RTX 5060 Laptop, all with raw cache 20
  and excess cache 0. Both scored prompts passed in all three repetitions, so
  the aggregate quality score was 1.0. All requests selected instantaneous
  power integration during this run.
- Scope: ignored local acceptance artifact from the unmerged stabilization
  branch. It verifies the correction but is not the publishable research run;
  the run must be repeated from the reviewed `pilot-v1-code` tag.
