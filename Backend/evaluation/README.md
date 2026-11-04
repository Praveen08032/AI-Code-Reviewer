# Review evaluation

This benchmark measures static AI issue classification against 30 manually labeled examples: one correct program, one logic/boundary bug and one security issue in each supported language. The examples state their input assumptions. It does not run submitted programs or prove the improved code is correct.

From `Backend`, run:

```powershell
.\venv\Scripts\python.exe evaluate_reviews.py
```

This consumes up to 30 real Gemini requests and writes `results/latest.json` after each response. It stops on provider quota/unavailability errors. `--limit 3 --output evaluation/results/small-run.json` selects a smaller run. Do not report a partial run as full ten-language coverage. Outputs record the model, time and prompt hash for reproducibility; model responses can vary.

## Recorded run on 3 November 2026

The checked-in run completed 21 of 30 examples before Gemini returned HTTP 429. Nine examples remain unfinished; Rust, PHP and Ruby have no completed live cases in that run.

| Measurement | Completed subset |
| --- | --- |
| Correct classifications | 20 / 21 |
| Labeled buggy programs detected | 14 / 14 |
| Correct programs incorrectly flagged | 1 / 7 |
| Uncertain assessments | 0 |
| Median response time | 3.47 seconds |

The false alarm was Java palindrome code: the model requested null validation despite a nonnull input precondition. A later prompt clarification now explicitly respects guaranteed inputs. That change still needs a fresh real-provider evaluation after quota is available; the saved results retain the earlier prompt hash and observation.

These small examples establish a reproducible baseline, not a general accuracy guarantee or a security certification. Review findings and generated fixes need human review and normal project tests. Next evaluation work should include larger projects, independently authored examples and sandboxed execution with resource/network limits if execution testing becomes a product feature. No arbitrary code execution is enabled in this application.
