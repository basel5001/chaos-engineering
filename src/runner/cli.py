"""CLI entrypoint for the chaos engineering runner."""
import json
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from src.runner.orchestrator import (
    ExperimentPlan,
    load_plan_from_yaml,
    run_experiment,
    generate_report,
    results_to_dicts,
)

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure structured logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@click.command()
@click.option("--manifest", "-m", required=True, type=click.Path(exists=True), help="Experiment plan YAML file")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate experiments without executing")
@click.option("--analyze", is_flag=True, default=False, help="Run AI analysis on results via AWS Bedrock")
@click.option("--output", "-o", type=click.Choice(["markdown", "json", "table"]), default="table", help="Output format")
@click.option("--outfile", type=click.Path(), default=None, help="Write results to file")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Verbose logging")
def main(manifest: str, dry_run: bool, analyze: bool, output: str, outfile: str | None, verbose: bool) -> None:
    """Chaos Engineering Runner — execute experiment plans against Kubernetes clusters."""
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    # Load plan
    console.print(f"\n[bold blue]Loading experiment plan:[/] {manifest}")
    plan = load_plan_from_yaml(manifest)
    console.print(f"[bold]Plan:[/] {plan.name}")
    console.print(f"[dim]{plan.description}[/]")
    console.print(f"[bold]Experiments:[/] {len(plan.experiments)}")

    if dry_run:
        console.print("[yellow]DRY RUN MODE — no changes will be made[/]\n")

    # Run experiments
    console.print("[bold green]Running experiments...[/]\n")
    results = run_experiment(plan, dry_run=dry_run)

    # AI Analysis
    if analyze:
        console.print("\n[bold purple]Running AI analysis via AWS Bedrock...[/]")
        try:
            from src.ai.analyzer import analyze_results
            analysis = analyze_results(results_to_dicts(results))
            for r in results:
                r.ai_analysis = analysis
            console.print("[green]AI analysis complete.[/]")
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            console.print(f"[red]AI analysis failed: {e}[/]")

    # Output results
    if output == "table":
        _print_table(results)
    elif output == "markdown":
        md = generate_report(results)
        console.print(md)
    elif output == "json":
        console.print_json(json.dumps(results_to_dicts(results), indent=2, default=str))

    # Write to file
    if outfile:
        outpath = Path(outfile)
        outpath.parent.mkdir(parents=True, exist_ok=True)
        if outfile.endswith(".json"):
            outpath.write_text(json.dumps(results_to_dicts(results), indent=2, default=str))
        else:
            outpath.write_text(generate_report(results))
        console.print(f"\n[green]Results written to:[/] {outfile}")

    # Summary
    passed = sum(1 for r in results if r.status == "completed")
    failed = sum(1 for r in results if r.status == "failed")
    console.print(f"\n[bold]Summary:[/] {passed} passed, {failed} failed, {len(results)} total")

    if failed > 0:
        sys.exit(1)


def _print_table(results: list) -> None:
    """Print results as a rich table."""
    table = Table(title="Experiment Results")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Namespace")
    table.add_column("Status")
    table.add_column("Duration", justify="right")

    for r in results:
        status_style = "green" if r.status == "completed" else "red" if r.status == "failed" else "yellow"
        table.add_row(
            r.name,
            r.type,
            r.namespace,
            f"[{status_style}]{r.status}[/]",
            f"{r.duration_seconds:.1f}s",
        )

    console.print(table)


if __name__ == "__main__":
    main()
