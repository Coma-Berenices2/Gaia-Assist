"""Small opt-in live comparison. Never runs on application startup."""
import json
from pathlib import Path
import time
from scientist_network import NetworkOptions, query_context, tap_query
from scientist_catalogue import build_query


def main():
    options = NetworkOptions(overall_timeout=15, optional_timeout=15, request_timeout=12, attempts=1)
    identifiers = ["1542553623374596352", "4710235730956507648"]
    try:
        with query_context(options=options):
            sample = tap_query("SELECT TOP 20 source_id FROM gaiadr3.gaia_source WHERE source_id BETWEEN 1542453623374596352 AND 1542653623374596352", mode="sync")
            if len(sample) == 20:
                identifiers = [row["source_id"] for row in sample]
    except Exception as error:
        print("Sampling:", error, flush=True)
    results = []
    for ids, kind, mode in ((identifiers[:2], "joined", "sync"), (identifiers[:2], "joined", "async"),
                            (identifiers, "joined", "sync"), (identifiers, "joined", "async")):
        start = time.monotonic()
        record = {"mode": mode, "kind": kind, "ids": len(ids), "limit_seconds": 15}
        try:
            with query_context(options=options):
                rows = tap_query(build_query(ids, kind), len(ids), mode=mode)
            record.update(status="success", rows=len(rows))
        except Exception as error:
            record.update(status=type(error).__name__, detail=str(error))
        record["elapsed_seconds"] = round(time.monotonic()-start, 3)
        results.append(record)
        print(json.dumps(record), flush=True)
    Path("scientist_network_batch_benchmark.json").write_text(json.dumps({"timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "notes": "Single pass, sequential cold client calls; server cache/load uncontrolled. Timeouts are censored timings, not server completion times.", "results": results}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
