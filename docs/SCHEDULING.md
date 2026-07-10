# Scheduling

Run daily generation after the data window closes and weekly generation once per week. Start in synthetic mode to avoid provider costs. Advanced SSH & Web Terminal must remain installed, protected, and running; this project never restarts or uninstalls it.

Example Home Assistant automation using an intentionally narrow command exposed by your terminal environment:

```yaml
automation:
  - alias: Personal video daily
    triggers:
      - trigger: time
        at: "06:15:00"
    actions:
      - action: shell_command.personal_video_daily
```

Do not place `SUPERVISOR_TOKEN` or provider keys in automation YAML. Prefer an in-environment scheduler if cross-add-on shell commands are unavailable.

