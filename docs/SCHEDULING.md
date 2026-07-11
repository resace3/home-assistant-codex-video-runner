# Scheduling

The supported scheduler runs inside the **Personal Video Runner** Home Assistant app. Configure `daily_time`, `weekly_day`, and `weekly_time` in the app options. Monday is day `0`; Sunday is day `6`.

This removes the unsupported cross-app `shell_command` bridge and survives host or app restarts. Do not place `SUPERVISOR_TOKEN` or provider keys in automation YAML. Supervisor injects the token into the runner app at runtime.

Advanced SSH & Web Terminal is not involved in scheduling and is never stopped, restarted, uninstalled, or reconfigured by this project.
