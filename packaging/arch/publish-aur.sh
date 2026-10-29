#!/bin/sh
# Обновляет пакет в AUR: подставляет версию и sha256 архива тега, пересобирает .SRCINFO, пушит.
#   packaging/arch/publish-aur.sh <версия>
# Нужен SSH-ключ, добавленный в аккаунт https://aur.archlinux.org (в CI — секрет AUR_SSH_KEY).
set -eu
VER=$1
URL="https://github.com/miahke/kachaning/archive/refs/tags/v$VER.tar.gz"
W=$(mktemp -d)
trap 'rm -rf "$W"' EXIT

curl -fsSL "$URL" -o "$W/src.tar.gz"
SUM=$(sha256sum "$W/src.tar.gz" | cut -d' ' -f1)
git clone -q ssh://aur@aur.archlinux.org/kachaning.git "$W/aur"
sed -e "s/^pkgver=.*/pkgver=$VER/" -e "s/^pkgrel=.*/pkgrel=1/" -e "s/^sha256sums=.*/sha256sums=('$SUM')/" \
    -e '/^# в репозитории — SKIP/d' packaging/arch/PKGBUILD > "$W/aur/PKGBUILD"
cp packaging/arch/kachaning.install "$W/aur/"
python3 packaging/arch/srcinfo.py "$W/aur/PKGBUILD" > "$W/aur/.SRCINFO"
cd "$W/aur"
git add PKGBUILD .SRCINFO kachaning.install
if git diff --cached --quiet; then echo "AUR: nothing to update"; exit 0; fi
git -c user.name=miahke -c user.email=miahke@users.noreply.github.com commit -qm "Update to $VER"
git push -q origin HEAD:master
echo "AUR: kachaning $VER pushed"
