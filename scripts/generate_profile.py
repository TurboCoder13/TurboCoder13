"""Generate the profile README hero and repo-card SVGs.

Renders a neofetch-style terminal hero (dark + light) and pin-style repo
cards from live GitHub data, writing them to ``assets/``. Run nightly by
``.github/workflows/update-profile.yml`` so ages, stats, releases, and CI
states never rot.

Terminal design inspired by https://github.com/Andrew6rant.

Requires the ``gh`` CLI (authenticated via ``GH_TOKEN`` in CI).
"""

from __future__ import annotations

import json
import subprocess  # nosec B404 - fixed-arg gh CLI calls only
import textwrap
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape  # nosec B406 - escaping output, not parsing

USER = "TurboCoder13"
ORG = "lgtm-hq"
BIRTHDAY = date(1994, 7, 13)
ACCOUNT_CREATED_YEAR = 2018
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

FEATURED: list[tuple[str, str]] = [
    (ORG, "py-lintro"),
    (ORG, "lgtm-ci"),
    (ORG, "turbo-themes"),
    (ORG, "Rustume"),
    (ORG, "ai-skills"),
    (ORG, "holy-grail"),
]

LOC_REPOS: list[tuple[str, str]] = [
    (USER, "TurboCoder13"),
    (USER, "shell-alias-collections"),
    (ORG, "py-lintro"),
    (ORG, "lgtm-ci"),
    (ORG, "turbo-themes"),
    (ORG, "Rustume"),
    (ORG, "podex"),
    (ORG, "winnow"),
    (ORG, "ai-skills"),
    (ORG, "holy-grail"),
    (ORG, "homebrew-tap"),
    (ORG, "lintro-pre-commit"),
    (ORG, ".github"),
    (ORG, "ui-framework"),
]

LANG_COLORS: dict[str, str] = {
    "Python": "#3572A5",
    "Shell": "#89e051",
    "TypeScript": "#3178c6",
    "Rust": "#dea584",
    "MDX": "#fcb32c",
    "Ruby": "#701516",
}

HERO_THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#161b22",
        "border": "#30363d",
        "dim": "#8b949e",
        "key": "#ffa657",
        "val": "#c9d1d9",
        "head": "#58a6ff",
        "bolt": "#e3b341",
        "ok": "#3fb950",
        "err": "#f85149",
        "fg": "#e6edf3",
    },
    "light": {
        "bg": "#f6f8fa",
        "border": "#d0d7de",
        "dim": "#57606a",
        "key": "#953800",
        "val": "#24292f",
        "head": "#0969da",
        "bolt": "#9a6700",
        "ok": "#1a7f37",
        "err": "#cf222e",
        "fg": "#1f2328",
    },
}

CARD_THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#161b22",
        "border": "#30363d",
        "title": "#58a6ff",
        "fg": "#c9d1d9",
        "dim": "#8b949e",
        "rel": "#d29922",
        "ok": "#3fb950",
        "err": "#f85149",
    },
    "light": {
        "bg": "#f6f8fa",
        "border": "#d0d7de",
        "title": "#0969da",
        "fg": "#24292f",
        "dim": "#57606a",
        "rel": "#9a6700",
        "ok": "#1a7f37",
        "err": "#cf222e",
    },
}

REPO_ICON = (
    "M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75"
    "h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05"
    "A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074-1 .208V2.5"
    "a1 1 0 011-1h8z"
)
BOLT_PATH = "M62 4 L18 96 H48 L34 168 L112 66 H76 L94 4 Z"

PANEL_COLS = 64
FONT_SIZE = 15
LINE_HEIGHT = 24
HERO_WIDTH = 848
CARD_WIDTH = 420
CARD_HEIGHT = 150

Segment = tuple[str, str]


@dataclass
class RepoCard:
    """Data rendered onto a single repo pin-card."""

    owner: str
    name: str
    description: str
    language: str
    release: str
    ci: str


