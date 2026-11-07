# Standalone application repositories

All 16 applications have independent local Git repositories. **10 are published to GitHub; 6 await GitHub repository creation.** Each app has its own root page, API routes, database schema, tests, CI workflow, README, and preview. Published repositories retain the original private visibility.

| Application | Repository | Publication status |
| --- | --- | --- |
| Issue Desk | [issue-desk](https://github.com/Michaelhoang8/issue-desk) | Published · private |
| Stockroom | [stockroom](https://github.com/Michaelhoang8/stockroom) | Published · private |
| Experiment Studio | [experiment-studio](https://github.com/Michaelhoang8/experiment-studio) | Published · private |
| Dataset Explorer | [dataset-explorer](https://github.com/Michaelhoang8/dataset-explorer) | Published · private |
| Pipeline Studio | [pipeline-studio](https://github.com/Michaelhoang8/pipeline-studio) | Published · private |
| Revenue Lens | [revenue-lens](https://github.com/Michaelhoang8/revenue-lens) | Published · private |
| Auth Watch | [auth-watch](https://github.com/Michaelhoang8/auth-watch) | Published · private |
| Header Review | [header-review](https://github.com/Michaelhoang8/header-review) | Published · private |
| Secret Sentinel | [secret-sentinel](https://github.com/Michaelhoang8/secret-sentinel) | Published · private |
| Classifier Lab | [classifier-lab](https://github.com/Michaelhoang8/classifier-lab) | Published · private |
| Retrieval Studio | `retrieval-studio` — local repository ready | GitHub creation rate-limited |
| Model Observatory | `model-observatory` — local repository ready | GitHub creation rate-limited |
| Manifest Review | `manifest-review` — local repository ready | GitHub creation rate-limited |
| Pipeline Planner | `pipeline-planner` — local repository ready | GitHub creation rate-limited |
| Reliability Desk | `reliability-desk` — local repository ready | GitHub creation rate-limited |
| REST Studio | `rest-studio` — local repository ready | GitHub creation rate-limited |

## Run an app

From an app repository, run `python run.py` and open http://127.0.0.1:8000/. Use `--port 8001` to run another app alongside it. REST Studio additionally requires `PORTFOLIO_API_KEY`. Each README provides its setup and verification commands.

## Validation

All 16 apps were exercised in the browser. The standalone suites pass 274 Python tests and 82 JavaScript tests in total, including root-page assets, app-specific API requests, rejection of unrelated app endpoints, and isolated database schemas.

## Local workspace

The local repositories are under `outputs/standalone-apps/` beside the original `outputs/portfolio-lab/` folder. The standalone directory contains `publish_remaining.py`; running it with an authenticated GitHub CLI publishes prepared repositories, stops on the first failure, and does not retry rate limits automatically.

## Migration source

Portfolio Lab is retained as the original combined implementation and development history. New app work belongs in the respective standalone repository. Each standalone repository starts with an explicit extraction commit and links to its source commit. Existing runtime databases were not copied or removed.
