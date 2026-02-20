-- RIFT 2026 Autonomous CI/CD Healing Agent
-- Starter PostgreSQL schema

create extension if not exists pgcrypto;

create table if not exists runs (
  run_id text primary key,
  fingerprint text not null,
  repo_url text not null,
  team_name varchar(120) not null,
  leader_name varchar(120) not null,
  branch_name varchar(200) not null,
  status text not null check (status in ('queued','running','passed','failed','quarantined')),
  start_time timestamptz not null,
  end_time timestamptz,
  total_time_secs double precision,
  base_score int,
  speed_bonus int,
  efficiency_penalty int,
  final_score int,
  total_failures int,
  total_fixes int,
  total_commits int,
  total_iterations int,
  total_llm_cost_usd double precision,
  quarantine_reason text,
  report_pdf bytea,
  created_at timestamptz not null default now()
);

create index if not exists idx_runs_status on runs(status);
create index if not exists idx_runs_created_at on runs(created_at desc);
create index if not exists idx_runs_fingerprint on runs(fingerprint);

create table if not exists fixes (
  fix_id text primary key default gen_random_uuid()::text,
  run_id text not null references runs(run_id) on delete cascade,
  file_path text not null,
  bug_type text not null check (bug_type in ('LINTING','SYNTAX','LOGIC','TYPE_ERROR','IMPORT','INDENTATION')),
  line_number int not null,
  line_end int,
  description text not null,
  fix_description text not null,
  original_code text,
  fixed_code text,
  status text not null check (status in ('applied','failed','rolled_back','skipped')),
  commit_sha varchar(40),
  commit_message text,
  confidence_score double precision check (confidence_score >= 0.0 and confidence_score <= 1.0),
  model_used varchar(60),
  consensus_votes jsonb,
  kb_match boolean,
  causal_commit_sha varchar(40),
  causal_explanation text,
  token_cost_usd double precision,
  applied_at timestamptz not null default now()
);

create index if not exists idx_fixes_run_id on fixes(run_id);
create index if not exists idx_fixes_bug_status on fixes(bug_type, status);
create index if not exists idx_fixes_kb_match_true on fixes(kb_match) where kb_match = true;

create table if not exists ci_events (
  event_id text primary key default gen_random_uuid()::text,
  run_id text not null references runs(run_id) on delete cascade,
  iteration int not null,
  github_run_id bigint,
  status text not null check (status in ('pending','running','passed','failed','no_ci')),
  failures_before int,
  failures_after int,
  new_failures text[],
  regression_detected boolean not null default false,
  rollback_triggered boolean not null default false,
  rollback_commit_sha varchar(40),
  duration_secs double precision,
  triggered_at timestamptz not null,
  completed_at timestamptz
);

create index if not exists idx_ci_events_run_iter on ci_events(run_id, iteration);

create table if not exists execution_traces (
  trace_id text primary key default gen_random_uuid()::text,
  run_id text not null references runs(run_id) on delete cascade,
  step_index int not null,
  agent_node varchar(60) not null,
  action_type varchar(60) not null,
  action_label text not null,
  payload jsonb,
  thought_text text,
  related_fix_id text references fixes(fix_id) on delete set null,
  related_ci_event_id text references ci_events(event_id) on delete set null,
  emitted_at timestamptz not null default now()
);

create index if not exists idx_traces_run_step on execution_traces(run_id, step_index);

create table if not exists strategy_weights (
  weight_id text primary key default gen_random_uuid()::text,
  bug_type text unique not null,
  strategy_rule_first double precision not null,
  strategy_llm_single double precision not null,
  strategy_llm_consensus double precision not null,
  strategy_kb_lookup double precision not null,
  total_attempts int not null,
  total_successes int not null,
  generation int not null,
  last_evolved_at timestamptz
);

create table if not exists benchmark_scores (
  bench_id text primary key default gen_random_uuid()::text,
  run_id text not null references runs(run_id) on delete cascade,
  criterion varchar(80) not null,
  max_points int not null,
  predicted_score int not null,
  actual_score int,
  calibration_gap int,
  reasoning text,
  scored_at timestamptz not null default now()
);

create index if not exists idx_benchmark_run_criterion on benchmark_scores(run_id, criterion);
