# SailPoint MCP Server

An MCP (Model Context Protocol) server that gives an AI assistant real access to
your SailPoint Identity Security Cloud tenant, via the
[SailPoint Python SDK](https://github.com/sailpoint-oss/python-sdk).

Authentication, token refresh, error handling, and tool registration are already
done. Your job for the Hackathon is to write tools.

Ships with one working tool, `search_identities`, as a reference implementation.

```
You:  Tell me more about the identity Tyler Mairose.

      → search_identities(query="Tyler Mairose")

Claude: Tyler Mairose is a Developer Tools Lead in Developer Relations,
        reporting to Ada Lovelace. Active lifecycle state, accounts on
        Active Directory and Workday, 42 access items total.
```

---

## Quick start

### 1. Get SailPoint credentials

In Identity Security Cloud: **Admin → Global Settings → Personal Access Tokens →
New Token**. Copy the client ID and secret — the secret is shown only once.

### 2. Set up the project

```bash
git clone <this-repo> && cd python-mcp-server

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # then fill in your three values
chmod 600 .env
```

<details>
<summary>Using <code>uv</code> instead</summary>

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```
</details>

Your `.env`:

```bash
SAIL_BASE_URL=https://your-tenant.api.identitynow.com
SAIL_CLIENT_ID=...
SAIL_CLIENT_SECRET=...
```

These are the variable names the SailPoint SDK reads natively, so the same `.env`
works for any other SDK script you write.

The server loads `.env` from its own project folder, so it works no matter which
directory the MCP client launches it from. Keep the file private: it is
gitignored, and `chmod 600 .env` makes it readable only by you. Variables set in
your shell or in an MCP client's `env` block take precedence over `.env`.

### 3. Verify credentials before touching an MCP client

```bash
python scripts/check_auth.py "<Search String>"
```

You should see three `OK` lines and a JSON identity record. If this fails, the
problem is your credentials or tenant URL — fix it here, where the error messages
are readable.

### 4. Connect it to your assistant

**Claude Code** — from the project directory:

```bash
claude mcp add sailpoint -- /full/path/to/python-mcp-server/.venv/bin/python -m sailpoint_mcp
```

**Claude Desktop / Cursor / other clients** — add to the MCP config file
(`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "sailpoint": {
      "command": "/full/path/to/python-mcp-server/.venv/bin/python",
      "args": ["-m", "sailpoint_mcp"]
    }
  }
}
```

Use absolute paths — the client does not run from your project directory. No
`env` block is needed; the server reads your `.env`.

Restart the client, then ask: *"Tell me more about the identity `someone at your
company`."*

---

## Adding your own tool

Three steps, no wiring:

```bash
cp src/sailpoint_mcp/tools/_template.py src/sailpoint_mcp/tools/list_sources.py
# edit it
# restart your MCP client
```

Every module in [src/sailpoint_mcp/tools/](src/sailpoint_mcp/tools/) with a
`register(mcp)` function is discovered and loaded at startup. There is no central
registry to update, so two people can add tools without merge conflicts. Files
starting with `_` are ignored.

A minimal tool:

```python
from mcp.server import MCPServer
from sailpoint import SourcesApi

from ..client import call_sailpoint, describe_api_error


def register(mcp: MCPServer) -> None:
    @mcp.tool(name="list_sources")
    def list_sources(limit: int = 25) -> dict:
        """List the identity sources configured in the tenant.

        Args:
            limit: Maximum sources to return. Default 25.
        """
        try:
            sources = call_sailpoint(
                lambda client: SourcesApi(client).list_sources_v3(limit=limit)
            )
        except Exception as exc:
            return {"error": describe_api_error(exc)}

        return {
            "sources": [
                {"id": s.id, "name": s.name, "type": s.type} for s in sources
            ]
        }
