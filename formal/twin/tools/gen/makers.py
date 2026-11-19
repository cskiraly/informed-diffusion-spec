#!/usr/bin/env python3
"""The makers of a `Tables` value in the replay as built: Lean's own account (TablesMakers.lean), and its controls.

    python3 makers.py --check TWINDIR             TWINDIR is a built twin (its .lake holds the replay's modules)
    python3 makers.py --control TWINDIR WORKDIR   ten copies of TWINDIR's sources, each with one declaration planted

gen.py --check holds the hand-written files to one instance of `Tables`, by their text. A text rule sees the
spellings it names. TablesMakers.lean asks the built modules which constants make a `Tables` value, however they
are written, and fails unless the list is the replay's one instance; this script runs it (`lake env lean`).

The controls: each plants one declaration that makes a `Tables` value at the end of a hand-written file, in a
spelling the text rule passes (a qualified name, an abbreviation, no type written, a `let` inside a function, a
structure update, an axiom, an `opaque` constant's body, a module of the twin's under one of the toolchain's names), builds
the copy from nothing, and runs the check on it: the check must fail and list
the planted constant, with how it is made. Each line also says what gen.py's text check finds in that copy (it
must be nothing: that is why this check exists). A plant that does not build fails its control.

Each build and check runs as a plain child, under the caller's limits; `lake` and `lean` are the ones on PATH.
"""
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gen                              # noqa: E402: the text check, for what it finds in a planted copy

ONE = "SpecTwin.Replay.instTablesR (SpecTwin.Replay): a Tables value; mentions [SpecTwin.Tables.ofState]"
ST = "StateM SpecTwin.State"
R = "SpecTwin.Replay.R"
PLANTS = [  # (what, the file it is appended to, the text, the line the check must list)
    ("an instance by `def`, its type written with the namespace", "SpecTwin/Sec61.lean",
     f"\n@[instance] def SpecTwin.mineQ : SpecTwin.Tables ({ST}) := SpecTwin.Tables.ofState fun _ => pure ()\n",
     "SpecTwin.mineQ (SpecTwin.Sec61): a Tables value; mentions [SpecTwin.Tables.ofState]"),
    ("an instance of an abbreviation of Tables", "SpecTwin/Sec61.lean",
     f"\nabbrev SpecTwin.T2 := SpecTwin.Tables\n"
     f"instance SpecTwin.viaAbbrev : SpecTwin.T2 ({ST}) :=\n  SpecTwin.Tables.ofState fun _ => pure ()\n",
     "SpecTwin.viaAbbrev (SpecTwin.Sec61): a Tables value; mentions [SpecTwin.Tables.ofState]"),
    ("a definition with no type written", "SpecTwin/Sec61.lean",
     f"\ndef SpecTwin.untyped := SpecTwin.Tables.ofState (m := {ST}) fun _ => pure ()\n",
     "SpecTwin.untyped (SpecTwin.Sec61): a Tables value; mentions [SpecTwin.Tables.ofState]"),
    ("a `let` of one inside a function", "SpecTwin/Replay.lean",
     f"\ndef SpecTwin.Replay.shadowed : {R} Unit :=\n"
     f"  let _ : SpecTwin.Tables {R} := SpecTwin.Tables.lift (m := {R}) fun x => x\n  pure ()\n",
     "SpecTwin.Replay.shadowed (SpecTwin.Replay): not a Tables value; mentions [SpecTwin.Tables.lift]"),
    ("the replay's instance with one operation changed, by a structure update", "SpecTwin/Replay.lean",
     f"\ndef SpecTwin.Replay.weaker : SpecTwin.Tables {R} :=\n"
     f"  {{ (inferInstance : SpecTwin.Tables {R}) with setTried := fun _ _ _ => pure () }}\n",
     "SpecTwin.Replay.weaker (SpecTwin.Replay): a Tables value; mentions [SpecTwin.Tables.mk]"),
    ("an axiom of one", "SpecTwin/Sec44.lean",
     f"\naxiom SpecTwin.given : SpecTwin.Tables ({ST})\n",
     "SpecTwin.given (SpecTwin.Sec44): a Tables value; mentions []"),
    # the value of an opaque constant must be read too
    ("an `opaque` constant with a `let` of one inside it", "SpecTwin/Replay.lean",
     f"\nopaque SpecTwin.Replay.hidden : {R} Unit :=\n"
     f"  let _ : SpecTwin.Tables {R} := SpecTwin.Tables.lift (m := {R}) fun x => x\n  pure ()\n",
     "SpecTwin.Replay.hidden (SpecTwin.Replay): not a Tables value; mentions [SpecTwin.Tables.lift]"),
    # a module of the twin's own under a name of the toolchain's, made a library of its own in the lakefile and
    # imported by Replay.lean. A module is the twin's by its file. (Under `Lean.` such a twin does not build: its
    # directory hides Lean's own modules from Replay.lean, which imports Lean.Data.Json. `Lake.` is a root of the
    # toolchain's that this twin does not import.)
    ("a module of the twin's named Lake.ExtraTables, which makes one", "SpecTwin/Replay.lean", "",
     "Lake.ExtraTables.made (Lake.ExtraTables): a Tables value; mentions [SpecTwin.Tables.ofState]"),
]
# Two plants that the check must refuse outright, each with the words of its refusal.
REFUSED = [
    ("a library of the package whose source lies outside the twin's directory, named Lake.OutsideTables, which makes one",
     "outside", "the replay imports a module that is neither a file of the twin nor the toolchain's: [Lake.OutsideTables"),
    ("a maker more in the generated SpecTwin/Tables.lean", "generated",
     "the generated SpecTwin.Tables gives a Tables by other constants than the five known"),
]


