#!/usr/bin/env python3
"""Gera os cards SVG do README a partir da API do GitHub.

Roda no CI (.github/workflows/cards.yml) e escreve em assets/.
Sem dependencias externas: usa apenas a stdlib.

Uso: GITHUB_TOKEN=... python3 scripts/render_cards.py [login]
"""

import json
import os
import sys
import urllib.error
import urllib.request
from collections import OrderedDict

API = "https://api.github.com/graphql"

THEME = {
    "bg": "#1a1b27",
    "border": "#2a2e45",
    "title": "#70a5fd",
    "icon": "#bf91f3",
    "text": "#38bdae",
    "muted": "#8b93b8",
}

# Escala do calendario de contribuicoes (tokyonight).
LEVELS = {
    "NONE": "#232436",
    "FIRST_QUARTILE": "#1f4b63",
    "SECOND_QUARTILE": "#2a6f8f",
    "THIRD_QUARTILE": "#3f9dc4",
    "FOURTH_QUARTILE": "#70cdf0",
}

FONT = "'Segoe UI', Ubuntu, Sans-Serif"

ICONS = {
    "star": "M8 .25a.75.75 0 01.673.418l1.882 3.815 4.21.612a.75.75 0 01.416 1.279l-3.046 2.97.719 4.192a.75.75 0 01-1.088.791L8 12.347l-3.766 1.98a.75.75 0 01-1.088-.79l.72-4.194L.818 6.374a.75.75 0 01.416-1.28l4.21-.611L7.327.668A.75.75 0 018 .25z",
    "commit": "M11.93 8.5a4.002 4.002 0 01-7.86 0H.75a.75.75 0 010-1.5h3.32a4.002 4.002 0 017.86 0h3.32a.75.75 0 010 1.5h-3.32zM8 10a2 2 0 100-4 2 2 0 000 4z",
    "pr": "M7.177 3.073L9.573.677A.25.25 0 0110 .854v4.792a.25.25 0 01-.427.177L7.177 3.427a.25.25 0 010-.354zM3.75 2.5a.75.75 0 100 1.5.75.75 0 000-1.5zm-2.25.75a2.25 2.25 0 113 2.122v5.256a2.251 2.251 0 11-1.5 0V5.372A2.25 2.25 0 011.5 3.25zM11 2.5h-1V4h1a1 1 0 011 1v5.628a2.251 2.251 0 101.5 0V5A2.5 2.5 0 0011 2.5zm1 10.25a.75.75 0 111.5 0 .75.75 0 01-1.5 0zM3.75 12a.75.75 0 100 1.5.75.75 0 000-1.5z",
    "issue": "M8 9.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3zM8 0a8 8 0 100 16A8 8 0 008 0zM1.5 8a6.5 6.5 0 1113 0 6.5 6.5 0 01-13 0z",
    "fork": "M5 3.25a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm0 2.122a2.25 2.25 0 10-1.5 0v.878A2.25 2.25 0 005.75 8.5h1.5v2.128a2.251 2.251 0 101.5 0V8.5h1.5a2.25 2.25 0 002.25-2.25v-.878a2.25 2.25 0 10-1.5 0v.878a.75.75 0 01-.75.75h-4.5A.75.75 0 015 6.25v-.878zm3.75 7.378a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm3-8.75a.75.75 0 100-1.5.75.75 0 000 1.5z",
}

QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    name
    login
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks {
          firstDay
          contributionDays { date contributionCount contributionLevel weekday }
        }
      }
    }
    pullRequests { totalCount }
    issues { totalCount }
    repositoriesContributedTo(
      contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY]
    ) { totalCount }
    repositories(
      first: 100
      after: $after
      ownerAffiliations: OWNER
      isFork: false
      orderBy: { field: STARGAZERS, direction: DESC }
    ) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        stargazerCount
        languages(first: 10, orderBy: { field: SIZE, direction: DESC }) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def graphql(token, login, after=None):
    payload = json.dumps({"query": QUERY, "variables": {"login": login, "after": after}})
    req = urllib.request.Request(
        API,
        data=payload.encode("utf-8"),
        headers={
            "Authorization": "bearer " + token,
            "Content-Type": "application/json",
            "User-Agent": "maedaarthur-readme-cards",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit("GitHub API HTTP %s: %s" % (exc.code, exc.read().decode("utf-8")[:500]))
    if body.get("errors"):
        raise SystemExit("GitHub API error: %s" % json.dumps(body["errors"])[:500])
    return body["data"]["user"]


def fetch(token, login):
    user = graphql(token, login)
    repos = list(user["repositories"]["nodes"])
    page = user["repositories"]["pageInfo"]
    while page["hasNextPage"]:
        nxt = graphql(token, login, page["endCursor"])
        repos.extend(nxt["repositories"]["nodes"])
        page = nxt["repositories"]["pageInfo"]
    user["_repos"] = repos
    return user


def esc(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def card_open(width, height, title):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" fill="none" role="img" aria-label="%s">\n'
        '  <rect x="0.5" y="0.5" width="%d" height="%d" rx="6" fill="%s" stroke="%s"/>\n'
        '  <text x="25" y="35" class="title">%s</text>\n'
        % (
            width, height, width, height, esc(title),
            width - 1, height - 1, THEME["bg"], THEME["border"],
            esc(title),
        )
    )


def stats_card(user, out):
    contrib = user["contributionsCollection"]
    stars = sum(r["stargazerCount"] for r in user["_repos"])
    rows = [
        ("star", "Total de estrelas", stars),
        ("commit", "Commits (último ano)", contrib["totalCommitContributions"]),
        ("pr", "Pull requests", user["pullRequests"]["totalCount"]),
        ("issue", "Issues", user["issues"]["totalCount"]),
        ("fork", "Contribuiu em", user["repositoriesContributedTo"]["totalCount"]),
    ]
    width, top, step = 460, 70, 27
    height = top + step * len(rows) + 22

    svg = [card_open(width, height, "Estatísticas do GitHub")]
    for i, (icon, label, value) in enumerate(rows):
        y = top + i * step
        svg.append(
            '  <g transform="translate(25 %d)">\n'
            '    <svg x="0" y="-12" width="16" height="16" viewBox="0 0 16 16" fill="%s">'
            '<path d="%s"/></svg>\n'
            '    <text x="28" y="0" class="label">%s</text>\n'
            '    <text x="%d" y="0" class="value" text-anchor="end">%s</text>\n'
            '  </g>\n'
            % (y, THEME["icon"], ICONS[icon], esc(label), width - 50, "{:,}".format(value).replace(",", "."))
        )
    svg.append(
        '  <text x="25" y="%d" class="muted">%s contribuições no último ano</text>\n'
        % (height - 14, "{:,}".format(contrib["contributionCalendar"]["totalContributions"]).replace(",", "."))
    )
    svg.append("</svg>\n")
    write(out, "".join(svg))


def language_totals(repos, limit=6):
    totals = {}
    colors = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            lang = edge["node"]["name"]
            totals[lang] = totals.get(lang, 0) + edge["size"]
            colors[lang] = edge["node"]["color"] or THEME["icon"]
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    top = OrderedDict(ranked[:limit])
    grand = sum(totals.values())
    return top, colors, grand


def langs_card(user, out):
    top, colors, grand = language_totals(user["_repos"])
    rows = (len(top) + 1) // 2
    width, height = 340, 92 + rows * 26 - 4
    svg = [card_open(width, height, "Linguagens mais usadas")]

    if not grand:
        svg.append('  <text x="25" y="70" class="label">Sem dados de linguagem ainda</text>\n</svg>\n')
        write(out, "".join(svg))
        return

    bar_x, bar_y, bar_w, bar_h = 25, 55, width - 50, 8
    shown = sum(top.values())
    svg.append('  <mask id="bar"><rect x="%d" y="%d" width="%d" height="%d" rx="4" fill="#fff"/></mask>\n'
               % (bar_x, bar_y, bar_w, bar_h))
    svg.append('  <g mask="url(#bar)">\n')
    offset = 0.0
    for lang, size in top.items():
        seg = bar_w * (float(size) / shown)
        svg.append('    <rect x="%.2f" y="%d" width="%.2f" height="%d" fill="%s"/>\n'
                   % (bar_x + offset, bar_y, seg + 0.5, bar_h, colors[lang]))
        offset += seg
    svg.append('  </g>\n')

    col_w = (width - 50) / 2
    for i, (lang, size) in enumerate(top.items()):
        col, row = i % 2, i // 2
        x = 25 + col * col_w
        y = 92 + row * 26
        pct = 100.0 * size / shown
        svg.append(
            '  <g transform="translate(%.1f %d)">\n'
            '    <circle cx="5" cy="-4" r="5" fill="%s"/>\n'
            '    <text x="16" y="0" class="label">%s %.1f%%</text>\n'
            '  </g>\n' % (x, y, colors[lang], esc(lang), pct)
        )
    svg.append("</svg>\n")
    write(out, "".join(svg))


MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def calendar_card(user, out):
    cal = user["contributionsCollection"]["contributionCalendar"]
    weeks = cal["weeks"]
    cell, gap = 11, 3
    left, top = 42, 70
    width = left + len(weeks) * (cell + gap) + 22
    height = top + 7 * (cell + gap) + 30

    svg = [card_open(width, height, "Contribuições no último ano")]
    svg.append('  <text x="%d" y="35" class="muted" text-anchor="end">%s contribuições</text>\n'
               % (width - 25, "{:,}".format(cal["totalContributions"]).replace(",", ".")))

    for i, label in enumerate(["seg", "qua", "sex"]):
        y = top + (1 + i * 2) * (cell + gap) + cell - 1
        svg.append('  <text x="25" y="%d" class="tiny" text-anchor="end">%s</text>\n' % (y, label))

    last_month = None
    for wi, week in enumerate(weeks):
        month = int(week["firstDay"][5:7])
        if month != last_month and wi < len(weeks) - 1:
            if last_month is not None or wi == 0:
                svg.append('  <text x="%d" y="%d" class="tiny">%s</text>\n'
                           % (left + wi * (cell + gap), top - 8, MONTHS[month - 1]))
            last_month = month
        for day in week["contributionDays"]:
            x = left + wi * (cell + gap)
            y = top + day["weekday"] * (cell + gap)
            fill = LEVELS.get(day["contributionLevel"], LEVELS["NONE"])
            svg.append('  <rect x="%d" y="%d" width="%d" height="%d" rx="2" fill="%s"><title>%s: %d</title></rect>\n'
                       % (x, y, cell, cell, fill, day["date"], day["contributionCount"]))

    legend_x = width - 25 - (5 * (cell + gap) + 82)
    legend_y = height - 16
    svg.append('  <text x="%d" y="%d" class="tiny">menos</text>\n' % (legend_x, legend_y))
    for i, key in enumerate(["NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE"]):
        svg.append('  <rect x="%d" y="%d" width="%d" height="%d" rx="2" fill="%s"/>\n'
                   % (legend_x + 46 + i * (cell + gap), legend_y - 9, cell, cell, LEVELS[key]))
    svg.append('  <text x="%d" y="%d" class="tiny">mais</text>\n'
               % (legend_x + 46 + 5 * (cell + gap) + 8, legend_y))
    svg.append("</svg>\n")
    write(out, "".join(svg))


STYLE_SPEC = OrderedDict([
    ("title", ("600", "18", THEME["title"])),
    ("value", ("600", "14", THEME["text"])),
    ("label", ("400", "14", THEME["text"])),
    ("muted", ("400", "12", THEME["muted"])),
    ("tiny", ("400", "10", THEME["muted"])),
])


def inline_styles(svg):
    """Troca class="..." por atributos de apresentacao.

    O GitHub serve SVG do proprio repo por um sanitizador que pode descartar
    <style>; atributo inline sempre sobrevive.
    """
    for kind, (weight, size, fill) in STYLE_SPEC.items():
        base = 'font-family="%s" font-weight="%s" fill="%s"' % (FONT, weight, fill)
        svg = svg.replace('class="%s"' % kind, base + ' font-size="%s"' % size)
    return svg


def write(path, content):
    content = inline_styles(content)
    directory = os.path.dirname(path)
    if directory:
        try:
            os.makedirs(directory)
        except OSError:
            pass
    with open(path, "w") as handle:
        handle.write(content)
    print("escrito: %s (%d bytes)" % (path, len(content)))


def main():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("defina GITHUB_TOKEN")
    login = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GITHUB_LOGIN", "MaedaArthur")
    user = fetch(token, login)
    stats_card(user, "assets/stats.svg")
    langs_card(user, "assets/top-langs.svg")
    calendar_card(user, "assets/contributions.svg")


if __name__ == "__main__":
    main()
