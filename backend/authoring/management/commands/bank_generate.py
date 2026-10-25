from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from authoring.bank_workflow import LIVE, Bank, Kind, drafts, next_version, write
from authoring.bankgen import BankGenerator
from contentkit.models import VerbBank
from curriculum import content
from inference.providers import get_chat_model


class Command(BaseCommand):
    help = "Generate verb banks or vocabulary sets with the local LLM into content/drafts/."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("kind", choices=["verbs", "vocab"])
        parser.add_argument("ids", nargs="*", help="infinitives or theme ids (default: all)")
        parser.add_argument("--set", action="append", default=[], help="verb set id(s)")
        parser.add_argument("--level", action="append", default=[], help="theme level(s)")
        parser.add_argument("--force", action="store_true", help="regenerate published ones")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args: Any, **options: Any) -> None:
        root = Path(settings.CONTENT_DIR)
        ref, banks = content.reference(), content.banks()
        generator = BankGenerator(
            get_chat_model(),
            ref,
            model_name=f"ollama/{settings.INFERENCE['LLM_MODEL']}",
            progress=lambda m: self.stdout.write(f"  {m}"),
        )
        kind: Kind = "verbs" if options["kind"] == "verbs" else "vocabulary"
        existing = set(drafts(root, kind)) | {p.stem for p in (root / LIVE[kind]).glob("*.yaml")}
        todo = self._targets(kind, options, banks)
        if not options["force"]:
            todo = [t for t in todo if t[0] not in existing]
        if options["limit"]:
            todo = todo[: options["limit"]]
        if not todo:
            self.stdout.write("Nothing to generate.")
            return
        for bank_id, target in todo:
            version = next_version(root, kind, bank_id)
            self.stdout.write(f"{bank_id}: generating v{version}")
            bank: Bank
            try:
                if kind == "verbs":
                    infinitive, tenses = target
                    bank, issues = generator.verb_bank(
                        infinitive, extra_tenses=tenses, version=version
                    )
                else:
                    bank, issues = generator.vocab_set(target, version=version)
            except Exception as exc:  # keep going: one bad item must not stop a batch
                self.stderr.write(f"{bank_id}: failed: {exc}")
                continue
            path = write(root, kind, bank)
            size = len(bank.sentences) if isinstance(bank, VerbBank) else len(bank.entries)
            errors = [i for i in issues if i.severity == "error"]
            self.stdout.write(
                f"{bank_id}: {size} items, {len(errors)} errors -> {path.relative_to(root)}"
            )
            for issue in issues:
                self.stdout.write(f"    {issue}")
        stats = generator.stats
        self.stdout.write(
            f"{stats.calls} LLM calls, {stats.seconds:.0f}s, {stats.tokens} tokens, "
            f"{stats.repairs} repairs"
        )

    def _targets(self, kind: str, options: dict[str, Any], banks: Any) -> list[tuple[str, Any]]:
        from contentkit.conjugation import verb_slug

        if kind == "verbs":
            sets = banks.verb_sets.sets if banks.verb_sets else []
            chosen = [s for s in sets if s.id in options["set"]] if options["set"] else sets
            if options["set"] and len(chosen) != len(options["set"]):
                raise CommandError("unknown verb set")
            tenses: dict[str, list[str]] = {}
            for verb_set in sets:
                for verb in verb_set.verbs:
                    tenses.setdefault(verb, []).extend(verb_set.tenses)
            verbs = options["ids"] or [v for s in chosen for v in s.verbs]
            return [
                (verb_slug(v), (v, sorted(set(tenses.get(v, []))))) for v in dict.fromkeys(verbs)
            ]
        themes = banks.vocab_themes.themes if banks.vocab_themes else []
        if options["ids"]:
            unknown = set(options["ids"]) - {t.id for t in themes}
            if unknown:
                raise CommandError(f"unknown theme(s): {', '.join(sorted(unknown))}")
            themes = [t for t in themes if t.id in options["ids"]]
        if options["level"]:
            themes = [t for t in themes if t.level in options["level"]]
        return [(t.id, t) for t in themes]
