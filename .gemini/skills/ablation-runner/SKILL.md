---
name: ablation-runner
description: Managing ablation experiments for components C1-C6 and enforcing VCL flag discipline.
---
# Instructions
- **Ablation-First Logic:** Any new function or class must be wrapped in a `@gated_by(VCLFlag.X)` decorator.
- **Flag Consistency:** Ensure that the flag provided in the decorator matches the component's role.
- **Runtime Enforcement:** Never suggest code that bypasses the `set_current_manifest(manifest)` requirement before invoking gated components.
- **Validation:** Always verify that adding a new variant configuration results in a unique hash.
