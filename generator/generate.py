"""Write data/ from the seed. Same seed gives identical bytes. Run: uv run python -m generator.generate"""
import copy
import hashlib
import json
import shutil
from pathlib import Path

import yaml

from generator.cards import draw_cards
from generator.labels import make_label
from generator.render import load_variants, render_base, render_cover_letter, rng_for
from generator.splits import build_splits, tone_requests

GENERATOR_DIR = Path(__file__).parent
ROOT = GENERATOR_DIR.parent
DATA = ROOT / "data"


def load_config():
    return yaml.safe_load((GENERATOR_DIR / "config.yaml").read_text())


def load_truth_table():
    return yaml.safe_load((GENERATOR_DIR / "truth_table.yaml").read_text())


def dump_jsonl(rows):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def write_application(out, case_id, form, cover_letter, attachments):
    folder = out / "applications" / case_id
    (folder / "attachments").mkdir(parents=True)
    (folder / "form.json").write_text(json.dumps(form, ensure_ascii=False, indent=2) + "\n")
    (folder / "cover_letter.txt").write_text(cover_letter)
    for name, text in sorted(attachments.items()):
        (folder / "attachments" / name).write_text(text)


def dataset_hash(out):
    digest = hashlib.sha256()
    for path in sorted(p for p in out.rglob("*") if p.is_file() and p.name != "manifest.json"):
        digest.update(str(path.relative_to(out)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main(out=DATA):
    cfg = load_config()
    table = load_truth_table()
    variants = load_variants()
    cards = draw_cards(cfg)
    toned = set(tone_requests(cards, cfg))

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    out_cards, out_labels = [], []
    for card in sorted(cards, key=lambda c: c["base_id"]):
        rng = rng_for(cfg, card["base_id"])
        form, attachments, slots, families = render_base(card, cfg, variants, rng)
        card["families"] = families
        label = make_label(card, cfg, table)
        write_application(out, card["case_id"], form, render_cover_letter(variants, families["cover_letter"], slots, "plain"), attachments)
        out_cards.append(card)
        out_labels.append(label)
        if card["base_id"] in toned:
            for tone in cfg["tones"]["extra"]:
                twin = copy.deepcopy(card)
                twin["case_id"] = f"{card['base_id']}-{tone}"
                twin["split"] = "tone"
                twin["tone"] = tone
                write_application(out, twin["case_id"], form, render_cover_letter(variants, families["cover_letter"], slots, tone), attachments)
                out_cards.append(twin)
                out_labels.append({**label, "case_id": twin["case_id"]})

    (out / "cards.jsonl").write_text(dump_jsonl(out_cards))
    (out / "labels.jsonl").write_text(dump_jsonl(out_labels))
    (out / "splits.json").write_text(json.dumps(build_splits(out_cards), indent=1) + "\n")
    manifest = {"seed": cfg["seed"], "generator_version": cfg["version"], "dataset_hash": dataset_hash(out),
                "counts": {"cards": len(out_cards), "base_requests": len(cards)}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"Wrote {len(out_cards)} cases. Dataset hash {manifest['dataset_hash']}")


if __name__ == "__main__":
    main()
