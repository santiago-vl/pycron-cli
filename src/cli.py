"""CLI for pycron - schedule Python scripts on macOS using launchd."""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from src import __version__
from src.cron_parse import CronParseError, format_schedule, parse_cron
from src.launchd import (
    LaunchdError,
    create_plist,
    create_wrapper,
    get_status,
    load,
    remove,
    stop,
    unload,
    validate_plist,
)
from src.paths import LAUNCH_AGENTS_DIR, get_log_path, get_username

app = typer.Typer(name="pycron", help="Schedule Python scripts on macOS using launchd.", add_completion=False)
console = Console()

EXIT_CODE_MESSAGES = {
    0: "Success",
    1: "General Error",
    2: "Misuse of shell command",
    126: "Command cannot execute",
    127: "Command not found",
    128: "Invalid exit argument",
    130: "Terminated by Ctrl+C",
    137: "Killed (SIGKILL)",
    139: "Segmentation fault",
    143: "Terminated (SIGTERM)",
}


def _get_exit_message(code: int) -> str:
    return EXIT_CODE_MESSAGES.get(code, f"Error (code {code})")


def _get_log_stats(log_path: Path) -> tuple[int, str | None, str | None, bool | None]:
    if not log_path.exists():
        return 0, None, None, None

    try:
        content = log_path.read_text()
        lines = content.splitlines()

        run_count = sum(1 for l in lines if '] START' in l)

        last_run = None
        for line in reversed(lines):
            if '] START' in line and line.startswith('[') and ']' in line:
                last_run = line[1:line.index(']')]
                break

        last_error_time = None
        for line in reversed(lines):
            if '] END (error' in line and line.startswith('[') and ']' in line:
                last_error_time = line[1:line.index(']')]
                break

        last_was_success = None
        for line in reversed(lines):
            if '] END (success)' in line:
                last_was_success = True
                break
            elif '] END (error' in line:
                last_was_success = False
                break

        if not last_run and lines:
            mtime = log_path.stat().st_mtime
            last_run = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            run_count = len([l for l in lines if l.strip()])

        return run_count, last_run, last_error_time, last_was_success
    except Exception:
        return 0, None, None, None


def _version_callback(value: bool) -> None:
    if value:
        rprint(f"pycron-cli {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[Optional[bool], typer.Option("--version", "-v", callback=_version_callback, is_eager=True)] = None,
) -> None:
    pass


@app.command()
def add(
    name: Annotated[str, typer.Option("--name", "-n", help="Task name")],
    py: Annotated[Path, typer.Option("--py", "-p", help="Python script path")],
    cron: Annotated[str, typer.Option("--cron", "-c", help="Cron expression (5 fields)")],
    workdir: Annotated[Optional[Path], typer.Option("--workdir", "-w", help="Working directory")] = None,
    python: Annotated[str, typer.Option("--python", help="Python interpreter")] = "/usr/bin/python3",
) -> None:
    """Add or update a scheduled task."""
    py = py.resolve()
    if not py.is_file():
        rprint(f"[red]Error:[/red] Script not found: {py}")
        raise typer.Exit(1)

    if not Path(python).exists():
        rprint(f"[red]Error:[/red] Python not found: {python}")
        raise typer.Exit(1)

    workdir = (workdir or py.parent).resolve()
    if not workdir.is_dir():
        rprint(f"[red]Error:[/red] Workdir not found: {workdir}")
        raise typer.Exit(1)

    try:
        schedule = parse_cron(cron)
    except CronParseError as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    status = get_status(name)
    if status["loaded"]:
        rprint(f"[yellow]Updating existing task '{name}'...[/yellow]")
        unload(name)

    try:
        wrapper = create_wrapper(name, py, workdir, python)
        rprint(f"[green]✓[/green] Wrapper: {wrapper}")

        plist = create_plist(name, wrapper, schedule)
        rprint(f"[green]✓[/green] Plist: {plist}")

        validate_plist(plist)
        load(name)
        rprint(f"[green]✓[/green] Loaded")

        rprint(f"\n[bold green]Task '{name}' scheduled![/bold green]")
        rprint(f"  Schedule: {format_schedule(schedule)}")
        rprint(f"  Logs: {get_log_path(name)}")
    except (LaunchdError, Exception) as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def status(name: Annotated[str, typer.Option("--name", "-n", help="Task name")]) -> None:
    """Check task status."""
    s = get_status(name)
    log = get_log_path(name)
    run_count, last_run, last_error_time, last_was_success = _get_log_stats(log)

    table = Table()
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Label", s["label"])
    table.add_row("Registered", "[green]Yes[/green]" if s["plist_exists"] else "[red]No[/red]")
    table.add_row("Status", "[green]Active[/green]" if s["loaded"] else "[yellow]Inactive[/yellow]" if s["plist_exists"] else "[red]Not found[/red]")
    table.add_row("PID", str(s["pid"]) if s["pid"] else "-")

    if last_was_success is not None:
        if last_was_success:
            table.add_row("Last Status", "[green]Success[/green]")
        else:
            table.add_row("Last Status", "[red]Error[/red]")
    elif s["exit_status"] is not None:
        exit_msg = _get_exit_message(s["exit_status"])
        if s["exit_status"] == 0:
            table.add_row("Last Status", f"[green]{exit_msg}[/green]")
        else:
            table.add_row("Last Status", f"[red]{exit_msg}[/red]")

    if last_run:
        table.add_row("Last Run", last_run)

    if last_error_time:
        table.add_row("Last Error", f"[red]{last_error_time}[/red]")

    if run_count > 0:
        table.add_row("Run Count", str(run_count))

    if log.exists():
        size = log.stat().st_size
        size_str = f"{size}B" if size < 1024 else f"{size/1024:.1f}KB" if size < 1048576 else f"{size/1048576:.1f}MB"
        table.add_row("Log", f"{size_str}")

    console.print(table)

    if not s["plist_exists"]:
        rprint(f"\n[yellow]Task '{name}' not found. Use 'pycron add' to create it.[/yellow]")
    elif not s["loaded"]:
        rprint(f"\n[dim]Task registered but not loaded. Run 'pycron reload --name {name}'[/dim]")


