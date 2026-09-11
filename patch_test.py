import subprocess

def test():
    subprocess.run(["git", "init", "ptest"])
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd="ptest")
    with open("ptest/staged.txt", "w") as f: f.write("staged")
    subprocess.run(["git", "add", "staged.txt"], cwd="ptest")

    with open("ptest/unstaged.txt", "w") as f: f.write("unstaged")
    subprocess.run(["git", "add", "unstaged.txt"], cwd="ptest")
    subprocess.run(["git", "commit", "-m", "add"], cwd="ptest")
    with open("ptest/unstaged.txt", "w") as f: f.write("unstaged_mod")

    with open("ptest/staged_new.txt", "w") as f: f.write("staged_new")
    subprocess.run(["git", "add", "staged_new.txt"], cwd="ptest")

    res = subprocess.run(["git", "diff", "HEAD"], cwd="ptest", capture_output=True, text=True)
    print(res.stdout)

test()
