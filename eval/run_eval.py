"""
Runs the benchmark: full system, per-agent ablations, and (optionally) the LLM injection test.

    python eval/generate.py
    python eval/run_eval.py                 # rule-based system + ablations
    python eval/run_eval.py --llm           # also NaiveJudge vs GuardedJudge (needs RENTINEL_LLM_BASE_URL)

"Flagged" means the verdict label is medium or high.
Attack success rate (ASR) = share of adversarial scams that were NOT flagged.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent / "src"))

from rentinel.config import Settings  # noqa: E402
from rentinel.models import Listing  # noqa: E402
from rentinel.agents.images import load_images, phash_hex  # noqa: E402
from rentinel.orchestrator import AGENT_NAMES, Orchestrator  # noqa: E402
from rentinel.store import Store  # noqa: E402


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def to_listing(r: dict) -> Listing:
    fields = {k: v for k, v in r.items() if k in Listing.model_fields}
    fields["image_paths"] = [str(ROOT / p) for p in r.get("image_paths", [])]
    return Listing(**fields)


def seeded_store(corpus: list[dict]) -> Store:
    """Simulates prior traffic: listings checked before the test set arrived."""
    store = Store(":memory:")
    for r in corpus:
        lst = to_listing(r)
        store.add_observation(lst.listing_id, lst.cma, lst.bedrooms, lst.price, lst.address)
        hashes = [phash_hex(i) for i in load_images([], lst.image_paths)]
        store.add_image_hashes(lst.listing_id, hashes, lst.address, lst.cma, lst.price)
    return store


def auroc(scores: list[float], labels: list[int]) -> float:
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def metrics(rows: list[dict], flagged: list[bool], scores: list[float]) -> dict:
    labels = [r["label"] for r in rows]
    tp = sum(f and y for f, y in zip(flagged, labels))
    fp = sum(f and not y for f, y in zip(flagged, labels))
    fn = sum((not f) and y for f, y in zip(flagged, labels))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    by_cat = defaultdict(list)
    for r, f in zip(rows, flagged):
        by_cat[r["category"]].append(f)
    flag_rate = {c: sum(v) / len(v) for c, v in by_cat.items()}
    by_attack = defaultdict(list)
    for r, f in zip(rows, flagged):
        if r["category"] == "scam_adversarial":
            by_attack[r["attack"]].append(f)
    legit = [f for r, f in zip(rows, flagged) if r["label"] == 0]
    adv = by_cat.get("scam_adversarial", [])
    return {
        "precision": precision, "recall": recall, "f1": f1, "auroc": auroc(scores, labels),
        "false_positive_rate": sum(legit) / len(legit) if legit else 0.0,
        "attack_success_rate": 1 - sum(adv) / len(adv) if adv else float("nan"),
        "flag_rate_by_category": flag_rate,
        "asr_by_attack": {a: 1 - sum(v) / len(v) for a, v in sorted(by_attack.items())},
    }


def run_system(rows, corpus, disable=()) -> tuple[dict, list[float]]:
    orch = Orchestrator(settings=Settings(), store=seeded_store(corpus), disable=disable)
    flagged, scores, latencies = [], [], []
    for r in rows:
        t = time.perf_counter()
        v = orch.check_sync(to_listing(r), register=False)
        latencies.append((time.perf_counter() - t) * 1000)
        flagged.append(v.label.value != "low")
        scores.append(v.risk_score)
    m = metrics(rows, flagged, scores)
    lat = sorted(latencies)
    m["latency_ms_p50"] = statistics.median(lat)
    m["latency_ms_p95"] = lat[int(0.95 * (len(lat) - 1))]
    return m, scores


def run_llm(rows, limit: int) -> dict:
    from rentinel.llm import ChatClient, GuardedJudge, NaiveJudge
    client = ChatClient(Settings())
    subset = [r for r in rows if r["category"] == "scam_adversarial"][:limit] + \
             [r for r in rows if r["label"] == 0][:limit]
    out = {}
    for name, judge in (("naive_llm", NaiveJudge(client)), ("guarded_llm", GuardedJudge(client))):
        flagged = [judge.judge(to_listing(r)) in ("medium", "high") for r in subset]
        out[name] = metrics(subset, flagged, [float(f) for f in flagged])
    return out


def pct(x):
    return "n/a" if x != x else f"{100 * x:.1f}%"


def write_report(results: dict, n: dict, path: Path, dataset: str):
    lines = ["# Rentinel benchmark results", "",
             f"Synthetic benchmark v0, dataset `eval/{dataset}` (see `eval/generate.py`). "
             "Flagged = medium or high risk.", "",
             "Test set: " + ", ".join(f"{k}={v}" for k, v in n.items()), "",
             "| System | Precision | Recall | F1 | AUROC | False-positive rate | Attack success rate | p95 latency |",
             "|---|---|---|---|---|---|---|---|"]
    for name, m in results.items():
        if name.startswith("_"):
            continue
        lat = f"{m['latency_ms_p95']:.1f} ms" if "latency_ms_p95" in m else "-"
        auc = f"{m['auroc']:.3f}" if m["auroc"] == m["auroc"] else "-"
        lines.append(f"| {name} | {pct(m['precision'])} | {pct(m['recall'])} | {pct(m['f1'])} | {auc} | "
                     f"{pct(m['false_positive_rate'])} | {pct(m['attack_success_rate'])} | {lat} |")
    full = results["full"]
    lines += ["", "## Full system: flag rate by category", "", "| Category | Flagged |", "|---|---|"]
    lines += [f"| {c} | {pct(v)} |" for c, v in sorted(full["flag_rate_by_category"].items())]
    lines += ["", "## Attack success rate by evasion technique", "",
              "| Attack | Full system | Without firewall |", "|---|---|---|"]
    nofw = results.get("without firewall", {}).get("asr_by_attack", {})
    lines += [f"| {a} | {pct(v)} | {pct(nofw.get(a, float('nan')))} |" for a, v in full["asr_by_attack"].items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--llm-limit", type=int, default=40)
    ap.add_argument("--data", default="data", help="dataset folder under eval/ (from generate.py --out)")
    ap.add_argument("--report", default="results", help="report name (writes eval/<name>.md and .json)")
    args = ap.parse_args()

    data = ROOT / args.data
    rows, corpus = load(data / "test.jsonl"), load(data / "corpus.jsonl")
    n = defaultdict(int)
    for r in rows:
        n[r["category"]] += 1

    results = {}
    results["full"], _ = run_system(rows, corpus)
    for agent in AGENT_NAMES:
        results[f"without {agent}"], _ = run_system(rows, corpus, disable={agent})
    if args.llm:
        results.update(run_llm(rows, args.llm_limit))

    (ROOT / f"{args.report}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    write_report(results, dict(n), ROOT / f"{args.report}.md", args.data)
    print((ROOT / f"{args.report}.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
