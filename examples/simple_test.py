import time
from pathlib import Path
from labrunner.pueue import PueueAdapter, TaskState

def run_simple_test():
    print("Initializing PueueAdapter...")
    adapter = PueueAdapter()

    # 1. Check health
    health = adapter.health()
    print(f"Pueue Health: {health}")
    if not health.daemon_running:
        print("Error: Pueue daemon is not running. Please start it by running `pueued -d`.")
        return

    # 2. Submit a task (sleep, echo, create file)
    test_file = Path("test_output.txt")
    if test_file.exists():
        test_file.unlink()

    print("Submitting a simple task to sleep 1s, echo a message, and write to a file...")
    task_id = adapter.submit(
        run_id="example_run_01",
        argv=["bash", "-c", "sleep 1 && echo 'Hello from Pueue!' && echo 'File contents' > test_output.txt"],
        cwd=Path.cwd(),
        env={}
    )
    print(f"Task submitted successfully. Task ID: {task_id}")

    # 3. Wait for the task to finish
    print("Waiting for task to complete...")
    while True:
        status = adapter.status(task_id)
        print(f"Current State: {status.state}")
        if status.state in [TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED]:
            # Sometimes 'Done' appears while pueue is still cleaning up. Let's give it an extra tiny wait.
            time.sleep(0.5)
            status = adapter.status(task_id) # reload to be absolutely sure
            break
        time.sleep(0.5)

    # 4. Check the results
    print(f"\nTask Finished with state: {status.state}")

    # Wait a short bit to ensure file system buffers have flushed before checking for file
    time.sleep(0.5)

    logs = adapter.logs(task_id)
    print("Task Logs:")
    print(logs.output)

    if test_file.exists():
        print(f"\nSuccess! File '{test_file}' was created.")
        print(f"File contents: {test_file.read_text().strip()}")
        test_file.unlink() # Cleanup
    else:
        print("\nError: The output file was not created.")

if __name__ == "__main__":
    run_simple_test()
