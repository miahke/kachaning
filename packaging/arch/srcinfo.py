#!/usr/bin/env python3
"""Печатает .SRCINFO для нашего PKGBUILD без makepkg (в CI на Ubuntu его нет).
Значения берёт сам bash из PKGBUILD, так что результат совпадает с `makepkg --printsrcinfo`."""
import subprocess
import sys

FIELDS = ["pkgdesc", "pkgver", "pkgrel", "url", "install", "arch", "license",
          "depends", "optdepends", "source", "sha256sums"]
script = 'source "$1"; for v in %s; do eval "printf \'%%s\\0\' \\"\\${#$v[@]}\\" \\"\\${$v[@]}\\""; done' % " ".join(FIELDS)
out = subprocess.run(["bash", "-c", script, "_", sys.argv[1]], capture_output=True, check=True, text=True).stdout
vals, it = {}, iter(out.split("\0"))
for f in FIELDS:
    vals[f] = [next(it) for _ in range(int(next(it)))]
name = subprocess.run(["bash", "-c", 'source "$1"; printf %s "$pkgname"', "_", sys.argv[1]],
                      capture_output=True, check=True, text=True).stdout

print("pkgbase = " + name)
for f in FIELDS:
    for v in vals[f]:
        print("\t%s = %s" % (f, v))
print("\npkgname = " + name)
