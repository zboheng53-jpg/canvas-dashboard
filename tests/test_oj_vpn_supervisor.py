import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="VPN supervisor requires POSIX pseudo-terminals")


@pytest.mark.parametrize("outcome, expected", [("Vpn is connected!", (True, False)), ("Login failed", (False, True))])
def test_interactive_login_selects_ldap_and_handles_result(tmp_path, monkeypatch, outcome, expected):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "deploy"))
    import oj_vpn_supervisor

    client = tmp_path / "fake_client"
    client.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('0 default_method_localdb\\n1 LDAP\\n2 LDAP2\\nchoose login method number:(0~3)',end='',flush=True)\n"
        "assert sys.stdin.readline().strip() == '1'\n"
        "print('Input username: ',end='',flush=True); assert sys.stdin.readline().strip() == 'fake'\n"
        "print('Input password: ',end='',flush=True); assert sys.stdin.readline().strip() == 'secret'\n"
        f"print({outcome!r},flush=True)\n",
        encoding="utf-8",
    )
    client.chmod(0o700)
    monkeypatch.setattr(oj_vpn_supervisor, "CLIENT", str(client))
    assert oj_vpn_supervisor.connect({"username": "fake", "password": "secret"}) == expected
