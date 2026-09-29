"""
Resolve secrets from AWS SSM Parameter Store into the process environment.

In AWS (Lambda) no secret is ever passed as a plain environment variable --
Terraform only sets *pointers*: for every `<NAME>_SSM_PARAM=/path/to/param`
env var, this module fetches `/path/to/param` (SecureString, decrypted) and
exports its value as `<NAME>`, e.g.

    DATABASE_URL_SSM_PARAM=/finance-data-platform/supabase/pooler-transaction-url
        -> os.environ["DATABASE_URL"] = "<decrypted value>"

It runs once per process (i.e. once per Lambda cold start), right before
src/core/config.py builds `Settings`, so the rest of the codebase keeps reading
plain settings and never knows SSM exists. Locally / in CI no `*_SSM_PARAM`
variable is set, so this is a no-op and boto3 is never even imported.

A value already present in the environment always wins (an explicit override
is never clobbered). A parameter that doesn't exist (e.g. an optional vendor
key nobody has created yet) is logged and skipped, not fatal -- Settings' own
validation still fails fast if a *required* value ends up missing.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

SSM_PARAM_SUFFIX = "_SSM_PARAM"
# GetParameters accepts at most 10 names per call.
_BATCH_SIZE = 10


def load_ssm_parameters_into_env(environ: dict[str, str] | None = None, ssm_client=None) -> dict[str, str]:
    """Export every `<NAME>_SSM_PARAM` pointer as `<NAME>`. Returns the
    {NAME: parameter path} mapping that was actually resolved."""
    env = os.environ if environ is None else environ

    wanted: dict[str, str] = {}  # parameter path -> target env var name
    for key, path in env.items():
        if not key.endswith(SSM_PARAM_SUFFIX) or not path:
            continue
        target = key[: -len(SSM_PARAM_SUFFIX)]
        if target and not env.get(target):
            wanted[path] = target

    if not wanted:
        return {}

    if ssm_client is None:
        import boto3

        ssm_client = boto3.client("ssm")

    resolved: dict[str, str] = {}
    paths = sorted(wanted)
    for i in range(0, len(paths), _BATCH_SIZE):
        batch = paths[i : i + _BATCH_SIZE]
        resp = ssm_client.get_parameters(Names=batch, WithDecryption=True)
        for param in resp.get("Parameters", []):
            target = wanted[param["Name"]]
            env[target] = param["Value"]
            resolved[target] = param["Name"]
        for missing in resp.get("InvalidParameters", []):
            logger.warning("SSM parameter %s not found; %s left unset", missing, wanted[missing])

    return resolved
