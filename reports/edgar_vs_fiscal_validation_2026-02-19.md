# EDGAR vs Fiscal Validation (required 6-ticker set)

Required tickers: KO, AAL, CB, PGR, JPM, BAC

## Coverage check

| Ticker | In EDGAR output | In fiscal cache |
|---|---:|---:|
| KO | yes | no |
| AAL | no | yes |
| CB | yes | yes |
| PGR | yes | no |
| JPM | yes | no |
| BAC | yes | yes |

## Strict value match check on overlapping data

Method: normalize year labels to YYYY (ignore LTM and estimates), intersect labels+years, compare numeric cells exactly as stored (no unit-scaling assumptions).

| Ticker | Statement | Comparable cells | Exact matches | Mismatches |
|---|---|---:|---:|---:|
| CB | IS | 61 | 0 | 61 |
| CB | BS | 78 | 0 | 78 |
| CB | CF | 26 | 0 | 26 |
| BAC | IS | 64 | 0 | 64 |
| BAC | BS | 80 | 0 | 80 |
| BAC | CF | 56 | 0 | 56 |

## Conclusion

- Required 6-ticker fiscal-vs-EDGAR verification is **not complete** (coverage gaps).
- On overlapping cached data (CB, BAC), strict exact-match comparison shows **0 exact matches** across comparable cells.
- Therefore the current EDGAR pipeline is **not validated** against fiscal.ai equivalence.