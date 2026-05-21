# Runtime Content Branch Loop Fix Design

## 1. Problem Summary

The workflow editor can create this graph:

```text
source -> loop -> classify_by_content -> output A / output B
```

However, runtime delivery currently does not preserve branch-specific payloads after content classification, especially when the branch node is the loop body.

## 2. Current Runtime Flow

- Spring translates `CONDITION_BRANCH` nodes to FastAPI `runtime_type = "if_else"`.
- Spring preserves edge `label`, `sourceHandle`, and `targetHandle`.
- FastAPI routes file-type branch outputs through `branch_outputs`.
- FastAPI loop execution runs the body node separately, stores one aggregate body output, marks the body node as handled, then continues.
- Output nodes receive input through `_resolve_input_data`, preferring edge-specific payloads when present.

## 3. Wrong Points

- `classify_by_content` exists in mapping rules but Spring `BranchRuntimeConfigResolver` only creates runtime branch config for `branch_by_file_type`.
- FastAPI `IfElseNodeStrategy` only creates multi-branch `branch_outputs` for `FILE_LIST` file-type branches.
- When a loop body node is an `if_else` node, the main `if_else` routing block is skipped because the body node is added to `handled_nodes`.
- The loop aggregate currently collapses repeated branch results into one payload, so downstream outputs can receive the same full aggregate instead of branch-specific data.

## 4. Fix Direction

Keep the existing workflow schema and runtime payload shape. Add missing runtime config and branch-output generation only.

- Add a content branch mode for `classify_by_content`.
- Generate `branch_outputs` keyed by branch keys that match outgoing edge labels/source handles.
- Reuse the existing `_build_multi_branch_edge_outputs` edge routing helper.
- Preserve existing file-type branch, boolean branch, loop, and output behavior.

## 5. Spring Design

Update `BranchRuntimeConfigResolver`:

- Keep `branch_by_file_type` behavior unchanged.
- Detect `classify_by_content`.
- Resolve selected branch keys from `choiceSelections`, `branchKeys`, `branchTypes`, or related existing config fields.
- Emit runtime config like:

```json
{
  "branch_type": "content_classification",
  "branch_rules": [
    { "key": "important_ref", "label": "important_ref", "matcher": { "type": "content_classification", "keywords": [] } }
  ],
  "fallback_branch": { "key": "other", "label": "Other" }
}
```

The exact matcher remains deterministic and runtime-safe. FastAPI must not depend on output service names.

## 6. FastAPI Design

Update `IfElseNodeStrategy`:

- Add content classification branch detection.
- Accept `TEXT`, `API_RESPONSE`, and item-like payloads that can be represented as text.
- Select a branch key from existing payload metadata when available, for example `branch_key`, `classification`, `category`, or `label`.
- Fall back to deterministic keyword matching from branch rules.
- If no rule matches, use fallback branch.
- Return `branch_outputs` with list payloads so existing branch routing can decide active/inactive targets.

Update `WorkflowExecutor`:

- When loop body aggregate output contains `branch_outputs`, immediately build edge-specific outputs for the loop body node before marking it handled.
- Reuse `_build_multi_branch_edge_outputs`.
- Skip inactive branch targets using `_resolve_multi_branch_skipped_nodes`.
- Keep non-branch loop aggregation unchanged.

## 7. Test Design

Spring:

- `classify_by_content` creates `content_classification` branch runtime config.
- Existing `branch_by_file_type` tests stay unchanged.
- `WorkflowTranslator` includes content branch runtime config.

FastAPI:

- Content branch strategy creates `branch_outputs` for TEXT input.
- File-type branch tests continue to pass.
- Loop body content branch routes each branch to the matching downstream edge.
- Non-branch loop aggregate tests continue to pass.
- Output tests continue to pass without external API calls.

## 8. Regression Risks

- Empty branches must still be skipped without skipping shared merge nodes.
- Branch edge keys must remain `label || sourceHandle`.
- Loop body nodes must not be re-executed in topological order.
- Output node accepted input types must not be changed.

## 9. Verification Commands

FastAPI:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_executor.py tests/test_logic_node.py tests/test_output_node.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Spring:

```powershell
.\gradlew.bat test --no-daemon --console=plain
```

## 10. Stop Conditions

- Existing file-type branch tests fail.
- Existing loop tests fail.
- Existing output tests fail.
- Content branch does not produce `branch_outputs`.
- Loop body branch outputs are not routed to edge-specific payloads.
- The fix requires frontend graph changes.
- Secrets or environment files need modification.