def refused_plant(d, kind):
    if kind == "outside":               # the module's source beside the copy, not in it; its library in the lakefile
        out = d.parent / (d.name + "-outside") / "Lake"
        if out.parent.exists():
            shutil.rmtree(out.parent)
        out.mkdir(parents=True)
        (out / "OutsideTables.lean").write_text(
            f"import SpecTwin.Tables\n\ndef Lake.OutsideTables.made : SpecTwin.Tables ({ST}) :=\n"
            f"  SpecTwin.Tables.ofState fun _ => pure ()\n")
        lf = d / "lakefile.lean"
        lf.write_text(lf.read_text() + f"\nlean_lib Outside where\n  srcDir := \"../{d.name}-outside\"\n  roots := #[`Lake.OutsideTables]\n")
        rp = d / "SpecTwin" / "Replay.lean"
        rp.write_text("import Lake.OutsideTables\n" + rp.read_text())
    else:                               # in the generated file itself, inside its namespace: one more function that gives a Tables
        f = d / "SpecTwin" / "Tables.lean"
        text = f.read_text()
        end = "\nend SpecTwin"
        assert text.count(end) == 1, "the generated Tables.lean does not end its namespace once"
        f.write_text(text.replace(end, "\ndef Tables.again {m : Type → Type} [Tables m] : Tables m := inferInstance\n" + end))


def control_refused(twin, work, n, what, kind, must):
    d = Path(work) / f"makers-{n}"
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(twin, d, ignore=shutil.ignore_patterns(*gen.NOT_SOURCES))
    refused_plant(d, kind)
    b = subprocess.run(["lake", "build", "replay"], cwd=d, capture_output=True, text=True)
    if b.returncode:
        return False, f"control, {what}: the planted copy does not build  <-- it must\n{(b.stdout + b.stderr)[-1500:]}"
    rc, out = lean(d)
    good = rc == 1 and must in out.replace("\n", "")
    return good, (f"control, {what}: the check rc={rc}; {'says: ' + must if must in out.replace(chr(10), '') else 'does NOT say: ' + must}"
                  f"{'' if good else '  <-- must be rc=1, with those words'}")


