from pathlib import Path

from datetime import datetime, timezone

import argparse

import difflib

import hashlib

import json

import sys



META_DIR = ".minigit"





def get_repo():

    """Return the repository directory."""

    repo = Path.cwd() / META_DIR

    if not repo.is_dir():

        raise RuntimeError("Repository not initialized. Run init first.")

    return repo





def get_head_commit(repo):

    """Return the current branch, commit ID, and commit data."""

    head = (repo / "HEAD").read_text(encoding="utf-8").strip()

    branch_path = repo / head



    if not branch_path.is_file():

        raise RuntimeError("The current branch reference is missing.")



    commit_id = branch_path.read_text(encoding="utf-8").strip()

    if not commit_id:

        return head, None, None



    commit_path = repo / "commits" / f"{commit_id}.json"

    if not commit_path.is_file():

        raise RuntimeError(f"Commit not found: {commit_id}")



    data = json.loads(commit_path.read_text(encoding="utf-8"))

    return head, commit_id, data





def get_safe_relative_path(filename):

    """Validate a user path and return its project-relative form."""

    root = Path.cwd().resolve()

    supplied = Path(filename)



    if supplied.is_absolute():

        candidate = supplied.resolve()

    else:

        candidate = (root / supplied).resolve()



    if not candidate.is_relative_to(root):

        raise ValueError("File must be inside the project.")



    relative_path = candidate.relative_to(root)

    if not relative_path.parts:

        raise ValueError("A file path is required.")

    if META_DIR in relative_path.parts:

        raise ValueError("Cannot operate on Mini Git's internal files.")



    return root, candidate, relative_path.as_posix()






def is_ignored(relative_name, root):
    """Return True when a path matches a non-comment .gitignore rule."""
    import fnmatch
    ignore_file = root / ".gitignore"
    if not ignore_file.is_file():
        return False
    path = relative_name.replace("\\", "/")
    for raw in ignore_file.read_text(encoding="utf-8").splitlines():
        rule = raw.strip()
        if not rule or rule.startswith("#"):
            continue
        negated = rule.startswith("!")
        if negated:
            rule = rule[1:]
        rule = rule.lstrip("/")
        directory_rule = rule.endswith("/")
        rule = rule.rstrip("/")
        matched = fnmatch.fnmatch(path, rule) or fnmatch.fnmatch(Path(path).name, rule)
        if directory_rule:
            matched = matched or path.startswith(rule + "/")
        if matched:
            ignored = not negated
    return locals().get("ignored", False)


def resolve_commit(repo, reference):
    """Resolve HEAD, a branch name, or a unique commit ID prefix."""
    reference = reference.strip()
    if reference.upper() == "HEAD":
        _, commit_id, data = get_head_commit(repo)
        if not commit_id:
            raise ValueError("HEAD does not point to a commit yet.")
        return commit_id, data
    branch_path = repo / "refs" / "heads" / reference
    if branch_path.is_file():
        commit_id = branch_path.read_text(encoding="utf-8").strip()
        if not commit_id:
            raise ValueError(f"Branch '{reference}' has no commits yet.")
        path = repo / "commits" / f"{commit_id}.json"
        return commit_id, json.loads(path.read_text(encoding="utf-8"))
    if not reference or any(ch not in "0123456789abcdefABCDEF" for ch in reference):
        raise ValueError("Use HEAD, a branch name, or a hexadecimal commit ID.")
    matches = list((repo / "commits").glob(f"{reference.lower()}*.json"))
    if not matches:
        raise ValueError(f"Commit or branch '{reference}' was not found.")
    if len(matches) > 1:
        raise ValueError(f"Commit prefix '{reference}' is ambiguous.")
    data = json.loads(matches[0].read_text(encoding="utf-8"))
    return matches[0].stem, data


def tag(name=None, reference="HEAD"):
    """List tags or create a lightweight tag pointing to a commit."""
    repo = get_repo()
    tags_dir = repo / "refs" / "tags"
    tags_dir.mkdir(parents=True, exist_ok=True)
    if name is None:
        tags = sorted(tags_dir.iterdir())
        if not tags:
            print("No tags.")
        for item in tags:
            if item.is_file():
                print(f"{item.name} -> {item.read_text(encoding='utf-8').strip()}")
        return
    if name.startswith(".") or name in {"", ".", ".."} or "/" in name or "\\" in name or any(c.isspace() for c in name):
        raise ValueError("Invalid tag name.")
    target = tags_dir / name
    if target.exists():
        raise ValueError(f"Tag '{name}' already exists.")
    commit_id, _ = resolve_commit(repo, reference)
    target.write_text(commit_id, encoding="utf-8")
    print(f"Created tag '{name}' at {commit_id[:8]}.")


