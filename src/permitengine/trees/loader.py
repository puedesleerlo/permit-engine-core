"""Trees and weights. A tree file holds questions and first-guess leaves. Weights are levels and soft counts per leaf."""
import copy
import json
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path

import yaml

from ..hashing import content_hash
from ..workspace import EngineError

TREE_IDS = ("traffic.likelihood", "traffic.severity", "crowd.likelihood", "crowd.severity", "medical.likelihood", "medical.severity")
LEVEL_NAMES = {"likelihood": ["rare", "possible", "likely"], "severity": ["minor", "serious", "critical"]}


@dataclass
class Tree:
    id: str
    hazard: str
    scale: str
    version: int
    questions: list  # dicts, as in the file
    whens: list  # one per leaf, in file order: {question id: bool}
    first_levels: list  # first guess per leaf, or [] until written

    @property
    def question_ids(self) -> list:
        return [q["id"] for q in self.questions]

    def question(self, question_id: str) -> dict:
        return next(q for q in self.questions if q["id"] == question_id)


def all_whens(question_ids) -> list:
    """Every combination, true first."""
    return [dict(zip(question_ids, bits)) for bits in product([True, False], repeat=len(question_ids))]


def parse_tree(raw: dict) -> Tree:
    question_ids = [q["id"] for q in raw["questions"]]
    leaves = raw.get("leaves") or []
    if leaves:
        whens = [dict(leaf["when"]) for leaf in leaves]
        levels = [list(leaf["levels"]) for leaf in leaves]
    else:
        whens, levels = all_whens(question_ids), []
    return Tree(id=raw["id"], hazard=raw["hazard"], scale=raw["scale"], version=raw.get("version", 1),
                questions=raw["questions"], whens=whens, first_levels=levels)


def load_trees(rules_dir: Path, first_guess_dir: Path | None = None) -> dict:
    """Trees from rules/trees/. `first_guess_dir` supplies leaves from elsewhere, for a temporary check only."""
    folder = Path(rules_dir) / "trees"
    trees = {}
    for tree_id in TREE_IDS:
        path = folder / f"{tree_id}.yaml"
        if not path.exists():
            raise EngineError(f"tree file {path} does not exist")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if first_guess_dir is not None:
            other = yaml.safe_load((Path(first_guess_dir) / f"{tree_id}.yaml").read_text(encoding="utf-8"))
            raw["leaves"] = other["leaves"]
        trees[tree_id] = parse_tree(raw)
    return trees


def require_first_guess(trees: dict) -> None:
    empty = [t.id for t in trees.values() if not t.first_levels]
    if empty:
        raise EngineError(
            "these trees have no first-guess leaves yet: " + ", ".join(empty) +
            ". Write them in rules/trees/, or pass --first-guess with a folder that holds them.")


def crossings_tree(rules_dir: Path, base: Tree) -> Tree:
    """The planted question. The first guess of each new leaf copies the leaf it splits, unless the file gives its own."""
    path = Path(rules_dir) / "proposals" / "traffic.likelihood.crossings.yaml"
    if not path.exists():
        raise EngineError(f"{path} does not exist")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    questions = raw.get("questions") or base.questions + [raw["question"]]
    question_ids = [q["id"] for q in questions]
    leaves = raw.get("leaves") or []
    if leaves:
        whens = [dict(leaf["when"]) for leaf in leaves]
        levels = [list(leaf["levels"]) for leaf in leaves]
    else:
        whens = all_whens(question_ids)
        levels = []
        for when in whens:
            parent = base.whens.index({k: when[k] for k in base.question_ids})
            levels.append(list(base.first_levels[parent]))
    return Tree(id=base.id, hazard=base.hazard, scale=base.scale, version=raw.get("version", base.version + 1),
                questions=questions, whens=whens, first_levels=levels)


@dataclass
class Model:
    """Weights for a set of trees. `levels[tree][leaf]` is a distribution, `counts[tree][leaf]` the soft counts behind it."""
    version: str
    trees: dict
    levels: dict
    counts: dict
    corrections: int = 0
    thresholds: dict = field(default_factory=dict)

    def copy(self, version=None) -> "Model":
        return Model(version or self.version, dict(self.trees), copy.deepcopy(self.levels), copy.deepcopy(self.counts),
                     self.corrections, dict(self.thresholds))

    def weights_json(self) -> dict:
        return {"levels": self.levels, "counts": self.counts,
                "whens": {t: tree.whens for t, tree in self.trees.items()}}

    def weights_hash(self) -> str:
        return content_hash(self.weights_json())

    def by_hazard(self) -> dict:
        out = {}
        for tree in self.trees.values():
            out.setdefault(tree.hazard, {})[tree.scale] = tree.id
        return out


def first_guess(trees: dict, strength: float) -> Model:
    require_first_guess(trees)
    levels = {t: [list(d) for d in tree.first_levels] for t, tree in trees.items()}
    counts = {t: [[strength * v for v in d] for d in tree.first_levels] for t, tree in trees.items()}
    return Model("first-guess", dict(trees), levels, counts)


def save_model(model: Model, folder: Path, extra: dict | None = None) -> None:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    trees = {t: {"id": tree.id, "hazard": tree.hazard, "scale": tree.scale, "version": tree.version,
                 "questions": tree.questions, "whens": tree.whens, "first_levels": tree.first_levels}
             for t, tree in model.trees.items()}
    body = {"version": model.version, "trees": trees, "levels": model.levels, "counts": model.counts,
            "thresholds": model.thresholds, "corrections": model.corrections, "weights_hash": model.weights_hash()}
    if extra:
        body.update(extra)
    (folder / "weights.json").write_text(json.dumps(body, indent=1, sort_keys=True), encoding="utf-8")


def load_model(folder: Path) -> Model:
    path = Path(folder) / "weights.json"
    if not path.exists():
        raise EngineError(f"{path} does not exist; run `train` first")
    body = json.loads(path.read_text(encoding="utf-8"))
    trees = {t: Tree(**raw) for t, raw in body["trees"].items()}
    return Model(body["version"], trees, body["levels"], body["counts"], body.get("corrections", 0), body.get("thresholds", {}))
