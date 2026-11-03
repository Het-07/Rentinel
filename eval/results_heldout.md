# Rentinel benchmark results

Synthetic benchmark v0, dataset `eval/heldout` (see `eval/generate.py`). Flagged = medium or high risk.

Test set: legit_hard=60, legit=140, scam_subtle=70, scam_obvious=50, scam_adversarial=80

| System | Precision | Recall | F1 | AUROC | False-positive rate | Attack success rate | p95 latency |
|---|---|---|---|---|---|---|---|
| full | 100.0% | 94.0% | 96.9% | 0.980 | 0.0% | 5.0% | 14.5 ms |
| without firewall | 100.0% | 91.5% | 95.6% | 0.971 | 0.0% | 11.3% | 13.9 ms |
| without scam_patterns | 100.0% | 88.0% | 93.6% | 0.966 | 0.0% | 5.0% | 11.7 ms |
| without price | 100.0% | 91.0% | 95.3% | 0.965 | 0.0% | 5.0% | 13.9 ms |
| without images | 100.0% | 78.5% | 88.0% | 0.963 | 0.0% | 10.0% | 4.0 ms |
| without consistency | 100.0% | 93.5% | 96.6% | 0.980 | 0.0% | 5.0% | 13.3 ms |

## Full system: flag rate by category

| Category | Flagged |
|---|---|
| legit | 0.0% |
| legit_hard | 0.0% |
| scam_adversarial | 95.0% |
| scam_obvious | 100.0% |
| scam_subtle | 88.6% |

## Attack success rate by evasion technique

| Attack | Full system | Without firewall |
|---|---|---|
| combo | 0.0% | 12.5% |
| hidden_html | 0.0% | 5.9% |
| homoglyph | 5.3% | 5.3% |
| visible | 25.0% | 25.0% |
| zero_width | 5.0% | 15.0% |
