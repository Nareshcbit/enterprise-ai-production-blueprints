# Project 3: Production Agentic Incident Responder with Human-in-the-Loop & State Persistence

## The Enterprise Problem It Solves

Pure chat models cannot take actions safely. Autonomous agent loops risk executing destructive commands or hallucinating API arguments, causing enterprise security teams to block them.

```
                         [ CloudWatch Alarm / PagerDuty ]
                                        │
                                        ▼
                        [ Agent State Graph (LangGraph) ]
                                        │
                         ┌──────────────┴──────────────┐
                         ▼                             ▼
                 [ Read Diagnostics ]          [ Draft Remediation ]
                 - Describe EC2 instances      - Query AWS Knowledge Base
                 - Pull VPC Flow Logs          - Formulate Fix Plan
                 - Query CloudWatch metrics            │
                                                       ▼
                                            [ Intercept / Review Gate ]
                                            - Persists state in DynamoDB
                                            - Sends Slack interactive card
                                                       │
                                        ┌──────────────┴──────────────┐
                                        ▼ (Approve)                   ▼ (Reject)
                               [ Execute Remediation ]        [ Abort & Log Ticket ]
                               (e.g., scale ASG, restart pod)
```

## What You Build (The Deliverables)

### Deterministic State Machine (LangGraph / Bedrock AgentCore)
- Implement an agentic graph that receives an infrastructure incident alert (e.g., "High latency on ALB target group").
- Define strict Pydantic schemas for AWS API diagnostic tools (`get_cloudwatch_metrics`, `describe_pod_status`, `check_route_tables`).

### Strict Schema Reflection & Guardrails
- The agent uses structured tool-calling. If the model outputs malformed JSON or an invalid argument, the runtime feeds the Pydantic validation error back into the model to self-correct.

### State Persistence & Human-in-the-Loop (HITL) Checkpointing
- Persist agent conversation and execution state in Amazon DynamoDB.
- If the agent determines that a state-changing action is required (e.g., rebooting a database, terminating an EC2 instance, or updating a security group), it halts execution, enters a `WAIT_FOR_HUMAN` state, and posts an interactive action card to a Slack channel via webhook.
- Once a human clicks "Approve", the agent resumes from the exact checkpoint in DynamoDB and executes the change.
