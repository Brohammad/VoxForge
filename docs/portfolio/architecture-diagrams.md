# Architecture Diagrams

## System context

```mermaid
C4Context
  title VoxForge System Context
  Person(operator, "Operator", "Dashboard user")
  Person(enduser, "End User", "Voice caller")
  System(voxforge, "VoxForge", "Voice AI platform")
  System_Ext(providers, "Voice Providers", "STT, LLM, TTS")
  System_Ext(livekit, "LiveKit", "WebRTC media")
  Rel(enduser, voxforge, "Voice session")
  Rel(operator, voxforge, "Manage, replay")
  Rel(voxforge, providers, "API calls")
  Rel(voxforge, livekit, "Tokens, rooms")
```

## Voice session sequence

```mermaid
sequenceDiagram
  participant C as Client
  participant T as Transport
  participant V as VoicePipeline
  participant A as AgentOrchestrator
  participant E as Evaluation

  C->>T: Connect (WS / LiveKit)
  T->>V: Start session
  V->>V: STT
  V->>A: User utterance + context
  A->>A: Planner → Safety → Executor
  opt Tool requested and tools enabled
    A->>A: Execute tool → resume Executor
  end
  A->>A: Critic → Coordinator
  A-->>V: Final response + tool trace
  V->>V: TTS
  V->>E: Score turn
  V-->>C: Audio + transcript
```

## Deployment topology

```mermaid
flowchart TB
  subgraph Internet
    U[Users]
  end
  subgraph VPS
    N[NGINX :443]
    A[App :8000]
    P[(Postgres)]
    R[(Redis)]
    CB[Certbot]
    W[Workers]
    M[Prometheus/Grafana]
  end
  U --> N
  N --> A
  A --> P
  A --> R
  CB --> N
  A --> W
  A --> M
```

## Database ERD (core entities)

```mermaid
erDiagram
  Organization ||--o{ User : has
  Organization ||--o{ Session : owns
  Organization ||--o{ KnowledgeDocument : owns
  Session ||--o{ Message : contains
  Session ||--o{ Evaluation : scored
  Session ||--o{ HandoffRequest : may_escalate
  User ||--o{ ApiKey : has
```

## Component diagram

```mermaid
flowchart LR
  subgraph API
    Auth
    VoiceGW
    Knowledge
    Handoff
    Dashboard
  end
  subgraph Core
    Pipeline[VoicePipelineService]
    Orchestrator[AgentOrchestrator]
    Memory
    Tools[MCP Router]
  end
  VoiceGW --> Pipeline
  Pipeline --> Orchestrator
  Orchestrator --> Memory
  Orchestrator --> Tools
  Knowledge --> Orchestrator
```

Export PNGs for README: use [Mermaid Live Editor](https://mermaid.live) or `mmdc -i diagram.mmd -o diagram.png`.