def gh_api(path: str, *, jq: str | None = None) -> str | None:
    """Call ``gh api`` and return stdout, or None on failure.

    Args:
        path: API path (or full flag list target) passed to ``gh api``.
        jq: Optional jq filter applied by ``gh``.

    Returns:
        Trimmed stdout on success, otherwise None.
    """
    cmd = ["gh", "api", path]
    if jq:
        cmd += ["--jq", jq]
    proc = subprocess.run(cmd, capture_output=True, text=True)  # nosec B603 B607
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def gh_graphql(query: str, *, jq: str) -> str | None:
    """Run a GraphQL query via ``gh api graphql``.

    Args:
        query: GraphQL query string.
        jq: jq filter for the response.

    Returns:
        Trimmed stdout on success, otherwise None.
    """
    proc = subprocess.run(  # nosec B603 B607
        ["gh", "api", "graphql", "-f", f"query={query}", "--jq", jq],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def compute_uptime(today: date) -> str:
    """Return age since BIRTHDAY as ``N years, N months, N days``."""
    years = today.year - BIRTHDAY.year
    months = today.month - BIRTHDAY.month
    days = today.day - BIRTHDAY.day
    if days < 0:
        months -= 1
        prev_month = today.month - 1 or 12
        prev_year = today.year if today.month > 1 else today.year - 1
        import calendar

        days += calendar.monthrange(prev_year, prev_month)[1]
    if months < 0:
        years -= 1
        months += 12
    return f"{years} years, {months} months, {days} days"


def fetch_contributions(today: date) -> tuple[int, int]:
    """Sum all-time commit and PR contributions year by year."""
    commits = prs = 0
    for year in range(ACCOUNT_CREATED_YEAR, today.year + 1):
        result = gh_graphql(
            f'{{ user(login:"{USER}"){{ contributionsCollection('
            f'from:"{year}-01-01T00:00:00Z", to:"{year}-12-31T23:59:59Z")'
            "{ totalCommitContributions totalPullRequestContributions } } }",
            jq=(
                '.data.user.contributionsCollection | "'
                "\\(.totalCommitContributions) "
                '\\(.totalPullRequestContributions)"'
            ),
        )
        if result:
            commit_part, pr_part = result.split()
            commits += int(commit_part)
            prs += int(pr_part)
    return commits, prs


def fetch_repo_count() -> int:
    """Count public repos across the personal account and the org."""
    personal = gh_api(f"users/{USER}", jq=".public_repos") or "0"
    org = gh_api(f"orgs/{ORG}", jq=".public_repos") or "0"
    return int(personal) + int(org)


def fetch_loc() -> tuple[int, int]:
    """Sum lines added/removed across LOC_REPOS via code-frequency stats.

    GitHub returns HTTP 202 while computing stats, so pending repos are
    retried once after a pause.
    """

    def try_fetch(owner: str, repo: str) -> list[list[int]] | None:
        raw = gh_api(f"repos/{owner}/{repo}/stats/code_frequency")
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, list) and data else None

    added = removed = 0
    pending: list[tuple[str, str]] = []
    for owner, repo in LOC_REPOS:
        weeks = try_fetch(owner, repo)
        if weeks is None:
            pending.append((owner, repo))
            continue
        added += sum(week[1] for week in weeks)
        removed += sum(-week[2] for week in weeks)
    if pending:
        time.sleep(20)
        for owner, repo in pending:
            weeks = try_fetch(owner, repo)
            if weeks:
                added += sum(week[1] for week in weeks)
                removed += sum(-week[2] for week in weeks)
    return added, removed


def fetch_card(owner: str, repo: str) -> RepoCard:
    """Fetch the metadata rendered onto one repo card."""
    raw = gh_api(
        f"repos/{owner}/{repo}",
        jq='{desc: (.description // ""), lang: (.language // "")}',
    )
    meta = json.loads(raw) if raw else {"desc": "", "lang": ""}
    release = gh_api(f"repos/{owner}/{repo}/releases/latest", jq=".tag_name") or ""
    runs_raw = gh_api(
        f"repos/{owner}/{repo}/actions/runs?branch=main&status=completed&per_page=10",
        jq="[.workflow_runs[].conclusion] | @json",
    )
    ci = ""
    if runs_raw:
        conclusions = json.loads(runs_raw)
        real = [c for c in conclusions if c in ("success", "failure")]
        if real:
            ci = "passing" if real[0] == "success" else "failing"
    return RepoCard(
        owner=owner,
        name=repo,
        description=meta["desc"],
        language=meta["lang"],
        release=release,
        ci=ci,
    )


