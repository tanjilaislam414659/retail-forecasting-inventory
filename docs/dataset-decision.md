# Dataset decision

Reviewed: **2026-11-01**. Scope: three public candidates, official publisher or
competition-organizer sources, metadata only. No dataset files were downloaded.
Listed sizes are publisher figures, not local measurements.

## Comparison

| Candidate | Access and terms | History and scale | Variables and task fit | CPU implications (planning estimates) |
| --- | --- | --- | --- | --- |
| [UCI Online Retail](https://archive.ics.uci.edu/dataset/352/online+retail) | Public download link; no account indicated. CC BY 4.0. XLSX, 22.6 MB. | 2010-12-01 to 2011-12-09; 541,909 transaction rows. | Invoice, product, description, quantity, timestamp, price, customer, country. Requires aggregation into SKU sales series. | Smallest option. Spreadsheet parsing can use substantially more RAM than file size; process selected columns and aggregate early. |
| [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) | Public download link; no account indicated. CC BY 4.0. XLSX, 43.5 MB. | 2009-12-01 to 2011-12-09; 1,067,371 transaction rows. | Similar transaction fields, cancellations and missing values documented. UK non-store gift retailer; many wholesale customers. | Moderate ingestion work on CPU. Read sheets incrementally and start forecasting with a bounded SKU subset. Recommended starting budget: 8 GB RAM; actual peak must be measured. |
| [M5 / Walmart](https://github.com/Mcompetitions/M5-methods) | Organizer repository links dataset resources in Drive. [Kaggle data](https://www.kaggle.com/competitions/m5-forecasting-accuracy/data) and [rules](https://www.kaggle.com/competitions/m5-forecasting-accuracy/rules) pages returned no readable content in this review. Account requirements and current data reuse terms remain unverified; public visibility alone does not establish reuse rights. | Daily history 2011-01-29 to 2016-06-19; 30,490 product-store series. Initially 1,913 training days, then 28 validation and 28 test days. | Unit sales, hierarchy, calendar/events, prices, and promotional information. Strongest ready-made forecasting benchmark. | About 58.3 million series-days in the initial training panel alone, calculated as 30,490 x 1,913. Wide-to-long conversion and lag features can require several GB. CPU subsets are feasible; full-panel experimentation is heavier. |

M5 history and split details come from the organizers' primary paper,
[Makridakis, Spiliotis, and Assimakopoulos, *The M5 competition: Background,
organization, and implementation*](https://doi.org/10.1016/j.ijforecast.2021.07.007),
including the [author-uploaded manuscript](https://www.researchgate.net/profile/Evangelos-Spiliotis/publication/351458556_The_M5_competition_Background_organization_and_implementation/links/60995f39a6fdccaebd2077db/The-M5-competition-Background-organization-and-implementation.pdf).
Organizer metadata was accessible; the linked Drive download path was not exercised.
We have not assigned M5 a permissive license or asserted redistribution rights.

## Recommendation: UCI Online Retail II

Choose Online Retail II for the first implementation. Its explicit reuse license,
two-year history, manageable file size, and raw transactions support both a data
science story and an engineering story: auditable cleaning, temporal validation,
forecasting, and decision simulation. Online Retail is a smaller fallback; its
shorter history limits annual comparisons. M5 is a possible later extension once
its current data terms and access are confirmed.

This recommendation is an engineering judgment. Memory and runtime have not been
benchmarked on this computer, and neither workbook contents nor download integrity
have been checked yet. UCI's variable descriptions must be reconciled with actual
sheet headers during ingestion.

## Planned scope and limitations

- Forecast daily observed positive sales units for a fixed development cohort of
  at most 100 SKUs, chosen using training-period activity only. Assess whether
  daily sparsity justifies weekly aggregation before modeling.
- Preserve raw transactions; audit cancellations, returns, invalid quantities and
  prices, duplicates, non-product codes, missing fields, and incomplete boundary days.
  Keep a separate returns ledger; do not silently treat returns as negative demand.
- Do not equate missing transactions with confirmed zero demand. Define active
  product windows and document zero-filling assumptions and possible stockout censoring.
- Country describes customer location, not a store. Customer identifiers are
  unnecessary for SKU forecasts and will be excluded from derived panels.
- Two years allow only limited evidence about annual patterns. Gift/wholesale
  purchasing is not a representative grocery demand benchmark.
- No inventory balance, supplier lead times, or holding/shortage costs are supplied.
  Replenishment policies will be evaluated under explicit synthetic scenarios.
  Report simulated cost/service changes, never claimed real savings.
- Plan time-ordered development, validation, and final test windows. Lock the final
  test period before tuning. Prices and other features must be available at each
  forecast origin; future realized transaction prices are not known covariates.

## Attribution and usage terms

Dataset citation: Chen, D. (2012). *Online Retail II* [Dataset]. UCI Machine Learning
Repository. [DOI: 10.24432/C5CG6D](https://doi.org/10.24432/C5CG6D).

UCI identifies the dataset as [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Retain attribution, link the source and license, and identify cleaning, aggregation,
and other changes in derived outputs. Do not imply endorsement. Keep data outside
Git as a project storage choice, not as a claimed license restriction. This dataset
license does not select a license for this project's own code.

## Next acquisition gate

The next milestone may download the selected public workbook after checking its
current advertised size. Record retrieval time, source, byte count, and SHA-256;
inspect sheets and headers; write a quality report before defining the daily panel.
No model training is needed for that milestone.
