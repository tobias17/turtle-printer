"""
Directly patches the installed amulet-core package to fix a real bug in
its Java 1.12.2 ("anvil_na") chunk encoder.

(A runtime monkeypatch - reassigning AnvilNAInterface._encode_height from
our own code at import time - was tried first and didn't take effect, for
reasons not fully tracked down: amulet must resolve _encode_height some
way other than a plain attribute lookup on the class, since the
reassignment provably had no effect on an actual save even though the
class attribute itself was confirmed reassigned. Editing the installed
file directly sidesteps that entirely, since it changes what actually
executes.)

AnvilNAInterface._encode_height has its if/else branches inverted: when a
valid heightmap IS provided, it writes 256 zeros (discarding the real
data); when none is provided, it crashes calling .ravel() on None. Every
chunk this project's world_import/import_structure.py has ever written
ends up with a HeightMap claiming "nothing above Y=0" as a result,
regardless of how much real content is there - confirmed directly by
round-tripping a hand-computed heightmap through a save/reload cycle.

Idempotent and safe to re-run: checks whether the buggy snippet is still
present before touching anything, and no-ops if it's already been fixed
(by this script, or by a future amulet-core release). Run this once after
any fresh `pip install -r requirements.txt` (import_structure.py does NOT
run this automatically - it's a one-time environment fix, not a per-import
step):

    python world_import/patch_amulet.py
"""

from pathlib import Path

import amulet.level.interfaces.chunk.anvil.anvil_na as anvil_na

TARGET_FILE = Path(anvil_na.__file__)

BUGGY = '''        if (
            isinstance(height, numpy.ndarray)
            and numpy.issubdtype(height.dtype, numpy.integer)
            and height.shape == (16, 16)
        ):
            self.set_layer_obj(
                data,
                self.HeightMap,
                IntArrayTag(numpy.zeros(256, dtype=numpy.uint32)),
            )
        elif self._features["height_map"] == "256IARequired":
            self.set_layer_obj(data, self.HeightMap, IntArrayTag(height.ravel()))'''

FIXED = '''        if (
            isinstance(height, numpy.ndarray)
            and numpy.issubdtype(height.dtype, numpy.integer)
            and height.shape == (16, 16)
        ):
            self.set_layer_obj(
                data,
                self.HeightMap,
                IntArrayTag(height.ravel().astype(numpy.uint32)),
            )
        elif self._features["height_map"] == "256IARequired":
            self.set_layer_obj(data, self.HeightMap, IntArrayTag(numpy.zeros(256, dtype=numpy.uint32)))'''


def main():
    text = TARGET_FILE.read_text()
    if FIXED in text:
        print(f"{TARGET_FILE} already patched - nothing to do")
        return
    if BUGGY not in text:
        raise SystemExit(
            f"Expected buggy snippet not found in {TARGET_FILE} - amulet-core's version/code has "
            f"likely changed since this patch was written. Check whether the bug still exists "
            f"(see this file's docstring) before assuming it's already fixed."
        )
    TARGET_FILE.write_text(text.replace(BUGGY, FIXED))
    print(f"Patched {TARGET_FILE}")


if __name__ == "__main__":
    main()
