"""VECTOR telemetry CLI.

Query the SQLite telemetry store written by core.inference.ollama_safe.

Usage:
    python -m vectorcode.src.vector_cli.telemetry_cmd stats [--hours N] [--model NAME]
    python -m vectorcode.src.vector_cli.telemetry_cmd leaderboard [--hours N]
    python -m vectorcode.src.vector_cli.telemetry_cmd model <name>
    python -m vectorcode.src.vector_cli.telemetry_cmd live [--limit N]
    python -m vectorcode.src.vector_cli.telemetry_cmd export <out.csv> [--hours N]
    python -m vectorcode.src.vector_cli.telemetry_cmd capabilities
    python -m vectorcode.src.vector_cli.telemetry_cmd clear --yes

Subcommands:
    stats         — summary across last N hours (default 24): calls, tokens,
                    joules, mean watts, mean latency, total cost
    leaderboard   — ranks models by tokens-per-joule (energy efficiency)
    model NAME    — full breakdown for one model
    live          — tail the most recent N inference records (default 20)
    export        — CSV/JSON dump of last N hours of records
    capabilities  — show which telemetry subsystems are wired (gpu / energy / etc.)
    clear --yes   — wipe the telemetry table (requires --yes confirmation)
"""
from __future__ import annotations
from loguru import logger

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Locate the telemetry DB the same way ollama_safe.py does
_DEFAULT_DB = Path(__file__).resolve().parent.parent.parent.parent / "data" / "telemetry.db"