```

> **Note:** this project targets the MCP Python SDK 2.x, where the server class
> is `MCPServer` (`from mcp.server import MCPServer`). Examples you find online
> may still use the 1.x name `FastMCP` from `mcp.server.fastmcp`; the decorator
> and `run()` API are otherwise the same.

### Four rules that make tools work well

1. **Write the docstring for the model.** It is the only thing the assistant sees
   when deciding whether to call your tool. Say *when* it applies, and give a
   concrete example for each argument. A vague docstring means a tool that never
   gets called — or gets called with garbage.
2. **Always go through `call_sailpoint()`.** It hands you an authenticated
   `ApiClient` and retries once if the token was rejected. Do not construct
   `Configuration` yourself; that triggers a fresh token request every call.
3. **Return small, flat dicts.** One raw ISC identity is kilobytes of JSON. Ten
   of them will crowd out everything else in the model's context. Project the
   fields you need — see `RESULT_FIELDS` and `summarize_identity()` in
   [search_identities.py](src/sailpoint_mcp/tools/search_identities.py).
4. **Return errors as data, not exceptions.** `{"error": describe_api_error(exc)}`
   gives the assistant a sentence it can act on and relay to the user. An
   uncaught exception gives it a stack trace.

### Finding the right SDK call

```python
from sailpoint import SourcesApi
print([m for m in dir(SourcesApi) if not m.startswith("_")])
```

- API classes are exported flat: `from sailpoint import AccountsApi, SearchApi, ...`
- Models live under their partition: `from sailpoint.search.models.search import Search`
- Method names carry the API version: `list_sources_v3`, `search_post_v1`
- Reference: <https://developer.sailpoint.com/docs/api/>
- Python SDK docs: <https://developer.sailpoint.com/docs/tools/sdk/python/>

---

## Project layout

```
src/sailpoint_mcp/
├── server.py        # entry point: stdio transport, startup validation
├── config.py        # loads + validates SAIL_* credentials
├── client.py        # authenticated ApiClient, cached, retries on 401
└── tools/
    ├── __init__.py           # auto-discovers every tool module
    ├── search_identities.py  # the reference tool -- read this first
    └── _template.py          # copy this to start your own
scripts/check_auth.py         # credential + connectivity smoke test
tests/                        # pytest, no tenant required
```

## `search_identities`

| Argument | Type | Notes |
| --- | --- | --- |
| `query` | str | A plain name (`Tyler Mairose`) is quoted into a phrase match. Elasticsearch query-string syntax is passed through untouched. `*` matches everyone. |
| `limit` | int | 1–250, default 10. |
| `offset` | int | Skip this many matches, for paging. Default 0. |
| `sort` | list[str] | Fields to sort by, `-` prefix for descending. Defaults to `["-accessCount", "id"]`. |
| `attributes` | list[str] | Restrict returned fields, e.g. `["id", "displayName", "email"]`. Replaces the default projection. |
| `include_nested` | bool | Include each identity's `access` / `accounts` / `apps` arrays. Default false. |
| `count` | bool | Also return `total_count`, matches ignoring `limit`/`offset`. Costs latency. |

By default each hit is flattened by `summarize_identity()`. Passing `attributes`
or `include_nested` means the caller has asked for a shape the summarizer would
discard, so the raw documents are returned instead (minus the `_type` / `_index`
search plumbing).

Note that the SDK's `Search` model defaults `includeNested` to **true** — the
tool sets it explicitly, so nested objects only appear when asked for.

Full query syntax: <https://developer.sailpoint.com/docs/api/v3/search-post>

## Tests

```bash
pytest
```

These cover the pure logic (query building, response shaping, tool registration)
and need no tenant or credentials.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `Missing SailPoint credentials` | No `.env` and no exported vars. See step 2. |
| 401 on every call | Bad client ID/secret, or the PAT was revoked. Re-run `scripts/check_auth.py`. |
| 403 on a specific API | Your PAT's identity lacks the user level or scope that API needs. |
| Server missing in the client | Path in the MCP config isn't absolute, or the client wasn't restarted. |
| Tool not appearing | Module name starts with `_`, or it has no `register(mcp)`. Check stderr. |
| Garbled protocol / client won't connect | Something printed to **stdout**. Logs must go to stderr; use `log.info`, never `print`. |

Verbose logging: `SAILPOINT_MCP_LOG_LEVEL=DEBUG`.
