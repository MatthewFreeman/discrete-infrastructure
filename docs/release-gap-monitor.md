# Canonical release and deployment gap monitor

The scheduled GitHub Action in this repository checks every active public repository in the
`discretecoin` organization every six hours and can also be run manually. It is read-only: it does not
merge, tag, publish, deploy, open issues, or modify another repository.

The current inventory is public, so the workflow works without a secret. GitHub's built-in
`GITHUB_TOKEN` is deliberately not used for cross-repository reads because it is scoped to this
repository. If private repositories are added or unauthenticated API limits become a problem, add a
read-only GitHub App token or fine-grained token as the `DISCRETE_MONITOR_TOKEN` repository secret.

## What makes the run fail

- A canonical branch contains commits after its latest stable GitHub release.
- A release tag is not an ancestor of the configured canonical branch.
- The exact current source SHA of a direct GitHub Pages repository has no successful deployment.
- The exact current source SHA of a workflow-published Pages repository has no successful deploy
  workflow run.
- A new active public repository appears without an explicit monitoring policy.
- Required GitHub evidence cannot be read or a configured default branch no longer matches GitHub.

The failing run summary names the repository, exact source SHA, release or deployment evidence,
and the latest 25 unreleased commits. Pull request links are included when the commit subject contains a
PR number.

## Policy file

`monitoring/release-gap/config.json` is the canonical inventory. Supported policy kinds are:

- `release`: compare the latest stable release tag with the canonical branch.
- `pages-direct`: require a successful deployment for the exact canonical-branch SHA.
- `pages-workflow`: require a successful named deployment workflow run for the exact source SHA.

Repository discovery deliberately fails closed. When a new active public repository is added to
the organization, the monitor stays red until its release/deployment policy is added.

## Evidence boundary

A merge is not a release, and a release is not proof that a production process or VPS runs that
version. The Core and desktop-wallet policies detect unreleased source only. Production deployment
claims require a separate authenticated receipt emitted by the actual deployment path, such as a
GitHub deployment tied to the deployed commit or release asset digest.

For GitHub Pages repositories, GitHub's deployment/workflow records are the observed delivery
evidence. The monitor does not probe user-visible page content.

## Operator use

Open **Actions → Monitor canonical release and deployment gaps**. A green run means all configured
GitHub evidence is current within the boundaries above. A red run requires inspecting its summary
or the retained `release-gap-report` artifact.

Enable GitHub Actions web or email notifications in the account notification settings, preferably
for failed workflows only. GitHub sends scheduled-workflow notifications to the user who last
changed the cron schedule. The README badge is a second visible indicator.

GitHub can disable scheduled workflows in a public repository after 60 days without repository
activity. If this repository becomes dormant, re-enable the workflow in the Actions tab or change
the schedule in a normal reviewed commit.

Local validation:

```bash
node --test monitoring/release-gap/monitor.test.mjs
node --check monitoring/release-gap/monitor.mjs
node monitoring/release-gap/monitor.mjs --fail-on-gap=false
```

The last command queries live public GitHub state and writes `release-gap-report.json` and
`release-gap-report.md` in the current directory.
