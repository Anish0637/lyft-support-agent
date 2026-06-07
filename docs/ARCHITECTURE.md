# Architecture

## System Overview

The Lyft Support Agent is a **hierarchical multi-agent system**: a single meta-agent router receives every customer message, applies a safety gate, classifies intent, then dispatches to the correct specialist sub-agent. Sub-agents are defined as JSON configs and loaded dynamically — no redeploy needed.

---

## Full Request Flow

![Request Flow](images/01_request_flow.png)

---

## Meta-Agent State Graph

![State Graph](images/02_state_graph.png)

---

## Component Breakdown

![Component Map](images/03_component_map.png)

---

## Agent Config Lifecycle

![Agent Lifecycle](images/04_agent_lifecycle.png)

---

## Safety Gate Logic

![Safety Gate](images/05_safety_gate.png)

---

## Data Flow for a Charge Dispute

![Charge Dispute](images/06_charge_dispute.png)

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
