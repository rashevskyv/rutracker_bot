from digest.base import BaseDigest


def _digest(sections):
    lines = ["#homebrew_digest:", ""]
    for title, n in sections:
        lines.append(f"=== {title} ===")
        lines += [f"• {title} app {i} — " + "x" * 80 for i in range(n)]
        lines.append("")
    lines.append("📢 footer")
    return "\n".join(lines)


def _entries(parts):
    return [l for p in parts for l in p.split("\n") if l.startswith("•")]


split = BaseDigest("unused.json")._split_digest_message


def test_small_sections_share_one_part():
    msg = _digest([("Switch", 3), ("3DS", 3)])
    assert split(msg, 4096) == [msg]


def test_section_is_not_torn_when_it_fits_alone():
    # 3DS + Switch do not fit together; Switch alone does -> Switch must stay whole
    msg = _digest([("3DS", 10), ("Switch", 30)])
    parts = split(msg, 3000)
    assert len(parts) == 2
    assert parts[0].startswith("#homebrew_digest:") and "Switch" not in parts[0]
    assert parts[1].startswith("=== Switch ===")
    assert parts[1].count("• Switch") == 30
    assert parts[1].endswith("📢 footer")


def test_oversized_section_is_split_evenly_with_repeated_header():
    msg = _digest([("Switch", 50)])
    parts = split(msg, 2000)
    assert all(len(p) <= 2000 for p in parts)
    assert len(parts) == 3
    assert all(p.lstrip("#homebrew_digest:\n").startswith("=== Switch ===") for p in parts)
    counts = [p.count("• Switch") for p in parts]
    assert max(counts) - min(counts) <= 1, counts
    assert _entries(parts) == [l for l in msg.split("\n") if l.startswith("•")]


def test_oversized_tail_shares_part_with_next_section():
    msg = _digest([("Switch", 50), ("3DS", 2)])
    parts = split(msg, 2000)
    assert "=== 3DS ===" in parts[-1] and "• Switch" in parts[-1]
    assert _entries(parts) == [l for l in msg.split("\n") if l.startswith("•")]
