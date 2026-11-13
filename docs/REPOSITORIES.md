# Standalone application repositories

All 16 applications have independent local Git repositories. **16 are published to GitHub; 0 await GitHub repository creation.** Each app has its own root page, API routes, database schema, tests, CI workflow, README, and preview. Current repository visibility is shown below.

| Application | Repository | Publication status |
| --- | --- | --- |
| Issue Desk | [issue-desk](https://github.com/Michaelhoang8/issue-desk) | Published · public |
| Stockroom | [stockroom](https://github.com/Michaelhoang8/stockroom) | Published · public |
| Experiment Studio | [experiment-studio](https://github.com/Michaelhoang8/experiment-studio) | Published · public |
| Dataset Explorer | [dataset-explorer](https://github.com/Michaelhoang8/dataset-explorer) | Published · public |
| Pipeline Studio | [pipeline-studio](https://github.com/Michaelhoang8/pipeline-studio) | Published · public |
| Revenue Lens | [revenue-lens](https://github.com/Michaelhoang8/revenue-lens) | Published · public |
| Auth Watch | [auth-watch](https://github.com/Michaelhoang8/auth-watch) | Published · public |
| Header Review | [header-review](https://github.com/Michaelhoang8/header-review) | Published · public |
| Secret Sentinel | [secret-sentinel](https://github.com/Michaelhoang8/secret-sentinel) | Published · public |
| Classifier Lab | [classifier-lab](https://github.com/Michaelhoang8/classifier-lab) | Published · public |
| Retrieval Studio | [retrieval-studio](https://github.com/Michaelhoang8/retrieval-studio) | Published · public |
| Model Observatory | [model-observatory](https://github.com/Michaelhoang8/model-observatory) | Published · public |
| Manifest Review | [manifest-review](https://github.com/Michaelhoang8/manifest-review) | Published · public |
| Pipeline Planner | [pipeline-planner](https://github.com/Michaelhoang8/pipeline-planner) | Published · public |
| Reliability Desk | [reliability-desk](https://github.com/Michaelhoang8/reliability-desk) | Published · public |
| REST Studio | [rest-studio](https://github.com/Michaelhoang8/rest-studio) | Published · public |

## New independent projects

These projects were built independently after the original 16-app extraction. Each has its own public repository, interface, core implementation, tests, documentation, and CI.

| Application | Field | Focus | Publication status |
| --- | --- | --- | --- |
| [Packet Porch](https://github.com/Michaelhoang8/packet-porch) | Network analysis and forensics | Bounded PCAP parsing, IPv4/IPv6 metadata, conversation filters, and packet diagnostics | Published · public |
| [Thermal Commons](https://github.com/Michaelhoang8/thermal-commons) | Scientific computing | Verified Poisson fields, painted constraints, stationary solver comparisons, and residual evidence | Published · public |
| [Spatial Ledger](https://github.com/Michaelhoang8/spatial-ledger) | Geospatial systems | Persistent R-tree points, date-line and pole-aware radius searches, atomic imports, and versioned edits | Published · public |
| [Circuit Loom](https://github.com/Michaelhoang8/circuit-loom) | Digital logic and architecture | Validated netlists, simultaneous registers, clock undo, truth tables, and waveform traces | Published · public |
| [Contour Field](https://github.com/Michaelhoang8/contour-field) | Computer vision | Inspectable Gaussian/Sobel edge pipeline, connected hysteresis, pixel analysis, and PNG exports | Published · public |
| [Deadline Harbor](https://github.com/Michaelhoang8/deadline-harbor) | Real-time systems | Preemptive EDF/RM schedules, deadline evidence, and bounded schedulability analysis | Published · public |
| [Merge Margin](https://github.com/Michaelhoang8/merge-margin) | Developer tools | Exact-line three-way merging, conflict decisions, newline preservation, and portable sessions | Published · public |
| [Bytecode Atelier](https://github.com/Michaelhoang8/bytecode-atelier) | Compilers | Arithmetic compiler, constant folding, and reversible stack VM | Published · public |
| [Causal Post](https://github.com/Michaelhoang8/causal-post) | Distributed systems | Vector clocks, network faults, and replayable causal histories | Published · public |
| [Frame Garden](https://github.com/Michaelhoang8/frame-garden) | Operating systems | Page replacement, dirty writebacks, and capacity sweeps | Published · public |
| [Dispatch Room](https://github.com/Michaelhoang8/dispatch-room) | Backend infrastructure | Durable SQLite jobs, fenced leases, retries, and an operations console | Published · public |
| [Language Lens](https://github.com/Michaelhoang8/language-lens) | Formal languages | DFA minimization, equivalence proofs, shortest counterexamples, and DOT exports | Published · public |
| [Prefix Atlas](https://github.com/Michaelhoang8/prefix-atlas) | Computer networking | IPv4/IPv6 prefix tries, explained routing decisions, and exact subnet plans | Published · public |
| [Signal Study](https://github.com/Michaelhoang8/signal-study) | Digital signal processing | Verified FFT, window comparisons, spectral inspection, and PCM WAV export | Published · public |
| [Proof Parcel](https://github.com/Michaelhoang8/proof-parcel) | Applied cryptography | Merkle inclusion proofs, tamper detection, and separately trusted checkpoints | Published · public |
| [Ray Room](https://github.com/Michaelhoang8/ray-room) | Computer graphics | Progressive CPU ray tracing, BVH comparisons, reflections, and image exports | Published · public |
| [Allocation Desk](https://github.com/Michaelhoang8/allocation-desk) | Operations research | Minimum-cost maximum flow, capacity constraints, and independently checked optimality certificates | Published · public |
| [Index Press](https://github.com/Michaelhoang8/index-press) | Information retrieval | Persistent positional index, explainable BM25 ranking, phrase search, and versioned document edits | Published · public |
| [Terrain Pilot](https://github.com/Michaelhoang8/terrain-pilot) | Robotics and planning | Weighted A-star and Dijkstra, footprint clearance, editable costmaps, and route replay | Published · public |
| [Clause Cabinet](https://github.com/Michaelhoang8/clause-cabinet) | Formal verification | 2-SAT configuration checking, verified contradiction witnesses, forced values, and repair candidates | Published · public |
| [Sequence Dock](https://github.com/Michaelhoang8/sequence-dock) | Bioinformatics | Global/local DNA alignment, affine gaps, reverse complements, FASTA workflows, and verified traceback | Published · public |
| [Query Quarry](https://github.com/Michaelhoang8/query-quarry) | Database systems | Real SQLite index experiments, bounded queries, plan comparisons, and measured result previews | Published · public |
| [Byte Press](https://github.com/Michaelhoang8/byte-press) | Information theory and compression | Lossless Huffman files, verified binary round trips, CRC checks, and complete container accounting | Published · public |

## Run an app

From an app repository, run `python run.py` and open http://127.0.0.1:8000/. Use `--port 8001` to run another app alongside it. REST Studio additionally requires `PORTFOLIO_API_KEY`. Each README provides its setup and verification commands.

## Validation

All 16 apps were exercised in the browser. The standalone suites pass 274 Python tests and 82 JavaScript tests in total, including root-page assets, app-specific API requests, rejection of unrelated app endpoints, and isolated database schemas.

The new projects are verified separately: Bytecode Atelier has 11 JavaScript tests and one Python server test; Causal Post has 11 JavaScript tests and one Python server test; Frame Garden has 10 JavaScript tests and one Python server test; Dispatch Room has 17 Python tests including a separate worker process; Language Lens has nine JavaScript tests and one Python server test; Prefix Atlas has 11 Python tests; Signal Study has 10 JavaScript tests and one Python server test; Proof Parcel has nine JavaScript tests and one Python server test; Ray Room has nine JavaScript tests and one Python server test; Allocation Desk has 11 Python tests including exhaustive small-network optimization oracles; Index Press has 13 Python tests covering ranking, transactions, concurrency, persistence, and API boundaries; Terrain Pilot has 10 JavaScript tests and one Python server test; Clause Cabinet has 10 JavaScript tests and one Python server test; Sequence Dock has 11 JavaScript tests and one Python server test; Query Quarry has 12 Python tests covering query plans, result equality, execution limits, and API boundaries; Byte Press has 12 JavaScript tests and one Python server test. Merge Margin has 12 JavaScript tests and one Python server test. Deadline Harbor has 12 JavaScript tests and one Python server test. Contour Field has 13 JavaScript tests and one Python server test. Circuit Loom has 11 JavaScript tests and one Python server test. Spatial Ledger has 13 Python tests including independent geospatial oracles, transactions, concurrency, and API boundaries. Thermal Commons has 11 JavaScript tests and one Python server test. Packet Porch has 12 JavaScript tests and one Python server test. All have browser-verified workflows. Their READMEs describe the checks and model limitations.

## Local workspace

The local repositories are under `outputs/standalone-apps/` beside the original `outputs/portfolio-lab/` folder. The standalone directory contains `publish_remaining.py`; running it with an authenticated GitHub CLI publishes prepared repositories, stops on the first failure, and does not retry rate limits automatically.

## Migration source

Portfolio Lab is retained as the original combined implementation and development history. New app work belongs in the respective standalone repository. The original 16 standalone repositories start with explicit extraction commits and link to their source commit; the new independent projects have their own implementation history. Existing runtime databases were not copied or removed.
