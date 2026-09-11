# LabRunner

LabRunner is a research lab execution system designed for a small cluster of heterogeneous compute machines. It is engineered to decouple global experiment scheduling from local process supervision.

Phase 1 establishes **Pueue** as the local execution and process-supervision layer for LabRunner workers.

## Architecture

The intended eventual architecture separates global state (LabRunner) from local process execution (Pueue):

```text
                    LabRunner Controller
                            |
                            | HTTP
                            v
                    LabRunner Worker
                            |
                            | local interface (Python Adapter)
                            v
                          Pueue
                            |
                            v
                         Executor
                       /          \
                 Podman            Native
               Linux/CUDA        macOS/MPS
```

## Setup & Testing

1. **Prerequisites**: Python >= 3.12, `pytest`, and `psutil`.
2. **Pueue Binaries**: Download the `pueue` and `pueued` binaries and place them in `bin/` in the project root. Ensure they are executable.
3. **Run Tests**: Execute `PYTHONPATH=src PATH="$PWD/bin:$PATH" pytest tests/pueue/` to run all integration tests safely in isolated ephemeral daemon contexts.

## Project Structure

- `src/labrunner/pueue.py`: Contains the `PueueAdapter` used to safely interface with the local Pueue daemon.
- `docs/`: Evaluation, design, and how-to documentation for Phase 1.
- `tests/pueue/`: `pytest` integration test suite mapping LabRunner requirements to Pueue behavior.

## Dependencies

- Python >= 3.12
- `pytest` (for testing)
- `pyyaml` (for YAML parsing)

To set up your environment, simply install these requirements:
```bash
python3 -m pip install -r requirements.txt
```
