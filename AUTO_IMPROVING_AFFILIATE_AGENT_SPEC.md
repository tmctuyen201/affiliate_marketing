# Auto-Improving Affiliate Agent System — Full Specification

## 1. Purpose

Build autonomous affiliate operation system that continuously improves strategy from live data to maximize net profit and reduce cost, while staying inside safety and compliance limits.

### 1.1 Mission

- Increase net profit per day/week/month
- Reduce wasted ad spend and low-yield content production
- Keep policy violations and refund risk below thresholds

### 1.2 Core Objective Function

For optimization windows (hourly/daily), maximize:

```text
J = NetProfit - λ1*RiskPenalty - λ2*Volatility - λ3*PolicyViolationCost
```

Where:

```text
NetProfit = CommissionRevenue - AdSpend - ContentCost - RefundLoss - InfraCost
```

---

## 2. Scope

### 2.1 In Scope (v1)

- Affiliate product discovery and scoring
- Traffic/content distribution optimization
- Budget and creative strategy adaptation
- Automated low-risk execution
- Human-gated high-impact execution
- Closed feedback loop for self-improvement

### 2.2 Out of Scope (v1)

- Fully autonomous high-risk financial decisions without guardrails
- Multi-country legal/compliance engine depth
- Advanced long-horizon RL with no human override

---

## 3. System Principles

1. Event-driven over cron-driven for core decisions
2. Immutable event history and full auditability
3. Safety-first autonomy (hard limits + approvals)
4. Learning layer must outperform baseline before expanded control
5. Deterministic rollback path for every high-impact action

---

## 4. High-Level Architecture

```text
Data Producers -> Event Bus -> Stream Processing -> State Store -> Decision Engine
-> Risk/Policy Gate -> Action Executor -> Outcome Evaluator -> Learner Update
-> Dashboard/Alerts/Audit
```

### 4.1 Component Roles

- **Data Producers**: Shopee/TikTok affiliate feeds, ad platforms, click trackers, order updates, trend feeds
- **Event Bus**: backbone for realtime message flow
- **Stream Processing**: transform events into windowed features and state updates
- **State Store**: source of truth for entities, metrics, decisions, outcomes
- **Decision Engine**: generate and rank candidate actions
- **Risk/Policy Gate**: enforce hard constraints and compliance
- **Action Executor**: perform API actions with idempotent guarantees
- **Outcome Evaluator**: attribute business outcome to actions
- **Learner**: update policy quality from outcomes
- **Dashboard/Alerts**: observability, health, business KPIs, incidents

---

## 5. Multi-Agent Design

### 5.1 Observer Agent

- Ingest all external/internal events
- Normalize payloads to common schema
- Detect ingestion failures and staleness

### 5.2 Feature Agent

- Compute rolling metrics in 1m/5m/1h/1d windows
- Build state vectors per product/campaign/creative/segment

### 5.3 Strategy Agent

- Produce candidate actions from playbooks and learned policy
- Score expected uplift and confidence per action

### 5.4 Policy/Risk Agent

- Apply hard rules, compliance checks, step limits
- Route high-risk actions to human approval

### 5.5 Executor Agent

- Execute approved actions on external platforms
- Guarantee idempotency and safe retries

### 5.6 Evaluator Agent

- Measure delayed outcomes by attribution window
- Compute reward, confidence, and side-effects

### 5.7 Learner Agent

- Update contextual bandit model online/offline
- Promote/demote strategies by evidence

### 5.8 Supervisor Agent

- Watch system health, drift, anomaly, queue lag
- Trigger rollback, freeze mode, or kill switch

---

## 6. Realtime Observation Model (Human-Like Awareness)

No system can literally “see everything instantly”; architecture must combine:

1. **Push-first signals** (webhooks, callbacks)
2. **Streaming telemetry** (near realtime event ingestion)
3. **Fallback polling** for sources lacking push support

### 6.1 Observation Guarantees

