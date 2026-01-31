# Pycron CLI

Schedule Python scripts on **macOS** using `launchd` with cron-like syntax.

Perfect for executing **standalone Python scripts** as scheduled tasks on macOS, in a quick and easy way to manage.

<img src="--help.png" width="600" alt="pycron help">

<img src="--status.png" width="600" alt="pycron status">

> ⚠️ Uses macOS launchd, NOT cron. Accepts a cron-like subset and translates it to launchd.

## Quick Start

```bash
# Every 5 minutes
pycron add --name my-task --py /path/to/script.py --cron "*/5 * * * *"

# Weekdays at 9:00
pycron add --name morning --py /path/to/report.py --cron "0 9 * * 1-5"

# Check status
pycron status --name my-task

# View logs
pycron logs --name my-task

# List all tasks
pycron list

# Remove
pycron remove --name my-task
```

## Cron Syntax (Subset)

```
┌─────── minute (0-59)
│ ┌───── hour (0-23)  
│ │ ┌─── day of month (must be *)
│ │ │ ┌─ month (must be *)
│ │ │ │ ┌ day of week (0-6, 0=Sun)
* * * * *
```

| Pattern | Example | Description |
|---------|---------|-------------|
| `*/N * * * *` | `*/5 * * * *` | Every N minutes |
| `M H * * *` | `0 9 * * *` | Daily at H:M |
| `M H * * DOW` | `0 9 * * 1-5` | Specific days at H:M |
| `M H1,H2 * * *` | `0 9,18 * * *` | Multiple hours |

**Not supported:** day of month, month, minute ranges, named days, @hourly/@daily.

## Commands

| Command | Description |
|---------|-------------|
| `add` | Add or update a task |
| `status` | Check task status (shows last run time & execution count) |
| `logs` | View task logs |
| `stop` | Stop running task |
| `reload` | Reload registered task |
| `remove` | Remove a task |
| `remove-all` | Remove all tasks |
| `list` | List all tasks |

## Persistence

Tasks are **saved on disk** and will continue to run after your Mac reboots or shuts down. When you restart your machine and log in, all scheduled tasks will automatically resume.

## Requirements

- macOS 10.15+
- Python 3.11+

## License

MIT
