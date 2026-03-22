# experiments - Hypothesis Validation

## Purpose

Each subdirectory is a self-contained experiment validating a specific hypothesis.

## Directory Convention

```
experiments/
  001_mask_vs_remove_tools/
    hypothesis.md      # What we're testing and why
    config.yaml        # All experiment parameters
    run.py             # Entry point (self-contained)
    results/           # Output data
      run_1.json
      run_2.json
      summary.md       # Conclusions with data
```

## Requirements

- **Reproducible**: same config.yaml + run.py must produce comparable results
- **Data-supported**: conclusions backed by quantitative results
- **Self-contained**: each experiment has its own config, no shared mutable state
- **Documented**: hypothesis.md explains what and why before running

## Naming

Use `<NNN>_<short_name>/` format. Number sequentially.
