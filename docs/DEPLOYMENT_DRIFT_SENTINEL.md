# BoTTube Deployment Drift Sentinel

The deployment drift sentinel compares three route inventories without starting
BoTTube or changing a deployment:

1. Operations documented in `openapi.yaml`.
2. Flask routes declared in configured Python sources.
3. Optional live route availability checks.

The application inventory uses Python's AST. It does not import
`bottube_server.py`, start services, or initialize BoTTube databases.
It recognizes Flask/Blueprint constructor import aliases, local app or blueprint
aliases, `rule=` registrations, and local `app.register_blueprint(...,
url_prefix=...)` overrides. A qualified route owner or cross-file prefix override
that cannot be resolved fails visibly with exit code 64 instead of guessing a
route path. Add the relevant source or assign the owner to a local alias when
that happens.

## Offline Check

Run the repository policy used by CI:

```bash
python3 deployment_drift.py --config deployment-drift.json
```

JSON output is deterministic and suitable for another check to consume:

```bash
python3 deployment_drift.py --config deployment-drift.json --format json
```

The report keeps the drift classes separate:

- `missing_in_code`: documented or canary operations absent from Flask source.
- `missing_in_spec`: Flask operations in the configured documentation scope but
  absent from OpenAPI. Canaries are excluded because UI canaries need not be API
  operations.
- `live_unavailable`: safe expected routes that returned 404, 405, or 5xx, lacked
  a fixture, or could not be reached.

The application count distinguishes declared operations from effective Flask
operations. Flask automatically supplies HEAD for GET and normally supplies
OPTIONS for every route. Those implicit operations may satisfy matching OpenAPI
operations, but they are not treated as declared application operations and do
not create `missing_in_spec` noise. A literal
`provide_automatic_options=False` is honored; unsupported dynamic route metadata
fails rather than being inferred.

`deployment-drift.json` records the collaboration operations currently
documented but absent from `bottube_server.py` as known drift. They remain in
every report. New drift blocks CI, and a fixed route makes its old allowance
stale and also blocks CI until the allowance is removed. This lets the check be
green on the current repository without concealing its existing inconsistency.

`missing_in_spec_patterns` defines the part of the Flask inventory that this
OpenAPI document owns. The repository policy covers registration, documented
agent-self routes, and the collaboration API family. Expanding OpenAPI ownership
requires expanding those patterns.

## Live Check

Live mode is deliberately opt-in and requires both flags:

```bash
python3 deployment_drift.py \
  --config deployment-drift.json \
  --live \
  --live-base-url https://staging.example.test
```

The sentinel has no credential option. It sends only `HEAD` requests with
`Accept` and `User-Agent` headers, does not follow redirects, and rejects POST,
PUT, PATCH, DELETE, OPTIONS, or TRACE canaries. It never deploys, restarts, or
changes the target. A 2xx, 3xx, 400, 401, 402, 403, or 429 response proves that a
route exists; 404, 405, and 5xx responses are unavailable. HEAD is not retried as
GET, so a service that does not support Flask's normal automatic HEAD handling
will be reported unavailable rather than receiving a less conservative request.
Malformed IPv6 hosts and invalid or out-of-range ports are configuration errors,
as are non-positive or non-finite timeout values.

OpenAPI GET and HEAD operations are probed by default. Set
`live_probe_openapi_reads` to `false` when a config should probe only its explicit
canary route set.

### Issue #1410 Canary

`deployment-drift.issue-1410.example.json` contains the 14 merged aliases from
[issue #1410](https://github.com/Scottcjn/bottube/issues/1410). All 14 are present
in `bottube_server.py`, and the config probes only those canaries:

```bash
python3 deployment_drift.py \
  --config deployment-drift.issue-1410.example.json \
  --live \
  --live-base-url https://bottube.ai
```

When source and policy agree but the deployed process still serves 404 for all
14 aliases, the report has zero blocking `missing_in_code`, zero blocking
`missing_in_spec`, 14 `live_unavailable` entries, and exit code `4`. That is the
precise "merged routes remain 404 in production" state. Running this command
only observes it; deployment or restart decisions remain a separate human
operation.

## Path Fixtures

OpenAPI and Flask parameters normalize to `{name}`. Supply fixture values in the
config's `fixtures` object or override them on the command line:

```bash
python3 deployment_drift.py \
  --config deployment-drift.json \
  --fixture video_id=known-public-video \
  --fixture agent_name=known-public-agent \
  --live \
  --live-base-url https://staging.example.test
```

Fixture values must be nonempty, single path segments. Literal or percent-encoded
slashes, backslashes, control characters, `.` and `..` dot segments, repeated
encoding that could normalize into traversal, and excessively nested encoding
are rejected before any request. Accepted values are percent-encoded as one path
segment. Missing fixtures are reported as `live_unavailable`; no request is
attempted. Use stable public canary objects because an application-level 404
cannot be distinguished from a missing route by an external observer.

## Exit Codes

Drift exit codes are a bitmask and can be combined:

| Bit | Meaning |
|---:|---|
| 0 | No blocking drift |
| 1 | Missing in code |
| 2 | Missing in spec |
| 4 | Live unavailable |
| 8 | Stale known-drift allowance |
| 64 | Invalid config or unsupported source syntax |

For example, exit code `3` means both static drift classes are present and `5`
means missing-in-code plus live-unavailable drift. Standard command-line usage
errors emitted by `argparse` use exit code `2` before the sentinel runs.

## Triage Runbook

1. Run the offline policy first. Fix or deliberately baseline static drift before
   interpreting a deployment result.
2. Run live mode against staging or another explicitly chosen base URL. Production
   probing should be an intentional operator action.
3. For `missing_in_code`, verify the route was merged into configured source and
   that method and parameter names match OpenAPI.
4. For `missing_in_spec`, update OpenAPI or narrow the ownership pattern only when
   that route family truly belongs elsewhere.
5. For `live_unavailable` with clean static results, compare the deployed revision
   and service route inventory through the normal operations process. Do not add a
   static allowance for a deployment problem.
6. After a route fix, remove its stale allowance in the same change. The CI check
   enforces this cleanup.

CI runs only the offline tests and repository policy. It does not depend on
production availability and does not hide the sentinel's exit status.
