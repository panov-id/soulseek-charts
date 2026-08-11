# analysis

Scripts that answer a question once, rather than run continuously. They read
the archive and change nothing.

## trends.sh

    SOULSEEK_ARCHIVE=/path/to/collector/data/raw bash trends.sh 3 24

What is rising: a recent window against a longer baseline.

Compares **shares of searchers**, not absolute rates — collection volume differs
between windows, so absolute rates compare nothing. And it never truncates the
baseline, because a small top makes every tail item look brand new.

Belongs inside `soulseek-charts` as a flag eventually.

## coverage_experiment.sh

Reproduces the claim that one node is enough. Capture with several parents,
then compare what each delivered:

    # in probe/
    VERBOSE=1 PARENTS=3 OUTPUT_NAME=coverage.jsonl bash run.sh 4m

    bash coverage_experiment.sh ../probe/results/coverage.jsonl

Measured 9 August 2026, parents at branch levels 4, 6 and 6: pairwise Jaccard
0.995–0.999, 99.4% of queries seen from all three. Depth in the tree affects
latency, not coverage.

Worth re-running against parents on **different branch roots** — roots change
through the day, and whether they carry different traffic has not been tested.
