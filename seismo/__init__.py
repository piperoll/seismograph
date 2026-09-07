"""PipeRoll Seismograph - model-behavior drift observatory.

Package layout:
    providers  - HTTP adapters for model APIs (stdlib urllib only)
    battery    - probe battery loading and canonical hashing (Tier 1, fixed)
    dynamic    - Tier 2: seeded procedural battery (the gaming tripwire)
    grade      - mechanical graders (the frozen ruler: no LLM judges in v0)
    run        - collection orchestrator: battery x roster -> raw session
    digest     - raw session -> public reading (aggregates only, no raw text)
    detect     - advisory baseline comparison across readings (drift)
    divergence - fixed-vs-dynamic gap across the two tiers (anti-gaming)
"""

RUNNER_VERSION = "0.1.0"
GRADER_VERSION = "0.1.0"
