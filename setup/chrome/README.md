# Chromium argv contract

This directory reserves the host check for a later QA browser. Step 3 does not start Chromium and does not install Playwright.

`chromium-argv.sh` refuses `--no-sandbox` and `--disable-setuid-sandbox`. A browser run under rootless, including a seccomp profile, belongs to the QA step.

If `playwright` or a Chromium binary is absent, the doctor records that the tool is not installed yet. That is not a failed startup.