def _open(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        print(f"[!] telemetry DB not found at {db_path}")
        print("    Make some chat() calls in VECTOR first, then re-run this command.")
        sys.exit(1)
    return sqlite3.connect(db_path, check_same_thread=False)


def _human_joules(j: float) -> str:
    if j >= 3600:
        return f"{j/3600:.2f} Wh"
    if j >= 1:
        return f"{j:.1f} J"
    return f"{j*1000:.1f} mJ"


def _hours_filter(hours: int | None) -> str:
    """Return WHERE-clause snippet, or empty string for all-time."""
    if hours is None or hours <= 0:
        return ""
    cutoff = f"strftime('%s','now') - {hours * 3600}"
    return f"WHERE timestamp >= {cutoff}"


# ── stats ────────────────────────────────────────────────────────────────────


def cmd_stats(args: argparse.Namespace) -> int:
    db = _open(args.db)
    where = _hours_filter(args.hours)
    if args.model:
        where = f"{where} AND model_id = ?" if where else "WHERE model_id = ?"
    params: tuple = (args.model,) if args.model else ()

    q = f"""
        SELECT
            COUNT(*),
            COALESCE(SUM(prompt_tokens),0),
            COALESCE(SUM(completion_tokens),0),
            COALESCE(SUM(total_tokens),0),
            COALESCE(SUM(energy_joules),0),
            COALESCE(AVG(power_watts),0),
            COALESCE(AVG(latency_seconds),0),
            COALESCE(AVG(throughput_tok_per_sec),0),
            COALESCE(SUM(cost_usd),0),
            COALESCE(AVG(gpu_utilization_pct),0),
            COALESCE(AVG(gpu_temperature_c),0)
        FROM telemetry
        {where}
    """
    row = db.execute(q, params).fetchone()
    (calls, p_tok, c_tok, t_tok, j, w, lat, tps, cost, util, temp) = row

    label = "All time" if not args.hours else f"Last {args.hours}h"
    if args.model:
        label += f" — model={args.model}"

    print(f"VECTOR Telemetry — {label}")
    print("─" * 60)
    print(f"  Calls:                 {calls:>15,}")
    print(f"  Prompt tokens:         {p_tok:>15,}")
    print(f"  Completion tokens:     {c_tok:>15,}")
    print(f"  Total tokens:          {t_tok:>15,}")
    print(f"  Total energy:          {_human_joules(j):>15}")
    print(f"  Avg power:             {w:>13.2f} W")
    print(f"  Avg latency:           {lat:>13.2f} s")
    print(f"  Avg throughput:        {tps:>13.2f} tok/s")
    if c_tok > 0 and j > 0:
        print(f"  Avg J / output token:  {j/c_tok:>13.4f} J")
        print(f"  Tokens per joule:      {c_tok/j:>13.2f}")
    print(f"  Avg GPU utilization:   {util:>13.1f} %")
    print(f"  Avg GPU temperature:   {temp:>13.1f} °C")
    if cost > 0:
        print(f"  Total cost:            ${cost:>13.4f}")
    return 0


# ── leaderboard ──────────────────────────────────────────────────────────────


def cmd_leaderboard(args: argparse.Namespace) -> int:
    db = _open(args.db)
    where = _hours_filter(args.hours)

    q = f"""
        SELECT
            model_id,
            COUNT(*),
            SUM(completion_tokens),
            SUM(energy_joules),
            AVG(latency_seconds),
            AVG(throughput_tok_per_sec)
        FROM telemetry
        {where}
        GROUP BY model_id
        ORDER BY (CASE WHEN SUM(energy_joules) > 0
                       THEN SUM(completion_tokens) * 1.0 / SUM(energy_joules)
                       ELSE 0 END) DESC
    """
    rows = db.execute(q).fetchall()
    if not rows:
        print("(no records yet — run some chat() calls first)")
        return 0

    label = "All time" if not args.hours else f"Last {args.hours}h"
    print(f"VECTOR Model Leaderboard — {label}")
    print("─" * 88)
    print(f"  {'Model':<28}  {'Calls':>6}  {'Out tokens':>10}  "
          f"{'Energy':>10}  {'Tok/J':>8}  {'Latency':>9}  {'Tok/s':>7}")
    print("  " + "─" * 86)
    for model, calls, c_tok, j, lat, tps in rows:
        c_tok = c_tok or 0
        j = j or 0.0
        tok_per_j = (c_tok / j) if j > 0 else 0.0
        print(
            f"  {model:<28}  {calls:>6,}  {c_tok:>10,}  "
            f"{_human_joules(j):>10}  {tok_per_j:>8.2f}  {lat:>7.2f}s  {tps:>7.1f}"
        )
    return 0


# ── model details ────────────────────────────────────────────────────────────


def cmd_model(args: argparse.Namespace) -> int:
    db = _open(args.db)
    q = """
        SELECT
            COUNT(*) AS calls,
            MIN(timestamp) AS first_seen,
            MAX(timestamp) AS last_seen,
            COALESCE(SUM(total_tokens),0),
            COALESCE(SUM(completion_tokens),0),
            COALESCE(SUM(energy_joules),0),
            COALESCE(AVG(power_watts),0),
            COALESCE(MIN(latency_seconds),0),
            COALESCE(AVG(latency_seconds),0),
            COALESCE(MAX(latency_seconds),0),
            COALESCE(AVG(throughput_tok_per_sec),0),
            COALESCE(MAX(gpu_temperature_c),0)
        FROM telemetry
        WHERE model_id = ?
    """
    row = db.execute(q, (args.model,)).fetchone()
    if not row or not row[0]:
        print(f"(no records for model '{args.model}')")
        return 0

    (calls, first, last, t_tok, c_tok, j, w,
     lat_min, lat_avg, lat_max, tps, peak_temp) = row

    import datetime as _dt
    first_iso = _dt.datetime.fromtimestamp(first).isoformat(timespec='seconds')
    last_iso = _dt.datetime.fromtimestamp(last).isoformat(timespec='seconds')

    print(f"VECTOR Telemetry — {args.model}")
    print("─" * 60)
    print(f"  First call:            {first_iso}")
    print(f"  Last call:             {last_iso}")
    print(f"  Calls:                 {calls:,}")
    print(f"  Total tokens:          {t_tok:,}")
    print(f"  Output tokens:         {c_tok:,}")
    print(f"  Total energy:          {_human_joules(j)}")
    print(f"  Avg power:             {w:.2f} W")
    print(f"  Latency  min / avg / max:  "
          f"{lat_min:.2f} / {lat_avg:.2f} / {lat_max:.2f} s")
    print(f"  Avg throughput:        {tps:.1f} tok/s")
    print(f"  Peak GPU temp:         {peak_temp:.1f} °C")
    if c_tok > 0 and j > 0:
        print(f"  Energy efficiency:     {c_tok/j:.2f} tokens/J  "
              f"({j/c_tok*1000:.1f} mJ/token)")
    return 0


# ── live tail ────────────────────────────────────────────────────────────────


def cmd_live(args: argparse.Namespace) -> int:
    db = _open(args.db)
    q = """
        SELECT timestamp, model_id, latency_seconds, completion_tokens,
               energy_joules, power_watts, gpu_temperature_c
        FROM telemetry
        ORDER BY timestamp DESC
        LIMIT ?
    """
    rows = db.execute(q, (args.limit,)).fetchall()
    if not rows:
        print("(no records yet)")
        return 0
    import datetime as _dt
    print(f"{'Time':<19}  {'Model':<24}  {'Lat':>6}  {'OutT':>5}  "
          f"{'Energy':>10}  {'Watts':>6}  {'Temp':>6}")
    print("─" * 96)
    for ts, model, lat, c_tok, j, w, t in reversed(rows):
        when = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{when}  {model:<24}  {lat:>5.2f}s  {c_tok:>5,}  "
              f"{_human_joules(j or 0):>10}  {w or 0:>5.1f}W  {t or 0:>5.1f}°C")
    return 0


