import os
import subprocess
import time
import pytest
from pathlib import Path

from labrunner.pueue import PueueAdapter, PueueUnavailable

# Ensure the `pueue` and `pueued` binaries downloaded during setup are in PATH
import os
os.environ["PATH"] = f"{os.getcwd()}/bin:{os.environ.get('PATH', '')}"


class EphemeralPueue:
    def __init__(self, tmp_path: Path):
        self.tmp_path = tmp_path
        self.config_dir = tmp_path / "config"
        self.config_dir.mkdir()
        self.config_path = self.config_dir / "pueue.yml"

        self.state_dir = tmp_path / "state"
        self.state_dir.mkdir()

        self.socket_dir = tmp_path / "socket"
        self.socket_dir.mkdir()

        self._write_config()

        self.daemon_process = None
        self.adapter = PueueAdapter(config_path=self.config_path)

    def _write_config(self):
        socket_path = self.socket_dir / "pueue.socket"
        config_content = f"""
---
shared:
  pueue_directory: {self.state_dir}
  use_unix_socket: true
  unix_socket_path: {socket_path}
  host: 127.0.0.1
  port: "6924"
  daemon_cert: {self.state_dir}/certs/daemon.cert
  daemon_key: {self.state_dir}/certs/daemon.key
  shared_secret_path: {self.state_dir}/shared_secret

client:
  restart_in_place: false
  read_local_logs: true
  show_confirmation_questions: false
  show_expanded_aliases: false
  dark_mode: false
  max_status_lines: null
  status_time_format: "%Y-%m-%d %H:%M:%S"
  status_datetime_format: "%Y-%m-%d"

daemon:
  default_parallel_tasks: 1
  pause_group_on_failure: false
  pause_all_on_failure: false
  callback: ""
  callback_log_lines: 10
  env_vars: {{}}
  groups:
    default: 1
"""
        self.config_path.write_text(config_content)

    def start(self):
        cmd = ["pueued", "-c", str(self.config_path)]
        self.daemon_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._wait_until_healthy()

    def stop(self):
        if self.daemon_process:
            self.daemon_process.terminate()
            try:
                self.daemon_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.daemon_process.kill()
                self.daemon_process.wait()
            self.daemon_process = None

    def _wait_until_healthy(self, timeout=10.0):
        start = time.time()
        while time.time() - start < timeout:
            if self.adapter.health().daemon_running:
                res = subprocess.run(["pueue", "--config", str(self.config_path), "status"], capture_output=True)
                if res.returncode == 0:
                    return

            if self.daemon_process.poll() is not None:
                _, stderr = self.daemon_process.communicate()
                raise RuntimeError(f"Daemon process died prematurely: {stderr.decode()}")

            time.sleep(0.1)
        raise RuntimeError("Pueue daemon failed to become healthy within timeout.")


@pytest.fixture
def pueue_env(tmp_path):
    env = EphemeralPueue(tmp_path)
    env.start()
    yield env
    env.stop()
