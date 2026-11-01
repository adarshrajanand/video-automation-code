# Runtime workflow definitions

`explainer_validation_v1.yaml` is the versioned runtime copy of the canonical
fast-validation workflow in
`docs/kb/docs/registries/fast_workflow.yaml` (source repository:
`video-automation-code/docs`).

The documentation repository remains canonical. This copy exists so the runtime
loader and readiness tests have a stable local definition without reading the
separate docs checkout. When the canonical registry changes, update this file in
the same code change and keep the two byte-identical with:

```bash
diff -u docs/kb/docs/registries/fast_workflow.yaml \
  workflows/explainer_validation_v1.yaml
```

The file is parsed with `yaml.safe_load` and validated only through
`pipeline.contracts.WorkflowDefinition`. Do not add a second schema here.
