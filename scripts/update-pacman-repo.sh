#!/bin/sh
# Кладёт пакет для Arch в pacman-репозиторий (ветка gh-pages → https://miahke.github.io/kachaning/arch),
# подписывает пакет и базу данных.
#   scripts/update-pacman-repo.sh <каталог gh-pages> <файл .pkg.tar.zst> <отпечаток ключа>
# Нужны repo-add (пакет pacman) и gpg с секретным ключом.
set -eu
REPO=$1 PKG=$2 KEY=$3
D=$REPO/arch
B=$(basename "$PKG")

mkdir -p "$D"
rm -f "$D"/kachaning-*.pkg.tar.zst "$D"/kachaning-*.pkg.tar.zst.sig
cp "$PKG" "$D/$B"
gpg --batch --yes --local-user "$KEY" --detach-sign --no-armor -o "$D/$B.sig" "$D/$B"
cd "$D"
rm -f kachaning.db* kachaning.files*
repo-add --sign --key "$KEY" kachaning.db.tar.zst "$B" >/dev/null
# GitHub Pages плохо переносит симлинки: pacman просит kachaning.db, подставляем настоящие копии
for f in kachaning.db kachaning.db.sig kachaning.files kachaning.files.sig; do
    cp -L --remove-destination "$f" "$f.tmp"
    mv "$f.tmp" "$f"
done
