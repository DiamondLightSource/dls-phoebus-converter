# Conversion tests

## Golden master test

`test_front_ends` in `tests/integration/test_conversion_dls.py` converts the screens in
`config/front_ends.yaml` from `/dls_sw` and compares them with a golden master, kept in
<https://gitlab.diamond.ac.uk/controls/tools/phoebus-converted-files>. It needs
`/dls_sw` and the DLS network, so it does not run in CI.

From the repo root, clone the golden master to `tests/test_data/dls_golden_master/`,
which is gitignored, and check out the commit in the test's `GOLDEN_MASTER_COMMIT`:

```bash
git clone https://gitlab.diamond.ac.uk/controls/tools/phoebus-converted-files.git tests/test_data/dls_golden_master
git -C tests/test_data/dls_golden_master checkout <GOLDEN_MASTER_COMMIT>
```

Before converting, the test fails if the clone's `front_ends/` does not match the pinned
commit or has uncommitted changes, and says how to fix it. Commits that leave
`front_ends/` alone, such as merge commits, need no new pin.

pytest skips the test unless given `--run-dls`. From the repo root:

```bash
pytest --run-dls tests/integration/test_conversion_dls.py
```

## Updating the golden master

When a converter change alters the output on purpose:

1. Branch the clone from the pin:
   `git -C tests/test_data/dls_golden_master switch -c <branch>`.
2. Run the "Regenerate golden master" VS Code task, or
   `tests/regenerate_golden_master.sh`. It runs the test and replaces
   `tests/test_data/dls_golden_master/front_ends/` with the output.
3. Review the changes, commit them, and push the branch. After
   `git -C tests/test_data/dls_golden_master add -A`,
   `git -C tests/test_data/dls_golden_master diff --cached` shows new files as well as
   changed ones.
4. Set `GOLDEN_MASTER_COMMIT` to
   `git -C tests/test_data/dls_golden_master rev-parse HEAD`, in the converter commit
   that changed the output, and check the test passes.
5. Merge the golden master merge request before the converter change. The golden master
   repo merges with merge commits, so the pinned commit stays in `main`'s history.

If another golden master change merges first, rebase the converter branch, check out its
new pin in the clone, and start again from step 1.

## CI tests

Each test in `tests/integration/test_conversion_ci.py` converts screens from
`tests/test_data/opi_files/` with one of the `config/example*.yaml` configs, and
compares the files in its `files_to_compare` with their references in
`tests/test_data/bob_files/`.

When a change alters those files on purpose, run each failing test on its own, then copy
the files it compares from `test_output/` over their references. Each test empties
`test_output/` first, so copy before running the next one.
