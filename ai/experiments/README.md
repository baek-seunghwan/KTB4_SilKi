# Experiments

Keep notebooks and one-off provider comparisons here. Production imports must
never depend on this directory.

Recommended experiment outputs:

- CLOVA transcription accuracy and turn-finalization latency by noise level.
- Gemini Flash-Lite structured-output validity, timeout rate, and fallback rate.
- Semantic-search Recall@3 for exact names, descriptions, dialect, and negative
  attributes.
- Search score distributions used to calibrate
  `SILKI_AI_SEARCH_SCORE_THRESHOLD`.

Do not commit credentials, raw user audio, or personally identifying transcripts.
