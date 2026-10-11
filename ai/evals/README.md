# AI evaluation data

`data/query_refinement.jsonl` contains independently authored Korean utterances
for regression testing the boundary between STT, query refinement, and menu
search. It intentionally evaluates query/attribute extraction only; it contains
no expected cart mutation or order decision.

Run the deterministic fallback evaluation with:

```bash
python evals/run_fallback_eval.py
```

Provider-backed quality and latency runs belong in `experiments/` and must not be
part of production startup.