- Data freshness SLO by source (example: < 60s for click events)
- Staleness alarms when source exceeds freshness budget
- Degraded mode behavior when key signals stale

### 6.2 Why This Solves “Agent Goes Idle”

Agent sessions may idle, but event system remains live. Incoming events trigger new decision cycles continuously.

---

## 7. Decision and Learning Engine

### 7.1 Decision Pipeline

1. Update state from new event
2. Generate candidate actions
3. Filter by policy/risk constraints
4. Select action via hybrid policy
5. Execute
6. Evaluate outcome
7. Update learner

### 7.2 Hybrid Policy

- **Layer A: Hard Rule Constraints** (non-negotiable safety)
- **Layer B: Contextual Bandit Selector** (adaptive optimization)

### 7.3 Contextual Bandit Setup

- **Context**: channel, SKU, audience segment, hour/day, CTR, CVR, EPC, refund rate, fatigue score, volatility
- **Action Arms**:
  - scale budget +x%
  - cut budget -x%
  - pause campaign
  - swap creative variant
  - shift audience allocation
  - replace promoted SKU
- **Reward**:

```text
r = ΔNetProfit(horizon) - α*RiskEvents - β*SpendWaste
```

- Exploration rate starts small (5–10%), then decays with confidence

### 7.4 Promotion Criteria for Strategy Changes

- Statistically significant uplift versus baseline
- No policy incident during validation window
- Drawdown and volatility within risk budget

---

## 8. Control Policies (v1 Examples)

### 8.1 Underperformance Cut

- Trigger: CVR drop > 25% over 60m, minimum click sample met
- Action: reduce budget by 20%
- Guard: spend floor and cooldown
- Rollback: restore partially if recovery signal appears

### 8.2 Winner Scale

- Trigger: EPC above p75, stable for N windows
- Action: increase budget by 10%
- Guard: daily cap, max increments/day
- Rollback: undo if metrics revert below baseline

### 8.3 Creative Fatigue Rotation

- Trigger: CTR decay > 30% vs trailing baseline
- Action: rotate creative variant
- Guard: max rotations/day

### 8.4 Refund/Complaint Risk Pause

- Trigger: refund rate spike or complaint anomaly
- Action: pause SKU/campaign promotion
- Guard: human approval required for unpause

### 8.5 Segment Reallocation

- Trigger: persistent low CVR in segment with adequate traffic
- Action: shift 15% budget to top-performing segment

---

## 9. Guardrails and Safety

### 9.1 Hard Limits

- Global daily ad spend cap
- Per-campaign spend cap
- Max step-change per action (for example ±20%)
- Minimum data threshold before high-confidence moves

### 9.2 Approval Gates

Mandatory human approval for:

- Budget changes above configured threshold
- New high-impact strategy not yet validated
- Potentially non-compliant marketing content

### 9.3 Kill Switches

- Global emergency stop for all spend-changing actions
- Per-channel and per-campaign stop switches

### 9.4 Auto-Rollback

Every action class defines rollback conditions and rollback action.

---

## 10. Data Model (Minimum)

### 10.1 Core Tables/Streams

- `events_raw`
- `events_normalized`
- `products`
- `campaigns`
- `creatives`
- `segments`
- `metrics_window_1m`
- `metrics_window_1h`
- `metrics_window_1d`
- `decisions`
- `actions`
- `action_outcomes`
- `policy_rules`
- `model_versions`
- `experiments`
- `audit_logs`

### 10.2 Data Design Rules

- Events immutable
- Decision/action/outcome lineage required
- Every external action has idempotency key
- Audit log append-only

---

## 11. Reliability and Fault Tolerance

- At-least-once event processing
- Idempotent action execution
- Dead-letter queues for poisoned messages
- Circuit breakers for external APIs
- Retry with exponential backoff
- Fallback mode: if learner unavailable, use rule-only policy
- Freeze scale-up decisions when critical data stale

---

## 12. Security and Compliance Baseline

