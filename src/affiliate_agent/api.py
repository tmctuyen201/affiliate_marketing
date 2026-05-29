from __future__ import annotations

from dataclasses import asdict
from html import escape

from fastapi import APIRouter, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from affiliate_agent.decisioning import DecisionContext, DecisionEngine
from affiliate_agent.policies import ApprovalRouter, PolicyGate, TaskGenerator
from affiliate_agent.services import ALL_SERVICES
from affiliate_agent.contracts import TaskContract


class DecisionContextPayload(BaseModel):
    account_id: str
    platform: str
    campaign_id: str
    daily_spend_cap: float
    current_budget: float
    baseline_cvr: float
    current_cvr: float
    clicks: int
    cooldown_active: bool
    current_epc: float
    epc_p75: float
    stable_windows: int
    fatigue_baseline_ctr: float
    current_ctr: float
    refunds_baseline_rate: float
    current_refund_rate: float
    complaints_anomaly: bool
    segments: dict[str, dict[str, float]]
    daily_spend: float
    per_campaign_cap: float
    spend_change_today_pct: float
    max_step_change_pct: float
    validated_strategies: list[str]
    risk_category: str
    sensitive_vertical: bool
    critical_daily_budget_threshold: float
    requested_by: str
    creative_rotation_count_today: int = 0
    creative_candidates: list[str] = []
    current_creative_id: str | None = None
    sku_id: str | None = None

    def to_context(self) -> DecisionContext:
        data = self.model_dump()
        data["validated_strategies"] = set(data["validated_strategies"])
        return DecisionContext(**data)


class TelegramChat(BaseModel):
    id: int


class TelegramUser(BaseModel):
    id: int
    username: str | None = None


class TelegramMessage(BaseModel):
    chat: TelegramChat
    from_user: TelegramUser = Field(alias="from")
    text: str


class TelegramUpdate(BaseModel):
    message: TelegramMessage


