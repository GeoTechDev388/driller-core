from __future__ import annotations

from decimal import Decimal
import re


STANDARD_SPT_METHOD_KEY = "spt_standard"
STANDARD_SPT_RULE_TYPE = "phase1_standard_spt"


def _normalize_depth(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def standard_spt_rule_config() -> dict:
    return {
        "segments": [
            {
                "start_depth": "0.00",
                "end_depth": "10.00",
                "intervals": [
                    {"from": "0.50", "to": "2.00"},
                    {"from": "2.50", "to": "4.00"},
                    {"from": "4.50", "to": "6.00"},
                    {"from": "6.50", "to": "8.00"},
                    {"from": "8.50", "to": "10.00"},
                ],
            },
            {
                "start_depth": "10.00",
                "cadence_ft": "5.00",
                "run_length_ft": "1.50",
                "run_end_depths": "15.00+",
            },
        ]
    }


def generate_standard_spt_intervals(target_depth: Decimal) -> list[tuple[Decimal, Decimal]]:
    target_depth = _normalize_depth(max(Decimal("0.00"), target_depth))
    intervals: list[tuple[Decimal, Decimal]] = []

    for start in (
        Decimal("0.50"),
        Decimal("2.50"),
        Decimal("4.50"),
        Decimal("6.50"),
        Decimal("8.50"),
    ):
        end = start + Decimal("1.50")
        if end <= target_depth:
            intervals.append((_normalize_depth(start), _normalize_depth(end)))

    run_end = Decimal("15.00")
    while run_end <= target_depth:
        start = run_end - Decimal("1.50")
        intervals.append((_normalize_depth(start), _normalize_depth(run_end)))
        run_end += Decimal("5.00")

    return intervals


def sample_label_for_boring(boring_name: str, sequence_number: int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", (boring_name or "B").strip()).strip("-") or "B"
    return f"{cleaned}-S{sequence_number}"
