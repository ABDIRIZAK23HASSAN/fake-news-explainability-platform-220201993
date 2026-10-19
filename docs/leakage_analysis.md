# Dataset leakage analysis

Label convention used everywhere: `0 = Fake`, `1 = Real`. All numbers come from
`scripts/run_experiments.py` (stored in `docs/experiments/results.json`) or from the data itself.

## What the data leaks

| Observation (instructor's `train.csv`, stemmed) | Fake | Real |
|---|---|---|
| articles containing the token `reuter` | 1.2% | 99.8% |

* Every *Real* article is from Reuters (`subject` is only `politicsNews` / `worldnews`), almost all start with a
  dateline such as `WASHINGTON (Reuters) -`. A classifier can reach very high accuracy by memorising that one word.
* The `subject` column separates the classes perfectly (the two Real subjects never occur in Fake). It is therefore
  **never used as a model feature**.
* `Fake.csv` has 6,026 duplicated texts and 630 empty texts; `True.csv` has 225 duplicated texts. The instructor's
  `train.csv` and `test.csv` share **82 identical articles**.

## What we did

1. Removed duplicates and empty articles before splitting (our own stratified 80/20 split, seed 42).
2. Added a *source-artifact removal* step to the preprocessing pipeline (not in the assignment list): the Reuters
   dateline and the word "Reuters" (level 1), plus publisher boilerplate such as "21st Century Wire says",
   "Featured image via", "Getty Images", "(VIDEO)" (level 2, used in production).
3. Measured the effect (Logistic Regression + TF-IDF unigram, our split, 7,731 test articles):

| Preprocessing variant | Accuracy | F1 |
|---|---|---|
| L0 – no source-artifact removal | 99.38% | 99.44% |
| L1 – Reuters removed | 98.65% | 98.78% |
| **L2 – Reuters + boilerplate removed (used)** | **98.58%** | 98.71% |
| L2, no stemming | 98.69% | 98.81% |
| L2, keep stop-words | 98.75% | 98.86% |

On the instructor's split as given Logistic Regression scores 99.12%; deleting only the token `reuter` gives 98.60%.

## How to read this honestly

* Removing the Reuters fingerprint costs ~0.7 points, but accuracy stays high. The two classes also differ in
  **writing style** (reporting verbs such as "said", informal words, calls to action such as "Read more").
  The model therefore recognises *the style of these particular sources*, not whether a claim is true.
* Differences below ~0.3 points between configurations are inside the statistical noise of a single split
  (standard error ≈ 0.13 points at n = 7,731); we do not claim one stemming/stop-word choice is better.
* The test set comes from the same two sources as the training set. Performance on news from other publishers is
  unknown and is expected to be lower. This is why the platform presents itself as a decision-support tool and
  always shows the confidence and the words behind each prediction.
