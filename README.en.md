# CUMCM 2026 Problem C: Rolling Microgrid Dispatch

This is a clean, history-free public extraction of the original competition workspace. It contains the original Python implementation for grid purchasing, storage dispatch, forecast updates, settlement, and chronological strategy evaluation.

This repository is not affiliated with the contest organizer and is not an official solution. Problem statements, official workbooks, paper templates, third-party papers, the submitted paper, and submission archives are intentionally excluded.

## Quick start

```bash
conda env create -f environment.yml
conda activate cumcm26-open
python scripts/smoke_synthetic.py
python -m pytest -q
```

Tests backed by synthetic data run without contest files. Integration tests are skipped until the official inputs listed in [`data/INPUTS.sha256`](data/INPUTS.sha256) are placed under `c_grid/attachments/`.

For the full workflow, source boundary, and limitations, see the [Chinese README](README.md), [reproducibility guide](docs/REPRODUCIBILITY.md), and [model limitations](docs/MODEL_AND_LIMITS.md).

Original code and documentation in this repository are licensed under the [MIT License](LICENSE). Excluded third-party materials retain their respective rights.

