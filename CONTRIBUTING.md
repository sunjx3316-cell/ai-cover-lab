# Contributing

Report Windows version, GPU/VRAM, driver version, application version and a
redacted error message. Do not upload personal recordings to public issues.
Preserve upstream license notices; keep model weights, runtimes and audio out of
Git. Original contributions are under the project's MIT license; third-party
components retain their own terms.

Run contract tests with the installed runtime:

```powershell
.\runtime\python\python.exe -m unittest test_contracts -v
```

For an online installation, use `envs\ying\Scripts\python.exe` instead.
GPU integration checks need authorized test inputs and are not audio-quality
benchmarks. Do not use the bundled character model as an automatic test fixture
for public CI or upload generated audio as part of tests.
