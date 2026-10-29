#!/bin/sh
# Добавляет .deb в apt-репозиторий (ветка gh-pages → https://miahke.github.io/kachaning) и подписывает его.
#   scripts/update-apt-repo.sh <каталог gh-pages> <файл .deb> <отпечаток ключа>
# Нужны apt-ftparchive (пакет apt-utils) и gpg с импортированным секретным ключом.
set -eu
REPO=$1 DEB=$2 KEY=$3
ARCHES="amd64 arm64 armhf i386 all"

mkdir -p "$REPO/pool/main/k/kachaning"
cp "$DEB" "$REPO/pool/main/k/kachaning/"
cd "$REPO"
for a in $ARCHES; do
    d=dists/stable/main/binary-$a
    mkdir -p "$d"
    apt-ftparchive packages pool > "$d/Packages"
    gzip -9nkf "$d/Packages"
done
apt-ftparchive \
    -o APT::FTPArchive::Release::Origin=Kachaning \
    -o APT::FTPArchive::Release::Label=Kachaning \
    -o APT::FTPArchive::Release::Suite=stable \
    -o APT::FTPArchive::Release::Codename=stable \
    -o "APT::FTPArchive::Release::Architectures=$ARCHES" \
    -o APT::FTPArchive::Release::Components=main \
    -o APT::FTPArchive::Release::Description="Kachaning updates" \
    release dists/stable > Release.tmp
mv Release.tmp dists/stable/Release
rm -f dists/stable/InRelease dists/stable/Release.gpg
gpg --batch --yes --local-user "$KEY" --clearsign -o dists/stable/InRelease dists/stable/Release
gpg --batch --yes --local-user "$KEY" -abs -o dists/stable/Release.gpg dists/stable/Release
gpg --export "$KEY" > kachaning-archive-keyring.gpg
touch .nojekyll
cat > index.html <<HTML
<!doctype html><meta charset="utf-8"><title>Kachaning apt repository</title>
<p>apt repository for <a href="https://github.com/miahke/kachaning">Kachaning</a>.
Install the .deb from <a href="https://github.com/miahke/kachaning/releases/latest">Releases</a> — it adds this repository automatically.
HTML
