from __future__ import annotations

import re
from bs4 import BeautifulSoup


def clean_html(html: str | None) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(" ", strip=True)


POSITIVE = {
    "стаж": 18,
    "junior": 18,
    "джуниор": 18,
    "младш": 15,
    "без опыта": 15,
    "информационн": 18,
    "кибербезопас": 18,
    "защита информации": 16,
    "soc": 20,
    "siem": 12,
    "мониторинг": 10,
    "инцидент": 10,
    "linux": 12,
    "ubuntu": 8,
    "bash": 8,
    "python": 12,
    "fastapi": 5,
    "api": 5,
    "dns": 8,
    "tcp/ip": 10,
    "http": 6,
    "https": 6,
    "ssh": 8,
    "vps": 5,
    "cloudflare": 5,
    "docker": 6,
    "ctf": 8,
    "wireshark": 8,
    "nmap": 8,
    "devops": 5,
    "системн": 7,
    "администр": 7,
}

NEGATIVE = {
    "senior": -35,
    "middle": -18,
    "ведущий": -30,
    "главный": -25,
    "руководитель": -30,
    "начальник": -30,
    "тимлид": -30,
    "team lead": -30,
    "от 3 лет": -25,
    "от 5 лет": -35,
    "3 года": -18,
    "5 лет": -25,
    "3-6 лет": -25,
    "продаж": -30,
    "менеджер по продажам": -40,
    "маркетинг": -25,
    "1с": -20,
    "php": -10,
    "битрикс": -15,
    "android": -10,
    "ios": -10,
    "data scientist": -10,
    "дизайнер": -30,
    "преподаватель": -25,
}

GOOD_TITLE = [
    r"стаж[её]р.*(иб|информац|soc|linux|security)",
    r"junior.*(security|soc|linux|python|devops)",
    r"младш.*(иб|информац|систем|linux|security)",
    r"аналитик.*soc",
    r"специалист.*информационн.*безопас",
    r"системн.*администратор",
]

BAD_TITLE = [
    r"senior|middle|ведущий|главный|руководитель|начальник|продаж|маркетинг|дизайнер",
]


def score_vacancy(vacancy: dict) -> tuple[int, str]:
    title = vacancy.get("name") or ""
    employer = (vacancy.get("employer") or {}).get("name") or ""
    description = clean_html(vacancy.get("description"))
    snippet = " ".join(
        [
            (vacancy.get("snippet") or {}).get("requirement") or "",
            (vacancy.get("snippet") or {}).get("responsibility") or "",
        ]
    )
    text = f"{title} {employer} {description} {snippet}".lower()
    title_lower = title.lower()

    score = 30
    reasons: list[str] = []

    experience = (vacancy.get("experience") or {}).get("id", "")
    if experience == "noExperience":
        score += 20
        reasons.append("+ без опыта")
    elif experience == "between1And3":
        score += 3
        reasons.append("± опыт 1–3 года, можно пробовать")

    employment = (vacancy.get("employment") or {}).get("name", "")
    if "стаж" in employment.lower():
        score += 15
        reasons.append("+ стажировка")

    schedule = (vacancy.get("schedule") or {}).get("name", "")
    if any(word in schedule.lower() for word in ["удален", "гибк", "смен"]):
        score += 4
        reasons.append(f"+ формат: {schedule}")

    for pattern in GOOD_TITLE:
        if re.search(pattern, title_lower):
            score += 18
            reasons.append("+ название хорошо совпадает")
            break

    for pattern in BAD_TITLE:
        if re.search(pattern, title_lower):
            score -= 35
            reasons.append("− плохое совпадение по названию")
            break

    for keyword, value in POSITIVE.items():
        if keyword in text:
            score += value
            if len(reasons) < 9:
                reasons.append(f"+ {keyword}")

    for keyword, value in NEGATIVE.items():
        if keyword in text:
            score += value
            if len(reasons) < 12:
                reasons.append(f"− {keyword}")

    # Salary sanity: do not reject no salary. Slightly prefer entry-level visible salary.
    salary = vacancy.get("salary") or {}
    if salary:
        salary_from = salary.get("from") or 0
        salary_to = salary.get("to") or 0
        if 30000 <= max(salary_from, salary_to) <= 150000:
            score += 4
            reasons.append("+ зарплата похожа на junior/стажировку")

    # Hard cap
    score = max(0, min(100, score))
    reason = "\n".join(dict.fromkeys(reasons)) or "Совпадение по общему поиску"
    return score, reason


def category(vacancy: dict) -> str:
    title = (vacancy.get("name") or "").lower()
    description = clean_html(vacancy.get("description")).lower()
    text = f"{title} {description}"
    if "soc" in text or "siem" in text or "мониторинг" in text or "инцидент" in text:
        return "soc"
    if "linux" in text or "администратор" in text or "системн" in text or "dns" in text or "ssh" in text:
        return "infra"
    if "python" in text or "fastapi" in text or "api" in text or "разработ" in text:
        return "dev"
    return "security"
