# Customer Support Tools

Enterprise support capabilities for the VoxForge voice agent workflow.

## Product flow

```mermaid
flowchart LR
    Call[Customer call] --> Agent[Voice Agent]
    Agent --> KB[knowledge_base_lookup]
    Agent --> TL[ticket_lookup]
    Agent --> TC[ticket_create]
    KB --> Handoff[Human handoff]
    TL --> Handoff
    TC --> Handoff
    Agent --> Eval[Evaluation]
    Agent --> Replay[Replay]
    Agent --> Dash[Dashboard]
```

## Tools

| Tool | Purpose |
|------|---------|
| `knowledge_base_lookup` | Search KB articles for self-service answers |
| `ticket_lookup` | Find tickets by ID or customer email |
| `ticket_create` | Open a new support ticket for human follow-up |

Tools are enabled when `SUPPORT_TOOLS_ENABLED=true` (default) and `TOOLS_ENABLED=true`.

## Architecture

Follows ports/adapters — same pattern as STT/LLM/TTS providers:

```
Tool handlers (support_tools.py)
    ↓
Ports (KnowledgeBaseProvider, TicketingProvider)
    ↓
Adapters (mock, Zendesk ticketing)
```

Zendesk is implemented for ticket lookup and creation. Knowledge remains `internal` or `mock`;
Freshdesk is not implemented.

### Key files

| Layer | Path |
|-------|------|
| Domain | `src/voxforge/core/domain/support.py` |
| Ports | `src/voxforge/core/interfaces/support.py` |
| Mock adapters | `src/voxforge/infrastructure/providers/support/mock.py` |
| Zendesk adapter | `src/voxforge/infrastructure/providers/support/zendesk.py` |
| Factory | `src/voxforge/infrastructure/providers/support/factory.py` |
| Tool handlers | `src/voxforge/infrastructure/tools/support_tools.py` |
| Registry wiring | `src/voxforge/infrastructure/tools/registry_factory.py` |

## MCP runtime discovery

Support tools register as an internal MCP server (`voxforge-support`) at startup:

- `GET /api/v1/tools` — lists all tools including support tools
- `GET /api/v1/tools/mcp/servers` — shows `voxforge-support` server
- `GET /api/v1/tools/mcp/health` — includes internal tool count

Execution remains in-process via `ToolRouter` (not external MCP stdio).

## Observability

| Signal | Mechanism |
|--------|-----------|
| Metrics | `voxforge_tool_calls_total`, `voxforge_tool_latency_seconds` |
| Tracing | `tool.router.execute`, `support.knowledge_base_lookup`, etc. |
| Persistence | `tool_calls` table via `ToolCallRepository` |
| Evaluation | `ToolAccuracyEvaluator` via agent trace |
| Replay | `tool_call` events in session replay timeline |
| Dashboard | Tool call counts and activity feed |

## Configuration

```env
TOOLS_ENABLED=true
SUPPORT_TOOLS_ENABLED=true
KNOWLEDGE_BASE_PROVIDER=mock
TICKETING_PROVIDER=zendesk
ZENDESK_SUBDOMAIN=your-company
ZENDESK_EMAIL=agent@example.com
ZENDESK_API_TOKEN=replace-me

# Future Freshdesk integration
FRESHDESK_DOMAIN=
FRESHDESK_API_KEY=
```

## Onboarding template

The `customer-support-deflection` template references these tools in `tool_config.enabled_tools`. Agent config preset application stores tool metadata for operator visibility; runtime registration is automatic when support tools are enabled.

## Mock data

**Knowledge base:** password reset, billing/refunds, shipping/tracking, human handoff.

**Tickets:** `TKT-1001` (refund), `TKT-1002` (delivery) for `customer@example.com`.

New tickets created via `ticket_create` receive sequential IDs (`TKT-1003`, …).

## Zendesk behavior

- Authenticates with `{ZENDESK_EMAIL}/token` and `ZENDESK_API_TOKEN`.
- Creates private ticket comments containing the conversation summary, replay URL, and
  VoxForge session ID.
- Adds a deterministic `voxforge_session_*` tag and searches it before creation to
  suppress duplicate tickets for the same session.
- Maps Zendesk `new/open`, `pending/hold`, `solved`, and `closed` statuses to the
  VoxForge ticket model.
- Raises a sanitized provider error on Zendesk failures; API response bodies and tokens
  are not exposed.

## Testing

```bash
pytest tests/unit/test_support_tools.py -v
```
