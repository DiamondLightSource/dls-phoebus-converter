# Golden master test

`test_front_ends` in `tests/integration/test_conversion_dls.py` converts the screens in
`config/front_ends.yaml` from `/dls_sw` and compares them with a golden master, kept in
<https://gitlab.diamond.ac.uk/controls/tools/phoebus-converted-files>. It needs `/dls_sw` and
the DLS network, so it does not run in CI.

From the repo root, clone the golden master to `tests/golden_master/`, which is gitignored,
and check out the commit in the test's `GOLDEN_MASTER_COMMIT`:

```bash
git clone https://gitlab.diamond.ac.uk/controls/tools/phoebus-converted-files.git tests/golden_master
git -C tests/golden_master checkout <GOLDEN_MASTER_COMMIT>
```

Before converting, the test fails if the clone is at another commit or `front_ends/` has
uncommitted changes, and prints the command that fixes it.

pytest skips the test unless given `--run-dls`. From the repo root:

```bash
pytest --run-dls tests/integration/test_conversion_dls.py
```