- API secrets in managed secret store
- Scoped credentials by channel/action type
- Role-based access control for approvals
- Signed action requests and immutable audit entries
- PII minimization and retention policy

---

## 13. Observability and KPI Framework

### 13.1 Business KPIs

- Net profit (daily/weekly)
- Profit per cost unit
- Incremental ROI uplift vs baseline
- Commission revenue growth

### 13.2 Efficiency KPIs

- Wasted spend rate
- Content cost per profitable conversion
- Time-to-stop losing campaign

### 13.3 Risk KPIs

- Refund rate
- Policy violation rate
- Drawdown and volatility

### 13.4 System KPIs

- Event lag / queue lag
- Data freshness by source
- Action execution success rate
- Mean time to recovery

---

## 14. Infrastructure Recommendation

### 14.1 MVP Default (Managed, fast build)

- Managed event bus
- Managed Postgres + Redis
- Serverless/managed workers for stream consumers
- Object storage for raw logs and replay

### 14.2 When to Add VPS

Add persistent VPS workers only when:

- Heavy 24/7 browser automation required
- Scraping/runtime cost too high on serverless
- Need long-lived custom workers with special binaries

### 14.3 Persistent Browser Automation Layer (Logged-In Accounts)

Goal: allow agent to operate authenticated ad accounts (Facebook, YouTube, TikTok) with persistent session/history, without cold-start browser each run.

#### Design

- Always-on browser worker on VPS or dedicated always-on machine
- Chromium launched with fixed persistent profile path (`--user-data-dir`)
- Task queue feeds browser worker with structured UI tasks
- Worker executes flows in logged-in session (cookies/history/session retained)
- Artifacts captured per task: screenshots, DOM snapshot, action trace, error logs

#### Tooling Options

1. Browser-use/Stagehand-style agentic browser framework with persistent profile
2. Playwright/Selenium with persistent browser context (`user-data-dir`)
3. RPA stack for heavy enterprise governance

Recommended: API-first + browser fallback

- Use official ads APIs for stable, high-volume operations
- Use browser automation only for UI-only flows not exposed by API

#### Safety and Reliability Requirements

- Human approval gate before publish/new campaign/high-budget changes
- Per-action idempotency key and replay-safe execution
- Anti-runaway limits: max operations/hour, spend cap, global kill switch
- Session health checks (login validity, 2FA challenge detection)
- Secure profile storage (encrypted disk, least-privilege host access)
- Compliance mode: block prohibited content patterns before submission

#### Known Constraints

- Platforms may trigger anti-bot checks/CAPTCHA/2FA
- UI selectors drift; maintenance needed
- Terms of service vary by platform; policy compliance required

---

## 15. Rollout Plan (6 Weeks)

### Week 1

- Event taxonomy and schemas
- Tracking links and attribution IDs
- Core DB schema and KPI dashboard skeleton

### Week 2

- Build connectors (catalog, ads, clicks, orders, commissions)
- Event bus and stream consumers live

### Week 3

- Rule engine v1
- Action executor v1
- Audit trail and idempotency enforcement

### Week 4

- Contextual bandit in shadow mode (recommendation-only)
- Outcome attribution windows and reward pipeline

### Week 5

- Limited autonomy for low-risk actions
- Approval workflow for high-risk actions
- Rollback and kill-switch drills

### Week 6

- Controlled production ramp
- A/B baseline comparison and tuning
- Go/no-go for wider autonomy scope

---

## 16. Maturity Stages

### Stage A: Rule-Only Optimizer

- Deterministic actions
- Fast safety validation

### Stage B: Hybrid Optimizer (Rule + Bandit)

- Controlled adaptive strategy
- Measured uplift under guardrails

### Stage C: Multi-Objective Autonomous Optimization

- Joint optimization of profit, risk, compliance, and stability
- Expanded action surface with strict governance

---

## 17. Non-Functional Requirements

