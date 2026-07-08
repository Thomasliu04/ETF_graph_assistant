import hashlib
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


class RunContext:
    def __init__(self, root_dir: Path, run_id: str | None = None):
        self.run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.root_dir = Path(root_dir)
        self.run_dir = self.root_dir / self.run_id
        self.input_dir = self.run_dir / "input"
        self.table_dir = self.run_dir / "tables"
        self.prompt_dir = self.run_dir / "prompts"
        self.ai_dir = self.run_dir / "ai"
        self.chart_dir = self.run_dir / "charts"
        for path in [self.input_dir, self.table_dir, self.prompt_dir, self.ai_dir, self.chart_dir]:
            path.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.run_dir / "run_manifest.json"
        self.manifest: dict[str, Any] = {
            "run_id": self.run_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "git_commit": self._git_commit(),
            "artifacts": {},
        }

    @staticmethod
    def file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def copy_input(self, source: Path, name: str | None = None) -> Path:
        target = self.input_dir / (name or source.name)
        shutil.copy2(source, target)
        self.record_artifact(f"input:{target.name}", target)
        return target

    def record_artifact(self, key: str, path: Path) -> None:
        path = Path(path)
        value: dict[str, Any] = {"path": str(path)}
        if path.exists() and path.is_file():
            value["sha256"] = self.file_hash(path)
            value["size_bytes"] = path.stat().st_size
        self.manifest["artifacts"][key] = value
        self.save_manifest()

    def record_value(self, key: str, value: Any) -> None:
        self.manifest[key] = value
        self.save_manifest()

    def save_json(self, key: str, relative_dir: Path, filename: str, data: Any) -> Path:
        path = relative_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.record_artifact(key, path)
        return path

    def save_text(self, key: str, relative_dir: Path, filename: str, text: str) -> Path:
        path = relative_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        self.record_artifact(key, path)
        return path

    def save_manifest(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _git_commit() -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except Exception:
            return None
