# Demo articles (held-out test split)

Active model when generated: **Logistic Regression / tfidf_bigram / 2026-10-15 02:52**. None of these articles was used to train it. Paste the text (or upload the .txt) into the Analyze page.

| file | true label (dataset) | model says | confidence | note |
|---|---|---|---|---|
| fake_1.txt | Fake | Fake | 98.1% | correct |
| fake_2.txt | Fake | Fake | 81.0% | correct |
| real_1.txt | Real | Real | 91.3% | correct |
| real_2.txt | Real | Real | 96.8% | correct |
| mistake.txt | Fake | Real | 98.4% | model is WRONG - good for discussing limits |

Test-set size: 4005 articles considered here; test accuracy on them: 98.63%.