- Decision latency target per event class (configurable)
- 99.9% availability target for core decision path
- End-to-end audit trace for every action
- Reproducible replay for incident analysis

---

## 18. Acceptance Criteria (v1)

1. System ingests realtime events and computes windowed features with SLO adherence
2. Rule engine executes safe low-risk actions autonomously
3. High-impact actions require explicit human approval
4. Every decision/action/outcome fully traceable in audit logs
5. Limited autonomy cohort shows positive incremental ROI vs baseline
6. Rollback and kill-switch verified in drills

---

## 19. Pseudocode Reference

```python
while True:
    event = bus.consume()
    state = state_store.update(event)

    candidates = strategy_agent.generate(state)
    safe_candidates = policy_risk_agent.filter(candidates)

    action = decision_policy.select(
        safe_candidates,
        model=bandit_model,
        exploration=epsilon
    )

    exec_result = executor_agent.execute(action)
    outcome = evaluator_agent.attribute(action, horizon="2h")

    learner_agent.update(
        context=state.context,
        action=action,
        reward=outcome.reward
    )

    supervisor_agent.observe(
        event=event,
        action=action,
        result=exec_result,
        outcome=outcome
    )

    audit_log.append(event, state, action, exec_result, outcome)
```

---

## 20. Task Schema and Workflow Templates

### 20.1 Unified Task Schema (JSON)

```json
{
  "task_id": "uuid",
  "task_type": "create_campaign|update_budget|rotate_creative|pause_campaign|publish_content",
  "platform": "facebook|tiktok|youtube",
  "account_id": "string",
  "priority": "low|normal|high|critical",
  "requested_by": "agent|human",
  "idempotency_key": "string",
  "approval_required": true,
  "approval_status": "pending|approved|rejected|not_required",
  "safety_profile": {
    "max_spend_change_pct": 20,
    "daily_spend_cap": 500,
    "ops_per_hour_cap": 30,
    "rollback_enabled": true
  },
  "payload": {
    "campaign": {
      "name": "string",
      "objective": "conversions|traffic|sales",
      "budget": {
        "amount": 100,
        "currency": "USD",
        "type": "daily|lifetime"
      },
      "schedule": {
        "start_at": "ISO8601",
        "end_at": "ISO8601|null"
      },
      "targeting": {
        "geo": ["VN"],
        "age_min": 18,
        "age_max": 45,
        "interests": ["shopping", "beauty"]
      },
      "placement": ["feed", "shorts", "stories"]
    },
    "creative": {
      "asset_id": "string",
      "headline": "string",
      "primary_text": "string",
      "cta": "Shop Now",
      "destination_url": "https://...",
      "tracking": {
        "utm_source": "string",
        "utm_campaign": "string",
        "click_id": "string"
      }
    },
    "optimization": {
      "target_metric": "net_profit|epc|cvr",
      "bid_strategy": "lowest_cost|cost_cap",
      "stop_loss": {
        "max_loss": 50,
        "window_minutes": 120
      }
    }
  },
  "prechecks": [
    "session_valid",
    "policy_scan_passed",
    "budget_within_limit",
    "duplicate_task_check"
  ],
  "execution": {
    "status": "queued|running|succeeded|failed|rolled_back",
    "attempt": 0,
    "max_attempts": 3,
    "last_error": null,
    "artifacts": {
      "screenshots": [],
      "dom_snapshots": [],
      "api_logs": []
    }
  },
  "outcome": {
    "kpi_window": "2h",
    "delta": {
      "spend": 0,
      "clicks": 0,
      "cvr": 0,
      "commission": 0,
      "net_profit": 0
    },
    "reward": 0,
    "confidence": 0
  },
  "timestamps": {
    "created_at": "ISO8601",
    "approved_at": "ISO8601|null",
    "started_at": "ISO8601|null",
    "finished_at": "ISO8601|null"
  }
}
```

### 20.2 Workflow Template: Create Campaign

