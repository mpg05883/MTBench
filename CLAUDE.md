# MTBench data extension

- Goal: add new (time series, aligned text) sources to MTBench using the EXISTING pipeline. Do not rewrite the pipeline; add adapters.
- Source spec lives in docs/new_sources.md.
- Every sample must satisfy: text timestamp <= end of input window (no future leakage), TS window complete, entity/location match.
- Raw downloads go in data/raw/<source>/, processed output in data/processed/<source>/ in the same schema as the existing finance/weather outputs.
- Never download >2GB without asking. Log every URL fetched to data/raw/<source>/MANIFEST.md.
- Each source gets a script in scripts/sources/<source>.py and a short README section.
