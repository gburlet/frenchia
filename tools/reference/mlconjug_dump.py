# /// script
# requires-python = ">=3.10,<3.11"
# dependencies = [
#   "mlconjug3==4.0.1",
# ]
# ///
"""Helper for build_reference.py: dump mlconjug3 simple-tense forms as JSON.

Runs in its own (Python 3.10) environment because mlconjug3 4.0.1 ships a
pickled model that only loads on py<3.11 and needs numpy<2, which conflicts
with verbecc 2.0.3 (numpy==2.3.3).

Usage: mlconjug_dump.py <in.json (list of infinitives)> <out.json>
"""
import json
import sys
import warnings

warnings.filterwarnings("ignore")
import mlconjug3  # noqa: E402

MAP = {
    "indicatif.present": ("Indicatif", "Présent"),
    "indicatif.imparfait": ("Indicatif", "Imparfait"),
    "indicatif.futur_simple": ("Indicatif", "Futur"),
    "indicatif.passe_simple": ("Indicatif", "Passé Simple"),
    "conditionnel.present": ("Conditionnel", "Présent"),
    "subjonctif.present": ("Subjonctif", "Présent"),
}
PERSONS = {"1s": "je", "2s": "tu", "3s": "il", "1p": "nous", "2p": "vous", "3p": "ils"}


def main() -> None:
    verbs = json.load(open(sys.argv[1], encoding="utf-8"))
    conj = mlconjug3.Conjugator(language="fr")
    out = {}
    for v in verbs:
        try:
            info = conj.conjugate(v).conjug_info
        except Exception as e:  # noqa: BLE001
            out[v] = {"error": repr(e)}
            continue
        res = {}
        for key, (mood, tense) in MAP.items():
            block = info.get(mood, {}).get(tense)
            if not block:
                continue
            res[key] = {PERSONS[k]: x for k, x in block.items() if k in PERSONS and x}
        out[v] = res
    json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
