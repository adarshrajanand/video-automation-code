# Archived Video Pipeline Documentation

**Status:** Historical / non-normative

These documents preserve earlier architecture, contract, infrastructure, event,
routing, and deployment discussions. They are retained for traceability and
context only. They must not be used as implementation authorities.

Use [`../README.md`](../README.md) for the current reading order and the
canonical documents. If an archived example conflicts with a canonical document
or registry, follow the canonical replacement and record a migration or decision
change where necessary.

## Archived documents

| Document | What it contains | Canonical replacement |
|---|---|---|
| [`AI_Video_Pipeline_Architecture_Long_Term_v5-1.md`](AI_Video_Pipeline_Architecture_Long_Term_v5-1.md) | Earlier long-term architecture, workflow topology, artifact graph, persistence, and implementation order | [`../AI_Video_Pipeline_Architecture.md`](../AI_Video_Pipeline_Architecture.md) |
| [`AI_Video_Pipeline_First_Class_Contracts_v2-1.md`](AI_Video_Pipeline_First_Class_Contracts_v2-1.md) | Earlier typed contract proposals for workflow, execution, routing, artifacts, quality, and content | [`../AI_Video_Pipeline_Contracts_and_Data_Model.md`](../AI_Video_Pipeline_Contracts_and_Data_Model.md) |
| [`AI_Video_Pipeline_End_to_End_Infrastructure_Blueprint-1.md`](AI_Video_Pipeline_End_to_End_Infrastructure_Blueprint-1.md) | Earlier end-state infrastructure, technology, deployment, and integration blueprint | [`../AI_Video_Pipeline_End_to_End_Implementation_Plan.md`](../AI_Video_Pipeline_End_to_End_Implementation_Plan.md) |
| [`AI_Video_Pipeline_Event_Driven_Compute_and_Routing_Addendum.md`](AI_Video_Pipeline_Event_Driven_Compute_and_Routing_Addendum.md) | Earlier event-driven execution, compute placement, provider routing, QC, and budget discussion | [`../AI_Video_Pipeline_Workflow_and_Event_Execution.md`](../AI_Video_Pipeline_Workflow_and_Event_Execution.md) and [`../AI_Video_Pipeline_Routing_and_Providers.md`](../AI_Video_Pipeline_Routing_and_Providers.md) |
| [`AI_Video_Pipeline_Batch_Execution_Scheduling_Deployment_Followup.md`](AI_Video_Pipeline_Batch_Execution_Scheduling_Deployment_Followup.md) | Earlier local scheduling, Docker, worker, transfer, and deployment options | [`../AI_Video_Pipeline_Workflow_and_Event_Execution.md`](../AI_Video_Pipeline_Workflow_and_Event_Execution.md) and [`../AI_Video_Pipeline_End_to_End_Implementation_Plan.md`](../AI_Video_Pipeline_End_to_End_Implementation_Plan.md) |

The design discussion log remains in the canonical documentation area because it
is an active rationale and change record. Accepted decisions belong in the
[Decision Log](../AI_Video_Pipeline_Decisions.md); the discussion log explains
why those decisions changed and what future changes must update.
