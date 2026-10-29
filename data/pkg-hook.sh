#!/bin/sh
# Вызывается менеджером пакетов (pacman, dpkg):
#   install — после установки или обновления: таймер автоотзыва прав переводится на файл из пакета;
#   remove  — перед удалением: права администратора снимаются, таймер и служебные файлы удаляются.
# Настройки SSH-сервера и ключи помощников в ~/.ssh/authorized_keys остаются — их видно и можно
# удалить на вкладке «Принимать» до удаления пакета.
set -e
UNIT=/etc/systemd/system/kachaning-expire.service
PKG_SCRIPT=/usr/share/kachaning/kachaning.py

case "$1" in
install)
    if [ -f "$UNIT" ] && ! grep -q "$PKG_SCRIPT" "$UNIT"; then
        sed -i "s|^ExecStart=.*|ExecStart=/usr/bin/python3 -I $PKG_SCRIPT --root expire-check|" "$UNIT"
        rm -rf /usr/local/lib/kachaning
        systemctl daemon-reload 2>/dev/null || true
    fi
    ;;
remove)
    systemctl disable --now kachaning-expire.timer 2>/dev/null || true
    rm -f /etc/sudoers.d/90-kachaning /etc/systemd/system/kachaning-expire.timer "$UNIT"
    rm -rf /etc/kachaning /usr/local/lib/kachaning
    systemctl daemon-reload 2>/dev/null || true
    ;;
*)
    echo "usage: $0 install|remove" >&2
    exit 2
    ;;
esac
