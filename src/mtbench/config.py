"""Shared constants for the source adapters and audits."""

# Samples whose output window starts after this date are flagged post_cutoff (defined only here).
POST_CUTOFF_DATE = "2025-07-01"

# Drop a sample when this fraction (or more) of its input or output window is missing.
MISSING_FRAC_MAX = 0.7

# Near-duplicate text detection (MinHash over word shingles).
MINHASH_NUM_PERM = 128
MINHASH_THRESHOLD = 0.9
MINHASH_SHINGLE = 5

TEXT_KINDS = ("report_of_past", "forecast_of_future", "mixed")
