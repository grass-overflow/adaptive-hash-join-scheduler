# Consolidated Results and Plots

This folder is a copy of the contents of the repository's `results/` directory as of 2026-10-25. It includes raw and summary CSVs, analysis outputs, plots, and other result artifacts from current and historical experiment runs.

The original directory structure is preserved so files remain attributable to their experiment. Root-level smoke-test CSVs are included at this folder's root. Original files remain unchanged in `results/`.

The current-source experiment sets are:

- `adaptive_linear_cost_final_grid/`
- `adaptive_linear_cost_final_z175/`
- `adaptive_linear_cost_final_small_z175/`

The curated static vs fixed-chunk-dynamic vs proposed-policy figures, paired-gain plots, data tables, and coefficient-selection explanation are in `three_scheduler_comparison/`. Its filtered win plot is accompanied by unfiltered views and seed-level confidence intervals.

Other subfolders contain historical, exploratory, tuning, or smoke-test artifacts. Do not combine results from different source versions as if they were one experiment. The current evidence and source-version caveats are documented in `../../FINAL_REPORT.md`.