1. Strategy agent emits `create_campaign` task.
2. Risk agent validates spend caps, policy scan, account health.
3. If above threshold, send approval request.
4. Executor uses API-first path; browser fallback if API unavailable.
5. Verify campaign state on platform UI/API.
6. Start outcome tracking window and emit `campaign_created` event.

### 20.3 Workflow Template: Budget Optimization

1. Evaluator detects trigger (`CVR drop`, `EPC spike`, or `stop-loss`).
2. Strategy agent emits `update_budget` task with bounded step change.
3. Policy gate enforces cooldown and per-day increment limits.
4. Executor applies update and records artifact logs.
5. Evaluator computes uplift vs baseline; learner updates bandit values.
6. If negative drift beyond threshold, auto-rollback.

### 20.4 Workflow Template: Creative Rotation

1. Feature agent flags fatigue (`CTR decay > threshold`).
2. Strategy agent emits `rotate_creative` with top alternative from library.
3. Compliance scanner validates text/claims before publish.
4. Executor swaps creative, preserves same campaign ID when possible.
5. Outcome tracked in matched time window for fair comparison.

### 20.5 Platform Adapter Contract

Each platform adapter must expose:

- `create_campaign(task_payload)`
- `update_budget(task_payload)`
- `pause_campaign(task_payload)`
- `rotate_creative(task_payload)`
- `get_campaign_state(account_id, campaign_id)`
- `validate_session(account_id)`

Adapter response shape:

```json
{
  "success": true,
  "platform_campaign_id": "string",
  "request_id": "string",
  "artifacts": {
    "api_request": "...",
    "api_response": "...",
    "screenshot": "..."
  },
  "error": null
}
```

### 20.6 Queue + Retry Rules

- FIFO per account, parallel across accounts
- Idempotency key required for every mutation task
- Exponential backoff retries for transient failures
- No retry for policy rejection or invalid payload
- Dead-letter queue after max attempts

### 20.7 Approval Policy Defaults

- Auto-approve: spend delta <= 10% and low-risk category
- Manual approve required: spend delta > 10%, new campaign launch, sensitive verticals
- Dual approval required: spend delta > 30% or daily budget > configured critical threshold

## 21. SQL Schema (PostgreSQL v1)

