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

### Running the Example

We provide a simple example script to verify that `LabRunner` and `Pueue` are functioning correctly together. This script submits a basic task (which sleeps, echoes a message, and creates a small file) and waits for its completion.

1. Ensure the `pueued` daemon is running (e.g., `pueued -d` or in a separate terminal).
2. Run the example script:
   ```bash
   PYTHONPATH=src PATH="$PWD/bin:$PATH" python examples/simple_test.py
   ```

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
