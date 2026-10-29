#!/bin/sh
# Раскладывает файлы программы в DESTDIR. Общий для PKGBUILD и сборки .deb.
# Запуск из корня репозитория: scripts/install-files.sh <DESTDIR>
set -eu
D=${1:?usage: install-files.sh DESTDIR}

install -Dm755 kachaning.py "$D/usr/share/kachaning/kachaning.py"
install -Dm755 data/pkg-hook.sh "$D/usr/share/kachaning/pkg-hook.sh"
install -Dm644 data/kachaning.desktop "$D/usr/share/applications/kachaning.desktop"
install -Dm644 data/kachaning.svg "$D/usr/share/icons/hicolor/scalable/apps/kachaning.svg"
install -d "$D/usr/bin"
ln -sf ../share/kachaning/kachaning.py "$D/usr/bin/kachaning"