```sql
-- enums
CREATE TYPE task_type_enum AS ENUM (
  'create_campaign','update_budget','rotate_creative','pause_campaign','publish_content'
);

CREATE TYPE platform_enum AS ENUM ('facebook','tiktok','youtube');
CREATE TYPE priority_enum AS ENUM ('low','normal','high','critical');
CREATE TYPE approval_status_enum AS ENUM ('pending','approved','rejected','not_required');
CREATE TYPE execution_status_enum AS ENUM ('queued','running','succeeded','failed','rolled_back');

-- core tasks
CREATE TABLE tasks (
  id UUID PRIMARY KEY,
  task_type task_type_enum NOT NULL,
  platform platform_enum NOT NULL,
  account_id TEXT NOT NULL,
  priority priority_enum NOT NULL DEFAULT 'normal',
  requested_by TEXT NOT NULL CHECK (requested_by IN ('agent','human')),
  idempotency_key TEXT NOT NULL UNIQUE,
  approval_required BOOLEAN NOT NULL DEFAULT true,
  approval_status approval_status_enum NOT NULL DEFAULT 'pending',

  max_spend_change_pct NUMERIC(5,2) NOT NULL DEFAULT 20,
  daily_spend_cap NUMERIC(14,2) NOT NULL DEFAULT 0,
  ops_per_hour_cap INTEGER NOT NULL DEFAULT 30,
  rollback_enabled BOOLEAN NOT NULL DEFAULT true,

  payload JSONB NOT NULL,
  prechecks JSONB NOT NULL DEFAULT '[]'::jsonb,

  execution_status execution_status_enum NOT NULL DEFAULT 'queued',
  attempt INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  last_error TEXT,

  outcome_window TEXT,
  reward NUMERIC(14,6),
  confidence NUMERIC(6,5),

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  approved_at TIMESTAMPTZ,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);

CREATE INDEX idx_tasks_status_priority ON tasks (execution_status, priority, created_at);
CREATE INDEX idx_tasks_platform_account ON tasks (platform, account_id, created_at DESC);
CREATE INDEX idx_tasks_approval ON tasks (approval_required, approval_status, created_at);
CREATE INDEX idx_tasks_payload_gin ON tasks USING GIN (payload jsonb_path_ops);

-- execution artifacts
CREATE TABLE task_artifacts (
  id BIGSERIAL PRIMARY KEY,
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  artifact_type TEXT NOT NULL CHECK (artifact_type IN ('screenshot','dom_snapshot','api_log','trace')),
  uri TEXT NOT NULL,
  meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_task_artifacts_task_id ON task_artifacts(task_id, created_at DESC);

-- approvals
CREATE TABLE task_approvals (
  id BIGSERIAL PRIMARY KEY,
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  approver_id TEXT NOT NULL,
  decision approval_status_enum NOT NULL CHECK (decision IN ('approved','rejected')),
  reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_task_approvals_task_id ON task_approvals(task_id, created_at DESC);

-- outcomes (windowed KPI deltas)
CREATE TABLE task_outcomes (
  task_id UUID PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
  kpi_window TEXT NOT NULL,
  delta_spend NUMERIC(14,4) NOT NULL DEFAULT 0,
  delta_clicks BIGINT NOT NULL DEFAULT 0,
  delta_cvr NUMERIC(10,6) NOT NULL DEFAULT 0,
  delta_commission NUMERIC(14,4) NOT NULL DEFAULT 0,
  delta_net_profit NUMERIC(14,4) NOT NULL DEFAULT 0,
  reward NUMERIC(14,6) NOT NULL DEFAULT 0,
  confidence NUMERIC(6,5) NOT NULL DEFAULT 0,
  measured_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- queue lease table (optional if external queue unavailable)
CREATE TABLE task_queue_lease (
  task_id UUID PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
  worker_id TEXT NOT NULL,
  leased_until TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_task_queue_lease_until ON task_queue_lease(leased_until);

-- policy rules
CREATE TABLE policy_rules (
  id BIGSERIAL PRIMARY KEY,
  rule_name TEXT NOT NULL UNIQUE,
  enabled BOOLEAN NOT NULL DEFAULT true,
  severity TEXT NOT NULL CHECK (severity IN ('info','warn','block')),
  condition_json JSONB NOT NULL,
  action_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- audit logs (append-only)
CREATE TABLE audit_logs (
  id BIGSERIAL PRIMARY KEY,
  task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
  event_type TEXT NOT NULL,
  actor TEXT NOT NULL,
  details JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_logs_task_id ON audit_logs(task_id, created_at DESC);
CREATE INDEX idx_audit_logs_event_type ON audit_logs(event_type, created_at DESC);

-- helper trigger for policy_rules.updated_at
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_policy_rules_updated_at
BEFORE UPDATE ON policy_rules
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
```

### 21.1 SQL Notes
- `payload` and `condition_json` stay JSONB for fast iteration.
- Move hot fields to typed columns when query profile stabilizes.
- Use external queue (Kafka/SQS/PubSub) for production scale; DB lease table only fallback.
- Keep `audit_logs` append-only; no update/delete in app layer.

## 22. UI and Telegram Copilot Experience

### 22.1 Product Surfaces

System exposes two operator surfaces:

1. **Web Dashboard** for deep monitoring, analysis, and control  
2. **Telegram Copilot** for fast communication, approvals, and alerts

### 22.2 Dashboard Requirements (Web)

#### A. Command Center
- Net revenue, ad spend, net profit, ROAS, refund rate (live windows)
- Realtime health badges: data freshness, queue lag, API health
- Profit trend and volatility charts (1h/24h/7d)

