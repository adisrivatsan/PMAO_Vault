import argparse
import sys
from pathlib import Path


def cmd_init(args) -> None:
    from pmao.vault import init_vault, seed_from_csv
    vault = Path(args.vault)
    for marker in ("project-config.yaml", "initiatives.json"):
        if (vault / marker).exists():
            print(f"Error: {vault} already contains {marker} — refusing to overwrite "
                  f"an existing vault. Delete the directory first to re-init.", file=sys.stderr)
            sys.exit(1)
    project_name = input("Project name: ").strip() or "My Project"
    owner = input("Primary owner/project manager: ").strip()
    init_vault(vault, project_name=project_name, owner=owner)
    print(f"Vault created: {vault.resolve()}")
    print(f"  project-config.yaml — project settings")
    print(f"  SCHEMA.md           — vault conventions (read by the LLM on ingest)")
    print(f"  projects/ tasks/ people/ meetings/ decisions/ notes/ docs/ inbox/")
    print(f"                      — one markdown file per item (seed projects via --roster FILE)")
    print(f"  workbook.xlsx       — blank workbook ready")
    if args.roster:
        count = seed_from_csv(vault, Path(args.roster))
        print(f"  Seeded {count} initiatives from {Path(args.roster).name}")


def cmd_migrate(args) -> None:
    from pmao.migrate import migrate_vault
    for folder, n in migrate_vault(Path(args.vault)).items():
        print(f"{folder}: {n}")


def cmd_ingest(args) -> None:
    from pmao.ingest import run_ingest
    run_ingest(
        vault_path=Path(args.vault),
        source_path=Path(args.source),
        yes=args.yes,
        config_override=args.backend,
    )


def cmd_status(args) -> None:
    from pmao.ingest import run_status
    run_status(vault_path=Path(args.vault), config_override=args.backend)


def cmd_summarize(args) -> None:
    from pmao.ingest import run_summarize
    run_summarize(vault_path=Path(args.vault), config_override=args.backend)


def cmd_lint(args) -> None:
    if args.stale_days < 1:
        print("Error: --stale-days must be >= 1", file=sys.stderr)
        sys.exit(1)
    from pmao.ingest import run_lint
    run_lint(
        vault_path=Path(args.vault),
        stale_days=args.stale_days,
        config_override=args.backend,
    )


def cmd_export(args) -> None:
    from pmao.vault import load_initiatives, refresh_workbook
    vault = Path(args.vault)
    initiatives = load_initiatives(vault)
    refresh_workbook(vault)
    print(f"Exported {len(initiatives)} initiatives to {(vault / 'workbook.xlsx').resolve()}")


def cmd_config(args) -> None:
    vault = Path(args.vault)
    config_path = vault / "project-config.yaml"
    if not config_path.exists():
        print(f"Error: No project-config.yaml found in {vault}", file=sys.stderr)
        sys.exit(1)
    print(config_path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser(prog="pmao", description="Project management assistant orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize a vault")
    p_init.add_argument("vault", help="Path to vault directory")
    p_init.add_argument("--roster", metavar="FILE", help="Seed initiative list from CSV (id,name,owner,priority)")
    p_init.set_defaults(func=cmd_init)

    p_migrate = sub.add_parser("migrate", help="Convert an old JSON vault to the folder layout")
    p_migrate.add_argument("vault", help="Path to vault directory")
    p_migrate.set_defaults(func=cmd_migrate)

    p_ingest = sub.add_parser("ingest", help="Ingest source material and extract updates")
    p_ingest.add_argument("vault", help="Path to vault directory")
    p_ingest.add_argument("--source", required=True, metavar="FILE", help=".vtt, .txt, or .md source file")
    p_ingest.add_argument("--yes", action="store_true", help="Apply without confirmation prompt")
    p_ingest.add_argument("--backend", choices=["claude", "codex"], default=None)
    p_ingest.set_defaults(func=cmd_ingest)

    p_status = sub.add_parser("status", help="Print status dashboard")
    p_status.add_argument("vault", help="Path to vault directory")
    p_status.add_argument("--backend", choices=["claude", "codex"], default=None)
    p_status.set_defaults(func=cmd_status)

    p_summarize = sub.add_parser("summarize", help="Produce executive summary")
    p_summarize.add_argument("vault", help="Path to vault directory")
    p_summarize.add_argument("--backend", choices=["claude", "codex"], default=None)
    p_summarize.set_defaults(func=cmd_summarize)

    p_lint = sub.add_parser("lint", help="Health check — find stale, incomplete, and contradictory state")
    p_lint.add_argument("vault", help="Path to vault directory")
    p_lint.add_argument("--stale-days", type=int, default=30, metavar="N",
                        help="Flag initiatives not touched in N days (default: 30)")
    p_lint.add_argument("--backend", choices=["claude", "codex"], default=None)
    p_lint.set_defaults(func=cmd_lint)

    p_export = sub.add_parser("export", help="Regenerate workbook.xlsx from project state")
    p_export.add_argument("vault", help="Path to vault directory")
    p_export.set_defaults(func=cmd_export)

    p_config = sub.add_parser("config", help="View project configuration")
    p_config.add_argument("vault", help="Path to vault directory")
    p_config.set_defaults(func=cmd_config)

    args = parser.parse_args()
    try:
        args.func(args)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        _cls = type(e).__name__
        print(f"{_cls}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
