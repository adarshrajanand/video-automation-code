# AI Video Automation Pipeline — Agent and Model Use

**Status:** Canonical guidance for agentifying bounded capabilities

**Purpose:** Define where ordinary code, structured model calls, bounded loops, agents, workers, and services belong.

## 1. The important distinctions

### Structured LLM task

One bounded request with typed input and typed output.

```text
input artifact(s) → prompt/model → validated structured output
```

### Python-controlled LLM loop

Ordinary Python controls repeated generation, validation, evaluation, and revision.

```text
generate → validate → evaluate → revise if policy allows → stop
```

### Bounded agent

A model can choose among approved tools or next actions inside one capability, subject to time, tool, token, spend, and iteration limits.

### Worker

A process/runtime boundary. It may run deterministic code, an LLM task, or an agent. A worker is not automatically an agent.

### Service

A separately deployed network boundary used for independent scaling, hardware, security, or ownership. It is not required merely because a component is called an agent.

## 2. Primary rule

Keep durable workflow control deterministic. An agent may recommend or produce a bounded result, but it must not:

- change workflow transitions directly;
- bypass a quality gate;
- exceed retry/budget policy;
- replace an artifact in place;
- publish without approval;
- access arbitrary filesystem paths or network destinations;
- invent source references;
- silently change domain/channel policy.

## 3. Initial classification

| Capability | Initial implementation | Agent needed initially? |
|---|---|---|
| Topic discovery from configured sources | ingestion + structured extraction + ranking | No |
| Idea generation | structured model call + Python constraints | No |
| Idea selection | ranking/scoring + stronger shortlist comparison | No |
| Research | source ingestion + claim/evidence extraction | No; bounded tools later |
| Script planning | structured model call | No |
| Script generation | structured model call + revision loop | No |
| Visual planning | structured model call | No |
| Asset search/reranking | APIs/CV + structured relevance check | No; tool loop later |
| Semantic quality | evaluator contract with evidence | No; may use tool-using evaluator later |
| TTS/ASR | adapters and signal tools | No |
| Composition/rendering | deterministic code and media tools | No |
| Targeted repair | gate policy + bounded revision capability | No initially |
| Adaptive research | model chooses searches/tools | Possible later |
| Complex revision investigation | bounded tool-using loop | Possible later |

## 4. Stable integration boundary

Stages depend on the generic capability protocol, not model implementations. A domain-specific convenience interface may exist inside a capability adapter, but it must map to the same persisted request/result records:

```python
class Capability(Protocol):
    def execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
    ) -> CapabilityResult:
        ...
```

Implementations may include:

- `DirectStructuredScriptGenerator`;
- `PythonRevisionLoopScriptGenerator`;
- `ToolUsingResearchAgent`;
- `FrameworkBackedScriptAgent`;
- `RemoteScriptServiceClient`.

The stage contract must not change when the implementation changes.

`CapabilityRequest`, `CapabilityResult`, and `ExecutionContext` are defined in [Contracts and Data Model](AI_Video_Pipeline_Contracts_and_Data_Model.md). A script-specific adapter can expose `generate(ScriptRequest) -> ScriptResult` internally, but the stage executor wraps it in the generic capability lifecycle.

## 5. In-process Python option

Recommended for initial content operations:

```text
Workflow Engine
  → Stage
    → Capability wrapper
      → Router
        → Provider adapter/model
```

Use this when:

- the task is bounded;
- debugging simplicity matters;
- no separate hardware is required;
- one process can tolerate the wait;
- the operation has a clear input/output contract.

Persist the capability execution and outputs through the normal execution path. The capability must not write workflow state directly.

## 6. Worker-process option

Move the same implementation into a worker when:

- local GPU inference is needed;
- render jobs are long-running;
- concurrency needs isolation;
- memory/resource limits differ;
- a worker can be stopped/restarted safely.

The worker receives a job ID and artifact references, not an in-memory object graph. The first process-worker implementation may use a local queue or subprocess, but production semantics require durable jobs, leases, idempotency, and recovery.

## 7. Service option

Use a service only when there is a concrete reason:

- independent deployment;
- independent scaling;
- separate GPU machine;
- multiple pipeline consumers;
- stronger security/isolation boundary;
- separately owned dependency lifecycle.

The service API should expose asynchronous submit/status/result for long jobs, not assume a long synchronous HTTP request is durable.

## 8. Bounded agent contract

If a bounded agent is introduced, its contract must declare:

```yaml
agent:
  id: research_agent_v1
  allowed_tools:
    - source_search
    - source_fetch
    - evidence_extract
  max_iterations: 5
  max_tool_calls: 12
  timeout_seconds: 180
  max_cost_minor: 50
  output_schema: research_result.v1
  stop_conditions:
    - required_claims_supported
    - unresolved_questions_returned
```

The agent returns a structured result and trace summary. It does not decide the outer workflow transition.

## 9. Tool security

Agent tools must be:

- explicitly allowlisted;
- schema-validated;
- time-limited;
- output-size limited;
- data-classification aware;
- protected against SSRF and arbitrary filesystem access;
- isolated from credentials not required for the task;
- observable without persisting sensitive raw content by default.

Retrieved web content is untrusted input. It must not be allowed to rewrite system policy or tool permissions through prompt injection.

## 10. Prompt and model artifacts

Persist:

- prompt/template ID and version;
- model/provider/version;
- structured output schema version;
- relevant input artifact IDs/hashes;
- tool definitions/version;
- generation settings;
- response usage/cost;
- normalized result and validation errors.

Store raw responses only under an explicit retention/data policy.

## 11. Model call retry policy

Separate:

- transport retry;
- provider retry;
- malformed-output repair request;
- quality-driven regeneration;
- human escalation.

Do not repeat a low-quality generation unchanged and call it recovery. A quality repair must include structured feedback, permitted scope, attempt number, and a new artifact version.

## 12. Initial implementation pattern

For script generation:

```text
1. load approved idea, evidence, profile, and target duration
2. create CapabilityRequest
3. router selects one eligible implementation
4. call structured generator
5. validate schema
6. run deterministic claim/reference checks
7. run narrow semantic checks
8. accept, repair, or escalate according to gate policy
9. persist artifact and evidence
```

The same pattern applies to visual plans, research extraction, and evaluators.

## 13. When to evaluate an agent framework

Only run a framework experiment if the task demonstrates:

- dynamic tool selection adds quality;
- internal branching is difficult to maintain in ordinary Python;
- internal state must be resumed independently;
- tool traces/debugging are insufficient;
- framework overhead is justified by measured value.

Benchmark against the plain Python baseline using the same examples and budgets. Compare quality, false passes, latency, cost, failure/recovery behavior, and observability—not framework features alone.

## 14. Agent test checklist

- [ ] output validates against a versioned schema;
- [ ] tool calls are allowlisted and bounded;
- [ ] budget and timeout are enforced outside the model’s discretion;
- [ ] agent cannot mutate workflow state;
- [ ] agent cannot overwrite artifacts;
- [ ] malformed output is recoverable;
- [ ] external side effects have idempotency/reconciliation;
- [ ] prompts/model/tools are versioned;
- [ ] deterministic validators run before semantic acceptance;
- [ ] agent can be replaced by a non-agent implementation behind the same capability.