#### B. Campaign Intelligence
- Campaign table with status, budget, EPC, CTR, CVR, risk score
- Sort/filter by platform/account/segment/strategy state
- Highlight winners, losers, and constrained campaigns

#### C. Approval Inbox
- Pending high-impact actions requiring human decision
- Side-by-side context: proposed change, expected uplift, risk impact
- Approve/reject with reason logging and full traceability

#### D. Execution Timeline
- Chronological stream: decision -> action -> platform result -> outcome
- Rollback markers and incident annotations
- Drill-down to artifacts (screenshots, API logs, DOM snapshots)

#### E. Guardrail Controls
- Daily spend cap, per-campaign cap, max step-change
- Cooldown intervals, stop-loss thresholds, automation level
- Global kill switch and per-platform emergency stop

### 22.3 Telegram Copilot Requirements

#### A. Communication Role
- Primary near-realtime communication channel with operator
- Delivers alerts, summaries, and action requests

#### B. Core Capabilities
- Daily briefing and periodic KPI summaries
- On-demand Q&A (profit drop analysis, top winners, underperformers)
- Approval workflow commands for high-risk tasks
- Incident notifications (spend spike, policy risk, stale data, queue lag)

#### C. Command Surface (v1)
- `/status` -> current health + top KPIs
- `/profit` -> profit breakdown by window/platform
- `/winners` -> top performing campaigns/products
- `/losers` -> campaigns flagged for cut/pause
- `/approvals` -> list pending approval tasks
- `/approve <task_id>` -> approve task
- `/reject <task_id> <reason>` -> reject task
- `/pause <campaign_id>` -> emergency pause request
- `/resume <campaign_id>` -> resume request (subject to policy)
- `/kill-switch on|off` -> global automation stop/start (restricted)

#### D. Telegram Interaction Model
1. System detects event and computes decision  
2. Low-risk action auto-executes and sends notification  
3. High-risk action creates approval ticket  
4. Telegram asks operator for approval  
5. Operator responds via command/button  
6. Executor runs action and reports outcome in Telegram + dashboard timeline

### 22.4 UX Principles
- Dashboard optimized for situational awareness and forensic analysis
- Telegram optimized for speed, mobility, and low-latency decisioning
- Every Telegram action links back to dashboard detail view
- Every dashboard approval can be completed from Telegram

### 22.5 Telegram Bot Setup and Runtime Model

#### A. BotFather Setup (One-Time)
1. Open Telegram and chat with `@BotFather`
2. Run `/newbot` and create bot name + username
3. Receive bot token (store in secret manager, never hardcode)
4. Set bot profile assets (`/setdescription`, `/setuserpic`, `/setcommands`)

#### B. Runtime Integration
- Backend registers webhook endpoint with Telegram Bot API
- Telegram delivers updates (messages, commands, button callbacks) to webhook
- Command router validates user/role and dispatches operation
- System replies in chat with action status + links to dashboard detail

#### C. Required Webhook Endpoints
- `POST /telegram/webhook` (main updates)
- `GET /telegram/health` (liveness/readiness)

#### D. Secrets and Access
- Store bot token in managed secret store
- Restrict accepted chat IDs/user IDs to allowlist
- Separate roles: operator, approver, admin

#### E. Failure Handling
- If webhook unavailable, queue outbound notifications and raise incident alert
- If command authorization fails, deny action and log audit event
- If action execution fails, return error + suggested next command

### 22.6 Security and Access Controls for UI/Chat
- Role-based permissions for dashboard modules and Telegram commands
- Sensitive commands (`kill-switch`, high-budget approval) restricted to privileged roles
- Signed callback validation for Telegram interactions
- Full audit logging of user identity, command, timestamp, decision

## 23. Summary

This specification defines complete event-driven, safety-governed, self-improving affiliate agent system. System learns from outcomes, adapts strategy under hard constraints, and optimizes net profit with controlled operational risk, with dual operator interfaces: web dashboard for depth and Telegram copilot for speed.