def create_app(
    *,
    allowed_chat_ids: set[int] | None = None,
    health_snapshot: dict[str, object] | None = None,
    approvals: list[dict[str, object]] | None = None,
    user_roles: dict[int, str] | None = None,
    execution_service: object | None = None,
) -> FastAPI:
    app = FastAPI(title="affiliate-agent")
    router = APIRouter()
    engine = DecisionEngine(generator=TaskGenerator(), gate=PolicyGate(), router=ApprovalRouter())
    allowed_chat_ids = allowed_chat_ids or set()
    health_snapshot = health_snapshot or {
        "net_profit": 0,
        "ad_spend": 0,
        "roas": 0,
        "queue_lag": "0s",
        "api_health": "unknown",
    }
    approvals_store = [dict(item) for item in (approvals or [])]
    user_roles = user_roles or {}
    timeline = [{"stage": "decision", "detail": "Awaiting operator actions"}]
    audit_log: list[dict[str, object]] = []
    global_kill_switch = False
    channel_kill_switches: set[str] = set()
    campaign_kill_switches: set[str] = set()
    telegram_secret = "dev-telegram-secret"

    def audit_entry(*, actor: str, user_id: int, role: str, command: str, reason: str, event: str) -> None:
        audit_log.append(
            {
                "event": event,
                "actor": actor,
                "user_id": user_id,
                "role": role,
                "command": command,
                "reason": reason,
            }
        )

    def deny(*, actor: str, user_id: int, role: str, command: str, reason: str, status_code: int) -> None:
        audit_entry(actor=actor, user_id=user_id, role=role, command=command, reason=reason, event="authorization_denied")
        detail = reason
        raise HTTPException(status_code=status_code, detail=detail)

    def require_admin(*, actor: str, user_id: int, role: str, command: str) -> None:
        if role != "admin":
            deny(actor=actor, user_id=user_id, role=role, command=command, reason="role_not_allowed", status_code=403)

    def find_task(task_id: str) -> dict[str, object]:
        task = next((item for item in approvals_store if item.get("task_id") == task_id), None)
        if task is None:
            raise HTTPException(status_code=404, detail="task_not_found")
        return task

    def ensure_task_not_blocked(task: dict[str, object], *, actor: str, user_id: int, role: str, command: str) -> None:
        platform = str(task.get("platform", ""))
        campaign_id = str(task.get("campaign_id", ""))
        if global_kill_switch:
            deny(actor=actor, user_id=user_id, role=role, command=command, reason="kill_switch_enabled_global", status_code=423)
        if platform and platform in channel_kill_switches:
            deny(actor=actor, user_id=user_id, role=role, command=command, reason=f"kill_switch_enabled_for_channel:{platform}", status_code=423)
        if campaign_id and campaign_id in campaign_kill_switches:
            deny(actor=actor, user_id=user_id, role=role, command=command, reason=f"kill_switch_enabled_for_campaign:{campaign_id}", status_code=423)

    @router.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "affiliate-agent",
            "services": ALL_SERVICES,
        }

    @router.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        pending = [item for item in approvals_store if item.get("approval_status") == "pending"]
        approval_rows = "".join(
            f"""<tr>
              <td>{escape(str(item['task_id']))}</td>
              <td>{escape(str(item['summary']))}</td>
              <td>{escape(str(item.get('risk_impact','-')))}</td>
              <td><span class="badge pending">pending</span></td>
            </tr>"""
            for item in pending
        ) or "<tr><td colspan='4' class='muted'>No pending approvals</td></tr>"

        timeline_items = "".join(
            f"<li><span class='stage'>{escape(str(item['stage']))}</span><span class='detail'>{escape(str(item['detail']))}</span></li>"
            for item in timeline[-10:]
        ) or "<li class='muted'>No timeline events yet</li>"

        kill_state = "ON" if global_kill_switch else "OFF"

        return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Affiliate Agent Command Center</title>
    <style>
      :root {{
        --bg:#0b1220; --panel:#121a2b; --panel2:#0f1726; --line:#253149;
        --text:#e7edf8; --muted:#91a0bc; --ok:#2ed47a; --warn:#ffbf47; --bad:#ff6b6b; --accent:#5ea1ff;
      }}
      * {{ box-sizing:border-box; }}
      body {{ margin:0; font-family:Inter, ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif; background:linear-gradient(180deg,#0b1220,#0a1020); color:var(--text); }}
      .wrap {{ max-width:1200px; margin:0 auto; padding:20px; }}
      .top {{ display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:16px; }}
      h1 {{ font-size:24px; margin:0; }}
      .sub {{ color:var(--muted); font-size:14px; }}
      .pill {{ padding:6px 10px; border-radius:999px; font-size:12px; border:1px solid var(--line); background:var(--panel2); }}
      .grid {{ display:grid; gap:12px; }}
      .kpis {{ grid-template-columns:repeat(5,minmax(140px,1fr)); }}
      .card {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:14px; }}
      .k-title {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
      .k-val {{ font-size:22px; font-weight:700; margin-top:6px; }}
      .main {{ grid-template-columns:1.4fr 1fr; margin-top:12px; }}
      .section-title {{ margin:0 0 10px; font-size:16px; }}
      table {{ width:100%; border-collapse:collapse; }}
      th,td {{ text-align:left; padding:10px 8px; border-bottom:1px solid var(--line); font-size:13px; }}
      th {{ color:var(--muted); font-weight:600; }}
      .badge {{ padding:3px 8px; border-radius:999px; font-size:11px; border:1px solid; }}
      .badge.pending {{ color:var(--warn); border-color:#6e5626; background:#2b2415; }}
      .list {{ list-style:none; padding:0; margin:0; display:grid; gap:8px; }}
      .list li {{ padding:10px; border:1px solid var(--line); border-radius:10px; background:var(--panel2); display:grid; gap:4px; }}
      .stage {{ font-size:11px; color:var(--accent); text-transform:uppercase; letter-spacing:.08em; }}
      .detail {{ font-size:13px; color:var(--text); }}
      .muted {{ color:var(--muted); }}
      .controls {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:8px; }}
      .control {{ padding:10px; border:1px solid var(--line); border-radius:10px; background:var(--panel2); font-size:13px; }}
      .footer {{ margin-top:12px; color:var(--muted); font-size:12px; }}
      @media (max-width:980px) {{
        .kpis {{ grid-template-columns:repeat(2,minmax(140px,1fr)); }}
        .main {{ grid-template-columns:1fr; }}
      }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="top">
        <div>
          <h1>Command Center</h1>
          <div class="sub">Realtime ops for affiliate automation: approvals, execution timeline, guardrails.</div>
          <div class="sub">Net revenue / profit snapshot</div>
        </div>
        <div class="pill">Kill switch: <strong>{kill_state}</strong></div>
      </div>

      <section class="grid kpis">
        <div class="card"><div class="k-title">Net Profit</div><div class="k-val">{escape(str(health_snapshot.get('net_profit', 0)))}</div></div>
        <div class="card"><div class="k-title">Ad Spend</div><div class="k-val">{escape(str(health_snapshot.get('ad_spend', 0)))}</div></div>
        <div class="card"><div class="k-title">ROAS</div><div class="k-val">{escape(str(health_snapshot.get('roas', 0)))}</div></div>
        <div class="card"><div class="k-title">Queue Lag</div><div class="k-val">{escape(str(health_snapshot.get('queue_lag', '0s')))}</div></div>
        <div class="card"><div class="k-title">API health</div><div class="k-val">{escape(str(health_snapshot.get('api_health', 'unknown')))}</div></div>
      </section>

      <section class="grid main">
        <div class="card">
          <h2 class="section-title">Approval Inbox</h2>
          <div class="muted">Pending approvals: {len(pending)}</div>
          <table>
            <thead><tr><th>Task</th><th>Summary</th><th>Risk</th><th>Status</th></tr></thead>
            <tbody>{approval_rows}</tbody>
          </table>
          <div class="footer">Use Telegram commands: /approvals, /approve &lt;id&gt;, /reject &lt;id&gt; &lt;reason&gt;</div>
          <div class="footer">Telegram actions link back to dashboard detail</div>
        </div>

        <div class="card">
          <h2 class="section-title">Execution Timeline</h2>
          <ul class="list">{timeline_items}</ul>
        </div>
      </section>

      <section class="card" style="margin-top:12px">
        <h2 class="section-title">Guardrail Controls</h2>
        <div class="controls">
          <div class="control">Daily spend cap / campaign cap / max step-change</div>
          <div class="control">Cooldown / stop-loss / automation level</div>
          <div class="control">Global kill switch + channel/campaign scope</div>
          <div class="control">Audit trail + rollback drills</div>
        </div>
      </section>
    </div>
  </body>
</html>"""

    @router.get("/telegram/health")
    def telegram_health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/api/approvals")
    def approval_inbox() -> list[dict[str, object]]:
        return approvals_store

    @router.get("/api/audit")
    def audit_feed() -> list[dict[str, object]]:
        return audit_log


    @router.get("/api/regression-harness")
    def regression_harness() -> dict[str, object]:
        pending = len([item for item in approvals_store if item.get("approval_status") == "pending"])
        approved = len([item for item in approvals_store if item.get("approval_status") == "approved"])
        last_event = str(audit_log[-1]["event"]) if audit_log else None
        if last_event == "kill_switch_changed" and global_kill_switch:
            last_event = "kill_switch_enabled"
        return {
            "kill_switch_enabled": global_kill_switch,
            "pending_approvals": pending,
            "approved_approvals": approved,
            "last_audit_event": last_event,
            "health_snapshot": health_snapshot,
        }

    @router.post("/decision/preview")
    def decision_preview(payload: DecisionContextPayload) -> dict[str, object]:
        decision = engine.decide(payload.to_context())
        return asdict(decision)


    @router.post("/execution/tasks")
    def execute_task(payload: dict[str, object]) -> dict[str, object]:
        if execution_service is None:
            raise HTTPException(status_code=404, detail="execution_service_unavailable")
        try:
            task = TaskContract(**payload)
            if hasattr(execution_service, "execute"):
                result = execution_service.execute(task)
            elif hasattr(execution_service, "run"):
                result = execution_service.run(task)
            else:
                raise RuntimeError("execution_service_invalid")
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=500, detail=str(exc))
        if hasattr(result, "to_dict"):
            return result.to_dict()
        return result

    @router.post("/telegram/webhook")
    def telegram_webhook(
        update: TelegramUpdate,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> dict[str, object]:
        message = update.message
        actor = message.from_user.username or "unknown"
        user_id = message.from_user.id
        role = user_roles.get(user_id, "operator")
        command, _, remainder = message.text.partition(" ")

        if x_telegram_bot_api_secret_token is not None and x_telegram_bot_api_secret_token != telegram_secret:
            deny(actor=actor, user_id=user_id, role=role, command=command, reason="invalid_telegram_signature", status_code=401)
        if message.chat.id not in allowed_chat_ids:
            deny(actor=actor, user_id=user_id, role=role, command=command, reason="chat_not_allowed", status_code=403)

        if command == "/status":
            return {
                "ok": True,
                "reply": (
                    f"Health {health_snapshot['api_health']} | Net profit {health_snapshot['net_profit']} "
                    f"| Ad spend {health_snapshot['ad_spend']} | ROAS {health_snapshot['roas']} "
                    f"| Queue lag {health_snapshot['queue_lag']}"
                ),
            }

        if command == "/approvals":
            pending = [item for item in approvals_store if item.get("approval_status") == "pending"]
            if not pending:
                return {"ok": True, "reply": "No pending approvals"}
            lines = [f"- {item['task_id']} | {item['summary']} | risk {item['risk_impact']}" for item in pending]
            return {"ok": True, "reply": "Pending approvals:\n" + "\n".join(lines)}

        if command == "/kill-switch":
            require_admin(actor=actor, user_id=user_id, role=role, command=command)
            parts = remainder.split()
            if not parts:
                raise HTTPException(status_code=400, detail="invalid_kill_switch_state")
            scope = "global"
            target = None
            if parts[0] in {"channel", "campaign"}:
                if len(parts) < 2:
                    raise HTTPException(status_code=400, detail="invalid_kill_switch_scope")
                scope = parts[0]
                target = parts[1]
                parts = parts[2:]
            elif parts[0] not in {"on", "off"}:
                raise HTTPException(status_code=400, detail="invalid_kill_switch_scope")
            elif len(parts) > 1:
                raise HTTPException(status_code=400, detail="invalid_kill_switch_state")
            if not parts:
                raise HTTPException(status_code=400, detail="invalid_kill_switch_scope" if scope != "global" else "invalid_kill_switch_state")
            state = parts[0]
            if state not in {"on", "off"}:
                raise HTTPException(status_code=400, detail="invalid_kill_switch_state")
            if scope == "global":
                nonlocal_global = state == "on"
                globals()["__dummy__"] = None
                nonlocal global_kill_switch
                global_kill_switch = nonlocal_global
                reason = f"{'enabled' if state == 'on' else 'disabled'}_global"
                audit_entry(actor=actor, user_id=user_id, role=role, command=command, reason=reason, event="kill_switch_changed")
                reply = f"Kill switch {'enabled' if state == 'on' else 'disabled' if False else 'disabled'}"
                return {"ok": True, "reply": f"Kill switch {'enabled' if state == 'on' else 'disabled'} globally"}
            if scope == "channel":
                if state == "on":
                    channel_kill_switches.add(str(target))
                else:
                    channel_kill_switches.discard(str(target))
                reason = f"{'enabled' if state == 'on' else 'disabled'}_channel:{target}"
                audit_entry(actor=actor, user_id=user_id, role=role, command=command, reason=reason, event="kill_switch_changed")
                return {"ok": True, "reply": f"Kill switch {'enabled' if state == 'on' else 'disabled'} for channel {target}"}
            if scope == "campaign":
                if state == "on":
                    campaign_kill_switches.add(str(target))
                else:
                    campaign_kill_switches.discard(str(target))
                reason = f"{'enabled' if state == 'on' else 'disabled'}_campaign:{target}"
                audit_entry(actor=actor, user_id=user_id, role=role, command=command, reason=reason, event="kill_switch_changed")
                return {"ok": True, "reply": f"Kill switch {'enabled' if state == 'on' else 'disabled'} for campaign {target}"}
            raise HTTPException(status_code=400, detail="invalid_kill_switch_scope")

        if command == "/rollback":
            require_admin(actor=actor, user_id=user_id, role=role, command=command)
            task_id, _, _rest = remainder.partition(" ")
            if not task_id:
                raise HTTPException(status_code=400, detail="task_id_required")
            find_task(task_id)
            audit_entry(actor=actor, user_id=user_id, role=role, command=command, reason=f"rollback_drill_for:{task_id}", event="rollback_requested")
            return {"ok": True, "reply": f"Rollback drill queued for {task_id}"}

        if command in {"/approve", "/reject"}:
            if role not in {"approver", "admin"}:
                deny(actor=actor, user_id=user_id, role=role, command=command, reason="role_not_allowed", status_code=403)
            task_id, _, reason = remainder.partition(" ")
            if not task_id:
                raise HTTPException(status_code=400, detail="task_id_required")
            task = find_task(task_id)
            ensure_task_not_blocked(task, actor=actor, user_id=user_id, role=role, command=command)
            if command == "/approve":
                decision_reason = f"approved via telegram by {actor}"
                task["approval_status"] = "approved"
                task["decision_reason"] = decision_reason
                timeline.append({"stage": "approval", "detail": f"Approved {task_id}"})
                audit_entry(actor=actor, user_id=user_id, role=role, command=command, reason=f"approved:{task_id}", event="approval_recorded")
                return {"ok": True, "reply": f"Approved {task_id}. Reason logged: {decision_reason}"}
            if not reason.strip():
                raise HTTPException(status_code=400, detail="reject_reason_required")
            decision_reason = reason.strip()
            task["approval_status"] = "rejected"
            task["decision_reason"] = decision_reason
            timeline.append({"stage": "approval", "detail": f"Rejected {task_id}"})
            audit_entry(actor=actor, user_id=user_id, role=role, command=command, reason=f"rejected:{task_id}", event="approval_recorded")
            return {"ok": True, "reply": f"Rejected {task_id}. Reason logged: {decision_reason}"}

        raise HTTPException(status_code=400, detail="unsupported_command")

    app.include_router(router)
    return app
