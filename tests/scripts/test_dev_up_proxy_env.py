from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_dev_up_bypasses_dashscope_without_dropping_existing_no_proxy(tmp_path):
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "python").symlink_to(sys.executable)
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                "HTTP_PROXY=http://127.0.0.1:7890",
                "HTTPS_PROXY=http://127.0.0.1:7890",
                "NO_PROXY=127.*,localhost,100.*",
                "no_proxy=127.*,localhost,100.*",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", "scripts/dev_up.sh", "__print_proxy_env"],
        cwd=ROOT,
        env={
            **os.environ,
            "CUTAGENT_ENV_FILE": str(env_file),
            "CUTAGENT_VENV": str(venv),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    lines = dict(line.split("=", 1) for line in result.stdout.strip().splitlines())
    assert lines["NO_PROXY"].startswith("127.*,localhost,100.*")
    assert "dashscope.aliyuncs.com" in lines["NO_PROXY"].split(",")
    assert lines["no_proxy"].startswith("127.*,localhost,100.*")
    assert "dashscope.aliyuncs.com" in lines["no_proxy"].split(",")