def extra_module(d):
    """The last plant's files: the module, its library in the lakefile, and its import at Replay.lean's head."""
    (d / "Lake").mkdir()
    (d / "Lake" / "ExtraTables.lean").write_text(
        f"import SpecTwin.Tables\n\ndef Lake.ExtraTables.made : SpecTwin.Tables ({ST}) :=\n"
        f"  SpecTwin.Tables.ofState fun _ => pure ()\n")
    lf = d / "lakefile.lean"
    lf.write_text(lf.read_text() + "\nlean_lib LeanExtra where\n  roots := #[`Lake.ExtraTables]\n")
    rp = d / "SpecTwin" / "Replay.lean"
    rp.write_text("import Lake.ExtraTables\n" + rp.read_text())


def modules(twin):
    """The twin's modules, by its files: every .lean file of its directory but the build's and the lakefile, as a
    module's name (SpecTwin/Sec61.lean -> SpecTwin.Sec61)."""
    twin = Path(twin)
    return sorted(".".join(f.relative_to(twin).with_suffix("").parts) for f in twin.rglob("*.lean")
                  if not set(f.relative_to(twin).parts) & set(gen.NOT_SOURCES) and f.name != "lakefile.lean")


def lean(twin):
    """Run the check in a built twin: its exit code, and what it printed."""
    p = subprocess.run(["lake", "env", "lean", str(HERE / "TablesMakers.lean")], cwd=twin, capture_output=True,
                       text=True, env={**os.environ, "TWIN_MODULES": " ".join(modules(twin))})
    return p.returncode, p.stdout + p.stderr


def check(twin):
    rc, out = lean(twin)
    print(out, end="")
    return 1 if rc else 0


def listed(out):
    return [l[2:] for l in out.splitlines() if re.match(r"  \S+ \(\S+\): ", l)]


def control(twin, work, n, what, file, text, must):
    d = Path(work) / f"makers-{n}"
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(twin, d, ignore=shutil.ignore_patterns(*gen.NOT_SOURCES))
    (d / file).write_text((d / file).read_text() + text)
    if not text:
        extra_module(d)
    found = gen.differing(d)
    b = subprocess.run(["lake", "build", "replay"], cwd=d, capture_output=True, text=True)
    if b.returncode:
        return False, f"control, {what}: the planted copy does not build  <-- it must\n{(b.stdout + b.stderr)[-1500:]}"
    rc, out = lean(d)
    got = listed(out)
    good = rc == 1 and got == sorted([ONE, must]) and not found
    return good, (f"control, {what} (at the end of {file}): the check rc={rc}, lists {len(got)}: "
                  f"{'; '.join(g for g in got if g != ONE) or 'nothing but the one instance'}; gen.py's text check finds "
                  f"{', '.join(found) or 'nothing'}"
                  f"{'' if good else '  <-- must be rc=1, the one instance and: ' + must + '; and nothing by the text check'}")


def controls(twin, work):
    Path(work).mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(lambda np: control(twin, work, np[0], *np[1]), enumerate(PLANTS, 1)))
        res += list(ex.map(lambda np: control_refused(twin, work, np[0], *np[1]), enumerate(REFUSED, len(PLANTS) + 1)))
    for _, line in res:
        print(line)
    ok = all(g for g, _ in res)
    print("ok: every planted maker of a Tables value is listed, and the check fails on each" if ok
          else "controls of the makers' check wrong")
    return 0 if ok else 1


def main(argv):
    if len(argv) == 2 and argv[0] == "--check":
        return check(Path(argv[1]).resolve())
    if len(argv) == 3 and argv[0] == "--control":
        return controls(Path(argv[1]).resolve(), Path(argv[2]).resolve())
    print("usage: makers.py --check TWINDIR | --control TWINDIR WORKDIR", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
