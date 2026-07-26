# Create the Temporary GitHub Bootstrap Token

This token is used only to clone the private `MatthewFreeman/discrete-infrastructure` repository
onto a new VPS. After the repository deploy key works, delete the token.

> **Security boundary**
>
> Create a **fine-grained personal access token**, restrict it to this single repository, and grant
> only **Contents: Read-only**. Do not use a classic token and do not grant write permissions.

## 1. Open the token settings

Sign in to GitHub in a browser, then open:

[GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens](https://github.com/settings/personal-access-tokens)

Click **Generate new token**.

The equivalent menu path is:

```text
Profile picture
→ Settings
→ Developer settings
→ Personal access tokens
→ Fine-grained tokens
→ Generate new token
```

## 2. Configure the token

Use these values:

| Field | Required value |
|---|---|
| Token name | `discrete-infrastructure bootstrap` |
| Description | `Temporary read-only token for initial VPS clone` |
| Expiration | `7 days` or the shortest practical expiration |
| Resource owner | `MatthewFreeman` |
| Repository access | **Only select repositories** |
| Selected repository | `discrete-infrastructure` |

Under **Repository permissions**, set:

| Permission | Access |
|---|---|
| Contents | **Read-only** |

Leave every other configurable repository and account permission at **No access**. GitHub may
show **Metadata: Read-only** automatically; that is expected.

Click **Generate token**.

## 3. Copy the token once

Copy the complete value beginning with:

```text
github_pat_
```

GitHub will not show the complete token again after leaving the page. Treat it as a password.
Do not paste it into chat, documentation, screenshots, shell commands, or the clone URL.

## 4. Use the token for the initial clone

Run the clone command exactly as shown in the bootstrap runbook. When Git asks for credentials:

```text
Username: <your GitHub username>
Password: <paste the temporary token>
```

Nothing may appear while pasting the token into a terminal password prompt. That is normal.
Press Enter once after pasting.

Do not enable plaintext credential storage. In particular, do not run:

```bash
git config --global credential.helper store
```

## 5. Delete the token after the deploy key works

Continue the bootstrap runbook through registration and verification of the repository deploy key.
After this command succeeds without a username or token prompt:

```bash
git ls-remote \
  git@github-discrete:MatthewFreeman/discrete-infrastructure.git \
  HEAD
```

return to:

[GitHub fine-grained personal access tokens](https://github.com/settings/personal-access-tokens)

Delete `discrete-infrastructure bootstrap`. The VPS will use its dedicated read-only deploy key
for future `git pull` operations.

## Troubleshooting

### The repository is not listed

Confirm that **Resource owner** is `MatthewFreeman` and that the signed-in GitHub account has
access to the private repository.

### Git reports `Repository not found`

The token is usually assigned to the wrong resource owner, the repository was not selected, or
**Contents: Read-only** was not granted. Edit or recreate the token with the exact values above.

### Git keeps rejecting the account password

GitHub account passwords are not accepted for HTTPS Git operations. Enter the GitHub username in
the username prompt and the `github_pat_...` token in the password prompt.

## Official GitHub reference

GitHub documents the current fine-grained token creation process here:

[Managing your personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
