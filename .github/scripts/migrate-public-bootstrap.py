#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_once(content: str, old: str, new: str, path: str) -> str:
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one exact match, found {count}: {old[:80]!r}")
    return content.replace(old, new, 1)


def replace_section(content: str, start: str, end: str, replacement: str, path: str) -> str:
    start_index = content.find(start)
    if start_index < 0:
        raise RuntimeError(f"{path}: section start not found: {start!r}")
    end_index = content.find(end, start_index + len(start))
    if end_index < 0:
        raise RuntimeError(f"{path}: section end not found after {start!r}: {end!r}")
    return content[:start_index] + replacement + content[end_index:]


def migrate_debian_script() -> None:
    path = "bootstrap/debian-ipv4.sh"
    content = read(path)

    for line in (
        'readonly DEPLOY_KEY="/root/.ssh/discrete_infrastructure_deploy"\n',
        'readonly SSH_CONFIG="/root/.ssh/config"\n',
        'readonly SSH_ALIAS="github-discrete"\n',
    ):
        content = replace_once(content, line, "", path)

    public_access_function = '''verify_public_repository_access() {
    local origin

    origin="$(git -C "${REPO_DIR}" remote get-url origin 2>/dev/null)" \\
        || die "Cannot read Git origin."

    [[ "${origin}" =~ ^https://github\\.com/[^/]+/[^/]+(\\.git)?$ ]] \\
        || die "Git origin must use public GitHub HTTPS: ${origin}"

    GIT_TERMINAL_PROMPT=0 git ls-remote "${origin}" HEAD >/dev/null 2>&1 \\
        || die "Anonymous HTTPS access to Git origin failed: ${origin}"
}

'''

    content = replace_section(
        content,
        "repository_full_name() {\n",
        "build_bootstrap_fail2ban_config() {\n",
        public_access_function,
        path,
    )

    content = replace_once(
        content,
        '    local deploy_key_ready="no"\n    ensure_deploy_key && deploy_key_ready="yes"\n',
        '    verify_public_repository_access\n',
        path,
    )
    content = replace_once(
        content,
        '    printf \'Deploy key ready:      %s\\n\\n\' "${deploy_key_ready}"\n',
        "    printf 'Repository access:     public anonymous HTTPS\\n\\n'\n",
        path,
    )
    content = replace_once(
        content,
        '    ensure_deploy_key \\\n        || die "Register the printed deploy key in GitHub, then run finalize again."\n',
        '    verify_public_repository_access\n',
        path,
    )

    write(path, content)