def hero_line(key: str, value: str | list[Segment]) -> list[Segment]:
    """Build one dotted key/value fetch line as colored segments."""
    segments: list[Segment] = (
        [(value, "val")] if isinstance(value, str) else list(value)
    )
    value_len = sum(len(text) for text, _ in segments)
    dots = max(2, PANEL_COLS - len(key) - value_len - 5)
    return [
        (". ", "dim"),
        (key, "key"),
        (": ", "dim"),
        ("." * dots + " ", "dim"),
        *segments,
    ]


def hero_section(title: str) -> list[Segment]:
    """Build a section separator line."""
    bar = "─" * (PANEL_COLS - len(title) - 4)
    return [("─ ", "dim"), (title, "head"), (" " + bar, "dim")]


def build_hero_rows(today: date) -> list[list[Segment]]:
    """Assemble every text row of the hero panel from live data."""
    commits, prs = fetch_contributions(today)
    added, removed = fetch_loc()
    repo_count = fetch_repo_count()
    return [
        [
            ("eitel", "head"),
            ("@", "dim"),
            ("turbocoder13", "head"),
            (" " + "─" * (PANEL_COLS - 20), "dim"),
        ],
        hero_line("Role", "SDET & DevOps Engineer"),
        hero_line("Base", "Netherlands 🇳🇱 · ex-Cape Town 🇿🇦"),
        hero_line("Uptime", compute_uptime(today)),
        hero_line("Stack", "Python · TypeScript · Java · Rust · Shell"),
        hero_line("Testing", "Playwright"),
        [],
        hero_section("Day / Night"),
        hero_line("Day", "test frameworks + CI/CD governance"),
        hero_line("Night", "OSS dev tooling @ lgtm-hq"),
        [],
        hero_section("AI-augmented"),
        hero_line("AI.Writes", "Claude Code · Cursor · Codex"),
        hero_line("AI.Reviews", "CodeRabbit · Greptile · Macroscope"),
        hero_line("QualityGate", "Lintro 28+ tools · OpenSSF · full CI"),
        [],
        hero_section("Contact"),
        hero_line("Email", "turbocoder13@gmail.com"),
        hero_line("LinkedIn", "in/eitel-dagnin"),
        [],
        hero_section("GitHub Stats"),
        hero_line("Repos", f"{repo_count} public"),
        hero_line("Commits", f"{commits:,}"),
        hero_line("PRs", f"{prs:,}"),
        hero_line(
            "Lines of Code",
            [
                (f"{added - removed:,} ( ", "val"),
                (f"{added:,}++", "ok"),
                (", ", "val"),
                (f"{removed:,}--", "err"),
                (" )", "val"),
            ],
        ),
    ]


def render_hero(rows: list[list[Segment]]) -> None:
    """Render the hero rows to dark/light SVGs in ASSETS_DIR."""
    header_y = 22
    box_y = 38
    top = box_y + 42
    height = top + LINE_HEIGHT * len(rows) + 26
    bolt_x = HERO_WIDTH - 36 - 130
    mono = "SFMono-Regular,Consolas,Liberation Mono,Menlo,monospace"
    for theme, c in HERO_THEMES.items():
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{HERO_WIDTH}" '
            f'height="{height}" viewBox="0 0 {HERO_WIDTH} {height}">',
            f'<text x="2" y="{header_y}" font-family="{mono}" font-size="15" '
            'font-weight="600">'
            f'<tspan fill="{c["fg"]}">TurboCoder13</tspan>'
            f'<tspan fill="{c["dim"]}"> / </tspan>'
            f'<tspan fill="{c["fg"]}">README</tspan>'
            f'<tspan fill="{c["dim"]}">.md</tspan></text>',
            f'<rect x="1" y="{box_y}" width="{HERO_WIDTH - 2}" '
            f'height="{height - box_y - 1}" rx="10" fill="{c["bg"]}" '
            f'stroke="{c["border"]}"/>',
            f'<g transform="translate({bolt_x},'
            f'{box_y + (height - box_y - 172) // 2})">'
            f'<path d="{BOLT_PATH}" fill="{c["bolt"]}" opacity="0.92"/></g>',
            f'<g font-family="{mono}" font-size="{FONT_SIZE}" xml:space="preserve">',
        ]
        for i, row in enumerate(rows):
            if not row:
                continue
            tspans = "".join(
                f'<tspan fill="{c[k]}">{escape(t)}</tspan>' for t, k in row
            )
            parts.append(f'<text x="36" y="{top + i * LINE_HEIGHT}">{tspans}</text>')
        parts.append("</g></svg>")
        (ASSETS_DIR / f"hero_{theme}_mode.svg").write_text("\n".join(parts))


