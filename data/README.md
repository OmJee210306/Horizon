# Local data placement

Copy the downloaded source files into the folders below. Keep the raw files unchanged. The `.gitignore` excludes raw and processed data from GitHub by default.

```text
data/raw/primary/saas-subscriptions-v1.0.0-analysis.xlsx
data/raw/churn/MP_Synthetics_50000_Rows.csv
data/raw/sample_lab/subscription-sample-database-1k-en_GB-v2.json
data/raw/benchmarks/churn-benchmarks.json
```

Do not copy `churn-benchmarks.csv` as a second source; it duplicates the benchmark JSON with fewer driver details. Do not commit any raw data, credentials, tokens, payment details or personal fields to GitHub.
