# DSH human-request event catalog

This catalog is based on the installed DSH `0.1.1-rc.2` type contracts and the session event
model. The research record and upstream references are in
`docs/DSH-HUMAN-REQUEST-RESEARCH-2026-09-02.md`.

## Answerable blocking requests

| Wire frame / session event | Meaning | Identity | Response |
|---|---|---|---|
| `approval/requested` (mux) | Tool execution permission request, including file mutation tools such as `edit` | `rpcId` + `sessionId`; `approvalId` is audit identity; optional `callId` | `client-response`, echo `rpcId`, value `{sessionId, approvalId, outcome}` where outcome is `allowed-once` or `rejected` |
| `approval/asked` (session event) | Durable audit event for the same approval before the decision | `id`/`approvalId`, optional `callId`, session | Paired with `approval/decided`; Bridge converts it to compatibility `approval/request` |
| `question/requested` (mux) | One `ask()` batch; may contain one or many question items | `rpcId` + `sessionId` | `client-response`, echo `rpcId`, value `{sessionId, answer:{answers:[...]}}` |
| `tool/call` with `name: ask_user_question` | Session-event source for a question when mux is unavailable | `callId` + `sessionId` | Ordinary tool response; Bridge emits `question/requested` and closes on matching `tool/result` |

A question is one batch: multiple question items must remain in one response. Each item has
`id`, `question`, optional `header`/`detail`, `options[]`, optional `multiSelect`, and optional
`intent: {kind: "plan-review", approve}`. `plan-review` is a presentation intent over the
question contract, not a separate response transport.

## Non-blocking events that must not create a popup

`session/event` is the envelope for ordinary lifecycle, `assistant/message`, `tool/call`,
`tool/result`, `request/header`, `request/context`, `todo/write`, and `session/queue` records.
An `edit` tool call alone is an action record, not proof of a human wait. It should only become a
popup when DSH emits the approval request frame/event (or an explicit `ask_user_question` call).
This prevents every ordinary edit from generating a false approval popup.

## Control and authorization requests

`agent/request` and `agent/request-error` are model-request lifecycle hooks, not human-choice
requests. `ctx.authorization.prompt()` is an authorization-surface question, but it is not part of
the session mux approval/question frame union in the installed API contract; adapters must not
invent a response shape for it without an explicit bridge payload.

## Dynamic Cordis approval

Dynamic packages with a browser half can suspend a `cordis_run` operation until a person
approves or declines it. This is a forwarded Cordis event, not a Mux frame:

| Wire event | Meaning | Identity | Resolution |
|---|---|---|---|
| `cordis/request-run` | Dynamic client package activation request; actionable only when `requiresApproval` is true | `requestId` + `agentId` | User approves or rejects the run |
| `cordis/request-run-resolved` | The pending run left the answerable state | `requestId` + outcome | `approved`, `rejected`, `cancelled`, `failed`, or `completed` |

The payload must preserve `pluginId`, `packageId`, `mode`, `name`, `purpose`, and
`requiresApproval`. Cordis must remain distinguishable from ordinary tool approval because its
answer path and lifecycle are different.

## Bounded local surfacing (pet side)

The pet keeps at most `ALERT_QUEUE_LIMIT` pending alert bubbles plus one currently displayed
(`pet/window_alerts.py::ALERT_QUEUE_LIMIT` = 64). Approval, question and interaction requests are
**not exempt**: a burst of answerable requests must never grow the queue without bound.

The manager-side truth table is bounded too: `AgentLinkManager._PENDING_INTERACTION_MAX` = 256
(`pet/agent_link.py`), i.e. four times the display queue. When it is full the pet applies the same
policy as the display queue: reject an incoming lower-priority item, otherwise evict the oldest item
among the lowest-priority ones (`pending 交互表已满(...)` warning plus
`AgentLinkManager._pending_interaction_overflow_count`). Eviction resolves that alert id on the
display owner as well, so no unreachable sticky bubble is left behind. Identified approvals/questions
are **long-pending** state: no TTL applies to them (the capacity is their bound), while the identity-less
degraded prompts — which no `resolved` frame can ever pair with — expire after
`_PENDING_INTERACTION_HINT_TTL_S` (900 s).

Requests that arrive while nothing is visible keep their pending truth and are re-surfaced: the
multi-window proxy hands stateful alerts (`approval`/`question`/`interaction`/`cordis`/
`execution/failed`) to the application-level display owner even when no window is visible, and the
manager re-delivers the same `interaction_id` when a presentation target comes back
(`AgentLinkManager.redeliver_pending_interactions`, called on `resume()` plus a bounded, self-stopping
backoff timer). Re-delivery is idempotent because the display owner merges by `alert_id`.

Dropping a local prompt is a **local presentation** decision only:

- No response is sent upstream. A dropped prompt is neither `allowed-once` nor `rejected`; the
  request stays pending on the DSH side and can still be answered from any other DSH surface.
- The drop is recorded (`alert queue full(...)` warning plus the `_alert_overflow_count`
  counter on the host), so "why did I not see it" is answerable from the log.
- When the queue is full the pet prefers higher-priority items: it either rejects a new
  lower-priority item or evicts the oldest item among the lowest-priority ones. There is no
  unbounded summary replay afterwards (`quiet_mode` deferral stays bounded at its own limit) and
  no new setting controls this — the bound is a hard product limit, not a preference.

## Bridge/Pet invariants

- Preserve `rpcId` and `sessionId` on every answerable request.
- Preserve all question items and all option labels; never reduce a multi-question batch to its first item.
- Match resolution by `rpcId`/`approvalId`/`callId`/`requestId` **of the same field** (a `rpcId`
  never matches an `approvalId` that happens to carry the same string), always scoped by source and
  session. Both the semantic channel (`normalized_event`) and the legacy direct signal share one
  implementation (`AgentLinkManager._resolve_matching_interaction`), so one `approval/resolved`
  record closes exactly one pending interaction: the second channel finds no candidate and is a
  structural no-op (no text/time-based dedup involved).
- Treat `tool/result` as question resolution only when its `callId` is currently pending.
- Do not classify `edit/requested`, `permission/requested`, or other guessed event names as
  approval without a verified producer and response contract.
- Remove a resolved request by its own identity only; never remove a neighboring pending event
  to repair queue order.
- A locally dropped prompt (bounded queue, see above) is never an answer: do not synthesize
  `allowed-once`/`rejected`, and do not clear the pending state upstream.