@app.command()
def logs(
    name: Annotated[str, typer.Option("--name", "-n", help="Task name")],
    tail: Annotated[int, typer.Option("--tail", "-t", help="Lines to show")] = 20,
) -> None:
    """View task logs."""
    log = get_log_path(name)
    if not log.exists():
        rprint(f"[yellow]No logs for '{name}' yet[/yellow]")
        raise typer.Exit(0)

    result = subprocess.run(["tail", f"-{tail}", str(log)], capture_output=True, text=True)
    rprint(f"[bold]Logs: {name}[/bold] (last {tail} lines)\n")
    print(result.stdout or "[dim]Empty[/dim]", end="")


@app.command(name="stop")
def stop_cmd(name: Annotated[str, typer.Option("--name", "-n", help="Task name")]) -> None:
    """Stop a running task."""
    s = get_status(name)
    if not s["loaded"]:
        rprint(f"[yellow]Task '{name}' not loaded[/yellow]")
        raise typer.Exit(0)

    stop(name)
    rprint(f"[green]✓[/green] Stopped '{name}'")


@app.command()
def reload(name: Annotated[str, typer.Option("--name", "-n", help="Task name")]) -> None:
    """Reload a registered task."""
    s = get_status(name)
    if not s["plist_exists"]:
        rprint(f"[red]Error:[/red] Task '{name}' not registered")
        raise typer.Exit(1)

    if s["loaded"]:
        rprint(f"[yellow]Already loaded[/yellow]")
        raise typer.Exit(0)

    load(name)
    rprint(f"[green]✓[/green] Reloaded '{name}'")


@app.command(name="remove")
def remove_cmd(
    name: Annotated[str, typer.Option("--name", "-n", help="Task name")],
    keep_logs: Annotated[bool, typer.Option("--keep-logs", help="Keep logs")] = False,
) -> None:
    """Remove a task."""
    s = get_status(name)
    if not s["plist_exists"] and not s["wrapper_exists"]:
        rprint(f"[yellow]Task '{name}' not found[/yellow]")
        raise typer.Exit(0)

    remove(name, keep_logs=keep_logs)
    rprint(f"[green]✓[/green] Removed '{name}'")


@app.command(name="remove-all")
def remove_all(
    keep_logs: Annotated[bool, typer.Option("--keep-logs", help="Keep logs")] = False,
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
) -> None:
    """Remove all tasks."""
    prefix = f"com.{get_username()}.pycron."
    tasks = [f.stem.replace(prefix, "") for f in LAUNCH_AGENTS_DIR.glob(f"{prefix}*.plist")]

    if not tasks:
        rprint("[dim]No tasks found[/dim]")
        raise typer.Exit(0)

    rprint(f"[yellow]Found {len(tasks)} task(s):[/yellow] " + ", ".join(tasks))

    if not force and not typer.confirm("Remove all?", default=False):
        rprint("[yellow]Aborted[/yellow]")
        raise typer.Exit(0)

    for t in tasks:
        try:
            remove(t, keep_logs=keep_logs)
            rprint(f"[green]✓[/green] {t}")
        except Exception as e:
            rprint(f"[red]✗[/red] {t}: {e}")

    rprint(f"\n[green]Done[/green]")


@app.command(name="list")
def list_tasks() -> None:
    """List all tasks."""
    prefix = f"com.{get_username()}.pycron."
    tasks = [(f.stem.replace(prefix, ""), get_status(f.stem.replace(prefix, ""))) for f in LAUNCH_AGENTS_DIR.glob(f"{prefix}*.plist")]

    if not tasks:
        rprint("[dim]No tasks. Use 'pycron add' to create one.[/dim]")
        raise typer.Exit(0)

    table = Table(title="Tasks")
    table.add_column("Name", style="cyan")
    table.add_column("Status")
    table.add_column("PID")
    table.add_column("Exit")

    for name, s in sorted(tasks):
        status_str = "[green]Active[/green]" if s["loaded"] else "[yellow]Registered[/yellow]"
        pid = str(s["pid"]) if s["pid"] else "-"
        exit_code = str(s["exit_status"]) if s["exit_status"] is not None else "-"
        if s["exit_status"] is not None:
            exit_code = f"[green]{exit_code}[/green]" if s["exit_status"] == 0 else f"[red]{exit_code}[/red]"
        table.add_row(name, status_str, pid, exit_code)

    console.print(table)



if __name__ == "__main__":
    app()
