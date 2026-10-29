#!/bin/sh
# Собирает kachaning_<версия>_all.deb в dist/. Нужны только ar, tar, gzip/xz — dpkg-deb не обязателен.
# Запуск из корня репозитория: packaging/debian/build-deb.sh
set -eu
VER=$(python3 kachaning.py --version)
OUT=dist/kachaning_${VER}_all.deb
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
R="$WORK/root"
C="$WORK/control"

scripts/install-files.sh "$R"
install -Dm644 LICENSE "$R/usr/share/doc/kachaning/copyright"
# apt-источник: после установки .deb обновления приходят через «Менеджер обновлений»
install -Dm644 packaging/debian/kachaning.list "$R/etc/apt/sources.list.d/kachaning.list"
install -Dm644 packaging/debian/kachaning-archive-keyring.gpg "$R/usr/share/keyrings/kachaning-archive-keyring.gpg"

mkdir -p "$C"
SIZE=$(du -sk "$R" | cut -f1)
sed -e "s/@VERSION@/$VER/" -e "s/@SIZE@/$SIZE/" packaging/debian/control.in > "$C/control"
echo /etc/apt/sources.list.d/kachaning.list > "$C/conffiles"
for s in postinst prerm; do install -m755 "packaging/debian/$s" "$C/$s"; done
(cd "$R" && find . -type f ! -path ./etc/\* -printf '%P\0' | sort -z | xargs -0 md5sum) > "$C/md5sums"

# владелец файлов — root, время — фиксированное: сборка воспроизводима
T="--owner=0 --group=0 --numeric-owner --sort=name --mtime=@${SOURCE_DATE_EPOCH:-0}"
tar $T -C "$C" -czf "$WORK/control.tar.gz" .
tar $T -C "$R" -cJf "$WORK/data.tar.xz" .
echo 2.0 > "$WORK/debian-binary"
mkdir -p dist
rm -f "$OUT"
(cd "$WORK" && ar rcD "$OLDPWD/$OUT" debian-binary control.tar.gz data.tar.xz)
echo "$OUT"