def migrate_debian_runbook() -> None:
    path = "docs/bootstrap-from-zero.md"
    content = read(path)

    content = replace_once(
        content,
        "- a dedicated read-only GitHub deploy key;\n",
        "- anonymous read-only access to the public GitHub repository over HTTPS;\n",
        path,
    )

    step3 = '''## 3. Verify Debian 12, install Git, and clone the public repository

Confirm the provider created the requested operating system before changing the host:

```bash
. /etc/os-release
printf 'ID=%s VERSION_ID=%s VERSION_CODENAME=%s\\n' \\
  "$ID" "$VERSION_ID" "$VERSION_CODENAME"
```

Required output:

```text
ID=debian VERSION_ID=12 VERSION_CODENAME=bookworm
```

Install Git and the CA certificate bundle:

```bash
apt-get update
apt-get install -y ca-certificates git
```

Clone the public repository anonymously over HTTPS:

```bash
git clone \\
  https://github.com/MatthewFreeman/discrete-infrastructure.git \\
  /opt/discrete-infrastructure

cd /opt/discrete-infrastructure
```

A GitHub account, personal access token, deploy key, username, and password are not required.
Do not configure a Git credential helper on the VPS.

---

'''
    content = replace_section(
        content,
        "## 3. Install Git and clone the repository\n",
        "## 4. Run the `prepare` phase\n",
        step3,
        path,
    )

    content = replace_once(
        content,
        "16. generate a dedicated GitHub deploy key.\n",
        "16. verify anonymous HTTPS access to the public repository.\n",
        path,
    )
    content = replace_once(
        content,
        "Deploy key ready:      no\n",
        "Repository access:     public anonymous HTTPS\n",
        path,
    )
    content = replace_once(
        content,
        "`Deploy key ready` may show `yes` on a supported rerun after the key has already been\nregistered.\n\n",
        "",
        path,
    )
    content = replace_once(
        content,
        "If GitHub prompts for credentials during `git pull`, use the same temporary credentials\nspecified in step 3. Re-running `prepare` before `finalize` is supported.\n",
        "`git pull` must not prompt for credentials. Re-running `prepare` before `finalize` is supported.\n",
        path,
    )

    step5 = '''## 5. Verify anonymous repository access

Verify that the checkout can read the public repository without credentials:

```bash
GIT_TERMINAL_PROMPT=0 git ls-remote \\
  https://github.com/MatthewFreeman/discrete-infrastructure.git \\
  HEAD
```

Expected result: a commit SHA followed by `HEAD`, without a username, password, token, or SSH-key
prompt. Do not continue if anonymous HTTPS access fails.

---

'''
    content = replace_section(
        content,
        "## 5. Register the GitHub deploy key\n",
        "## 6. Test both IPv4 SSH access paths\n",
        step5,
        path,
    )

    content = replace_once(
        content,
        "5. verify the read-only GitHub deploy key;\n",
        "5. verify anonymous HTTPS access to the public repository;\n",
        path,
    )
    content = replace_once(
        content,
        "Git origin:            git@github-discrete:MatthewFreeman/discrete-infrastructure.git\n",
        "Git origin:            https://github.com/MatthewFreeman/discrete-infrastructure.git\n",
        path,
    )
    content = replace_once(
        content,
        "The VPS deploy key is read-only. Edit and commit managed configuration from GitHub or a\ntrusted workstation.\n",
        "The VPS uses anonymous HTTPS for read-only pulls. Edit and commit managed configuration from\nGitHub or a trusted workstation.\n",
        path,
    )

    write(path, content)


def migrate_ubuntu_runbook() -> None:
    path = "docs/bootstrap-ubuntu-24.04-from-zero.md"
    content = read(path)

    step4 = '''## 4. Install Git and clone the public repository

From the root shell:

```bash
apt-get update
apt-get install -y ca-certificates git
```

Clone the public repository anonymously over HTTPS:

```bash
git clone \\
  https://github.com/MatthewFreeman/discrete-infrastructure.git \\
  /opt/discrete-infrastructure

cd /opt/discrete-infrastructure
```

A GitHub account, personal access token, deploy key, username, and password are not required.
Do not configure a Git credential helper on the VPS.

Confirm the selected operating system before changing the host:

```bash
. /etc/os-release
printf 'ID=%s VERSION_ID=%s\\n' "$ID" "$VERSION_ID"
```

Required output:

```text
ID=ubuntu VERSION_ID=24.04
```

---

'''
    content = replace_section(
        content,
        "## 4. Install Git and clone the private repository\n",
        "## 5. Run the Ubuntu `prepare` phase\n",
        step4,
        path,
    )

    content = replace_once(
        content,
        "15. generate a dedicated read-only GitHub deploy key.\n",
        "15. verify anonymous HTTPS access to the public repository.\n",
        path,
    )
    content = content.replace(
        "Deploy key ready:      no\n",
        "Repository access:     public anonymous HTTPS\n",
    )
    content = replace_once(
        content,
        "`Deploy key ready` may show `yes` on a supported rerun after the key was registered.\n\n",
        "",
        path,
    )

    step6 = '''## 6. Verify anonymous repository access

Verify from the VPS:

```bash
GIT_TERMINAL_PROMPT=0 git ls-remote \\
  https://github.com/MatthewFreeman/discrete-infrastructure.git \\
  HEAD
```

Expected result: a commit SHA followed by `HEAD`, without a username, password, token, or SSH-key
prompt. Do not continue if anonymous HTTPS access fails.

---

'''
    content = replace_section(
        content,
        "## 6. Register the read-only GitHub deploy key\n",
        "## 7. Test both fresh IPv4 SSH paths\n",
        step6,
        path,
    )

    content = replace_once(
        content,
        "Git origin:            git@github-discrete:MatthewFreeman/discrete-infrastructure.git\n",
        "Git origin:            https://github.com/MatthewFreeman/discrete-infrastructure.git\n",
        path,
    )

    content = replace_once(
        content,
        "## 13. Normal future Ubuntu updates\n\n```bash\n",
        "## 13. Normal future Ubuntu updates\n\nThe VPS uses anonymous HTTPS for read-only pulls.\n\n```bash\n",
        path,
    )

    write(path, content)


