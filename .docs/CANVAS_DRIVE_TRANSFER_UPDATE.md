# Canvas LMS to Google Drive Transfer Update

> Date: 2026-05-01
> Branch: `feat/canvas-drive-transfer`
> Repository: `flowify-BE`

---

## 1. Summary

This update closes the main gap in the Canvas LMS to Google Drive flow.

Before this change, the Canvas input node mainly passed file metadata and download URLs.
The Google Drive output node then uploaded either:

- a real file only when `content` already existed, or
- a `*.metadata.json` file when only `url` existed.

As a result, the workflow looked connected on the canvas, but it did not actually copy the
Canvas file contents into Google Drive.

This patch changes that behavior so the Google Drive output node can download the file from
the Canvas URL first, then upload the downloaded bytes to Drive.

---

## 2. Scope

Included in this change:

1. Download real file bytes from `url` when Canvas returns file metadata without `content`
2. Upload those downloaded bytes to Google Drive
3. Add unit tests for URL-based upload behavior
4. Verify the behavior in an isolated local test stack

Not included in this change:

1. Shared Drive specific compatibility options such as `supportsAllDrives=true`
2. Canvas source payload shape changes
3. Spring OAuth flow redesign
4. Spring execution history persistence fix

---

## 3. Code Changes

### 3-1. `app/core/nodes/output_node.py`

The Google Drive sink path now receives the full `service_tokens` map instead of only the
Google Drive token.

This was necessary because the download step may need a token from a different integration:

- Canvas file URL -> `canvas_lms` token
- Google file URL -> `google_drive` token

Added helpers:

- `_get_single_file_bytes()`
- `_get_file_list_item_upload_data()`
- `_download_file_from_url()`
- `_resolve_download_token()`

Behavior after the change:

- `SINGLE_FILE`
  - if `content` exists, upload it as before
  - if `content` is missing and `url` exists, download from the URL first
- `FILE_LIST`
  - if an item has `content`, upload it as before
  - if an item has no `content` but has `url`, download the actual file first
  - only fall back to `*.metadata.json` when both `content` and `url` are missing

Download handling:

- client: `httpx.AsyncClient(follow_redirects=True)`
- `401` -> `OAUTH_TOKEN_INVALID`
- `403`, `404` -> `EXTERNAL_SERVICE_ERROR`
- other exceptions -> `EXTERNAL_API_ERROR`

### 3-2. `tests/test_output_node.py`

Added coverage for:

- URL-based file upload in `FILE_LIST`
- Canvas URL download in `SINGLE_FILE`
- Authorization header injection with `canvas_lms` token

### 3-3. `tests/conftest.py`

Added `canvas_lms` token to the shared `service_tokens` fixture so the new output-node
download path can be tested without special-case setup in each test.

---

## 4. Expected Runtime Behavior

### Before

- Canvas -> Google Drive often produced metadata uploads instead of real files
- `course_new_file` could produce an empty file upload when `content` was missing

### After

- Canvas URL is resolved into actual file bytes during the Google Drive output step
- those bytes are uploaded to Drive as the file content

Examples:

- `course_files` -> each `FILE_LIST.items[*].url` can now become a real uploaded file
- `course_new_file` -> `SINGLE_FILE.url` can now become a real uploaded file
- `term_all_files` -> each collected Canvas file URL can now be downloaded and uploaded

---

## 5. Test Results

Executed test commands:

```bash
pytest tests/test_output_node.py -q
pytest tests/test_canvas_lms.py -q
```

Expected outcome for this branch:

- `tests/test_output_node.py` passes
- `tests/test_canvas_lms.py` passes

Additional static checks should also be run before merge:

```bash
ruff check app/core/nodes/output_node.py tests/test_output_node.py tests/conftest.py
```

---

## 6. Isolated Local Test Environment

To avoid touching the user's existing local stack, a separate test stack was brought up.

### Active isolated stack

- FE: `http://localhost:5174`
- Spring: `http://localhost:8081`
- FastAPI: `http://localhost:8002`
- MongoDB: `localhost:27018`

### Goal

Keep the original local services untouched while validating only this branch's FastAPI changes.

### Notes

- The isolated FE talks to the isolated Spring server
- The isolated Spring server talks to the isolated FastAPI server
- Google OAuth redirect URIs for the isolated Spring environment must be registered for
  `http://localhost:8081/...`

---

## 7. Local Verification Findings

### 7-1. Canvas API direct checks

The provided Canvas token was tested directly against the Canvas API.

Observed results:

- `GET /api/v1/courses/3326` -> success
- `GET /api/v1/courses/3326/files` -> `403`
- `GET /api/v1/courses/3341/files` -> success

Interpretation:

- course `3326` itself is visible to the token
- but the token cannot access the course files endpoint for `3326`
- course `3341` is valid for real file-list testing

### 7-2. Workflow execution with course `3326`

When the workflow start node used:

- service: `canvas_lms`
- source mode: `course_files`
- target: `3326`

the execution failed at the start node because the Canvas files endpoint returned `403`.

Result:

- start node failed
- Google Drive node was skipped

### 7-3. Workflow execution with course `3341`

When the same workflow target was changed to `3341`:

- Canvas start node succeeded
- the output node reached Google Drive upload logic
- the execution then failed at Google Drive with `OAUTH_TOKEN_INVALID`

Root cause:

- the copied Google Drive token in the isolated Spring database was expired

This confirms that the Canvas download path introduced in this branch was actually reached.

---

## 8. Remaining Known Issues Outside This Patch

### 8-1. Expired Google Drive token in isolated test DB

The latest `3341` execution did not fail because of Canvas.
It failed because the isolated environment's `google_drive` token had expired.

This is an environment issue, not a failure of the new Canvas download logic.

### 8-2. UI stays at "execution starting"

Another separate issue was found during testing:

- FastAPI completes execution and calls Spring callback
- Spring responds with `EXECUTION_NOT_FOUND`
- the UI does not receive the final execution status update

Likely cause:

- Spring does not persist an execution record before calling FastAPI
- callback arrives later with an execution id Spring cannot resolve

This is outside the FastAPI patch scope and should be fixed in the Spring project.

---

## 9. Conclusion

This branch changes the Canvas LMS to Google Drive flow from metadata-only transfer to
real file-content transfer at the FastAPI layer.

The core behavior now works like this:

1. Canvas input provides file metadata and download URL
2. Google Drive output downloads the actual file bytes from that URL
3. Google Drive upload uses those bytes as the uploaded file content

The remaining blockers seen in local end-to-end testing were not caused by this patch itself:

- Canvas course permission issue for course `3326`
- expired Google Drive token in the isolated environment
- Spring execution callback persistence gap
