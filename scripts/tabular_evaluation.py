"""Independent synthetic task generator/checker, loaded only by the evaluator.

Reference arithmetic uses integers/Fraction, independently of the executable
Decimal primitives. This module is not in the model's messages or tool grants.
"""

import random
from fractions import Fraction


def money(value):
    sign = "-" if value < 0 else ""
    value = abs(value)
    # All reference values are cents; mean ties round to even, independently.
    cents = round(value * 100)
    return sign + str(cents // 100) + "." + f"{cents % 100:02}"


class Evaluator:
    def __init__(self, settings):
        self.settings = settings

    @staticmethod
    def compare(actual, expected):
        return actual == expected

    def cases(self, split, name):
        plan = self.settings["truth"]
        rng = random.Random(self.settings["seeds"][split])
        cases = []
        for _case in range(4 if split == "validation" else 2):
            rows, amounts, keep = [], [], []
            for index in range(9):
                cents = rng.choice((-123450, -5099, 0, 101, 125050, 234599))
                value = Fraction(cents, 100)
                if plan["divisor"] == 1:
                    integer, fraction = divmod(abs(cents), 100)
                    text = f"{integer:,}".replace(",", plan["thousands_separator"])
                    text += plan["decimal_separator"] + f"{fraction:02}"
                else:
                    text = str(abs(cents) * plan["divisor"] // 100)
                if cents < 0:
                    text = "-" + text
                text = plan["affix"] + text
                base = rng.choice((plan["accepted"][0], "void", "pending"))
                if index % 3 == 0:
                    base = " " + base.upper() + " "
                normalized = base.strip() if plan["trim"] else base
                normalized = normalized.casefold() if plan["casefold"] else normalized
                rows.append(
                    {"amount": text, "status": base, "group": rng.choice(("East", "east", "West"))}
                )
                amounts.append(value)
                keep.append(normalized in plan["accepted"])
            if name == "numeric":
                expected = {"values": [money(v) for v in amounts]}
            elif name == "status":
                expected = {"selected": keep}
            else:
                grouped = {}
                for row, value, selected in zip(rows, amounts, keep, strict=True):
                    if selected:
                        group = row["group"].casefold() if plan["group_casefold"] else row["group"]
                        grouped.setdefault(group, []).append(value)
                totals = {}
                for group, values in grouped.items():
                    value = Fraction(len(values)) if plan["operation"] == "count" else sum(values)
                    if plan["operation"] == "mean":
                        value /= len(values)
                    totals[group] = money(value)
                expected = {"totals": dict(sorted(totals.items()))}
            cases.append({"rows": rows, "expected": expected, "split": split})
        return cases


def family(index):
    variants = (
        (".", ",", "$", 1, True, True, ["paid"], "sum", True),
        (",", ".", "EUR", 1, True, True, ["settled"], "mean", False),
        (".", "", "", 100, True, False, ["OK"], "sum", False),
        (".", " ", "GBP", 1, False, True, ["cleared"], "count", True),
    )
    values = variants[index % len(variants)]
    truth = dict(
        zip(
            (
                "decimal_separator",
                "thousands_separator",
                "affix",
                "divisor",
                "trim",
                "casefold",
                "accepted",
                "operation",
                "group_casefold",
            ),
            values,
            strict=True,
        )
    )
    public = {
        "numeric": (
            f"Amounts use decimal {values[0]!r}, thousands {values[1]!r}, "
            f"literal currency affix {values[2]!r}. "
            "Remove this currency affix and thousands separators, then divide "
            f"the parsed value by {values[3]} to produce units with two decimals. "
            "Keep the sign and reject non-finite values. Do not change the row order."
        ),
        "status": (
            (
                "Trim surrounding whitespace. "
                if values[4]
                else "Whitespace is significant: do not trim. "
            )
            + ("Compare using casefold. " if values[5] else "Compare case-sensitively. ")
            + f"Accept only the exact normalized statuses {values[6]!r}; "
            "all other rows are excluded. Return a boolean per input row."
        ),
        "aggregate": (
            "Use the already formed numeric and status capabilities. "
            f"Calculate the {values[7]} of accepted numeric values for each group. "
            + (
                "Merge group names using casefold. "
                if values[8]
                else "Group names are case-sensitive. "
            )
            + "Omit groups with no accepted rows. Return two-decimal strings, "
            "rounding ties to even."
        ),
    }
    return truth, public