def migrate_readme() -> None:
    path = "README.md"
    content = read(path)
    content = replace_once(
        content,
        "Infrastructure-as-code repository for deploying and maintaining public Discrete.cash nodes.\n",
        "Infrastructure-as-code repository for deploying and maintaining public Discrete.cash nodes.\n\n"
        "This repository is public. Cloning and pulling over HTTPS require no GitHub account, personal\n"
        "access token, deploy key, username, or password.\n",
        path,
    )
    write(path, content)


def add_public_access_workflow() -> None:
    path = ROOT / ".github/workflows/validate-public-access.yml"
    content = '''name: Validate public repository access

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  validate-public-access:
    runs-on: ubuntu-latest

    steps:
      - name: Check out repository
        uses: actions/checkout@v4

      - name: Reject private-bootstrap authentication
        run: |
          test ! -e docs/create-github-access-token.md

          if git grep -n -E \\
            'github-discrete|discrete_infrastructure_deploy|github_pat_|create-github-access-token|DEPLOY_KEY|SSH_ALIAS' \\
            -- . \\
            ':(exclude).github/scripts/migrate-public-bootstrap.py' \\
            ':(exclude).github/workflows/migrate-public-bootstrap.yml' \\
            ':(exclude).github/workflows/validate-public-access.yml'; then
            echo 'Private-repository authentication remains in the current tree.' >&2
            exit 1
          fi

          grep -F 'verify_public_repository_access()' bootstrap/debian-ipv4.sh
          grep -F 'Repository access:     public anonymous HTTPS' bootstrap/debian-ipv4.sh
          grep -F 'https://github.com/MatthewFreeman/discrete-infrastructure.git' \\
            docs/bootstrap-from-zero.md
          grep -F 'https://github.com/MatthewFreeman/discrete-infrastructure.git' \\
            docs/bootstrap-ubuntu-24.04-from-zero.md

      - name: Prove anonymous HTTPS read access
        run: |
          GIT_TERMINAL_PROMPT=0 git \\
            -c credential.helper= \\
            -c http.https://github.com/.extraheader= \\
            ls-remote \\
            https://github.com/MatthewFreeman/discrete-infrastructure.git \\
            HEAD
'''
    path.write_text(content, encoding="utf-8")


def remove_obsolete_token_guide() -> None:
    path = ROOT / "docs/create-github-access-token.md"
    if not path.exists():
        raise RuntimeError("obsolete token guide is already missing before migration")
    path.unlink()


def verify_tree() -> None:
    excluded = {
        ".github/scripts/migrate-public-bootstrap.py",
        ".github/workflows/migrate-public-bootstrap.yml",
        ".github/workflows/validate-public-access.yml",
    }
    forbidden = re.compile(
        r"github-discrete|discrete_infrastructure_deploy|github_pat_|"
        r"create-github-access-token|DEPLOY_KEY|SSH_ALIAS"
    )

    failures: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative in excluded:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if forbidden.search(text):
            failures.append(relative)

    if failures:
        raise RuntimeError(f"private bootstrap references remain: {failures}")

    if (ROOT / "docs/create-github-access-token.md").exists():
        raise RuntimeError("obsolete token guide still exists")


migrate_debian_script()
migrate_debian_runbook()
migrate_ubuntu_runbook()
migrate_readme()
remove_obsolete_token_guide()
add_public_access_workflow()
verify_tree()
