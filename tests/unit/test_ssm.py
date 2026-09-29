from src.core.ssm import load_ssm_parameters_into_env


class _FakeSSM:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def get_parameters(self, Names, WithDecryption):
        assert WithDecryption is True
        self.calls.append(list(Names))
        return {
            "Parameters": [{"Name": n, "Value": self.values[n]} for n in Names if n in self.values],
            "InvalidParameters": [n for n in Names if n not in self.values],
        }


def test_noop_without_pointers():
    env = {"DATABASE_URL": "postgresql://x"}
    # No *_SSM_PARAM -> must not even need a client.
    assert load_ssm_parameters_into_env(env, ssm_client=None) == {}
    assert env == {"DATABASE_URL": "postgresql://x"}


def test_resolves_pointers_and_skips_missing():
    env = {
        "DATABASE_URL_SSM_PARAM": "/fdp/db",
        "FRED_API_KEY_SSM_PARAM": "/fdp/fred",
    }
    ssm = _FakeSSM({"/fdp/db": "postgresql://secret"})

    resolved = load_ssm_parameters_into_env(env, ssm_client=ssm)

    assert resolved == {"DATABASE_URL": "/fdp/db"}
    assert env["DATABASE_URL"] == "postgresql://secret"
    assert "FRED_API_KEY" not in env


def test_explicit_env_value_wins():
    env = {"API_KEY": "explicit", "API_KEY_SSM_PARAM": "/fdp/api-key"}
    ssm = _FakeSSM({"/fdp/api-key": "from-ssm"})

    load_ssm_parameters_into_env(env, ssm_client=ssm)

    assert env["API_KEY"] == "explicit"
    assert ssm.calls == []


def test_batches_by_ten():
    env = {f"V{i}_SSM_PARAM": f"/p/{i}" for i in range(12)}
    ssm = _FakeSSM({f"/p/{i}": str(i) for i in range(12)})

    load_ssm_parameters_into_env(env, ssm_client=ssm)

    assert [len(c) for c in ssm.calls] == [10, 2]
    assert env["V11"] == "11"
