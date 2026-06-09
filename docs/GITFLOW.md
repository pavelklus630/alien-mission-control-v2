# Git Flow — Mission Control v2

Solo-developer flow for `alien-mission-control-v2`. Optimized for one person
shipping a PyInstaller desktop app on a fast cadence. The v1 repo
(`alien-mission-control`) is **frozen** — this flow does not apply to it.

## Branching model: trunk-based + release tags

- **`main`** is the trunk. It is always releasable and `pytest` is green at
  every commit.
- **No long-lived branches.** No `develop`, no `release`, no `hotfix`.
- **Short-lived branches only when a change is risky or large** — something you
  might not finish in one sitting, or that could leave `main` broken halfway.

### Default: commit straight to `main`

Version bumps, DEVLOG, docs, and small confident fixes go directly to `main`.
As a solo dev there is no reviewer, so PRs add ceremony without payoff.

### Branch when it's risky

The branch is a **safety net**: if the work falls apart, `main` is untouched
and the branch can be thrown away.

```
git switch -c feat/sound-eq      # start risky work
... commit as you go ...
pytest                            # must be green before going back
git switch main
git merge feat/sound-eq           # fast-forward, no PR
git branch -d feat/sound-eq       # delete it
git push
```

### Branch naming

```
feat/<slug>          new capability          feat/sound-editor-eq
fix/<slug>           bug fix                 fix/mic-latency
chore/<slug>         build/deps/tooling      chore/pyinstaller-spec
docs/<slug>          DEVLOG/README only      docs/release-notes-2.4
experiment/<slug>    speculative, may never merge   experiment/realtime-fx
```

Use `experiment/` (not `feat/`) for speculative work so the branch list makes
clear it may be discarded. Keep experimental work behind a flag while in flux.

## Commit messages

Existing style — keep it:

- Release commits: `Mission Control v2.3.0 — Soundbank editor`
- Work commits: imperative, scoped — `Remove dead initWave() function; update DEVLOG`

## Release flow

Ties into the standard release process. **The release commit and its tag are
inseparable — no release ships without a matching `vX.Y.Z` annotated tag.**

```
1. pytest must pass
2. Bump BOTH __version__ (src/mission_control/__init__.py) AND CURRENT_VERSION
3. Update DEVLOG
4. Merge branch -> main (if work was on a branch)
5. git tag -a vX.Y.Z -m "Mission Control vX.Y.Z — <headline>"
6. git push origin main --follow-tags
7. build.sh -> zip
8. gh release create vX.Y.Z <asset>.zip
```

## Versioning

- **SemVer**: `MAJOR.MINOR.PATCH`, pre-release suffix `aN` / `bN`
  (e.g. `v2.0.0a0`).
- Tag name is `vX.Y.Z`. The git tag is the source of truth for what shipped.

## Day-to-day cheat sheet

| Situation | What you do |
|---|---|
| Small fix, version bump, DEVLOG | Commit to `main`, push |
| Big / risky / experimental feature | branch -> finish -> `pytest` -> merge to `main` -> delete branch |
| Shipping a release | bump both versions -> DEVLOG -> commit -> **tag** -> `push --follow-tags` -> `build.sh` -> `gh release` |

## Known drift to fix (one-time)

- Releases `v2.1.1`, `v2.2.0`, `v2.3.0` shipped **untagged**. Backfill:
  ```
  git tag -a v2.1.1 136dd52 -m "Mission Control v2.1.1 — Vibe scene editor"
  git tag -a v2.2.0 4211b7e -m "Mission Control v2.2.0 — Vibe scene redesign"
  git tag -a v2.3.0 1e63973 -m "Mission Control v2.3.0 — Soundbank editor"
  git push origin --tags
  ```
- `__version__` in `src/mission_control/__init__.py` is stale (`2.0.0a0`) and
  must be bumped to match the latest shipped release.
