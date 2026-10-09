"""Conservative topic identity: explicit aliases, never fuzzy semantic guesses."""

import hashlib
import json
import unicodedata
from functools import lru_cache

from app.config import ROOT


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


@lru_cache
def mappings():
    data = json.loads((ROOT / "content/learning-topics.json").read_text())
    if data["version"] != 1:
        raise ValueError("Unsupported topic mapping version")
    skills, topics = {}, {}
    for canonical, aliases in data["skills"].items():
        for alias in aliases:
            key = normalized(alias)
            if key in skills and skills[key] != canonical:
                raise ValueError("Conflicting skill alias")
            skills[key] = canonical
    for row in data["topics"]:
        for alias in row["aliases"]:
            key = normalized(row["skill"]), normalized(alias)
            if key in topics and topics[key] != row["topic"]:
                raise ValueError("Conflicting topic alias")
            topics[key] = row["topic"]
    return skills, topics


def identity(skill, topic):
    skills, topics = mappings()
    skill = skills.get(normalized(skill), " ".join(skill.split()))
    topic = topics.get((normalized(skill), normalized(topic)), " ".join(topic.split()))
    key = hashlib.sha256(f"{normalized(skill)}\0{normalized(topic)}".encode()).hexdigest()[:32]
    return key, skill, topic


def matches(content, topic_id):
    return any(
        identity(content["skill"], topic)[0] == topic_id for topic in content["expected_topics"]
    )