def render_card(card: RepoCard) -> None:
    """Render one repo card to dark/light SVGs in ASSETS_DIR."""

    def pill(x: float, cy: int, label: str, color: str) -> tuple[str, float]:
        width = 18 + len(label) * 6.9
        svg = (
            f'<rect x="{x:.0f}" y="{cy - 10}" width="{width:.0f}" height="20" '
            f'rx="10" fill="none" stroke="{color}"/>'
            f'<text x="{x + width / 2:.0f}" y="{cy}" font-size="12" '
            f'fill="{color}" text-anchor="middle" '
            f'dominant-baseline="central">{escape(label)}</text>'
        )
        return svg, width

    sans = "-apple-system,Segoe UI,Helvetica,Arial,sans-serif"
    for theme, c in CARD_THEMES.items():
        wrapped = textwrap.wrap(card.description, 52)
        desc_lines = wrapped[:3]
        if len(wrapped) > 3:
            desc_lines[-1] = desc_lines[-1][:49] + "…"
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" '
            f'height="{CARD_HEIGHT}" viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}">',
            f'<rect x="0.5" y="0.5" width="{CARD_WIDTH - 1}" '
            f'height="{CARD_HEIGHT - 1}" rx="8" fill="{c["bg"]}" '
            f'stroke="{c["border"]}"/>',
            f'<g transform="translate(20,22)" fill="{c["title"]}">'
            f'<path d="{REPO_ICON}"/></g>',
            f'<text x="44" y="35" font-family="{sans}" font-size="16" '
            f'font-weight="600" fill="{c["title"]}">{escape(card.name)}</text>',
            f'<g font-family="{sans}" font-size="13" fill="{c["dim"]}">',
        ]
        for i, desc_line in enumerate(desc_lines):
            parts.append(f'<text x="20" y="{60 + i * 19}">{escape(desc_line)}</text>')
        parts.append("</g>")
        cy = CARD_HEIGHT - 24
        parts.append(f'<g font-family="{sans}" font-size="13">')
        x: float = 20
        if card.language:
            color = LANG_COLORS.get(card.language, c["dim"])
            parts.append(f'<circle cx="{x + 6:.0f}" cy="{cy}" r="6" fill="{color}"/>')
            parts.append(
                f'<text x="{x + 18:.0f}" y="{cy}" fill="{c["fg"]}" '
                f'dominant-baseline="central">{escape(card.language)}</text>'
            )
            x += 18 + 7.5 * len(card.language) + 18
        if card.release:
            svg, width = pill(x, cy, card.release, c["rel"])
            parts.append(svg)
            x += width + 10
        if card.ci:
            mark = "✓" if card.ci == "passing" else "✗"
            color = c["ok"] if card.ci == "passing" else c["err"]
            svg, _ = pill(x, cy, f"ci {mark} {card.ci}", color)
            parts.append(svg)
        parts.append("</g></svg>")
        (ASSETS_DIR / f"card_{card.name}_{theme}.svg").write_text("\n".join(parts))


def main() -> None:
    """Regenerate all profile SVG assets."""
    today = date.today()
    ASSETS_DIR.mkdir(exist_ok=True)
    render_hero(build_hero_rows(today))
    for owner, repo in FEATURED:
        render_card(fetch_card(owner, repo))
    print(f"assets regenerated for {today.isoformat()}")


if __name__ == "__main__":
    main()