# ── export ───────────────────────────────────────────────────────────────────


def cmd_export(args: argparse.Namespace) -> int:
    db = _open(args.db)
    where = _hours_filter(args.hours)
    cur = db.execute(f"SELECT * FROM telemetry {where} ORDER BY timestamp ASC")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()

    out_path = Path(args.outfile)
    if out_path.suffix.lower() == ".json":
        records = [dict(zip(cols, r)) for r in rows]
        out_path.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")
    else:
        with out_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
    print(f"Wrote {len(rows):,} records to {out_path}")
    return 0


# ── capabilities ─────────────────────────────────────────────────────────────


def cmd_capabilities(_args: argparse.Namespace) -> int:
    try:
        from core.telemetry import capabilities  # type: ignore[import]
        caps = capabilities()
    except Exception as exc:
        print(f"[!] could not load core.telemetry: {exc}")
        return 1
    print("VECTOR Telemetry Capabilities")
    print("─" * 40)
    for name, on in caps.items():
        flag = "✓ READY" if on else "✗ unavailable"
        print(f"  {name:<18} {flag}")
    return 0


# ── clear ────────────────────────────────────────────────────────────────────


def cmd_clear(args: argparse.Namespace) -> int:
    if not args.yes:
        print("[!] refusing to wipe telemetry without --yes")
        return 1
    db = _open(args.db)
    db.execute("DELETE FROM telemetry")
    db.commit()
    print("Telemetry table cleared.")
    return 0


# ── argparse wiring ──────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vector telemetry", description=__doc__)
    p.add_argument(
        "--db",
        type=Path,
        default=_DEFAULT_DB,
        help=f"telemetry DB path (default: {_DEFAULT_DB})",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("stats", help="summary stats")
    sp.add_argument("--hours", type=int, default=24, help="window (0 = all-time)")
    sp.add_argument("--model", help="filter to one model")
    sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("leaderboard", help="rank models by efficiency")
    sp.add_argument("--hours", type=int, default=24)
    sp.set_defaults(func=cmd_leaderboard)

    sp = sub.add_parser("model", help="detailed stats for one model")
    sp.add_argument("model")
    sp.set_defaults(func=cmd_model)

    sp = sub.add_parser("live", help="tail recent records")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_live)

    sp = sub.add_parser("export", help="dump telemetry to CSV or JSON")
    sp.add_argument("outfile")
    sp.add_argument("--hours", type=int, default=0, help="0 = all time")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("capabilities", help="show wired telemetry subsystems")
    sp.set_defaults(func=cmd_capabilities)

    sp = sub.add_parser("clear", help="wipe the telemetry table")
    sp.add_argument("--yes", action="store_true", help="confirm wipe")
    sp.set_defaults(func=cmd_clear)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception as _sve:
        logger.debug("[VECTOR][vector_cli.telemetry_cmd] suppressed Exception: %s", _sve)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
