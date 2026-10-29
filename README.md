# Качанинг

[English](README.en.md)

Удалённая помощь между друзьями на Linux. Один помогает, другой принимает помощь, а связь идёт через [Tailscale](https://tailscale.com) — без белых IP, проброса портов и TeamViewer.

- **Мастер настройки** при первом запуске: ставит Tailscale, входит в сеть, настраивает SSH-сервер.
- **Каждый компьютер умеет и то, и другое**: подключаться к друзьям и принимать подключения.
- **Ключи помощников работают только из сети Tailscale.** Ключ из интернета не пустит, даже если утечёт.
- **Права администратора на время**: 2 часа, сутки, неделя или бессрочно. Срочные снимаются сами — systemd-таймер, даже если программа закрыта.
- **Проверка соединения по шагам**: Tailscale, доступность узла, SSH, ключ, sudo. На каждой ошибке — кнопка «Исправить».
- Темы в стиле Material You, светлая и тёмная, масштаб, русский и английский интерфейс.

## Установка

### Arch, CachyOS, Manjaro, EndeavourOS — свой pacman-репозиторий

Один раз добавьте ключ репозитория и сам репозиторий:

```bash
curl -fsSL https://miahke.github.io/kachaning/kachaning-archive-keyring.gpg | sudo pacman-key --add -
```

```bash
sudo pacman-key --lsign-key 0504ADA5305E316D8D6BC7B65E85D3F41F4E99E0
```

```bash
printf '\n[kachaning]\nSigLevel = Required DatabaseRequired\nServer = https://miahke.github.io/kachaning/arch\n' | sudo tee -a /etc/pacman.conf
```

Дальше обычная установка, а обновления приходят с `pacman -Syu`:

```bash
sudo pacman -Syu kachaning
```

Отпечаток ключа: `0504 ADA5 305E 316D 8D6B  C7B6 5E85 D3F4 1F4E 99E0`. Сверьте его с тем, что показал `pacman-key`, прежде чем доверять ключу.

Пакета в AUR пока нет. Из исходников можно собрать так: `git clone https://github.com/miahke/kachaning`, затем `cd kachaning/packaging/arch && makepkg -si` (источник в PKGBUILD — тег на GitHub).

### Linux Mint, Ubuntu, Debian, Pop!_OS

Скачайте `kachaning_*_all.deb` со страницы [Releases](https://github.com/miahke/kachaning/releases/latest) и откройте его двойным щелчком, или:

```bash
sudo apt install ./kachaning_*_all.deb
```

Пакет сам подключает apt-репозиторий программы, так что новые версии приходят через «Менеджер обновлений» вместе с остальными обновлениями системы.

<details>
<summary>Подключить репозиторий вручную</summary>

```bash
sudo curl -fsSLo /usr/share/keyrings/kachaning-archive-keyring.gpg https://miahke.github.io/kachaning/kachaning-archive-keyring.gpg
```

```bash
echo "deb [signed-by=/usr/share/keyrings/kachaning-archive-keyring.gpg] https://miahke.github.io/kachaning stable main" | sudo tee /etc/apt/sources.list.d/kachaning.list
```

```bash
sudo apt update && sudo apt install kachaning
```

Отпечаток ключа репозитория: `0504 ADA5 305E 316D 8D6B  C7B6 5E85 D3F4 1F4E 99E0`
</details>

### Без пакета

```bash
python3 kachaning.py --install
```

Ставит копию в `~/.local`. Обновлять придётся вручную. Если позже поставить пакет, программа сама уберёт эту копию и перейдёт на пакетную.

**Зависимости:** Python 3.8+, PyGObject, GTK 3, polkit (pkexec), OpenSSH, sudo, systemd. Tailscale мастер поставит сам.

## Как пользоваться

1. Оба друга ставят Качанинг и проходят мастер, входя в **одну** сеть Tailscale — или один делится своим компьютером с другим через админку Tailscale.
2. Друзья обмениваются кодами (строки `KCH1:…`):
   - помощник копирует **«код помощника»** на вкладке «Подключиться», друг вставляет его на вкладке «Принимать»;
   - друг копирует **«код для подключения»** на вкладке «Принимать», помощник вставляет его на вкладке «Подключиться».
3. Права администратора друг выдаёт помощнику на нужный срок и может снять их в любой момент.

## Безопасность

- Ключ помощника записывается в `~/.ssh/authorized_keys` с ограничением `from="100.64.0.0/10,fd7a:115c:a1e0::/48"`, то есть только адреса Tailscale.
- Права выдаются файлом `/etc/sudoers.d/90-kachaning`, который проверяется `visudo`. Снимает его таймер `kachaning-expire.timer`.
- Действия от root программа выполняет через `pkexec` и только из системного файла, который пользователь не может подменить.
- При удалении пакета права снимаются, а таймер удаляется. Ключи помощников остаются — удалите их на вкладке «Принимать» до удаления, если нужно.

Нашли уязвимость — напишите через [Security advisories](https://github.com/miahke/kachaning/security/advisories/new), а не в открытые issues.

## Для разработчиков

```bash
python3 tests/test_core.py
```

```bash
packaging/debian/build-deb.sh
```

```bash
cd packaging/arch && makepkg -si
```

Выпуск версии: добавить раздел в `CHANGELOG.md`, затем `scripts/release.sh X.Y.Z`. Тег запускает GitHub Actions: сборка `.deb`, релиз, обновление apt-репозитория на GitHub Pages, обновление pacman-репозитория. Подробнее — [RELEASING.md](RELEASING.md).

## Лицензия

[GPL-3.0-or-later](LICENSE) © 2026 miahke
