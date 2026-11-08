# Public dataset attribution and service limitations

The separately mounted runtime bundle contains processed data derived from:

Chen, D. (2012). **Online Retail II**. UCI Machine Learning Repository.
DOI: https://doi.org/10.24432/C5CG6D
Official source: https://archive.ics.uci.edu/dataset/502/online+retail+ii
License: **Creative Commons Attribution 4.0 International (CC BY 4.0)**,
https://creativecommons.org/licenses/by/4.0/

Changes: audited source-sheet reconciliation, explicit positive-sales/returns
routing, bounded daily aggregation and training-selected 100-SKU cohort, with a
separate modelling-history mask. Original provenance and retrieval/checksum
records are included as `provenance/data-provenance.json`. No raw workbook or
customer identifiers are included in the container image or forecast responses.

This is a historical demonstration over the 20 supported 2011 origins, not a live
retail feed. Observed sales are not latent demand or known stock availability.
Intervals are **experimental empirical historical-error daily prediction
intervals**, with no conditional, joint, conformal or finite-sample coverage
guarantee. Do not sum daily endpoints as a calibrated 28-day total interval.
