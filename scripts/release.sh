#!/bin/sh
# Выпуск новой версии: scripts/release.sh 2.4.0
# Меняет версию в kachaning.py и PKGBUILD, проверяет CHANGELOG, делает коммит и тег.
# Отправка на GitHub — после подтверждения; дальше всё делает .github/workflows/release.yml.
set -eu
VER=${1:?usage: scripts/release.sh X.Y.Z}
echo "$VER" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || { echo "version must be X.Y.Z"; exit 1; }
cd "$(dirname "$0")/.."
test -z "$(git status --porcelain)" || { echo "commit or stash your changes first"; exit 1; }
grep -q "^## $VER" CHANGELOG.md || { echo "add a '## $VER' section to CHANGELOG.md first"; exit 1; }
git rev-parse -q --verify "refs/tags/v$VER" >/dev/null && { echo "tag v$VER already exists"; exit 1; }

sed -i "s/^VERSION = \".*\"/VERSION = \"$VER\"/" kachaning.py
sed -i -e "s/^pkgver=.*/pkgver=$VER/" -e "s/^pkgrel=.*/pkgrel=1/" packaging/arch/PKGBUILD
python3 tests/test_core.py >/dev/null
git commit -qam "Release $VER"
git tag -a "v$VER" -m "Kachaning $VER"
echo "Ready: commit and tag v$VER."
printf "Push to GitHub now? [y/N] "
read -r a
case "$a" in
y|Y) git push origin HEAD "v$VER" ;;
*) echo "Later: git push origin HEAD v$VER" ;;
esac
