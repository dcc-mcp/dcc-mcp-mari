# Mari Install SOP v1

This is the adapter-owned, agent-first installation contract for
`dcc-mcp-mari`. The canonical raw document is
<https://raw.githubusercontent.com/dcc-mcp/dcc-mcp-mari/main/install.md>.

## Requirements

- Foundry Mari 5.0 or newer.
- An external Python 3.9 or newer with `dcc-mcp-core>=0.19.91` and the exact
  requested `dcc-mcp-mari` wheel installed. Mari's embedded Python does not
  host the Core runtime.
- Permission to write Mari's per-user `Scripts` directory.
- Close Mari before install, repair, upgrade, or uninstall so loaded files can
  be replaced safely.

The lifecycle commands accept the same automation flags: `--json`, `--yes`,
`--dry-run`, `--dcc-path`, and `--python`. Use `--script-dir` only when Mari's
user script directory is customized. Mutating commands require `--yes`.

## Supported versions

| Platform | Mari executable example | Default per-user scripts directory |
| --- | --- | --- |
| Windows | `C:\Program Files\Foundry\Mari7.5v2\Bundle\bin\Mari7.5v2.exe` | `%USERPROFILE%\Documents\Mari\Scripts` |
| macOS | `/Applications/Mari7.5v2.app/Contents/MacOS/Mari` | `~/Mari/Scripts` |
| Linux | `/opt/Foundry/Mari7.5v2/bin/Mari7.5v2` | `~/Mari/Scripts` |

Automatic detection checks `PATH` and conventional Foundry locations. Pass an
explicit `--dcc-path` when more than one Mari release is installed.

## Agent quick path

Install the wheel into the selected external Python first:

```shell
python -m pip install "dcc-mcp-mari==0.3.0"  # x-release-please-version
python -m dcc_mcp_mari.server install --dcc-path <mari-executable> --python <python> --dry-run --json
python -m dcc_mcp_mari.server install --dcc-path <mari-executable> --python <python> --yes --json
python -m dcc_mcp_mari.server status --dcc-path <mari-executable> --python <python> --json
```

`dcc-mcp-mari install`, `dcc-mcp-mari status`, and the other console commands
are equivalent. JSON responses use schema `1.0`, contain `operation`, `status`,
`exit_code`, `verify`, `detected`, and machine-executable `next_steps`, and do
not require parsing human prose.

Stable process exit codes are:

| Code | Meaning |
| --- | --- |
| `0` | Success, an idempotent no-op, or a valid plan |
| `10` | Preflight, version, receipt, confirmation, or partial-install failure |
| `20` | Pinned artifact acquisition or integrity failure |
| `30` | Installation or filesystem failure |
| `40` | Installed but verification or live readiness failed |
| `50` | Loaded or locked files require Mari to close or restart |

## Manual path

For a custom Mari profile, name both the host executable and scripts directory:

```shell
dcc-mcp-mari install --dcc-path <mari-executable> --python <python> --script-dir <mari-scripts> --dry-run --json
dcc-mcp-mari install --dcc-path <mari-executable> --python <python> --script-dir <mari-scripts> --yes --json
```

The installer stages the pure-Python host plugin before promotion, records
SHA-256 digests in `<mari-scripts>/.dcc-mcp/receipts/mari.json`, and retains a
receipt-owned backup of files that existed before this adapter. It never
installs Core into Mari's embedded Python and does not create another host
thread, job, or event pump.

## Verify

Restart Mari after installation, then run:

```shell
dcc-mcp-mari verify --dcc-path <mari-executable> --python <python> --json
```

Verification checks the receipt and managed-file digests, reads bounded
bootstrap error records, waits for the Core sidecar readiness contract, and
executes the adapter's bounded `ping` tool. Exit `0` with
`verify.directly_usable=true` is the machine-readable usable state. Without a
running Mari host, exit `40` is expected; installation tests alone are not a
live-host verification.

## Upgrade

Install the exact target wheel into the selected Python, close Mari, preview,
then promote it transactionally:

```shell
python -m pip install --upgrade "dcc-mcp-mari==<version>"
dcc-mcp-mari upgrade --dcc-path <mari-executable> --python <python> --dry-run --json
dcc-mcp-mari upgrade --dcc-path <mari-executable> --python <python> --yes --json
```

Use `--repair` with `install` or `upgrade` only after `status` reports a partial
receipt-owned installation. A failed replacement restores the prior files and
receipt.

## Uninstall

Close Mari, preview the receipt-owned removal, then uninstall:

```shell
dcc-mcp-mari uninstall --dcc-path <mari-executable> --python <python> --dry-run --json
dcc-mcp-mari uninstall --dcc-path <mari-executable> --python <python> --yes --json
```

Uninstall restores files recorded as pre-existing by the receipt. It does not
remove unrelated user scripts. An unsafe, missing, or altered receipt fails
closed instead of guessing ownership.

## Troubleshooting

- Exit `10`, stage `host`: pass the exact Mari executable with `--dcc-path`.
- Exit `10`, stage `python` or `core`: use the external Python where the wheel
  and `dcc-mcp-core>=0.19.91` are installed.
- Exit `10`, stage `partial_install`: inspect with `status`, close Mari, then
  rerun `install --repair --yes` using the same paths.
- Exit `40`, stage `bootstrap`: inspect the bounded JSONL error record at
  `~/.dcc-mcp/mari-bootstrap-errors.jsonl` (or
  `DCC_MCP_MARI_BOOTSTRAP_ERRORS`) and fix the reported import/start failure.
- Exit `40`, stage `host_readiness`: start or restart Mari, then rerun the exact
  command in `next_steps`.
- Exit `50`: close all Mari processes that load the plugin and retry. The
  receipt is retained so the operation can be resumed safely.
