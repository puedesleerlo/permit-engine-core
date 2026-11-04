"""Where everything lives, and how an application is read. Commands take a Workspace so tests can use a temporary one."""
import json
import os
from dataclasses import dataclass
from pathlib import Path


class EngineError(Exception):
    """A stop with a clear message. The command line prints it and exits."""


@dataclass(frozen=True)
class Application:
    case_id: str
    form: dict
    cover_letter: str
    attachments: dict  # name -> text

    def hash_input(self) -> dict:
        return {"form": self.form, "cover_letter": self.cover_letter, "attachments": self.attachments}


@dataclass(frozen=True)
class Workspace:
    root: Path

    @staticmethod
    def default() -> "Workspace":
        return Workspace(Path(os.environ.get("PERMITENGINE_ROOT") or Path(__file__).resolve().parents[2]))

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def rules(self) -> Path:
        return self.root / "rules"

    @property
    def settings_file(self) -> Path:
        return self.root / "settings" / "settings.yaml"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def ledger(self) -> Path:
        return self.root / "ledger"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def weights(self) -> Path:
        return self.root / "weights"

    @property
    def export(self) -> Path:
        return self.root / "export" / "demo"

    @property
    def web_data(self) -> Path:
        return self.root / "web" / "public" / "data"

    def splits(self) -> dict:
        path = self.data / "splits.json"
        if not path.exists():
            raise EngineError(f"{path} does not exist; the data must be generated first")
        return json.loads(path.read_text(encoding="utf-8"))

    def dataset_hash(self) -> str:
        path = self.data / "manifest.json"
        if not path.exists():
            raise EngineError(f"{path} does not exist; the data must be generated first")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        return manifest.get("dataset_hash") or manifest["hash"]

    def application(self, case_id: str) -> Application:
        folder = self.data / "applications" / case_id
        if not folder.exists():
            raise EngineError(f"no application folder for {case_id}")
        attachments = {}
        attach_dir = folder / "attachments"
        if attach_dir.exists():
            for path in sorted(attach_dir.iterdir()):
                attachments[path.name] = path.read_text(encoding="utf-8")
        cover = folder / "cover_letter.txt"
        return Application(
            case_id=case_id,
            form=json.loads((folder / "form.json").read_text(encoding="utf-8")),
            cover_letter=cover.read_text(encoding="utf-8") if cover.exists() else "",
            attachments=attachments,
        )
