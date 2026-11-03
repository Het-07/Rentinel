# Rentinel benchmark results

Synthetic benchmark v0, dataset `eval/data` (see `eval/generate.py`). Flagged = medium or high risk.

Test set: legit_hard=60, scam_obvious=50, legit=140, scam_adversarial=80, scam_subtle=70

| System | Precision | Recall | F1 | AUROC | False-positive rate | Attack success rate | p95 latency |
|---|---|---|---|---|---|---|---|
| full | 100.0% | 91.0% | 95.3% | 0.989 | 0.0% | 1.2% | 13.8 ms |
| without firewall | 100.0% | 84.5% | 91.6% | 0.978 | 0.0% | 17.5% | 12.7 ms |
| without scam_patterns | 100.0% | 81.5% | 89.8% | 0.975 | 0.0% | 1.2% | 14.0 ms |
| without price | 100.0% | 87.5% | 93.3% | 0.958 | 0.0% | 1.2% | 12.0 ms |
| without images | 100.0% | 81.5% | 89.8% | 0.983 | 0.0% | 5.0% | 3.5 ms |
| without consistency | 100.0% | 90.0% | 94.7% | 0.986 | 0.0% | 1.2% | 11.9 ms |

## Full system: flag rate by category

| Category | Flagged |
|---|---|
| legit | 0.0% |
| legit_hard | 0.0% |
| scam_adversarial | 98.8% |
| scam_obvious | 100.0% |
| scam_subtle | 75.7% |

## Attack success rate by evasion technique

| Attack | Full system | Without firewall |
|---|---|---|
| combo | 0.0% | 26.7% |
| hidden_html | 0.0% | 21.4% |
| homoglyph | 0.0% | 7.1% |
| visible | 5.6% | 11.1% |
| zero_width | 0.0% | 21.1% |
