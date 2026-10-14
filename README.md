
# Mini Git — A Git-Like Version Control System

Mini Git is a command-line version control system built in Python. It demonstrates core version control concepts such as content-addressed storage, commits, branches, file restoration, tags, and merging.

## Features

- Repository initialization
- File staging and commits
- Commit history and inspection
- Branch creation and checkout
- Working-tree status and file diffs
- File restoration
- `.gitignore` support
- Tags
- Fast-forward merging
- Soft reset to a previous commit
- Automated tests using Python's `unittest`

## Technology Stack

- Python 3
- JSON for repository metadata
- SHA-256 for object identifiers
- `unittest` for automated testing

## Project Structure

```text
minigit_project/
├── mini_git.py
├── README.md
└── tests/
    └── test_minigit.py
```

The `.minigit/` directory is created when a repository is initialized. It stores repository metadata, objects, commits, references, and the staging index.

## Getting Started

### Requirements

- Python 3.12 or a compatible Python 3 version
- Windows Command Prompt, PowerShell, or a terminal

### Run Mini Git

Open a terminal in the project directory and display the available commands:

```bash
python mini_git.py --help
```

Initialize a repository:

```bash
python mini_git.py init
```

Stage a file and commit it:

```bash
python mini_git.py add app.py
python mini_git.py commit -m "Add application file"
```

Inspect the repository:

```bash
python mini_git.py status
python mini_git.py log
python mini_git.py show HEAD
```

### Branches and Merging

```bash
python mini_git.py branch feature
python mini_git.py checkout feature
python mini_git.py checkout main
python mini_git.py merge feature
```

### Tags and Reset

```bash
python mini_git.py tag v1.0
python mini_git.py tag
python mini_git.py reset HEAD
```

**Note:** Reset moves the current branch reference while leaving working files unchanged. Files that differ from the target commit may appear as modified.

See `python mini_git.py --help` for the complete command list.

## Run the Tests

From the project directory:

```bash
python -m py_compile mini_git.py
python -m unittest discover -s tests -v
```

The current test suite contains seven tests covering commits, history, branches, checkout, fast-forward merging, tags, reset, ignore rules, invalid commit references, duplicate tags, and divergent-branch rejection.

## Limitations

Mini Git is an educational implementation, not a drop-in replacement for Git.

- The tested merge workflow supports fast-forward merges.
- Diverged-branch merging is rejected by the current implementation.
- Reset behavior is a soft reset; working files are not automatically restored.
- Additional edge-case testing is needed before treating it as production-ready.

## Learning Objectives

This project explores:

- Content-addressed storage using hashes
- Commit snapshots and parent references
- Branch pointers and `HEAD`
- Staging and working-tree state
- Command-line interface design
- Automated testing of file-system operations

## License

Add a license before publishing if you want others to reuse or distribute this project.