def reset(reference):
    """Safely move the current branch pointer; working files are not overwritten."""
    repo = get_repo()
    index = json.loads((repo / "index.json").read_text(encoding="utf-8"))
    if index:
        raise RuntimeError("Staged changes exist. Commit or unstage them before reset.")
    head, current_id, current_data = get_head_commit(repo)
    root = Path.cwd().resolve()
    current_snapshot = current_data["snapshot"] if current_data else {}
    for filename, old_hash in current_snapshot.items():
        path = (root / filename).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise RuntimeError(f"Tracked file '{filename}' is missing or unsafe.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != old_hash:
            raise RuntimeError(f"'{filename}' has uncommitted changes. Commit them before reset.")
    target_id, target_data = resolve_commit(repo, reference)
    (repo / head).write_text(target_id, encoding="utf-8")
    print(f"Moved {head.split('/')[-1]} to {target_id[:8]} (soft reset; working files unchanged).")
    print("Note: files differing from the target commit will appear modified; no files were deleted.")


def _ancestor_chain(repo, commit_id):
    chain = []
    while commit_id:
        chain.append(commit_id)
        path = repo / "commits" / f"{commit_id}.json"
        if not path.is_file():
            raise RuntimeError(f"Commit not found: {commit_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        commit_id = data.get("parent")
    return chain


def merge(branch_name):
    """Merge a branch when fast-forward is possible or snapshots merge cleanly."""
    repo = get_repo()
    head, current_id, current_data = get_head_commit(repo)
    if not current_id:
        raise RuntimeError("Cannot merge before the current branch has a commit.")
    target_ref = repo / "refs" / "heads" / branch_name
    if not target_ref.is_file():
        raise ValueError(f"Branch '{branch_name}' does not exist.")
    target_id = target_ref.read_text(encoding="utf-8").strip()
    if not target_id:
        raise RuntimeError("The target branch has no commits.")
    if target_id == current_id:
        print("Already up to date.")
        return
    index = json.loads((repo / "index.json").read_text(encoding="utf-8"))
    if index:
        raise RuntimeError("Staged changes exist. Commit them before merging.")
    root = Path.cwd().resolve()
    current_snapshot = current_data["snapshot"]
    for filename, old_hash in current_snapshot.items():
        path = root / filename
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != old_hash:
            raise RuntimeError(f"Working tree has changes to '{filename}'. Commit or restore them before merging.")
    target_data = json.loads((repo / "commits" / f"{target_id}.json").read_text(encoding="utf-8"))
    current_chain = _ancestor_chain(repo, current_id)
    target_chain = _ancestor_chain(repo, target_id)
    if current_id in target_chain:
        # Fast-forward: update files first, then branch pointer.
        target_snapshot = target_data["snapshot"]
        for filename, file_hash in target_snapshot.items():
            obj = repo / "objects" / file_hash
            if not obj.is_file():
                raise RuntimeError(f"Stored file object not found: {file_hash}")
            dest = (root / filename).resolve()
            if not dest.is_relative_to(root):
                raise RuntimeError(f"Unsafe path in snapshot: {filename}")
            if filename not in current_snapshot and dest.exists() and dest.read_bytes() != obj.read_bytes():
                raise RuntimeError(f"Untracked file '{filename}' would be overwritten.")
        for filename in current_snapshot.keys() - target_snapshot.keys():
            path = (root / filename).resolve()
            if path.is_relative_to(root) and path.is_file(): path.unlink()
        for filename, file_hash in target_snapshot.items():
            dest = (root / filename).resolve(); dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((repo / "objects" / file_hash).read_bytes())
        (repo / head).write_text(target_id, encoding="utf-8")
        print(f"Fast-forwarded to {branch_name} ({target_id[:8]}).")
        return
    common = next((cid for cid in current_chain if cid in set(target_chain)), None)
    if common is None:
        raise RuntimeError("No common ancestor found; merge aborted.")
    base_data = json.loads((repo / "commits" / f"{common}.json").read_text(encoding="utf-8"))
    base = base_data["snapshot"]; theirs = target_data["snapshot"]
    merged = dict(current_snapshot)
    conflicts = []
    for filename in set(base) | set(current_snapshot) | set(theirs):
        b, ours, theirs_hash = base.get(filename), current_snapshot.get(filename), theirs.get(filename)
        if ours == theirs_hash: continue
        if ours == b:
            if theirs_hash is None: merged.pop(filename, None)
            else: merged[filename] = theirs_hash
        elif theirs_hash == b:
            continue
        else:
            conflicts.append(filename)
    if conflicts:
        raise RuntimeError("Merge conflicts detected; no changes made: " + ", ".join(sorted(conflicts)))
    # Ensure all referenced blobs exist before changing the working tree.
    for filename, file_hash in merged.items():
        if not (repo / "objects" / file_hash).is_file():
            raise RuntimeError(f"Stored file object not found: {file_hash}")
    for filename in set(current_snapshot) - set(merged):
        path = (root / filename).resolve()
        if path.is_relative_to(root) and path.is_file(): path.unlink()
    for filename, file_hash in merged.items():
        dest = (root / filename).resolve()
        if filename not in current_snapshot and dest.exists() and dest.read_bytes() != (repo / "objects" / file_hash).read_bytes():
            raise RuntimeError(f"Untracked file '{filename}' would be overwritten; merge aborted.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((repo / "objects" / file_hash).read_bytes())
    commit_data = {"message": f"Merge branch '{branch_name}'", "timestamp": datetime.now(timezone.utc).isoformat(), "parent": current_id, "merge_parent": target_id, "snapshot": merged}
    serialized = json.dumps(commit_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    new_id = hashlib.sha256(serialized).hexdigest()
    (repo / "commits" / f"{new_id}.json").write_text(json.dumps({**commit_data, "id": new_id}, indent=2), encoding="utf-8")
    (repo / head).write_text(new_id, encoding="utf-8")
    print(f"Merged '{branch_name}' into {head.split('/')[-1]} ({new_id[:8]}).")


def init():

    """Initialize a Mini Git repository."""

    repo = Path.cwd() / META_DIR

    if repo.exists():

        print("Repository already initialized.")

        return



    (repo / "objects").mkdir(parents=True)

    (repo / "commits").mkdir()

    (repo / "refs" / "heads").mkdir(parents=True)

    (repo / "index.json").write_text("{}", encoding="utf-8")

    (repo / "HEAD").write_text("refs/heads/main", encoding="utf-8")

    (repo / "refs" / "heads" / "main").write_text("", encoding="utf-8")

    print("Initialized empty Mini Git repository.")





def add(filename):

    """Stage a file for the next commit."""

    repo = get_repo()

    root, file_path, relative_name = get_safe_relative_path(filename)



    if not file_path.is_file():

        raise FileNotFoundError(f"File not found: {filename}")



    if is_ignored(relative_name, root):
        raise ValueError(f"'{relative_name}' is ignored by .gitignore.")

    content = file_path.read_bytes()

    file_hash = hashlib.sha256(content).hexdigest()

    object_path = repo / "objects" / file_hash



    if not object_path.exists():

        object_path.write_bytes(content)



    index_path = repo / "index.json"

    index = json.loads(index_path.read_text(encoding="utf-8"))

    index[relative_name] = file_hash

    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    print(f"Staged: {relative_name}")





def commit(message):

    """Save staged changes as a commit."""

    repo = get_repo()

    index_path = repo / "index.json"

    index = json.loads(index_path.read_text(encoding="utf-8"))



    if not index:

        print("Nothing to commit. Stage a file first.")

        return



    head, parent_id, parent_data = get_head_commit(repo)

    branch_path = repo / head

    snapshot = parent_data["snapshot"].copy() if parent_data else {}

    snapshot.update(index)



    commit_data = {

        "message": message,

        "timestamp": datetime.now(timezone.utc).isoformat(),

        "parent": parent_id,

        "snapshot": snapshot,

    }



    serialized = json.dumps(

        commit_data, sort_keys=True, separators=(",", ":")

    ).encode("utf-8")

    commit_id = hashlib.sha256(serialized).hexdigest()

    commit_path = repo / "commits" / f"{commit_id}.json"

    commit_path.write_text(

        json.dumps({**commit_data, "id": commit_id}, indent=2),

        encoding="utf-8",

    )



    branch_path.write_text(commit_id, encoding="utf-8")

    index_path.write_text("{}", encoding="utf-8")

    print(f"[{head.split('/')[-1]} {commit_id[:8]}] {message}")





def show(commit_id):
    """Display details and the file list for a commit ID, unique prefix, or HEAD."""
    repo = get_repo()

    # Support HEAD as a shortcut for the current branch's latest commit.
    if commit_id.upper() == "HEAD":
        _, current_commit_id, _ = get_head_commit(repo)
        if not current_commit_id:
            raise ValueError("HEAD does not point to a commit yet.")
        commit_id = current_commit_id

    if not commit_id or any(
        ch not in "0123456789abcdefABCDEF" for ch in commit_id
    ):
        raise ValueError("Commit ID must contain hexadecimal characters only.")

    commits_dir = repo / "commits"
    matches = [
        path for path in commits_dir.iterdir()
        if path.is_file()
        and path.name.endswith(".json")
        and path.stem.startswith(commit_id.lower())
    ]

    if not matches:
        raise ValueError(f"Commit '{commit_id}' was not found.")
    if len(matches) > 1:
        raise ValueError(f"Commit prefix '{commit_id}' matches multiple commits.")

    commit_path = matches[0]
    try:
        data = json.loads(commit_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise RuntimeError(f"Could not read commit: {error}") from error

    print(f"Commit: {commit_path.stem}")
    print(f"Message: {data.get('message', '')}")
    print(f"Timestamp: {data.get('timestamp', '')}")
    print(f"Parent: {data.get('parent') or 'None'}")
    print("\nFiles in this commit:")

    snapshot = data.get("snapshot", {})
    if not snapshot:
        print("  None")
    else:
        for filename in sorted(snapshot):
            print(f"  {filename}")


def log():

    """Display commit history from newest to oldest."""

    repo = get_repo()

    head, commit_id, data = get_head_commit(repo)



    if not commit_id:

        print("No commits yet.")

        return



    while commit_id:

        print(f"Commit: {commit_id}")

        print(f"Message: {data['message']}")

        print(f"Timestamp: {data['timestamp']}")

        print(f"Parent: {data['parent'] or 'None'}")

        print("-" * 40)



        commit_id = data["parent"]

        if commit_id:

            commit_path = repo / "commits" / f"{commit_id}.json"

            if not commit_path.is_file():

                raise RuntimeError(f"Commit not found: {commit_id}")

            data = json.loads(commit_path.read_text(encoding="utf-8"))





def branch(name=None):

    """List branches or create a new branch."""

    repo = get_repo()

    branches_dir = repo / "refs" / "heads"



    if name is None:

        head = (repo / "HEAD").read_text(encoding="utf-8").strip()

        current_branch = head.split("/")[-1]

        for branch_path in sorted(branches_dir.iterdir()):

            if branch_path.is_file():

                marker = "*" if branch_path.name == current_branch else " "

                print(f"{marker} {branch_path.name}")

        return



    if (

        not name

        or name in {".", ".."}

        or "/" in name

        or "\\" in name

        or name.startswith(".")

        or any(char.isspace() for char in name)

    ):

        raise ValueError("Invalid branch name.")



    new_branch = branches_dir / name

    if new_branch.exists():

        print(f"Branch '{name}' already exists.")

        return



    head, commit_id, data = get_head_commit(repo)

    new_branch.write_text(commit_id or "", encoding="utf-8")

    print(f"Created branch '{name}'.")





def checkout(name):

    """Switch branches without overwriting uncommitted changes."""

    repo = get_repo()

    root = Path.cwd().resolve()

    branches_dir = repo / "refs" / "heads"



    if (

        not name

        or name in {".", ".."}

        or "/" in name

        or "\\" in name

        or name.startswith(".")

        or any(char.isspace() for char in name)

    ):

        raise ValueError("Invalid branch name.")



    target_branch = branches_dir / name

    if not target_branch.is_file():

        raise ValueError(f"Branch '{name}' does not exist.")



    current_head, current_id, current_data = get_head_commit(repo)

    if current_head == f"refs/heads/{name}":

        print(f"Already on branch '{name}'.")

        return



    index_path = repo / "index.json"

    index = json.loads(index_path.read_text(encoding="utf-8"))

    if index:

        raise RuntimeError("Staged changes exist. Commit them before switching.")



    current_snapshot = current_data["snapshot"] if current_data else {}



    # Refuse to switch if tracked files have working-tree changes.

    for filename, old_hash in current_snapshot.items():

        file_path = root / filename

        if not file_path.is_file():

            raise RuntimeError(

                f"Tracked file '{filename}' is missing. Restore it before switching."

            )

        current_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()

        if current_hash != old_hash:

            raise RuntimeError(

                f"'{filename}' has uncommitted changes. Commit them before switching."

            )



    target_id = target_branch.read_text(encoding="utf-8").strip()

    if target_id:

        target_commit_path = repo / "commits" / f"{target_id}.json"

        if not target_commit_path.is_file():

            raise RuntimeError("Target branch commit was not found.")

        target_data = json.loads(target_commit_path.read_text(encoding="utf-8"))

        target_snapshot = target_data["snapshot"]

    else:

        target_snapshot = {}



    # Validate every target object and avoid overwriting untracked files.

    for filename, file_hash in target_snapshot.items():

        destination = (root / filename).resolve()

        if not destination.is_relative_to(root):

            raise RuntimeError(f"Unsafe path in commit snapshot: {filename}")



        if filename not in current_snapshot and destination.exists():

            if not destination.is_file():

                raise RuntimeError(

                    f"Cannot switch: '{filename}' is not a regular file."

                )

            existing_hash = hashlib.sha256(destination.read_bytes()).hexdigest()

            if existing_hash != file_hash:

                raise RuntimeError(

                    f"Cannot switch: '{filename}' would be overwritten."

                )



        if not (repo / "objects" / file_hash).is_file():

            raise RuntimeError(f"Stored file object not found: {file_hash}")



    # All checks passed. Update the working tree.

    for filename in current_snapshot:

        if filename not in target_snapshot:

            old_path = (root / filename).resolve()

            if old_path.is_relative_to(root) and old_path.is_file():

                old_path.unlink()



    for filename, file_hash in target_snapshot.items():

        destination = (root / filename).resolve()

        destination.parent.mkdir(parents=True, exist_ok=True)

        destination.write_bytes((repo / "objects" / file_hash).read_bytes())



    (repo / "HEAD").write_text(

        f"refs/heads/{name}", encoding="utf-8"

    )

    print(f"Switched to branch '{name}'.")





def status():

    """Show staged, modified, and untracked files."""

    repo = get_repo()

    root = Path.cwd().resolve()

    index = json.loads((repo / "index.json").read_text(encoding="utf-8"))

    head, commit_id, data = get_head_commit(repo)

    tracked = data["snapshot"] if data else {}



    print(f"On branch: {head.split('/')[-1]}")



    print("\nStaged files:")

    if index:

        for filename in sorted(index):

            print(f"  {filename}")

    else:

        print("  None")



    print("\nModified files:")

    modified = []

    for filename, old_hash in tracked.items():

        file_path = root / filename

        if not file_path.is_file():

            modified.append(f"{filename} (deleted)")

            continue

        current_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()

        if current_hash != old_hash and filename not in index:

            modified.append(filename)



    if modified:

        for filename in sorted(modified):

            print(f"  {filename}")

    else:

        print("  None")



    print("\nUntracked files:")

    untracked = []

    for file_path in root.rglob("*"):

        if not file_path.is_file():

            continue

        relative_path = file_path.relative_to(root)

        if META_DIR in relative_path.parts or "__pycache__" in relative_path.parts:

            continue

        filename = relative_path.as_posix()

        if filename not in tracked and filename not in index:

            untracked.append(filename)



    if untracked:

        for filename in sorted(untracked):

            print(f"  {filename}")

    else:

        print("  None")





def diff(filename):

    """Show changes between a file and its latest committed version."""

    repo = get_repo()

    root, file_path, relative_name = get_safe_relative_path(filename)



    if not file_path.is_file():

        raise FileNotFoundError(f"File not found: {filename}")



    head, commit_id, data = get_head_commit(repo)

    if not data:

        print("No commits yet.")

        return



    snapshot = data["snapshot"]

    if relative_name not in snapshot:

        print(f"{relative_name} is not tracked in the latest commit.")

        return



    old_hash = snapshot[relative_name]

    object_path = repo / "objects" / old_hash

    if not object_path.is_file():

        raise RuntimeError(f"Stored file object not found: {old_hash}")



    old_content = object_path.read_bytes().decode("utf-8").splitlines()

    new_content = file_path.read_bytes().decode("utf-8").splitlines()

    changes = difflib.unified_diff(

        old_content,

        new_content,

        fromfile=f"committed/{relative_name}",

        tofile=f"working/{relative_name}",

        lineterm="",

    )

    output = "\n".join(changes)

    print(output if output else "No differences found.")





def restore(filename):

    """Restore one tracked file from the current commit."""

    repo = get_repo()

    root, file_path, relative_name = get_safe_relative_path(filename)



    head, commit_id, data = get_head_commit(repo)

    if not data:

        raise RuntimeError("No commits exist yet.")



    snapshot = data["snapshot"]

    if relative_name not in snapshot:

        raise ValueError(

            f"'{relative_name}' is not tracked in the current commit."

        )



    index_path = repo / "index.json"

    index = json.loads(index_path.read_text(encoding="utf-8"))

    if relative_name in index:

        raise RuntimeError(

            f"'{relative_name}' has staged changes. "

            "Commit them before restoring."

        )



    object_hash = snapshot[relative_name]

    object_path = repo / "objects" / object_hash

    if not object_path.is_file():

        raise RuntimeError(f"Stored file object not found: {object_hash}")



    if file_path.exists() and not file_path.is_file():

        raise ValueError(f"'{relative_name}' is not a regular file.")



    file_path.parent.mkdir(parents=True, exist_ok=True)

    file_path.write_bytes(object_path.read_bytes())

    print(f"Restored '{relative_name}' to the current commit.")





def main():

    """Register commands and execute the requested command."""

    parser = argparse.ArgumentParser(

        description="A simple Git-like version control system"

    )

    subparsers = parser.add_subparsers(dest="command", required=True)



    subparsers.add_parser("init", help="Initialize a repository")



    add_parser = subparsers.add_parser("add", help="Stage a file")

    add_parser.add_argument("filename")



    commit_parser = subparsers.add_parser("commit", help="Save a version")

    commit_parser.add_argument(

        "-m", "--message", required=True, help="Commit message"

    )



    subparsers.add_parser("log", help="Show commit history")



    show_parser = subparsers.add_parser("show", help="Show details of a commit")

    show_parser.add_argument("commit_id", help="Full or unique abbreviated commit ID")



    branch_parser = subparsers.add_parser(

        "branch", help="List or create branches"

    )

    branch_parser.add_argument(

        "name", nargs="?", help="Name of the branch to create"

    )



    checkout_parser = subparsers.add_parser(

        "checkout", help="Switch branches"

    )

    checkout_parser.add_argument("name", help="Name of the branch to switch to")



    subparsers.add_parser("status", help="Show repository status")



    diff_parser = subparsers.add_parser("diff", help="Show changes in a file")

    diff_parser.add_argument("filename")



    restore_parser = subparsers.add_parser(

        "restore", help="Restore a file from the current commit"

    )

    restore_parser.add_argument("filename")



    merge_parser = subparsers.add_parser("merge", help="Merge another branch")
    merge_parser.add_argument("branch", help="Branch to merge into the current branch")

    reset_parser = subparsers.add_parser("reset", help="Move current branch to a commit without deleting files")
    reset_parser.add_argument("reference", help="HEAD, branch name, or commit ID/prefix")

    tag_parser = subparsers.add_parser("tag", help="List tags or create a tag")
    tag_parser.add_argument("name", nargs="?", help="Tag name")
    tag_parser.add_argument("reference", nargs="?", default="HEAD", help="Commit or branch to tag (default: HEAD)")

    args = parser.parse_args()



    try:

        if args.command == "init":

            init()

        elif args.command == "add":

            add(args.filename)

        elif args.command == "commit":

            commit(args.message)

        elif args.command == "log":

            log()

        elif args.command == "show":

            show(args.commit_id)

        elif args.command == "branch":

            branch(args.name)

        elif args.command == "checkout":

            checkout(args.name)

        elif args.command == "status":

            status()

        elif args.command == "diff":

            diff(args.filename)

        elif args.command == "restore":

            restore(args.filename)

        elif args.command == "merge":

            merge(args.branch)

        elif args.command == "reset":

            reset(args.reference)

        elif args.command == "tag":

            tag(args.name, args.reference)

    except (

        RuntimeError,

        ValueError,

        FileNotFoundError,

        json.JSONDecodeError,

        OSError,

        UnicodeDecodeError,

    ) as error:

        print(f"Error: {error}", file=sys.stderr)

        sys.exit(1)





if __name__ == "__main__":

    main()
