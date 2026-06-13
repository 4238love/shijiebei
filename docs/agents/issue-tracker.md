# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues in `4238love/shijiebei`.

Use the `gh` CLI for all operations. Prefer running commands from a clone with `origin` set to `https://github.com/4238love/shijiebei.git`; if the remote is unavailable, pass `--repo 4238love/shijiebei` explicitly.

## Conventions

- **Create an issue**: `gh issue create --repo 4238love/shijiebei --title "..." --body "..."`
- **Read an issue**: `gh issue view <number> --repo 4238love/shijiebei --comments`
- **List issues**: `gh issue list --repo 4238love/shijiebei --state open --json number,title,body,labels,comments`
- **Comment on an issue**: `gh issue comment <number> --repo 4238love/shijiebei --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --repo 4238love/shijiebei --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --repo 4238love/shijiebei --comment "..."`

## When a skill says "publish to the issue tracker"

Create a GitHub issue in `4238love/shijiebei`.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --repo 4238love/shijiebei --comments`.
