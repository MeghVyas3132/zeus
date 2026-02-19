# Autonomous CI/CD Healing Agent

RIFT 2026 Hackathon
Track: AI/ML, DevOps Automation, Agentic Systems

This repository contains a production-style autonomous CI/CD healing system and judge-facing React dashboard.

## 1. Quick Links

- Live Dashboard URL: `https://<your-dashboard-url>`
- API Base URL: `https://<your-api-url>`
- Demo Video URL: `https://linkedin.com/<your-video-post>`
- Architecture Doc: `architecture.txt`
- User Flow Doc: `user-flow.txt`
- Database Doc: `db-architecture.txt`
- Source of Truth: `SOURCE_OF_TRUTH.md`
- Copilot Build Guide: `COPILOT_BUILD_GUIDE.md`

## 2. Project Objective

Given a GitHub repository URL, the system autonomously:
1. Validates input and creates a compliant branch name.
2. Clones/analyzes repository and runs tests in sandbox.
3. Detects failures and classifies bug types.
4. Generates fixes and validates them.
5. Commits fixes with `[AI-AGENT]` prefix to new branch.
6. Monitors CI and retries until pass or retry limit hit.
7. Produces `results.json` and updates dashboard in real time.

## 3. Track Compliance Matrix

### 3.1 Required Dashboard Sections

Implemented:
1. Input Section (`repo_url`, `team_name`, `leader_name`, run button, loading state)
2. Run Summary Card (repo, team, leader, branch, totals, status, duration)
3. Score Breakdown Panel (base, speed bonus, efficiency penalty, final)
4. Fixes Applied Table (file, bug type, line, commit message, status)
5. CI/CD Status Timeline (iteration, pass/fail, timestamp, retry progress)

### 3.2 Required Branch Format

Exact format: `TEAM_NAME_LEADER_NAME_AI_Fix`

Rules:
- team and leader tokens uppercase
- spaces replaced with underscores
- suffix is literal `_AI_Fix`
- no special chars except `_`

### 3.3 Required Bug Types

Primary fixes table uses:
- `LINTING`
- `SYNTAX`
- `LOGIC`
- `TYPE_ERROR`
- `IMPORT`
- `INDENTATION`

### 3.4 Required Output Artifact

`results.json` is generated for every completed run.

## 4. Architecture Summary

High-level components:
1. Frontend: React + Vite dashboard
2. Gateway: Node.js + Express + Socket.io
3. Queue: BullMQ + Redis
4. Agent Service: FastAPI + LangGraph
5. Sandbox: Docker containers per language
6. Data: PostgreSQL + Redis + filesystem (+ optional ChromaDB)

Details: see `architecture.txt`

## 5. End-to-End Execution

1. User submits repo/team/leader.
2. API validates and enqueues run.
3. Agent pre-scans and clones repository.
4. Agent analyzes code + runs tests.
5. Fix loop: classify -> generate -> validate -> commit -> push.
6. CI monitor loop with retries and rollback on regression.
7. Finalize outputs and emit `run_complete`.

Details: see `user-flow.txt`

## 6. Data Model and Storage

- PostgreSQL: runs, fixes, ci events, traces, strategy, benchmark
- Redis: queue state, live status cache, event buffer
- Filesystem: `/outputs/{run_id}/results.json`, `/outputs/{run_id}/report.pdf`
- Optional vector memory: fix-pattern retrieval and reuse

Details: see `db-architecture.txt`

## 7. API Reference (Public)

### `POST /run-agent`

Request:
```json
{
  "repo_url": "https://github.com/org/repo",
  "team_name": "RIFT ORGANISERS",
  "leader_name": "Saiyam Kumar"
}
```

Response:
```json
{
  "run_id": "run_abc123",
  "branch_name": "RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix",
  "status": "queued",
  "socket_room": "/run/run_abc123"
}
```

### `GET /results/:runId`
Returns run output JSON.

### `GET /report/:runId`
Returns generated PDF report.

### `GET /replay/:runId`
Returns execution trace for replay mode.

### `GET /agent/status/:runId`
Returns current node, iteration, and progress.

### `POST /agent/query`
Post-run natural-language Q/A grounded in trace data.

### `GET /health`
Health check.

## 8. WebSocket Contract

Room: `/run/:runId`

Events:
- `thought_event`
- `fix_applied`
- `ci_update`
- `telemetry_tick`
- `run_complete`

Payload schemas are defined in `API_CONTRACTS.md`.

## 9. Scoring Logic

- Base: `100`
- Speed bonus: `+10` if runtime `< 5 minutes`
- Efficiency penalty: `-2` per commit above 20

Formula:
`final = 100 + speed_bonus - efficiency_penalty`

## 10. Determinism Strategy (for test-case accuracy)

1. Rule-based failure parser first (exact mappings).
2. Strict bug-type normalizer.
3. Line number validator against parsed stack traces.
4. LLM fallback for unresolved cases only.
5. Output schema validation before persistence.

## 11. Installation and Local Setup

### 11.1 Prerequisites

- Node.js 20+
- Python 3.11+
- Docker
- Redis
- PostgreSQL

### 11.2 Suggested Folder Layout

- `frontend/` React app
- `backend/gateway/` Express + BullMQ
- `backend/agent/` FastAPI + LangGraph
- `outputs/` run artifacts

### 11.3 Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

### 11.4 Gateway

```bash
cd backend/gateway
npm install
cp .env.example .env
npm run dev
npm run worker
```

### 11.5 Agent Service

```bash
cd backend/agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8001
```

## 12. Environment Variables

### Frontend

```env
VITE_API_URL=http://localhost:3000
VITE_SOCKET_URL=http://localhost:3000
```

### Gateway

```env
PORT=3000
FASTAPI_URL=http://localhost:8001
FRONTEND_URL=http://localhost:5173
REDIS_URL=redis://localhost:6379
SESSION_SECRET=replace_me
```

### Agent

```env
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
GITHUB_PAT=
DATABASE_URL=postgresql://user:pass@localhost:5432/rift_agent
REDIS_URL=redis://localhost:6379
OUTPUT_DIR=/outputs
AGENT_MAX_RETRIES=5
AGENT_CONFIDENCE_THRESHOLD=0.70
ENABLE_KB_LOOKUP=true
ENABLE_SPECULATIVE_BRANCHES=false
ENABLE_ADVERSARIAL_TESTS=true
ENABLE_CAUSAL_GRAPH=true
ENABLE_PROVENANCE_PASS=true
```

## 13. Advanced Features (Track-Aligned)

All advanced features are optional and must not break required output contracts.

1. Counterfactual Branch Tournament
2. Causal Incident Graph
3. AI Commit Passport (provenance)
4. Replay Mode
5. Adaptive model routing

Implementation details: see `COPILOT_BUILD_GUIDE.md` and `IMPLEMENTATION_TASKS.md`.

## 14. Known Limitations

1. Non-deterministic LLM behavior on edge cases.
2. Third-party API latency can affect runtime bonus.
3. Large monorepos may require higher worker resources.
4. Multi-language integration requires tuned sandbox images.

## 15. Submission Checklist

Before submission, verify:
1. Live deployed dashboard works from clean browser.
2. Demo video is public and tagged correctly.
3. README contains required sections and links.
4. Branch naming and commit prefix checks pass.
5. `results.json` generated for every run.
6. No direct push to protected branches.

## 16. Team

- Team Lead: <name>
- Member 2: <name>
- Member 3: <name>
- Member 4: <name>

## 17. License

Hackathon submission repository. Add license as needed.
