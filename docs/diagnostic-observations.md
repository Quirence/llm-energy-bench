# Diagnostic GPU Observations

This document preserves useful pre-baseline evidence from contributor machines.
These observations are not dataset entries: the raw run directories were not
committed, the code was not tagged, and some launches fail the final validity
rules. They may motivate tests and Issues but cannot support the research
verdict.

## RTX 4060 Ti desktop — Qcsteeven (Lev)

- Historical pre-freeze identity: `rtx4060ti-desktop-observation`. The reviewed
  protocol now names the actual RTX 4060 Ti as the second primary host, but
  this does not retroactively validate the old local artifacts.
- Ollama 0.34.2 and the pilot Q4 model were observed fully placed on the GPU.
- Three local pilot launches produced 54/54 requests accepted by the then
  current validator.
- The larger local campaign reproduced a one-token cache excess: 24 of 480
  requests were rejected, and calibration launches showed the same boundary
  effect.
- A desktop wallpaper renderer caused measurable background GPU load in an
  earlier attempt. That attempt is contamination evidence, not repeatability
  evidence.
- No speed/energy ranking or hypothesis conclusion from these local artifacts
  is retained. They predate the final schema and are not reviewable in the
  repository; the primary run must be repeated from the tagged baseline.

## GTX 1080 — Skipl1 (Dimas)

- Distinct observation host outside the primary matrix: `gtx1080-observation`.
- Local pilot, calibration, and benchmark-shaped launches reproduced the
  one-token cache excess. Their accepted-request counts were respectively
  52/54, 337/360, and 454/480 under the then current validator.
- One calibration request failed after a CUDA illegal-instruction error. The
  next request included about 3.06 seconds of model loading but was incorrectly
  accepted as a warm measurement.
- This observation directly motivates the schema-v2 rule that a measured
  `load_duration` above 100 ms invalidates and aborts the complete launch.
- The local run-derived threshold and all cross-GPU/ranking conclusions are
  discarded. A launch containing a cold reload cannot establish repeatability.

## What may be cited

The observations may be cited only as engineering evidence for two validity
defects:

1. a unique cache marker can add one tokenizer-boundary cache token even when
   prompt content is not reused;
2. a runtime restart can silently turn the next nominally warm request into a
   cold model load.

Any numerical comparison of models or GPUs must be regenerated from the exact
`pilot-v1-code`/later campaign tag and committed with manifests, full digests,
hashes, raw request/output records, compressed telemetry, and validation.
