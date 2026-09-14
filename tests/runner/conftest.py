import pytest
import subprocess
from pathlib import Path

@pytest.fixture(autouse=True)
def pueue_daemon(tmp_path_factory):
    # Setup pueued for tests in a temp dir
    d = tmp_path_factory.mktemp("pueue_daemon")
    pueue_dir = d / "pueue"
    pueue_dir.mkdir()
    config_path = pueue_dir / "pueue.yml"

    import os

    # Generate a default config using `pueued -c <path> --generate` or similar, wait, `pueued --config <path>` will just fail if it doesn't exist?
    # Pueue creates it if it doesn't exist, but maybe we need to run `pueued` once?
    # No, `pueued` doesn't automatically generate config unless we use -c and it creates it in 3.4.1. Wait, let's just use the fixture logic from pueue tests.

    # Actually, in tests/pueue/conftest.py they do:
    # process = subprocess.Popen(["pueued", "-c", str(config_path)]...
    os.environ["PUEUE_CONFIG_PATH"] = str(config_path)

    # We can just write a default config to avoid issues
    config_path.write_text("""
client:
  restart_in_place: false
  read_local_logs: true
  show_confirmation_questions: false
  show_expanded_aliases: false
  dark_mode: false
  max_status_lines: null
  status_time_format: '%H:%M:%S'
  status_datetime_format: '%Y-%m-%d %H:%M:%S'
daemon:
  default_parallel_tasks: 1
  pause_group_on_failure: false
  pause_all_on_failure: false
  callback: null
  callback_log_lines: 10
shared:
  pueue_directory: """ + str(pueue_dir) + """
  use_unix_socket: true
  unix_socket_path: """ + str(pueue_dir / "pueue.socket") + """
  host: 127.0.0.1
  port: "6924"
  daemon_cert: null
  daemon_key: null
  shared_secret_path: """ + str(pueue_dir / "secret") + """
""")

    process = subprocess.Popen(["pueued", "--config", str(config_path)])

    import time
    time.sleep(1) # wait for daemon to start

    import os
    os.environ["PUEUE_CONFIG_PATH"] = str(config_path)

    yield

    process.terminate()
    process.wait()
