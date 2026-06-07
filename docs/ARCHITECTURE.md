# Architecture

## System Overview

The Lyft Support Agent is a **hierarchical multi-agent system**: a single meta-agent router receives every customer message, applies a safety gate, classifies intent, then dispatches to the correct specialist sub-agent. Sub-agents are defined as JSON configs and loaded dynamically — no redeploy needed.

---

## Full Request Flow

```mermaid
sequenceDiagram
    participant U as User (Browser)
    participant API as FastAPI /api/chat
    participant MG as Meta-Agent Graph
    participant SG as Safety Gate
    participant CL as Classifier
    participant SA as Sub-Agent
    participant T  as Mock Tools

    U->>API: POST /api/chat {message, user_type, conversation_id}
    API->>MG: run_support_agent(message, user_type, conversation_id)

    MG->>SG: safety node (gpt-4o-mini)
    alt blocked
        SG-->>MG: safety_passed=false
        MG-->>API: "I can't help with that."
    else passed
        SG-->>MG: safety_passed=true
        MG->>CL: classify node → intent label
        CL-->>MG: intent (e.g. "charge_review")
        MG->>SA: dispatch to matching sub-agent node
        SA->>T: tool calls (get_trip_info, process_refund…)
        T-->>SA: tool results
        SA-->>MG: final_response + tool_calls
        MG-->>API: {response, intent, agent_name, tool_calls, safety_passed}
    end

    API-->>U: ChatResponse (JSON)
    U->>U: Render bubble + meta badges
```

---

## Meta-Agent State Graph

```mermaid
flowchart TD
    START([__start__]) --> safety

    safety -->|blocked| END([__end__])
    safety -->|passed| classify

    classify -->|rider_intent|    rider_intent
    classify -->|driver_intent|   driver_intent
    classify -->|earnings|        earnings
    classify -->|damage_claim|    damage_claim
    classify -->|charge_review|   charge_review
    classify -->|driver_tax|      driver_tax
    classify -->|rider_general|   rider_general

    rider_intent   --> END
    driver_intent  --> END
    earnings       --> END
    damage_claim   --> END
    charge_review  --> END
    driver_tax     --> END
    rider_general  --> END

    style START fill:#FF00BF,color:#fff
    style END   fill:#1a1a2e,color:#fff
    style safety fill:#ef4444,color:#fff
    style classify fill:#3b82f6,color:#fff
```

---

## Component Breakdown

```mermaid
flowchart LR
    subgraph Browser
        CUI[Chat UI\nui/chat/index.html]
        BUI[Builder UI\nui/builder/index.html]
    end

    subgraph FastAPI["FastAPI  api/server.py"]
        CR[/api/chat\nchat.py]
        AR[/api/agents\nagents.py]
        HR[/health\nhealth.py]
    end

    subgraph LangGraph["LangGraph  agent/"]
        MG[meta_agent.py\nStateGraph]
        SG[safety.py\ngpt-4o-mini]
        CA[configurable_agent.py\nReAct agent]
    end

    subgraph Config["Config  config/"]
        CL[loader.py]
        CF[agents/*.json]
    end

    subgraph Tools["Tools  tools/"]
        ST[support_tools.py\n10 mock @tool functions]
    end

    subgraph CI["CI  ci/"]
        PL[prompt_linter.py]
    end

    CUI -->|fetch POST /api/chat| CR
    BUI -->|fetch GET/POST/PUT /api/agents| AR
    BUI -->|fetch POST /api/agents/lint| AR

    CR --> MG
    MG --> SG
    MG --> CA
    CA --> ST

    AR --> CL
    CL --> CF
    AR --> PL
```

---

## Agent Config Lifecycle

```mermaid
flowchart LR
    A[Domain Expert\nopens Builder UI] -->|fills form| B[POST /api/agents]
    B --> C[Saved to\nconfig/agents/intent.json]
    C --> D[loader.py reads JSON\non next request]
    D --> E[ConfigurableAgent\n= ReAct agent with prompt + tools]
    E --> F[Registered as node\nin meta StateGraph]
    F --> G[Live for all\nnew conversations]
```

---

## Safety Gate Logic

```mermaid
flowchart TD
    M[Incoming message] --> LLM[gpt-4o-mini\nsafety check]
    LLM -->|safe| PASS[safety_passed = true\ncontinue to classifier]
    LLM -->|unsafe| BLOCK[safety_passed = false\nreturn policy message]
    LLM -->|LLM error| FAILOPEN[fail-open\nsafety_passed = true]

    style BLOCK fill:#ef4444,color:#fff
    style PASS  fill:#22c55e,color:#fff
    style FAILOPEN fill:#f59e0b,color:#000
```

---

## Data Flow for a Charge Dispute

```mermaid
sequenceDiagram
    participant R  as Rider
    participant CL as Classifier
    participant CR as charge_review agent
    participant T1 as get_trip_info
    participant T2 as process_refund

    R->>CL: "I was overcharged on trip_003"
    CL->>CR: intent=charge_review
    CR->>T1: get_trip_info("trip_003")
    T1-->>CR: {amount:35.00, surge:13.00, base_fare:22.00}
    CR->>T2: process_refund(rider_001, trip_003, 13.00, "surge_overcharge")
    T2-->>CR: {refund_id:"REF-ABC", status:"approved", processing_days:3}
    CR-->>R: "I've processed a $13.00 refund for the surge charge…"
```

---

## Deployment Architecture (Production Target)

```mermaid
flowchart TD
    subgraph Edge
        CF[CloudFront CDN]
    end

    subgraph App["App Layer (ECS / EC2)"]
        UV[uvicorn workers]
        UV2[uvicorn workers]
    end

    subgraph Storage
        S3[S3\nagent configs]
        DDB[DynamoDB\nconversation history]
        SM[Secrets Manager\nAPI keys]
    end

    subgraph AI
        OAI[OpenAI API\ngpt-4o]
        LS[LangSmith\ntracing + eval]
    end

    CF --> UV
    CF --> UV2
    UV  --> S3
    UV  --> DDB
    UV  --> SM
    UV  --> OAI
    UV  --> LS
```

> **Current state**: single uvicorn process, in-memory conversation store, local JSON configs. Replace with the services shown above for production.
