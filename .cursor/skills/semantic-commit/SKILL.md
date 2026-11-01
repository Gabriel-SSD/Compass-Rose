---
name: semantic-commit
description: Writes git commit messages in Conventional Commits. Use only when the user explicitly asks for a semantic commit or names this skill.
disable-model-invocation: true
---

# Semantic commit

Write the commit message in Conventional Commits. Create the commit only when the user asks to commit, and follow the repository git protocol.

## Format

```
type(scope): subject

Optional body explaining why.

BREAKING CHANGE: description
```

`scope` is optional.

## Types

`feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`

## Subject

- Imperative mood
- Lowercase
- No trailing period
- About 72 characters or fewer
- Body, when present, explains why

## Breaking changes

Use `type!:` or a `BREAKING CHANGE:` footer.

## Examples

```
feat(dags): add open-meteo extract task

Pull the daily forecast so downstream tasks can read a stable file.
```

```
fix(storage): wait for the manual file before parsing

The sensor was succeeding on an empty prefix.
```

```
docs: describe local astro commands
```
