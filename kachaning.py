#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 miahke
#
# Качанинг — удалённая помощь через Tailscale.  https://github.com/miahke/kachaning
#
# Одна программа для обеих сторон:
#   «Сеть»         Tailscale: вкл/выкл, вход и продление ключа, аккаунты, устройства,
#                  выходной узел, Taildrop
#   «Подключиться» ты помогаешь: свои подключения к друзьям, проверка связи, SSH в терминале
#   «Принимать»    тебе помогают: SSH-сервер, ключи помощников, права админа на время
#
# Люди обмениваются кодами KCH1:… — в коде помощника его публичный SSH-ключ,
# в коде подключения имя компьютера в Tailscale и пользователь.
#
# Служебные режимы:
#   --root <действие>  действия от root (вызывается через pkexec или sudo)
#   --check            все проверки в терминале
#   --notify-check     уведомления о сроке ключей (таймер systemd --user)
#   --install          ярлык, таймер уведомлений, перенос со старой версии
#   --version          версия
#   --icon             значок (SVG) — для сборки пакетов
#
# Установка пакетом (AUR, .deb) кладёт программу в /usr/share/kachaning — тогда
# обновляет её менеджер пакетов, а копия в ~/.local не нужна.

import base64
import colorsys
import datetime as dt
import getpass
import glob
import html
import ipaddress
import json
import os
import pwd
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

VERSION = "2.3.1"
CONFIG_DIR = os.path.expanduser("~/.config/kachaning")
CONFIG_FILE = CONFIG_DIR + "/config.json"


# ───────────────────────── язык ─────────────────────────
# Тексты пишутся по-русски и проходят через tr(); английские — в словаре EN ниже.
# Язык выбирается при запуске: --lang (так его получает root), KACH_LANG, настройки, локаль системы.

def detect_lang():
    a = sys.argv
    if "--lang" in a[:-1] and a[a.index("--lang") + 1] in ("ru", "en"):
        return a[a.index("--lang") + 1]
    if os.environ.get("KACH_LANG") in ("ru", "en"):
        return os.environ["KACH_LANG"]
    try:
        with open(CONFIG_FILE) as f:
            v = json.load(f).get("lang")
        if v in ("ru", "en"):
            return v
    except (OSError, ValueError, AttributeError):
        pass
    for k in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        if os.environ.get(k):
            return "ru" if os.environ[k].lower().startswith("ru") else "en"
    return "ru"


LANG = detect_lang()


def tr(s):
    return EN.get(s, s) if LANG == "en" else s


# ключ — русский текст (в шаблонах {0}, {1}… вместо подстановок), значение — английский
EN = {
    "Качанинг установлен пакетом — обновления приходят через менеджер пакетов.": "Kachaning is installed as a package — updates come through the package manager.",
    "Установка": "Installation",
    "пакетом — обновления через менеджер пакетов": "as a package — updates through the package manager",
    "в ~/.local — новая версия: пакет из AUR или .deb с GitHub": "in ~/.local — for new versions use the AUR package or the .deb from GitHub",
    "Как в системе": "System default",
    "2 часа": "2 hours",
    "Сутки": "1 day",
    "Неделя": "1 week",
    "Бессрочно": "No limit",
    "Зелёная": "Green",
    "Бирюзовая": "Teal",
    "Синяя": "Blue",
    "Фиолетовая": "Purple",
    "Розовая": "Pink",
    "Янтарная": "Amber",
    "Красная": "Red",
    "Светлая": "Light",
    "Тёмная": "Dark",
    "Мельче": "Smaller",
    "Обычный": "Normal",
    "Крупнее": "Larger",
    "Крупный": "Large",
    "Автоматически": "Automatic",
    "Сеть": "Network",
    "Подключиться": "Connect",
    "Принимать": "Accept",
    "Где закрыл": "Where I left off",
    "Не обновлять": "Don't refresh",
    "Каждые 30 с": "Every 30 s",
    "Каждую минуту": "Every minute",
    "Раз в 5 минут": "Every 5 minutes",
    "3 дня": "3 days",
    "2 недели": "2 weeks",
    "Месяц": "1 month",
    "Принимать маршруты подсетей": "Accept subnet routes",
    "доступ к локальным сетям, которые раздают другие устройства": "access local networks shared by other devices",
    "обращаться к устройствам по имени, а не по адресу": "reach devices by name instead of address",
    "Локальная сеть при выходном узле": "Local network with exit node",
    "роутер и принтер остаются доступны, когда трафик идёт через выходной узел": "router and printer stay reachable while traffic goes through the exit node",
    "{0}: не найден": "{0}: not found",
    "{0}: превышено время ожидания": "{0}: timed out",
    "минута": "minute",
    "минуты": "minutes",
    "минут": "minutes",
    "час": "hour",
    "часа": "hours",
    "часов": "hours",
    "день": "day",
    "дня": "days",
    "дней": "days",
    "Tailscale не установлен": "Tailscale is not installed",
    "нет ответа": "no response",
    "служба tailscaled не отвечает": "tailscaled service is not responding",
    "истечение отключено — продлевать не нужно": "expiry disabled — no renewal needed",
    "истёк {0} — нужно продлить": "expired {0} — needs renewal",
    "истекает через {0} ({1})": "expires in {0} ({1})",
    "ещё {0} (до {1})": "{0} left (until {1})",
    "давно": "long ago",
    " назад": " ago",
    "нужно войти — ключ истёк или вход сброшен": "sign-in needed — key expired or sign-in was reset",
    "Tailscale выключен": "Tailscale is off",
    "устройство ждёт одобрения в админ-панели": "device is waiting for approval in the admin console",
    "подключается…": "connecting…",
    "служба запускается…": "service is starting…",
    "бессрочно": "no time limit",
    "ещё {0}": "{0} left",
    "Повторяю с текущими настройками: ": "Retrying with current settings: ",
    "серверы Tailscale доступны": "Tailscale servers are reachable",
    "не работает DNS — проверь подключение к интернету": "DNS is not working — check your internet connection",
    "нет связи с серверами Tailscale ({0})": "cannot reach Tailscale servers ({0})",
    "config.json — не объект": "config.json is not an object",
    "помощник": "helper",
    "ключ без имени": "unnamed key",
    "{0}: чужой владелец": "{0}: wrong owner",
    "{0}: запись для чужих": "{0}: writable by others",
    "уже есть": "already exists",
    "создан": "created",
    "это не код Качанинга — он начинается с KCH1:": "this is not a Kachaning code — it starts with KCH1:",
    "код повреждён — скопируй его целиком": "the code is damaged — copy it in full",
    "код неизвестного вида": "unknown code type",
    "в коде неправильное имя компьютера": "invalid computer name in the code",
    "в коде неправильное имя пользователя": "invalid user name in the code",
    "в коде нет правильного ключа": "no valid key in the code",
    "неправильное имя для ssh": "invalid name for ssh",
    "Интернет": "Internet",
    "Tailscale установлен": "Tailscale installed",
    "Служба Tailscale": "Tailscale service",
    "Вход в Tailscale": "Tailscale sign-in",
    "Срок ключа Tailscale": "Tailscale key expiry",
    "SSH-сервер": "SSH server",
    "Права на ~/.ssh": "~/.ssh permissions",
    "Вход по паролю": "Password login",
    "Помощники": "Helpers",
    "Фаервол": "Firewall",
    "Точное время": "Clock sync",
    "Права администратора": "Admin rights",
    "Автоотзыв прав": "Auto-revoke",
    "Компьютер в сети": "Computer online",
    "Срок его ключа Tailscale": "Its Tailscale key expiry",
    "Маршрут": "Route",
    "Порт SSH": "SSH port",
    "Вход по ключу": "Key login",
    "Короткая команда ssh": "Short ssh command",
    "Права на управление Tailscale": "Permission to manage Tailscale",
    "Настройки SSH-сервера": "SSH server settings",
    "Перенос со старой версии": "Migration from the old version",
    "Исправить": "Fix",
    "Выдать": "Grant",
    "Войти": "Sign in",
    "Продлить": "Renew",
    "Открыть": "Open",
    "Навсегда": "Forever",
    "Добавить": "Add",
    "Код": "Code",
    "Отключить": "Disable",
    "Ограничить": "Restrict",
    "не установлен": "not installed",
    "нужен Tailscale": "Tailscale required",
    "версия {0}": "version {0}",
    "служба не работает": "service is not running",
    "работает": "running",
    "в сети как {0} · {1}": "online as {0} · {1}",
    "нужен вход в Tailscale": "Tailscale sign-in required",
    "работает, порт 22": "running, port 22",
    "не запущен или не установлен": "not running or not installed",
    "SSH не примет ключи: ": "SSH will not accept keys: ",
    "в порядке": "OK",
    "SSH-сервер не установлен": "SSH server is not installed",
    "не удалось прочитать настройки SSH": "could not read SSH settings",
    "включён — пароль можно подбирать из локальной сети": "enabled — the password can be guessed from the local network",
    "выключен, только ключи": "disabled, keys only",
    "{0} из {1} пускают из любой сети, не только из Tailscale": "{0} of {1} allow login from any network, not only Tailscale",
    "ключ допущен": "key allowed",
    "ключа допущены": "keys allowed",
    "ключей допущено": "keys allowed",
    "{0} {1} к входу": "{0} {1} to log in",
    "ни одного — добавь код помощника": "none — add a helper code",
    "включён, SSH через Tailscale разрешён": "enabled, SSH over Tailscale allowed",
    "включён — может блокировать SSH": "enabled — may block SSH",
    "выключен, не мешает": "disabled, not in the way",
    "синхронизировано": "synchronized",
    "не синхронизировано — Tailscale может не войти": "not synchronized — Tailscale may fail to sign in",
    "выданы, {0}": "granted, {0}",
    "срок истёк, права снимаются": "expired, rights are being removed",
    "не выданы": "not granted",
    "таймер работает": "timer is running",
    "не установлен — права на время не снимутся сами": "not installed — timed rights won't be removed automatically",
    "Tailscale на этом компьютере не подключён": "Tailscale is not connected on this computer",
    "нет Tailscale": "no Tailscale",
    "«{0}» не виден в Tailscale — если у вас разные аккаунты, друг должен поделиться компьютером, а ты принять приглашение": "“{0}” is not visible in Tailscale — if you use different accounts, your friend must share the computer and you must accept the invite",
    "компьютер не найден": "computer not found",
    "{0} · {1} · в сети": "{0} · {1} · online",
    "не в сети (был {0}) — выключен или Tailscale не работает": "offline (last seen {0}) — turned off or Tailscale is not running",
    " — пусть владелец откроет «{0}» → «Сеть» → «Продлить»": " — ask the owner to open “{0}” → “Network” → “Renew”",
    "компьютер не в сети": "computer is offline",
    "{0} мс": "{0} ms",
    "через ретранслятор {0}": "via relay {0}",
    "напрямую": "direct",
    "{0}, {1} мс": "{0}, {1} ms",
    "не отвечает на ping через Tailscale": "no ping response over Tailscale",
    "закрыт — пусть владелец откроет «{0}» → «Принимать» → «Исправить всё»": "closed — ask the owner to open “{0}” → “Accept” → “Fix all”",
    "порт закрыт": "port closed",
    "открыт": "open",
    "у тебя ещё нет SSH-ключа — открой «Подключиться» и создай его": "you don't have an SSH key yet — open “Connect” and create one",
    "нет ключа": "no key",
    "ключ сервера изменился (переустановка системы?)": "server key changed (system reinstalled?)",
    "твой ключ защищён паролем — проверка не может войти сама, в терминале ssh спросит пароль ключа": "your key is password-protected — the check can't log in by itself; ssh will ask for the key password in the terminal",
    "ключ не принят — отправь другу свой код помощника": "key not accepted — send your friend your helper code",
    "нет входа по SSH": "no SSH login",
    "вход как {0}": "logged in as {0}",
    "есть, {0}": "yes, {0}",
    "есть (выданы вручную)": "yes (granted manually)",
    "нет — пусть друг нажмёт «Выдать права» в «{0}»": "no — ask your friend to press “Grant rights” in “{0}”",
    "можно настроить: ssh {0}": "can be set up: ssh {0}",
    "ssh {0} сейчас ведёт на {1}": "ssh {0} currently points to {1}",
    "Сеть:": "Network:",
    "Принимать:": "Accept:",
    "Подключение «{0}» ({1}@{2}):": "Connection “{0}” ({1}@{2}):",
    "Прерванная установка пакетов — доделываю (dpkg --configure -a)": "Interrupted package installation — finishing it (dpkg --configure -a)",
    "Обновляю списки пакетов": "Updating package lists",
    "Неизвестный менеджер пакетов": "Unknown package manager",
    "время синхронизировано": "clock is synchronized",
    "не удалось включить синхронизацию: {0}": "could not enable time sync: {0}",
    "включена синхронизация времени": "time sync enabled",
    "уже установлен": "already installed",
    "Добавляю репозиторий Tailscale ({0} {1})": "Adding the Tailscale repository ({0} {1})",
    "не удалось скачать ключ репозитория: {0}": "could not download the repository key: {0}",
    "установлен": "installed",
    "установка не удалась — подробности в журнале": "installation failed — details in the log",
    "служба работает": "service is running",
    "tailscaled не отвечает ({0}) — перезапускаю": "tailscaled is not responding ({0}) — restarting",
    "служба tailscaled не запускается — подробности в журнале": "tailscaled service won't start — details in the log",
    "{0} может управлять Tailscale без пароля": "{0} can manage Tailscale without a password",
    "не удалось: {0}": "failed: {0}",
    "уже работает": "already running",
    "Устанавливаю SSH-сервер": "Installing the SSH server",
    "не удалось установить SSH-сервер": "could not install the SSH server",
    "служба SSH не найдена": "SSH service not found",
    "работает (после перезапуска)": "running (after restart)",
    "SSH-сервер не запускается": "SSH server won't start",
    "в настройках SSH ошибка": "SSH settings contain an error",
    "# {0}: вход по ключу для удалённой помощи\nPubkeyAuthentication yes\n": "# {0}: key login for remote help\nPubkeyAuthentication yes\n",
    "не удалось включить вход по ключу": "could not enable key login",
    "включён вход по ключу": "key login enabled",
    "внимание: AllowUsers не включает {0}": "warning: AllowUsers does not include {0}",
    "# {0}: вход только по ключам\nPasswordAuthentication no\n{1} no\n": "# {0}: key login only\nPasswordAuthentication no\n{1} no\n",
    "sshd не принял настройку — ничего не изменено": "sshd rejected the setting — nothing changed",
    "sshd не читает /etc/ssh/sshd_config.d — отключи PasswordAuthentication вручную": "sshd does not read /etc/ssh/sshd_config.d — disable PasswordAuthentication manually",
    "ufw: SSH через Tailscale разрешён": "ufw: SSH over Tailscale allowed",
    "firewalld: Tailscale в доверенной зоне": "firewalld: Tailscale in the trusted zone",
    "фаервол выключен": "firewall is off",
    "[Unit]\nDescription={0}: снять истёкшие права администратора\n\n[Service]\nType=oneshot\nExecStart={1} -I {2} --root expire-check\n": "[Unit]\nDescription={0}: remove expired admin rights\n\n[Service]\nType=oneshot\nExecStart={1} -I {2} --root expire-check\n",
    "[Unit]\nDescription={0}: проверка срока прав\n\n[Timer]\nOnBootSec=1min\nOnUnitActiveSec=5min\nAccuracySec=30s\n\n[Install]\nWantedBy=timers.target\n": "[Unit]\nDescription={0}: rights expiry check\n\n[Timer]\nOnBootSec=1min\nOnUnitActiveSec=5min\nAccuracySec=30s\n\n[Install]\nWantedBy=timers.target\n",
    "таймер установлен": "timer installed",
    "права перенесены": "rights carried over",
    "старый таймер удалён": "old timer removed",
    "нечего переносить": "nothing to migrate",
    "вход выполнен": "signed in",
    "Нужен вход в Tailscale — открываю страницу входа в браузере": "Tailscale sign-in needed — opening the sign-in page in the browser",
    "вход выполнен, ключ продлён": "signed in, key renewed",
    "вход не завершён — повтори и войди в браузере": "sign-in not finished — try again and sign in in the browser",
    "# Создано программой «{0}». Снимается кнопкой «Отозвать»\n# или автоматически по истечении срока (kachaning-expire.timer).\n{1} ALL=(ALL:ALL) NOPASSWD: ALL\n": "# Created by “{0}”. Removed by the “Revoke” button\n# or automatically when the time runs out (kachaning-expire.timer).\n{1} ALL=(ALL:ALL) NOPASSWD: ALL\n",
    "visudo отклонил файл: {0}": "visudo rejected the file: {0}",
    "выданы на {0}": "granted for {0}",
    "выданы бессрочно": "granted with no time limit",
    "права отозваны": "rights revoked",
    "неправильный срок": "invalid duration",
    "{0}: срок прав истёк, права сняты": "{0}: rights expired and were removed",
    "{0}: права без записи о выдаче — сняты": "{0}: rights without a grant record — removed",
    "нужны права root": "root rights required",
    "неизвестно, кто вызвал (нет PKEXEC_UID/SUDO_UID)": "unknown caller (no PKEXEC_UID/SUDO_UID)",
    "неизвестное действие {0}": "unknown action {0}",
    "Открой «{0}» → «Сеть».": "Open “{0}” → “Network”.",
    "Tailscale не работает": "Tailscale is not working",
    "Нужен вход в Tailscale": "Tailscale sign-in needed",
    "Ключ Tailscale истёк": "Tailscale key expired",
    "Ключ Tailscale скоро истечёт": "Tailscale key expires soon",
    "Срок: {0}. {1} и нажми «Продлить».": "Expiry: {0}. {1} Then press “Renew”.",
    "Ключ Tailscale у «{0}» истекает": "Tailscale key of “{0}” is expiring",
    "{0}. Попроси открыть «{1}» → «Сеть» → «Продлить».": "{0}. Ask them to open “{1}” → “Network” → “Renew”.",
    "[Unit]\nDescription={0}: проверка срока ключей Tailscale\n\n[Service]\nType=oneshot\nExecStart={1} {2} --notify-check\n": "[Unit]\nDescription={0}: Tailscale key expiry check\n\n[Service]\nType=oneshot\nExecStart={1} {2} --notify-check\n",
    "[Unit]\nDescription={0}: проверка Tailscale дважды в сутки\n\n[Timer]\nOnStartupSec=3min\nOnUnitActiveSec=12h\n\n[Install]\nWantedBy=timers.target\n": "[Unit]\nDescription={0}: Tailscale check twice a day\n\n[Timer]\nOnStartupSec=3min\nOnUnitActiveSec=12h\n\n[Install]\nWantedBy=timers.target\n",
    "[Desktop Entry]\nType=Application\nName={0}\nComment=Удалённая помощь через Tailscale\nExec={1} {2}\nIcon={3}\nTerminal=false\nCategories=Network;System;\nStartupNotify=true\nStartupWMClass=kachaning\n": "[Desktop Entry]\nType=Application\nName={0}\nComment=Remote help over Tailscale\nExec={1} {2}\nIcon={3}\nTerminal=false\nCategories=Network;System;\nStartupNotify=true\nStartupWMClass=kachaning\n",
    "Установлено:": "Installed:",
    "Таймер уведомлений не включился": "Notification timer was not enabled",
    "проверяю…": "checking…",
    "Терминал": "Terminal",
    "Скопировать команду": "Copy command",
    "Изменить": "Edit",
    "Удалить": "Delete",
    "Проверить": "Check",
    "Подробнее": "Details",
    "Скрыть": "Hide",
    "Проверяю…": "Checking…",
    "Ошибка проверки: {0}: {1}": "Check error: {0}: {1}",
    "Можно подключаться, права администратора есть · {0}": "Ready to connect, admin rights granted · {0}",
    "Можно подключаться, без прав администратора · {0}": "Ready to connect, without admin rights · {0}",
    "Есть замечания": "There are warnings",
    "Старый ключ сервера удалён": "Old server key removed",
    "Не удалось записать ~/.ssh/config: {0}": "Could not write ~/.ssh/config: {0}",
    "Теперь можно просто: ssh {0}": "Now you can just run: ssh {0}",
    "Терминал не найден — команда скопирована": "Terminal not found — command copied",
    "Открыт терминал: ": "Terminal opened: ",
    "Команда скопирована": "Command copied",
    "Удалить подключение «{0}»?": "Delete connection “{0}”?",
    "Ключи и настройки у друга не изменятся.": "Keys and settings on your friend's computer won't change.",
    "Настройки": "Settings",
    "Обновить": "Refresh",
    "Скопировано": "Copied",
    "Ошибка: {0}: {1}": "Error: {0}: {1}",
    "Понятно": "Got it",
    "Отмена": "Cancel",
    "Да": "Yes",
    "Если у вас разные аккаунты Tailscale": "If you use different Tailscale accounts",
    "Компьютер друга появится у тебя в Tailscale, только когда он им поделится:\n\n1. Друг открывает админ-панель Tailscale (кнопка в «Сеть»).\n2. Находит свой компьютер → «⋯» → «Share…» и отправляет тебе ссылку-приглашение.\n3. Ты открываешь ссылку и принимаешь приглашение.\n\nЕсли вы в одном аккаунте Tailscale, делать ничего не нужно.": "Your friend's computer appears in your Tailscale only after they share it:\n\n1. Your friend opens the Tailscale admin console (button on “Network”).\n2. Finds their computer → “⋯” → “Share…” and sends you the invite link.\n3. You open the link and accept the invite.\n\nIf you share one Tailscale account, nothing needs to be done.",
    "Ключ без срока": "Key without expiry",
    "Tailscale раз в несколько месяцев требует войти заново — тогда связь пропадает.\n\nЧтобы этого не было, отключи срок ключа:\n1. Откроется админ-панель Tailscale — войди в свой аккаунт.\n2. Найди в списке «{0}».\n3. Нажми «⋯» справа → «Disable key expiry».\n\nПока срок не отключён, Качанинг предупредит за {1} до конца.": "Every few months Tailscale asks you to sign in again — the connection drops until you do.\n\nTo avoid this, disable key expiry:\n1. The Tailscale admin console will open — sign in to your account.\n2. Find “{0}” in the list.\n3. Click “⋯” on the right → “Disable key expiry”.\n\nUntil expiry is disabled, Kachaning will warn you {1} in advance.",
    "Подожди, предыдущее действие ещё выполняется": "Wait, the previous action is still running",
    "pkexec не найден": "pkexec not found",
    "Окно пароля недоступно — открываю терминал с sudo": "Password dialog unavailable — opening a terminal with sudo",
    "; echo; read -rp 'Готово. Нажми Enter…'": "; echo; read -rp 'Done. Press Enter…'",
    "Проверь результат в окне терминала": "Check the result in the terminal window",
    "Терминал не найден": "Terminal not found",
    "Пароль не введён или не принят — ничего не изменено": "Password not entered or not accepted — nothing changed",
    "выполняю…": "working…",
    "Готово": "Done",
    "Пароль не введён — ничего не изменено": "Password not entered — nothing changed",
    "Сделано не всё — подробности в «Настройки» → «Журнал»": "Not everything succeeded — details in “Settings” → “Log”",
    "Завершено с кодом {0}": "Finished with code {0}",
    "Пропускаю неожиданную ссылку: {0}": "Skipping unexpected link: {0}",
    "Открыл страницу входа: ": "Opened the sign-in page: ",
    "Открылась страница входа Tailscale — войди в аккаунт, программа подождёт": "The Tailscale sign-in page opened — sign in, the app will wait",
    "Вход в Tailscale…": "Signing in to Tailscale…",
    "Нужны права администратора — запрашиваю пароль": "Admin rights needed — asking for the password",
    "Разрешаю управлять Tailscale без пароля…": "Allowing Tailscale management without a password…",
    "Tailscale связывает компьютеры напрямую, где бы они ни были": "Tailscale connects computers directly, wherever they are",
    "Продлить ключ": "Renew key",
    "Админ-панель": "Admin console",
    "Забрать файлы": "Receive files",
    "Аккаунт": "Account",
    "Мой адрес": "My address",
    "Срок ключа": "Key expiry",
    "Выходной узел": "Exit node",
    "Устройства": "Devices",
    "«Подключиться» добавляет устройство в твои подключения. Taildrop (отправка файлов) работает только между твоими устройствами.": "“Connect” adds a device to your connections. Taildrop (file sending) works only between your own devices.",
    "Проверяю Tailscale…": "Checking Tailscale…",
    "Установлю его сам — понадобится пароль.": "I'll install it myself — the password will be needed.",
    "Установить": "Install",
    "Устанавливаю Tailscale…": "Installing Tailscale…",
    "Служба Tailscale не работает": "Tailscale service is not running",
    "Запустить": "Start",
    "Запускаю Tailscale…": "Starting Tailscale…",
    "Подключено": "Connected",
    "Включи переключатель, чтобы подключиться.": "Turn on the switch to connect.",
    "Нужно войти": "Sign-in needed",
    "Сменить": "Switch",
    "Аккаунт сменён": "Account switched",
    "Копировать": "Copy",
    "Скопировано: {0}": "Copied: {0}",
    "через {0}": "via {0}",
    "не используется": "not used",
    "нет доступных узлов": "no nodes available",
    "Не использовать": "Don't use",
    "Выходной узел изменён": "Exit node changed",
    "Других устройств пока нет. Поставь Tailscale на второй компьютер или попроси друга поделиться своим.": "No other devices yet. Install Tailscale on a second computer or ask a friend to share theirs.",
    "в сети": "online",
    "был {0}": "last seen {0}",
    "Скопировать адрес": "Copy address",
    "Проверить связь": "Check connection",
    "Отправить файл…": "Send file…",
    "Проверяю связь с {0}…": "Checking connection to {0}…",
    "через ретранслятор ": "via relay ",
    "{0}: {1}, {2} мс": "{0}: {1}, {2} ms",
    "{0} не отвечает": "{0} is not responding",
    "Файл для отправки": "File to send",
    "Отправляю {0}…": "Sending {0}…",
    "Отправлено": "Sent",
    "Не отправлено: {0}": "Not sent: {0}",
    "Получено файлов: {0} → {1}": "Files received: {0} → {1}",
    "Входящих файлов нет": "No incoming files",
    "Не получилось": "Didn't work",
    "Ты помогаешь: заходишь на компьютеры друзей по SSH": "You help: log in to your friends' computers over SSH",
    "Мой код помощника": "My helper code",
    "Отправь его другу. Он вставит код в «Качанинге» → «Принимать» → «Добавить помощника», и твой ключ начнёт пускать тебя к нему.": "Send it to your friend. They paste it in “Kachaning” → “Accept” → “Add helper”, and your key will let you in.",
    "Скопировать код": "Copy code",
    "Мои подключения": "My connections",
    "SSH-ключ: {0}": "SSH key: {0}",
    "Код помощника скопирован — отправь его другу": "Helper code copied — send it to your friend",
    "Не получилось прочитать ключ ~/.ssh/id_ed25519.pub": "Could not read the key ~/.ssh/id_ed25519.pub",
    "Ключа ещё нет — он создастся, когда нажмёшь «Скопировать код».": "No key yet — it will be created when you press “Copy code”.",
    "Подключений пока нет": "No connections yet",
    "Попроси у друга его «код для подключения» (в «Качанинге» → «Принимать») или выбери его компьютер в списке устройств.": "Ask your friend for their “connection code” (in “Kachaning” → “Accept”) or pick their computer in the device list.",
    "Добавить подключение": "Add connection",
    "Нажми «Проверить», чтобы проверить связь": "Press “Check” to test the connection",
    "Изменить подключение": "Edit connection",
    "Новое подключение": "New connection",
    "Код для подключения от друга": "Connection code from your friend",
    "или укажи вручную:": "or enter manually:",
    "имя компьютера в Tailscale": "computer name in Tailscale",
    "пользователь на том компьютере": "user on that computer",
    "как назвать (например, «Ваня»)": "display name (e.g. “Alex”)",
    "Компьютер": "Computer",
    "Пользователь": "User",
    "Название": "Name",
    "Сохранить": "Save",
    "это код помощника — его вставляют в «Принимать». Тебе нужен «код для подключения» друга": "this is a helper code — it goes into “Accept”. You need your friend's “connection code”",
    "укажи имя компьютера (как в списке устройств)": "enter the computer name (as in the device list)",
    "укажи пользователя латиницей, как при входе в систему": "enter the user name in Latin letters, as used to log in",
    "подключение {0}@{1} уже есть": "connection {0}@{1} already exists",
    "Подключение сохранено": "Connection saved",
    "Тебе помогают: помощники заходят к тебе по SSH": "You get help: helpers log in to you over SSH",
    "Права администратора для помощников": "Admin rights for helpers",
    "Когда срок выйдет, права снимутся сами. Входить по SSH без прав администратора помощники смогут и дальше — пока ты не удалишь их ключ.": "When the time runs out, the rights are removed automatically. Helpers can still log in over SSH without admin rights — until you delete their key.",
    "Выдать права": "Grant rights",
    "Отозвать": "Revoke",
    "Отзываю права…": "Revoking rights…",
    "Мой код для подключения": "My connection code",
    "Отправь его помощнику — он добавит тебя в «Подключиться».": "Send it to your helper — they will add you in “Connect”.",
    "Код скопирован — отправь помощнику": "Code copied — send it to your helper",
    "Разные аккаунты Tailscale?": "Different Tailscale accounts?",
    "Проверки": "Checks",
    "Исправить всё": "Fix all",
    "Настраиваю и выдаю права…": "Setting up and granting rights…",
    "Выдаю права…": "Granting rights…",
    "Настраиваю приём подключений…": "Setting up incoming connections…",
    "Права на ~/.ssh: ": "~/.ssh permissions: ",
    "Не всё исправлено: ": "Not everything fixed: ",
    "Права на ~/.ssh исправлены": "~/.ssh permissions fixed",
    "Отключить вход по паролю?": "Disable password login?",
    "К SSH-серверу можно будет войти только по ключу. Помощники входят по ключам, им это не помешает. Если ты сам заходишь на этот компьютер по SSH с паролем, сначала добавь свой ключ.": "The SSH server will accept key logins only. Helpers log in with keys, so this won't affect them. If you log in to this computer over SSH with a password yourself, add your key first.",
    "Отключаю вход по паролю…": "Disabling password login…",
    "Помощники теперь входят только через Tailscale": "Helpers can now log in only through Tailscale",
    "Права администратора выданы": "Admin rights granted",
    "{0} · адрес {1}": "{0} · address {1}",
    "Нужна настройка": "Setup needed",
    "Не в порядке: ": "Not OK: ",
    ".\nНажми «Исправить всё» — понадобится пароль.": ".\nPress “Fix all” — the password will be needed.",
    "Почти готово": "Almost ready",
    "Обрати внимание: ": "Pay attention to: ",
    "Готово к приёму подключений": "Ready to accept connections",
    "Помощники могут заходить по SSH. Права администратора сейчас не выданы.": "Helpers can log in over SSH. Admin rights are not granted right now.",
    "Пока никого. Попроси у помощника его «код помощника» и нажми «Добавить».": "Nobody yet. Ask your helper for their “helper code” and press “Add”.",
    "не в сети": "offline",
    "не найден в Tailscale": "not found in Tailscale",
    " · вход из любой сети": " · login from any network",
    "Удалить помощника «{0}»?": "Remove helper “{0}”?",
    "Он больше не сможет заходить к тебе по SSH. Права администратора, если выданы, остаются у всех помощников до отзыва.": "They will no longer be able to log in to you over SSH. Admin rights, if granted, stay with all helpers until revoked.",
    "«{0}» удалён": "“{0}” removed",
    "Добавить помощника": "Add helper",
    "Вставь «код помощника», который он тебе прислал. Можно и обычный открытый SSH-ключ (ssh-ed25519 …).": "Paste the “helper code” they sent you. A regular public SSH key (ssh-ed25519 …) works too.",
    "имя (необязательно)": "name (optional)",
    "это код для подключения — его вставляют в «Подключиться». Здесь нужен «код помощника»": "this is a connection code — it goes into “Connect”. Here you need a “helper code”",
    "не похоже ни на код, ни на SSH-ключ": "looks like neither a code nor an SSH key",
    "Пустить «{0}» к себе?": "Let “{0}” in?",
    "Владелец этого ключа сможет входить на этот компьютер по SSH как {0} (только через Tailscale), а пока выданы права администратора — управлять всей системой.\n\nОтпечаток ключа: {1}\n\nДобавляй только код, который тебе прислал тот, кому ты доверяешь.": "The owner of this key will be able to log in to this computer over SSH as {0} (only through Tailscale), and while admin rights are granted — control the whole system.\n\nKey fingerprint: {1}\n\nOnly add a code sent to you by someone you trust.",
    "Помощник «{0}» добавлен": "Helper “{0}” added",
    "Оформление, уведомления, подключения и Tailscale": "Appearance, notifications, connections and Tailscale",
    "Оформление": "Appearance",
    "Язык": "Language",
    "смена языка — после перезапуска": "language changes after a restart",
    "Цвет и тема": "Color and theme",
    "Размер текста": "Text size",
    "Анимации": "Animations",
    "плавная смена страниц и появление подсказок": "smooth page transitions and pop-up hints",
    "Общие": "General",
    "Открывать при запуске": "Open on startup",
    "«Автоматически» — «Подключиться», если подключения уже есть, иначе «Принимать»": "“Automatic” — “Connect” if you already have connections, otherwise “Accept”",
    "Обновлять открытую страницу": "Refresh the open page",
    "проверки и список устройств, пока окно активно": "checks and device list, while the window is active",
    "Мастер настройки": "Setup wizard",
    "пройти первоначальную настройку заново": "go through the initial setup again",
    "Уведомления": "Notifications",
    "Напоминать о сроке ключей": "Remind about key expiry",
    "свой ключ Tailscale и ключи компьютеров, к которым подключаешься": "your Tailscale key and keys of computers you connect to",
    "Предупреждать заранее": "Warn in advance",
    "Сообщать о проблемах Tailscale": "Report Tailscale problems",
    "служба остановлена или нужен вход": "service stopped or sign-in needed",
    "Подключение к друзьям": "Connecting to friends",
    "Автоматически ({0})": "Automatic ({0})",
    "{0} (не найден)": "{0} (not found)",
    "где открывается SSH по кнопке «Терминал»": "where SSH opens with the “Terminal” button",
    "Проверять связь при открытии": "Check connections on open",
    "иначе — по кнопке «Проверить» в карточке": "otherwise — with the “Check” button on the card",
    "Настраивать команду «ssh имя»": "Set up the “ssh name” command",
    "дописывать подключение в ~/.ssh/config после удачной проверки": "add the connection to ~/.ssh/config after a successful check",
    "Мой SSH-ключ": "My SSH key",
    "Приём подключений": "Incoming connections",
    "Срок прав администратора": "Admin rights duration",
    "выбор по умолчанию для кнопки «Выдать права»": "default choice for the “Grant rights” button",
    "ключи, которым разрешён вход, — на вкладке «Принимать»": "keys allowed to log in — on the “Accept” tab",
    "устройства, общий доступ, срок ключей": "devices, sharing, key expiry",
    "Журнал": "Log",
    "О программе": "About",
    "удалённая помощь через Tailscale и SSH": "remote help over Tailscale and SSH",
    "Папка настроек": "Settings folder",
    "Сбросить настройки": "Reset settings",
    "оформление и параметры; подключения и ключи останутся": "appearance and options; connections and keys stay",
    "Сбросить": "Reset",
    "Скопировать": "Copy",
    "Журнал скопирован": "Log copied",
    "Очистить": "Clear",
    "Перезапустить Качанинг?": "Restart Kachaning?",
    "Язык сменится после перезапуска программы.": "The language will change after the app restarts.",
    "Скопировать открытый": "Copy public key",
    "Открытый ключ скопирован": "Public key copied",
    "{0} — ещё не создан": "{0} — not created yet",
    "Создать": "Create",
    "SSH-ключ {0}": "SSH key {0}",
    "Ключ не создан: {0}": "Key not created: {0}",
    "Сбросить настройки?": "Reset settings?",
    "Оформление, уведомления и остальные параметры вернутся к исходным. Подключения, ключи и права не изменятся.": "Appearance, notifications and other options will return to defaults. Connections, keys and rights won't change.",
    "Настройки сброшены": "Settings reset",
    "Назад": "Back",
    "Далее": "Next",
    "Добро пожаловать в {0}": "Welcome to {0}",
    "Качанинг помогает друзьям помогать друг другу с компьютером: связывает вас через Tailscale, настраивает вход по SSH и выдаёт права администратора на время.\n\nКаждый компьютер с Качанингом умеет и то и другое: принимать помощь и подключаться к друзьям. Для начала выбери, как программа будет выглядеть.": "Kachaning helps friends help each other with their computers: it connects you through Tailscale, sets up SSH login and grants admin rights for a limited time.\n\nEvery computer with Kachaning can do both: accept help and connect to friends. First, choose how the app should look.",
    "Tailscale соединяет ваши компьютеры, даже если они в разных городах и за роутерами. Нужен бесплатный аккаунт — войти можно через Google, GitHub или Microsoft.": "Tailscale connects your computers even if they are in different cities and behind routers. You need a free account — you can sign in with Google, GitHub or Microsoft.",
    "Если Tailscale ещё не установлен, Качанинг поставит его сам и попросит пароль администратора этого компьютера.": "If Tailscale is not installed yet, Kachaning will install it and ask for this computer's admin password.",
    "Принимать подключения": "Accept connections",
    "Нужно включить SSH-сервер и защиту: прав администратора не будет, пока ты их не выдашь, а выданные снимутся сами по сроку.": "The SSH server and protection need to be enabled: there will be no admin rights until you grant them, and granted ones expire on their own.",
    "Настроить": "Set up",
    "Код помощника": "Helper code",
    "вставь код от помощника (можно позже)": "paste the code from your helper (can be done later)",
    "Отправь его помощнику, чтобы он добавил тебя к себе.": "Send it to your helper so they can add you.",
    "Код скопирован": "Code copied",
    "✓ Помощник добавлен": "✓ Helper added",
    "Подключаться к другим": "Connect to others",
    "Для входа к друзьям нужен SSH-ключ — Качанинг создал его. Отправь другу свой код помощника, а его «код для подключения» вставь ниже.": "To log in to friends you need an SSH key — Kachaning created it. Send your friend your helper code, and paste their “connection code” below.",
    "KCH1:… (можно позже)": "KCH1:… (can be done later)",
    "это код помощника — нужен «код для подключения» друга": "this is a helper code — you need your friend's “connection code”",
    "такое подключение уже есть": "this connection already exists",
    "✓ Добавлено: {0}@{1}": "✓ Added: {0}@{1}",
    "Готово!": "All set!",
    "Начать": "Start",
    "Нажми «Установить» — понадобится пароль.": "Press “Install” — the password will be needed.",
    "Tailscale подключён": "Tailscale connected",
    "Нужно войти в Tailscale": "Tailscale sign-in needed",
    "Откроется браузер — войди или создай аккаунт.": "A browser will open — sign in or create an account.",
    "Нужно настроить": "Setup needed",
    "Всё настроено": "All set up",
    "SSH-сервер работает, защита на месте.": "SSH server is running, protection is in place.",
    "не удалось создать ключ ~/.ssh/id_ed25519": "could not create the key ~/.ssh/id_ed25519",
    "• «Принимать» — выдавай права администратора, когда нужна помощь, и добавляй помощников по их кодам.": "• “Accept” — grant admin rights when you need help, and add helpers by their codes.",
    "подключение": "connection",
    "подключения": "connections",
    "подключений": "connections",
    "• «Подключиться» — {0} {1}; там же твой код помощника.": "• “Connect” — {0} {1}; your helper code is there too.",
    "• «Сеть» — Tailscale: включение, вход, устройства, отправка файлов.": "• “Network” — Tailscale: on/off, sign-in, devices, sending files.",
    "\nКачанинг напомнит, если ключ Tailscale скоро истечёт. Оформление, уведомления и остальное — в «Настройках», там же можно пройти мастер снова.": "\nKachaning will remind you when your Tailscale key is about to expire. Appearance, notifications and more are in “Settings”, where you can also run the wizard again.",
}
APP_NAME = "Kachaning" if LANG == "en" else "Качанинг"
LANGS = [("auto", tr("Как в системе")), ("ru", "Русский"), ("en", "English")]
USER_DIR = os.path.expanduser("~/.local/share/kachaning")
ROOT_DIR = "/usr/local/lib/kachaning"
PKG_DIR = "/usr/share/kachaning"
# из пакета программа уже лежит в системной папке root — таймер запускает её саму, без копии
PACKAGED = os.path.dirname(os.path.realpath(__file__)) == PKG_DIR
ROOT_COPY = os.path.realpath(__file__) if PACKAGED else ROOT_DIR + "/kachaning.py"
STATE_DIR = "/etc/kachaning"
STATE_FILE = STATE_DIR + "/state.json"
SUDOERS_FILE = "/etc/sudoers.d/90-kachaning"
NOPASS_CONF = "/etc/ssh/sshd_config.d/00-kachaning-nopass.conf"
AUTH_KEYS = os.path.expanduser("~/.ssh/authorized_keys")
CLIENT_KEY = os.path.expanduser("~/.ssh/id_ed25519")
KEY_TAG = "kachaning:"
# ключи помощников работают только с адресов Tailscale, даже если SSH виден из локальной сети
TS_ONLY = 'from="100.64.0.0/10,fd7a:115c:a1e0::/48"'
NODE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}")
USER_RE = re.compile(r"[a-z_][a-z0-9_.-]{0,31}")
ALIAS_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}")
CODE_PREFIX = "KCH1:"
WARN_DAYS = 14
ADMIN_URL = "https://login.tailscale.com/admin/machines"
AUTH_RE = re.compile(r"https://login\.tailscale\.com/a/[A-Za-z0-9]+")
DURATIONS = [(tr("2 часа"), 2 * 3600), (tr("Сутки"), 86400), (tr("Неделя"), 7 * 86400), (tr("Бессрочно"), 0)]
SEEDS = [("green", tr("Зелёная"), 125), ("teal", tr("Бирюзовая"), 178), ("blue", tr("Синяя"), 214),
         ("purple", tr("Фиолетовая"), 268), ("pink", tr("Розовая"), 328), ("orange", tr("Янтарная"), 32),
         ("red", tr("Красная"), 2)]
MODES = [("auto", tr("Как в системе")), ("light", tr("Светлая")), ("dark", tr("Тёмная"))]
SCALES = [("0.9", tr("Мельче")), ("1.0", tr("Обычный")), ("1.15", tr("Крупнее")), ("1.3", tr("Крупный"))]
START_PAGES = [("auto", tr("Автоматически")), ("net", tr("Сеть")), ("connect", tr("Подключиться")), ("host", tr("Принимать")),
               ("last", tr("Где закрыл"))]
REFRESH = [("0", tr("Не обновлять")), ("30", tr("Каждые 30 с")), ("60", tr("Каждую минуту")), ("300", tr("Раз в 5 минут"))]
WARN_CHOICES = [("3", tr("3 дня")), ("7", tr("Неделя")), ("14", tr("2 недели")), ("30", tr("Месяц"))]
# (команда, флаг Tailscale, поле в `tailscale debug prefs`, название, пояснение)
TS_PREFS = [("accept-routes", "RouteAll", tr("Принимать маршруты подсетей"),
             tr("доступ к локальным сетям, которые раздают другие устройства")),
            ("accept-dns", "CorpDNS", "MagicDNS", tr("обращаться к устройствам по имени, а не по адресу")),
            ("exit-node-allow-lan-access", "ExitNodeAllowLANAccess", tr("Локальная сеть при выходном узле"),
             tr("роутер и принтер остаются доступны, когда трафик идёт через выходной узел"))]
# первая версия называлась TS Bridge — её следы убираются при установке
LEGACY = {"sudoers": "/etc/sudoers.d/90-tsbridge", "state_dir": "/etc/tsbridge",
          "root_dir": "/usr/local/lib/tsbridge", "unit": "tsbridge-expire",
          "user_dir": os.path.expanduser("~/.local/share/tsbridge"), "user_unit": "tsbridge-notify"}


# ───────────────────────── общие утилиты ─────────────────────────

def run(cmd, timeout=30, input=None, env=None):
    """Запускает команду с английской локалью. Возвращает (код, stdout, stderr)."""
    e = dict(os.environ, LC_ALL="C", LANG="C")
    if env:
        e.update(env)
    try:
        p = subprocess.run(cmd, input=input, capture_output=True, text=True, timeout=timeout, env=e)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError:
        return 127, "", tr("{0}: не найден").format(cmd[0])
    except subprocess.TimeoutExpired:
        return 124, "", tr("{0}: превышено время ожидания").format(cmd[0])


def stream(cmd, on_line):
    """Запускает команду и отдаёт её вывод построчно. Возвращает (код, весь вывод)."""
    e = dict(os.environ, LC_ALL="C", LANG="C")
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=e)
    except FileNotFoundError:
        return 127, tr("{0}: не найден").format(cmd[0])
    lines = []
    for line in p.stdout:
        line = line.rstrip("\n")
        lines.append(line)
        on_line(line)
    return p.wait(), "\n".join(lines)


def plural(n, one, few, many):
    n = abs(int(n))
    if LANG == "en":
        return one if n == 1 else many
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def fmt_span(seconds):
    s = int(seconds)
    if s < 3600:
        m = max(1, s // 60)
        return f"{m} {plural(m, tr('минута'), tr('минуты'), tr('минут'))}"
    if s < 2 * 86400:
        h = max(1, round(s / 3600))
        return f"{h} {plural(h, tr('час'), tr('часа'), tr('часов'))}"
    d = round(s / 86400)
    return f"{d} {plural(d, tr('день'), tr('дня'), tr('дней'))}"


def parse_ts_time(s):
    if not s or s.startswith("0001-"):
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def ts_status():
    """(status-словарь, None) или (None, текст ошибки)."""
    if not shutil.which("tailscale"):
        return None, tr("Tailscale не установлен")
    rc, out, err = run(["tailscale", "status", "--json"], timeout=10)
    try:
        return json.loads(out), None
    except ValueError:
        msg = (err or out).splitlines()
        msg = msg[-1] if msg else tr("нет ответа")
        if "connect" in msg or "tailscaled" in msg:
            return None, tr("служба tailscaled не отвечает")
        return None, msg


def ts_profiles():
    """Аккаунты Tailscale на этом компьютере: [{"id", "tailnet", "account", "current"}]."""
    rc, out, _ = run(["tailscale", "switch", "--list"], timeout=10)
    if rc != 0:
        return []
    res = []
    for line in out.splitlines()[1:]:
        cols = re.split(r"\s{2,}", line.strip())
        if len(cols) >= 3:
            cur = cols[-1].endswith("*")
            res.append({"id": cols[0], "tailnet": cols[1], "account": cols[-1].rstrip("*"), "current": cur})
    return res


def peers(st):
    return list((st.get("Peer") or {}).values()) if st else []


def find_peer(st, name):
    name = (name or "").lower()
    for p in peers(st):
        if p.get("HostName", "").lower() == name or p.get("DNSName", "").split(".")[0].lower() == name:
            return p
    return None


def first_ip(node):
    ips = node.get("TailscaleIPs") or []
    v4 = [i for i in ips if "." in i]
    return (v4 or ips or ["?"])[0]


def key_expiry_result(node):
    """Строка «срок ключа» для узла: (state, detail, fix)."""
    exp = parse_ts_time(node.get("KeyExpiry"))
    if exp is None:
        return "ok", tr("истечение отключено — продлевать не нужно"), None
    left = (exp - now_utc()).total_seconds()
    date = exp.astimezone().strftime("%Y-%m-%d" if LANG == "en" else "%d.%m.%Y")  # %b зависит от локали GTK
    if left <= 0:
        return "err", tr("истёк {0} — нужно продлить").format(date), "renew"
    if left < WARN_DAYS * 86400:
        return "warn", tr("истекает через {0} ({1})").format(fmt_span(left), date), "renew"
    return "ok", tr("ещё {0} (до {1})").format(fmt_span(left), date), "noexpiry"


def last_seen(peer):
    t = parse_ts_time(peer.get("LastSeen"))
    if t is None:
        return tr("давно")
    return fmt_span((now_utc() - t).total_seconds()) + tr(" назад")


BACKEND_TEXT = {
    "NeedsLogin": tr("нужно войти — ключ истёк или вход сброшен"),
    "Stopped": tr("Tailscale выключен"),
    "NeedsMachineAuth": tr("устройство ждёт одобрения в админ-панели"),
    "Starting": tr("подключается…"),
    "NoState": tr("служба запускается…"),
}


def port_open(host, port, timeout=4):
    try:
        socket.create_connection((host, port), timeout).close()
        return True
    except OSError:
        return False


def read_state(path=STATE_FILE):
    try:
        with open(path) as f:
            st = json.load(f)
        return st if isinstance(st, dict) else {}
    except (OSError, ValueError):
        return {}


def access_text(admin):
    """Текст о сроке прав администратора или None, если не выданы. admin может прийти с чужой машины."""
    if not isinstance(admin, dict) or admin.get("granted") is not True:
        return None
    exp = admin.get("expires")
    if not exp:
        return tr("бессрочно")
    if not isinstance(exp, (int, float)):
        return None
    left = exp - time.time()
    if left <= 0:
        return None
    return tr("ещё {0}").format(fmt_span(left))


def tailscale_up(force, on_line):
    """`tailscale up` с сохранением текущих настроек. Ссылку для входа ищет вызывающий в on_line."""
    cmd = ["tailscale", "up", "--timeout=600s"] + (["--force-reauth"] if force else [])
    rc, text = stream(cmd, on_line)
    if rc != 0 and "non-default" in text:
        # tailscale сам подсказывает команду со всеми текущими флагами — повторяем её
        m = re.search(r"^\s*(tailscale up\b.*)$", text, re.M)
        if m:
            cmd2 = shlex.split(m.group(1))
            if not any(a.startswith("--timeout") for a in cmd2):
                cmd2.append("--timeout=600s")
            if force and "--force-reauth" not in cmd2:
                cmd2.append("--force-reauth")
            on_line(tr("Повторяю с текущими настройками: ") + " ".join(cmd2))
            rc, text = stream(cmd2, on_line)
    return rc, text


def ufw_enabled():
    try:
        with open("/etc/ufw/ufw.conf") as f:
            return re.search(r"^ENABLED=yes", f.read(), re.M) is not None
    except OSError:
        return False


def firewalld_active():
    return run(["systemctl", "is-active", "firewalld"])[1] == "active"


def net_check():
    try:
        socket.create_connection(("controlplane.tailscale.com", 443), 6).close()
        return "ok", tr("серверы Tailscale доступны"), None
    except socket.gaierror:
        return "err", tr("не работает DNS — проверь подключение к интернету"), None
    except OSError as e:
        return "err", tr("нет связи с серверами Tailscale ({0})").format(e.strerror or e), None


def downloads_dir():
    rc, out, _ = run(["xdg-user-dir", "DOWNLOAD"])
    if rc == 0 and out and out != os.path.expanduser("~") and os.path.isdir(out):
        return out
    for d in ("~/Загрузки", "~/Downloads"):
        if os.path.isdir(os.path.expanduser(d)):
            return os.path.expanduser(d)
    return os.path.expanduser("~")


# ───────────────────────── настройки ─────────────────────────

DEFAULT_CONFIG = {"version": 2, "wizard_done": False, "lang": "auto",
                  "theme": {"seed": "green", "mode": "auto", "scale": 1.0, "animations": True},
                  "duration": 86400, "notify": True, "notify_ts": True, "warn_days": 14,
                  "start_page": "auto", "last_page": "", "refresh": 30,
                  "auto_check": True, "auto_alias": True, "terminal": "", "connections": []}
CHOICES = {"duration": tuple(s for _, s in DURATIONS), "warn_days": tuple(int(v) for v, _ in WARN_CHOICES),
           "refresh": tuple(int(v) for v, _ in REFRESH), "start_page": tuple(v for v, _ in START_PAGES),
           "lang": tuple(v for v, _ in LANGS)}


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(tr("config.json — не объект"))
        for k, v in data.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    except (OSError, ValueError):
        pass
    cfg.pop("roles", None)   # до 2.1 вкладки включались по ролям
    if not isinstance(cfg.get("theme"), dict):
        cfg["theme"] = dict(DEFAULT_CONFIG["theme"])
    th = cfg["theme"]
    if th.get("seed") not in [s for s, _, _ in SEEDS]:
        th["seed"] = "green"
    if th.get("mode") not in [m for m, _ in MODES]:
        th["mode"] = "auto"
    if str(th.get("scale")) not in [v for v, _ in SCALES]:
        th["scale"] = 1.0
    if not isinstance(th.get("animations"), bool):
        th["animations"] = True
    for k, v in DEFAULT_CONFIG.items():
        if isinstance(v, bool) and not isinstance(cfg.get(k), bool):
            cfg[k] = v
    for k, allowed in CHOICES.items():
        if isinstance(cfg.get(k), bool) or cfg.get(k) not in allowed:
            cfg[k] = DEFAULT_CONFIG[k]
    for k in ("terminal", "last_page"):
        if not isinstance(cfg.get(k), str):
            cfg[k] = ""
    global WARN_DAYS
    WARN_DAYS = cfg["warn_days"]
    conns = cfg["connections"] if isinstance(cfg.get("connections"), list) else []
    cfg["connections"] = [c for c in conns if valid_conn(c)]
    for c in cfg["connections"]:
        if not (isinstance(c.get("alias"), str) and ALIAS_RE.fullmatch(c["alias"])):
            c["alias"] = alias_for(c["node"])
    return cfg


def valid_conn(c):
    """Подключение из конфига безопасно подставлять в команды ssh."""
    return (isinstance(c, dict) and all(isinstance(c.get(k), str) for k in ("id", "name", "node", "user"))
            and NODE_RE.fullmatch(c["node"]) and USER_RE.fullmatch(c["user"]))


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CONFIG_FILE)


# ───────────────────────── ключи и коды ─────────────────────────

KEY_RE = re.compile(r"((?:sk-)?(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(?:256|384|521))(?:@openssh\.com)?)"
                    r"\s+([A-Za-z0-9+/]{40,}={0,3})(?:\s+(.*))?$")


def parse_key_line(line):
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    m = KEY_RE.search(line)
    if not m:
        return None
    opts = line[:m.start()].strip()
    return {"type": m.group(1), "body": m.group(2), "comment": (m.group(3) or "").strip(), "line": line,
            "opts": opts, "ts_only": opts.startswith(TS_ONLY)}


def parse_pubkey(text):
    """Публичный ключ из вставленного текста. Опции authorized_keys перед ключом не принимаются."""
    for line in (text or "").strip().splitlines():
        k = parse_key_line(line)
        if k and line.strip().startswith(k["type"]):
            return k
    return None


def safe_name(s):
    s = re.sub(r"[^\w.@-]+", "_", (s or "").strip())[:40]
    return s or tr("помощник")


def list_keys():
    """Ключи, которым разрешён вход в эту учётную запись."""
    try:
        with open(AUTH_KEYS) as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    out, seen = [], set()
    for line in lines:
        k = parse_key_line(line)
        if not k or k["body"] in seen:
            continue
        seen.add(k["body"])
        c = k["comment"]
        k["ours"] = c.startswith(KEY_TAG)
        k["name"] = c[len(KEY_TAG):] if k["ours"] else (c or tr("ключ без имени"))
        out.append(k)
    return out


def write_auth_keys(lines):
    d = os.path.dirname(AUTH_KEYS)
    os.makedirs(d, mode=0o700, exist_ok=True)
    os.chmod(d, 0o700)
    tmp = AUTH_KEYS + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    os.chmod(tmp, 0o600)
    os.replace(tmp, AUTH_KEYS)


def ssh_perms_problems():
    """Что помешает sshd (StrictModes) принять ключ: запись для чужих или чужой владелец."""
    home = os.path.expanduser("~")
    probs = []
    for path in (home, os.path.dirname(AUTH_KEYS), AUTH_KEYS):
        short = path.replace(home, "~", 1)
        try:
            st = os.stat(path)
        except FileNotFoundError:
            continue
        except OSError as e:
            probs.append(f"{short}: {e.strerror}")
            continue
        if st.st_uid not in (0, os.getuid()):
            probs.append(tr("{0}: чужой владелец").format(short))
        elif st.st_mode & 0o022:
            probs.append(tr("{0}: запись для чужих").format(short))
    return probs


def fix_ssh_perms():
    """Исправляет права от имени пользователя: root не должен ходить по его папкам и симлинкам."""
    home = os.path.expanduser("~")
    for path, mode in ((home, None), (os.path.dirname(AUTH_KEYS), 0o700), (AUTH_KEYS, 0o600)):
        try:
            st = os.stat(path)
            if st.st_uid == os.getuid():
                os.chmod(path, mode if mode is not None else stat.S_IMODE(st.st_mode) & ~0o022)
        except OSError:
            pass
    return ssh_perms_problems()


def sshd_option(name, path="/etc/ssh/sshd_config", depth=0):
    """Первое значение опции sshd до блоков Match (как выберет sshd) или None.
    Бросает OSError, если файл настроек не прочитать."""
    with open(path) as f:
        lines = f.read().splitlines()
    for line in lines:
        parts = re.split(r"[\s=]+", line.strip(), maxsplit=1)
        if not parts[0] or parts[0].startswith("#"):
            continue
        key, val = parts[0].lower(), (parts[1] if len(parts) > 1 else "").strip()
        if key == "match":
            break
        if key == "include" and depth < 4:
            for pat in val.split():
                for inc in sorted(glob.glob(pat if pat.startswith("/") else "/etc/ssh/" + pat)):
                    v = sshd_option(name, inc, depth + 1)
                    if v is not None:
                        return v
        elif key == name:
            return val.split()[0].strip('"').lower() if val else None
    return None


def ssh_password_auth():
    """Пускает ли SSH-сервер по паролю: True/False, None — настройки не прочитать."""
    try:
        pw = sshd_option("passwordauthentication") or "yes"
        kbd = (sshd_option("kbdinteractiveauthentication") or sshd_option("challengeresponseauthentication")
               or "yes")
        pam = sshd_option("usepam") or "no"
    except OSError:
        return None
    return pw == "yes" or (kbd == "yes" and pam == "yes")


def _other_lines(body):
    """Строки authorized_keys без ключа body (сравнение по самому ключу, не по подстроке)."""
    try:
        with open(AUTH_KEYS) as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    return [l for l in lines if (parse_key_line(l) or {}).get("body") != body]


def add_helper_key(name, key):
    lines = _other_lines(key["body"])
    lines.append(f"{TS_ONLY} {key['type']} {key['body']} {KEY_TAG}{safe_name(name)}")
    write_auth_keys(lines)


def remove_helper_key(body):
    write_auth_keys(_other_lines(body))


def key_fingerprint(k):
    rc, out, _ = run(["ssh-keygen", "-lf", "-"], input=f"{k['type']} {k['body']}\n")
    parts = out.split()
    return parts[1] if rc == 0 and len(parts) > 1 else ""


def ensure_client_key():
    if os.path.exists(CLIENT_KEY):
        return True, tr("уже есть")
    os.makedirs(os.path.dirname(CLIENT_KEY), mode=0o700, exist_ok=True)
    rc, out, err = run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", CLIENT_KEY,
                        "-C", f"kachaning@{socket.gethostname()}"])
    return rc == 0, tr("создан") if rc == 0 else (err or out)


def self_node(st=None, query=True):
    if st is None and query:
        st = ts_status()[0]
    if st and st.get("Self") and st["Self"].get("HostName"):
        return st["Self"]["HostName"]
    return socket.gethostname()


def make_code(data):
    raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()
    return CODE_PREFIX + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def parse_code(text):
    """Разбирает код KCH1:…; бросает ValueError с понятным текстом."""
    t = re.sub(r"\s+", "", text or "")
    if not t.upper().startswith(CODE_PREFIX):
        raise ValueError(tr("это не код Качанинга — он начинается с KCH1:"))
    raw = t[len(CODE_PREFIX):]
    try:
        data = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except (ValueError, TypeError):
        raise ValueError(tr("код повреждён — скопируй его целиком"))
    if not isinstance(data, dict) or data.get("t") not in ("host", "helper"):
        raise ValueError(tr("код неизвестного вида"))
    if not isinstance(data.get("node"), str) or not NODE_RE.fullmatch(data["node"]):
        raise ValueError(tr("в коде неправильное имя компьютера"))
    if data["t"] == "host" and not (isinstance(data.get("user"), str) and USER_RE.fullmatch(data["user"])):
        raise ValueError(tr("в коде неправильное имя пользователя"))
    if data["t"] == "helper" and not (isinstance(data.get("key"), str) and parse_pubkey(data["key"])):
        raise ValueError(tr("в коде нет правильного ключа"))
    return data


def my_host_code(st=None, query=True):
    return make_code({"t": "host", "node": self_node(st, query), "user": getpass.getuser()})


def my_helper_code(st=None, query=True):
    try:
        with open(CLIENT_KEY + ".pub") as f:
            k = parse_pubkey(f.read())
    except OSError:
        return None
    if not k:
        return None
    return make_code({"t": "helper", "node": self_node(st, query), "key": f"{k['type']} {k['body']}"})


def alias_for(node):
    return re.sub(r"[^a-z0-9_.-]+", "-", (node or "").lower()).strip("-._")[:63] or "friend"


def ssh_config_hostname(alias):
    """HostName из блока `Host <alias>` в ~/.ssh/config или None."""
    try:
        with open(os.path.expanduser("~/.ssh/config")) as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    inside = False
    for line in lines:
        parts = line.strip().split()
        if not parts or parts[0].startswith("#"):
            continue
        key = parts[0].lower()
        if key in ("host", "match"):
            inside = key == "host" and alias in parts[1:]
        elif inside and key == "hostname" and len(parts) > 1:
            return parts[1]
    return None


def write_ssh_alias(alias, ip, user):
    # в ~/.ssh/config можно внедрить ProxyCommand — пишем только проверенные значения
    if not (ALIAS_RE.fullmatch(alias or "") and USER_RE.fullmatch(user or "")):
        raise ValueError(tr("неправильное имя для ssh"))
    ip = str(ipaddress.ip_address(ip))
    path = os.path.expanduser("~/.ssh/config")
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    try:
        with open(path) as f:
            lines = f.read().splitlines()
        if not os.path.exists(path + ".bak-kachaning"):
            shutil.copy2(path, path + ".bak-kachaning")
    except OSError:
        lines = []
    start = None
    for i, line in enumerate(lines):
        parts = line.strip().split()
        if parts and parts[0].lower() == "host" and alias in parts[1:]:
            start = i
            break
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines += [f"# {APP_NAME}", f"Host {alias}", f"    HostName {ip}", f"    User {user}",
                  f"    IdentityFile {CLIENT_KEY.replace(os.path.expanduser('~'), '~', 1)}"]
    else:
        end = len(lines)
        for j in range(start + 1, len(lines)):
            p = lines[j].strip().split()
            if p and p[0].lower() in ("host", "match"):
                end = j
                break
        for j in range(start + 1, end):
            p = lines[j].strip().split()
            if p and p[0].lower() == "hostname":
                lines[j] = re.sub(r"(?i)(hostname\s+)\S+", lambda m: m.group(1) + ip, lines[j])
                break
        else:
            lines.insert(start + 1, f"    HostName {ip}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(path, 0o600)


def ssh_base(ip, user):
    return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
            "-o", "StrictHostKeyChecking=accept-new", "-o", "IdentitiesOnly=yes",
            "-i", CLIENT_KEY, f"{user}@{ip}"]


# ───────────────────────── проверки ─────────────────────────

HOST_CHECKS = [
    ("net", tr("Интернет")),
    ("ts", tr("Tailscale установлен")),
    ("daemon", tr("Служба Tailscale")),
    ("login", tr("Вход в Tailscale")),
    ("expiry", tr("Срок ключа Tailscale")),
    ("ssh", tr("SSH-сервер")),
    ("perms", tr("Права на ~/.ssh")),
    ("pwauth", tr("Вход по паролю")),
    ("helpers", tr("Помощники")),
    ("firewall", tr("Фаервол")),
    ("time", tr("Точное время")),
    ("access", tr("Права администратора")),
    ("guard", tr("Автоотзыв прав")),
]

CONN_CHECKS = [
    ("peer", tr("Компьютер в сети")),
    ("peer_exp", tr("Срок его ключа Tailscale")),
    ("route", tr("Маршрут")),
    ("port", tr("Порт SSH")),
    ("auth", tr("Вход по ключу")),
    ("sudo", tr("Права администратора")),
    ("alias", tr("Короткая команда ssh")),
]

STEP_NAMES = {"operator": tr("Права на управление Tailscale"), "sshd_cfg": tr("Настройки SSH-сервера"),
              "migrate": tr("Перенос со старой версии")}

FIX_LABELS = {
    "setup": tr("Исправить"), "grant": tr("Выдать"), "login": tr("Войти"), "renew": tr("Продлить"),
    "admin": tr("Открыть"), "noexpiry": tr("Навсегда"), "tssetup": tr("Исправить"),
    "hostkey": tr("Исправить"), "alias": tr("Исправить"), "addhelper": tr("Добавить"), "copycode": tr("Код"),
    "net": tr("Сеть"), "perms": tr("Исправить"), "nopass": tr("Отключить"), "restrict": tr("Ограничить"),
}


def skip_rest(checks, start, why):
    ids = [c for c, _ in checks]
    for c in ids[ids.index(start):]:
        yield c, "skip", why, None


def host_checks(ctx):
    yield ("net",) + net_check()
    if not shutil.which("tailscale"):
        yield "ts", "err", tr("не установлен"), "setup"
        for c in ("daemon", "login", "expiry"):
            yield c, "skip", tr("нужен Tailscale"), None
    else:
        ver = run(["tailscale", "version"])[1].splitlines()
        yield "ts", "ok", tr("версия {0}").format(ver[0] if ver else '?'), None
        st, err = ts_status()
        if st is None:
            yield "daemon", "err", err, "setup"
            for c in ("login", "expiry"):
                yield c, "skip", tr("служба не работает"), None
        else:
            yield "daemon", "ok", tr("работает"), None
            bs = st.get("BackendState")
            me = st.get("Self") or {}
            ctx["self_ip"] = first_ip(me)
            if bs == "Running":
                yield "login", "ok", tr("в сети как {0} · {1}").format(me.get('HostName'), first_ip(me)), None
            elif bs == "NeedsMachineAuth":
                yield "login", "warn", BACKEND_TEXT[bs], "admin"
            else:
                yield "login", "err", BACKEND_TEXT.get(bs, bs), "login"
            if me.get("KeyExpiry"):
                yield ("expiry",) + key_expiry_result(me)
            else:
                yield "expiry", "skip", tr("нужен вход в Tailscale"), None

    if port_open("127.0.0.1", 22, 2):
        yield "ssh", "ok", tr("работает, порт 22"), None
    else:
        yield "ssh", "err", tr("не запущен или не установлен"), "setup"

    probs = ssh_perms_problems()
    if probs:
        yield "perms", "err", tr("SSH не примет ключи: ") + "; ".join(probs), "perms"
    else:
        yield "perms", "ok", tr("в порядке"), None

    if not os.path.exists("/etc/ssh/sshd_config"):
        yield "pwauth", "skip", tr("SSH-сервер не установлен"), None
    else:
        pw = ssh_password_auth()
        if pw is None:
            yield "pwauth", "info", tr("не удалось прочитать настройки SSH"), None
        elif pw:
            yield "pwauth", "warn", tr("включён — пароль можно подбирать из локальной сети"), "nopass"
        else:
            yield "pwauth", "ok", tr("выключен, только ключи"), None

    keys = list_keys()
    open_keys = [k for k in keys if k["ours"] and not k["ts_only"]]
    if open_keys:
        yield "helpers", "warn", tr("{0} из {1} пускают из любой сети, не только из Tailscale").format(len(open_keys), len(keys)), \
            "restrict"
    elif keys:
        n = len(keys)
        yield "helpers", "ok", tr("{0} {1} к входу").format(n, plural(n, tr('ключ допущен'), tr('ключа допущены'), tr('ключей допущено'))), None
    else:
        yield "helpers", "warn", tr("ни одного — добавь код помощника"), "addhelper"

    state = read_state()
    if ufw_enabled() or firewalld_active():
        if state.get("firewall") == "ok":
            yield "firewall", "ok", tr("включён, SSH через Tailscale разрешён"), None
        else:
            yield "firewall", "warn", tr("включён — может блокировать SSH"), "setup"
    else:
        yield "firewall", "ok", tr("выключен, не мешает"), None

    if run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"])[1] == "yes":
        yield "time", "ok", tr("синхронизировано"), None
    else:
        yield "time", "warn", tr("не синхронизировано — Tailscale может не войти"), "setup"

    adm = state.get("admin")
    txt = access_text(adm)
    if txt:
        ctx["access"] = txt
        yield "access", "ok", tr("выданы, {0}").format(txt), None
    elif isinstance(adm, dict) and adm.get("granted"):
        yield "access", "info", tr("срок истёк, права снимаются"), "grant"
    else:
        yield "access", "info", tr("не выданы"), "grant"

    if run(["systemctl", "is-enabled", "kachaning-expire.timer"])[0] == 0:
        yield "guard", "ok", tr("таймер работает"), None
    else:
        yield "guard", "warn", tr("не установлен — права на время не снимутся сами"), "setup"


def conn_checks(conn, ctx):
    C = CONN_CHECKS
    user, node = conn["user"], conn["node"]
    st, err = ts_status()
    if st is None or st.get("BackendState") != "Running":
        yield "peer", "err", tr("Tailscale на этом компьютере не подключён"), "net"
        yield from skip_rest(C, "peer_exp", tr("нет Tailscale"))
        return
    peer = find_peer(st, node)
    if not peer:
        yield ("peer", "err", tr("«{0}» не виден в Tailscale — если у вас разные аккаунты, друг должен поделиться компьютером, а ты принять приглашение").format(node), "admin")
        yield from skip_rest(C, "peer_exp", tr("компьютер не найден"))
        return
    ip = first_ip(peer)
    ctx["ip"] = ip
    online = peer.get("Online")
    if online:
        yield "peer", "ok", tr("{0} · {1} · в сети").format(peer.get('HostName'), ip), None
    else:
        yield "peer", "err", tr("не в сети (был {0}) — выключен или Tailscale не работает").format(last_seen(peer)), None
    state, detail, _ = key_expiry_result(peer)
    if state != "ok":
        detail += tr(" — пусть владелец откроет «{0}» → «Сеть» → «Продлить»").format(APP_NAME)
    yield "peer_exp", state, detail, None
    if not online:
        yield from skip_rest(C, "route", tr("компьютер не в сети"))
        return

    rc, out, _ = run(["tailscale", "ping", "-c", "3", "--timeout=5s", ip], timeout=30)
    pongs = re.findall(r"pong from .* via (\S+) in ([\d.]+)ms", out)
    if pongs:
        via, ms = pongs[-1]
        ms = round(float(ms))
        ctx["route"] = tr("{0} мс").format(ms)
        how = tr("через ретранслятор {0}").format(via) if via.startswith("DERP") else tr("напрямую")
        yield "route", "ok", tr("{0}, {1} мс").format(how, ms), None
    else:
        yield "route", "err", tr("не отвечает на ping через Tailscale"), None

    if not port_open(ip, 22, 6):
        yield "port", "err", tr("закрыт — пусть владелец откроет «{0}» → «Принимать» → «Исправить всё»").format(APP_NAME), None
        yield from skip_rest(C, "auth", tr("порт закрыт"))
        return
    yield "port", "ok", tr("открыт"), None

    if not os.path.exists(CLIENT_KEY):
        yield "auth", "err", tr("у тебя ещё нет SSH-ключа — открой «Подключиться» и создай его"), "copycode"
        yield from skip_rest(C, "sudo", tr("нет ключа"))
        return
    # через sh -c: у друга может быть fish или другая оболочка входа
    script = ("echo KCH_OK; sudo -n true 2>/dev/null && echo KCH_SUDO; "
              "cat /etc/kachaning/state.json 2>/dev/null || cat /etc/tsbridge/state.json 2>/dev/null")
    rc, out, err = run(ssh_base(ip, user) + ["sh -c " + shlex.quote(script)], timeout=25)
    if "KCH_OK" not in out:
        if "IDENTIFICATION HAS CHANGED" in err:
            yield "auth", "err", tr("ключ сервера изменился (переустановка системы?)"), "hostkey"
        elif "Permission denied" in err and run(["ssh-keygen", "-y", "-P", "", "-f", CLIENT_KEY])[0] != 0:
            yield "auth", "warn", tr("твой ключ защищён паролем — проверка не может войти сама, " \
                                  "в терминале ssh спросит пароль ключа"), None
        elif "Permission denied" in err:
            yield "auth", "err", tr("ключ не принят — отправь другу свой код помощника"), "copycode"
        else:
            yield "auth", "err", (err.splitlines() or [tr("нет ответа")])[-1], None
        yield from skip_rest(C, "sudo", tr("нет входа по SSH"))
        return
    yield "auth", "ok", tr("вход как {0}").format(user), None

    if "KCH_SUDO" in out:
        try:
            remote = json.loads(out[out.index("{"):])
        except ValueError:
            remote = {}
        txt = access_text(remote.get("admin") if isinstance(remote, dict) else None)
        ctx["sudo"] = True
        yield "sudo", "ok", tr("есть, {0}").format(txt) if txt else tr("есть (выданы вручную)"), None
    else:
        yield "sudo", "info", tr("нет — пусть друг нажмёт «Выдать права» в «{0}»").format(APP_NAME), None

    alias = conn.get("alias") or alias_for(node)
    cur = ssh_config_hostname(alias)
    if cur == ip:
        ctx["alias_ok"] = True
        yield "alias", "ok", f"ssh {alias}", None
    elif cur is None:
        ctx["alias_missing"] = True
        yield "alias", "info", tr("можно настроить: ssh {0}").format(alias), "alias"
    else:
        # чужой блок Host в ~/.ssh/config молча не переписываем
        yield "alias", "info", tr("ssh {0} сейчас ведёт на {1}").format(alias, cur), "alias"


def cli_check():
    cfg = load_config()
    marks = {"ok": "✓", "warn": "!", "err": "✕", "skip": "–", "info": "i"}
    bad = 0

    def show(checks, gen):
        nonlocal bad
        names = dict(checks)
        for cid, state, detail, fix in gen:
            bad += state == "err"
            extra = f"  [{FIX_LABELS[fix]}]" if fix else ""
            print(f"  {marks[state]} {names[cid]}: {detail}{extra}")

    st, err = ts_status()
    print(tr("Сеть:"), err or f"{st.get('BackendState')} · {self_node(st)}")
    print(tr("Принимать:"))
    show(HOST_CHECKS, host_checks({}))
    for conn in cfg["connections"]:
        print(tr("Подключение «{0}» ({1}@{2}):").format(conn['name'], conn['user'], conn['node']))
        show(CONN_CHECKS, conn_checks(conn, {}))
    return 1 if bad else 0


# ───────────────────────── действия от root ─────────────────────────

def root_python():
    """Python для запуска от root — только тот, который пользователь не может подменить."""
    for p in ("/usr/bin/python3", sys.executable):
        try:
            st = os.stat(p)
        except OSError:
            continue
        if st.st_uid == 0 and not st.st_mode & 0o022:
            return p
    return "/usr/bin/python3"


def emit(*parts):
    print("\t".join(str(p).replace("\n", " ").replace("\t", " ") for p in parts), flush=True)


def rlog(msg):
    for line in str(msg).splitlines():
        if line.strip():
            emit("LOG", line)


def os_release():
    d = {}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if "=" in line:
                    k, v = line.rstrip("\n").split("=", 1)
                    d[k] = v.strip('"')
    except OSError:
        pass
    return d


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


def update_state(**kw):
    os.makedirs(STATE_DIR, mode=0o755, exist_ok=True)
    st = read_state()
    st.update(kw)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o644)
    os.replace(tmp, STATE_FILE)


def apt_install(*pkgs):
    env = {"DEBIAN_FRONTEND": "noninteractive"}
    cmd = ["apt-get", "-y", "-o", "DPkg::Lock::Timeout=300", "install", *pkgs]
    rc, out, err = run(cmd, timeout=1200, env=env)
    if rc != 0 and "dpkg --configure -a" in out + err:
        rlog(tr("Прерванная установка пакетов — доделываю (dpkg --configure -a)"))
        run(["dpkg", "--configure", "-a"], timeout=1200, env=env)
        rc, out, err = run(cmd, timeout=1200, env=env)
    if rc != 0:
        rlog(tr("Обновляю списки пакетов"))
        run(["apt-get", "-o", "DPkg::Lock::Timeout=300", "update"], timeout=600, env=env)
        rc, out, err = run(cmd, timeout=1200, env=env)
    if rc != 0:
        rlog(err or out)
    return rc == 0


def pkg_install(debian_pkgs, arch_pkgs):
    if shutil.which("apt-get"):
        return apt_install(*debian_pkgs)
    for cmd in (["pacman", "-Sy", "--noconfirm", "--needed", *arch_pkgs],
                ["dnf", "install", "-y", *debian_pkgs], ["zypper", "--non-interactive", "install", *debian_pkgs]):
        if shutil.which(cmd[0]):
            rc, out, err = run(cmd, timeout=1200)
            if rc != 0:
                rlog(err or out)
            return rc == 0
    rlog(tr("Неизвестный менеджер пакетов"))
    return False


def s_net():
    return net_check()[:2]


def s_time():
    if run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"])[1] == "yes":
        return "ok", tr("время синхронизировано")
    rc, out, err = run(["timedatectl", "set-ntp", "true"])
    if rc != 0:
        return "warn", tr("не удалось включить синхронизацию: {0}").format(err or out)
    return "ok", tr("включена синхронизация времени")


def s_ts_install():
    if shutil.which("tailscale") and shutil.which("tailscaled"):
        return "ok", tr("уже установлен")
    if shutil.which("apt-get"):
        osr = os_release()
        like = (osr.get("ID", "") + " " + osr.get("ID_LIKE", "")).lower()
        if "ubuntu" in like:
            dist, code = "ubuntu", osr.get("UBUNTU_CODENAME") or osr.get("VERSION_CODENAME")
        else:
            dist, code = "debian", osr.get("DEBIAN_CODENAME") or osr.get("VERSION_CODENAME")
        base = f"https://pkgs.tailscale.com/stable/{dist}/{code}"
        rlog(tr("Добавляю репозиторий Tailscale ({0} {1})").format(dist, code))
        try:
            key = fetch(base + ".noarmor.gpg")
            lst = fetch(base + ".tailscale-keyring.list")
        except OSError as e:
            return "err", tr("не удалось скачать ключ репозитория: {0}").format(e)
        with open("/usr/share/keyrings/tailscale-archive-keyring.gpg", "wb") as f:
            f.write(key)
        with open("/etc/apt/sources.list.d/tailscale.list", "wb") as f:
            f.write(lst)
        run(["apt-get", "-o", "DPkg::Lock::Timeout=300", "update"], timeout=600,
            env={"DEBIAN_FRONTEND": "noninteractive"})
    if pkg_install(["tailscale"], ["tailscale"]) and shutil.which("tailscale"):
        return "ok", tr("установлен")
    return "err", tr("установка не удалась — подробности в журнале")


def s_ts_service():
    run(["systemctl", "enable", "--now", "tailscaled"], timeout=60)
    err = ""
    for _ in range(3):
        for _ in range(10):
            st, err = ts_status()
            if st is not None:
                return "ok", tr("служба работает")
            time.sleep(1)
        rlog(tr("tailscaled не отвечает ({0}) — перезапускаю").format(err))
        run(["systemctl", "restart", "tailscaled"], timeout=60)
    rlog(run(["journalctl", "-u", "tailscaled", "-n", "20", "--no-pager"])[1])
    return "err", tr("служба tailscaled не запускается — подробности в журнале")


def s_operator(user):
    rc, out, err = run(["tailscale", "set", f"--operator={user}"])
    if rc == 0:
        return "ok", tr("{0} может управлять Tailscale без пароля").format(user)
    return "warn", tr("не удалось: {0}").format(err or out)


def ssh_unit():
    for u in ("ssh", "sshd"):
        if run(["systemctl", "cat", f"{u}.service"])[0] == 0:
            return u
    return None


def s_ssh():
    if port_open("127.0.0.1", 22, 2):
        return "ok", tr("уже работает")
    if not (shutil.which("sshd") or os.path.exists("/usr/sbin/sshd")):
        rlog(tr("Устанавливаю SSH-сервер"))
        if not pkg_install(["openssh-server"], ["openssh"]):
            return "err", tr("не удалось установить SSH-сервер")
    unit = ssh_unit()
    if not unit:
        return "err", tr("служба SSH не найдена")
    run(["systemctl", "enable", "--now", f"{unit}.service"], timeout=60)
    for _ in range(10):
        if port_open("127.0.0.1", 22, 2):
            return "ok", tr("работает")
        time.sleep(1)
    run(["systemctl", "restart", f"{unit}.service"], timeout=60)
    time.sleep(2)
    if port_open("127.0.0.1", 22, 2):
        return "ok", tr("работает (после перезапуска)")
    rlog(run(["journalctl", "-u", unit, "-n", "20", "--no-pager"])[1])
    return "err", tr("SSH-сервер не запускается")


def s_sshd_cfg(user):
    sshd = shutil.which("sshd") or "/usr/sbin/sshd"
    rc, out, err = run([sshd, "-T"])
    if rc != 0:
        rlog(err)
        return "err", tr("в настройках SSH ошибка")
    conf = {}
    for line in out.splitlines():
        k, _, v = line.partition(" ")
        conf.setdefault(k, v)
    notes = []
    if conf.get("pubkeyauthentication") != "yes":
        dropin = "/etc/ssh/sshd_config.d/01-kachaning.conf"
        os.makedirs(os.path.dirname(dropin), exist_ok=True)
        with open(dropin, "w") as f:
            f.write(tr("# {0}: вход по ключу для удалённой помощи\nPubkeyAuthentication yes\n").format(APP_NAME))
        if run([sshd, "-t"])[0] != 0:
            os.remove(dropin)
            return "err", tr("не удалось включить вход по ключу")
        unit = ssh_unit()
        if unit:
            run(["systemctl", "try-reload-or-restart", f"{unit}.service"])
        notes.append(tr("включён вход по ключу"))
    allow = conf.get("allowusers")
    if allow and user not in allow.split():
        notes.append(tr("внимание: AllowUsers не включает {0}").format(user))
        return "warn", ", ".join(notes)
    return "ok", ", ".join(notes) or tr("в порядке")


def s_nopass():
    """Только вход по ключам. Файл 00-… читается раньше остальных, а у sshd побеждает первое значение."""
    sshd = shutil.which("sshd") or "/usr/sbin/sshd"
    os.makedirs(os.path.dirname(NOPASS_CONF), exist_ok=True)
    for kbd in ("KbdInteractiveAuthentication", "ChallengeResponseAuthentication"):  # второе — для старых sshd
        with open(NOPASS_CONF, "w") as f:
            f.write(tr("# {0}: вход только по ключам\nPasswordAuthentication no\n{1} no\n").format(APP_NAME, kbd))
        rc, out, err = run([sshd, "-t"])
        if rc == 0:
            break
    else:
        os.remove(NOPASS_CONF)
        rlog(err or out)
        return "err", tr("sshd не принял настройку — ничего не изменено")
    conf = dict(l.partition(" ")[::2] for l in run([sshd, "-T"])[1].splitlines())
    if conf.get("passwordauthentication") != "no":
        os.remove(NOPASS_CONF)
        return "err", tr("sshd не читает /etc/ssh/sshd_config.d — отключи PasswordAuthentication вручную")
    unit = ssh_unit()
    if unit:
        run(["systemctl", "try-reload-or-restart", f"{unit}.service"])
    return "ok", tr("выключен, только ключи")


def s_firewall():
    if shutil.which("ufw") and ufw_enabled():
        rc, out, err = run(["ufw", "allow", "in", "on", "tailscale0", "to", "any", "port", "22", "proto", "tcp"])
        if rc != 0:
            return "err", f"ufw: {err or out}"
        update_state(firewall="ok")
        return "ok", tr("ufw: SSH через Tailscale разрешён")
    if shutil.which("firewall-cmd") and firewalld_active():
        run(["firewall-cmd", "--permanent", "--zone=trusted", "--add-interface=tailscale0"])
        run(["firewall-cmd", "--reload"])
        update_state(firewall="ok")
        return "ok", tr("firewalld: Tailscale в доверенной зоне")
    update_state(firewall="none")
    return "ok", tr("фаервол выключен")


def s_guard():
    src = os.path.realpath(__file__)
    if src != ROOT_COPY:
        os.makedirs(ROOT_DIR, mode=0o755, exist_ok=True)
        shutil.copyfile(src, ROOT_COPY)
        os.chown(ROOT_COPY, 0, 0)
        os.chmod(ROOT_COPY, 0o755)
    elif os.path.isdir(ROOT_DIR):
        shutil.rmtree(ROOT_DIR, ignore_errors=True)  # копия от установки без пакета больше не нужна
    with open("/etc/systemd/system/kachaning-expire.service", "w") as f:
        f.write(tr("[Unit]\nDescription={0}: снять истёкшие права администратора\n\n[Service]\nType=oneshot\nExecStart={1} -I {2} --root expire-check\n").format(APP_NAME, root_python(), ROOT_COPY))
    with open("/etc/systemd/system/kachaning-expire.timer", "w") as f:
        f.write(tr("[Unit]\nDescription={0}: проверка срока прав\n\n[Timer]\nOnBootSec=1min\nOnUnitActiveSec=5min\nAccuracySec=30s\n\n[Install]\nWantedBy=timers.target\n").format(APP_NAME))
    run(["systemctl", "daemon-reload"])
    rc, out, err = run(["systemctl", "enable", "--now", "kachaning-expire.timer"])
    if rc != 0:
        return "err", err or out
    return "ok", tr("таймер установлен")


def s_migrate(user):
    """Перенос со старой версии (TS Bridge): действующие права сохраняются."""
    notes = []
    if os.path.exists(LEGACY["sudoers"]):
        old = read_state(LEGACY["state_dir"] + "/state.json").get("admin") or {}
        exp = old.get("expires")
        if old.get("granted") and (not exp or exp > time.time()):
            grant_until(user, exp)
            notes.append(tr("права перенесены"))
        os.remove(LEGACY["sudoers"])
    unit = LEGACY["unit"]
    if os.path.exists(f"/etc/systemd/system/{unit}.timer"):
        run(["systemctl", "disable", "--now", f"{unit}.timer"])
        for ext in ("timer", "service"):
            try:
                os.remove(f"/etc/systemd/system/{unit}.{ext}")
            except FileNotFoundError:
                pass
        run(["systemctl", "daemon-reload"])
        notes.append(tr("старый таймер удалён"))
    for d in (LEGACY["root_dir"], LEGACY["state_dir"]):
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
    if os.path.exists("/etc/ssh/sshd_config.d/01-tsbridge.conf"):
        os.replace("/etc/ssh/sshd_config.d/01-tsbridge.conf", "/etc/ssh/sshd_config.d/01-kachaning.conf")
    return "ok", ", ".join(notes) or tr("нечего переносить")


def s_login(user, force=False):
    st, err = ts_status()
    if st is None:
        return "err", err
    me = st.get("Self") or {}
    running = st.get("BackendState") == "Running"
    exp = parse_ts_time(me.get("KeyExpiry"))
    expiring = exp is not None and (exp - now_utc()).total_seconds() < WARN_DAYS * 86400
    if running and not expiring and not force:
        return "ok", tr("вход выполнен")
    rlog(tr("Нужен вход в Tailscale — открываю страницу входа в браузере"))
    seen = set()

    def on_line(line):
        rlog(line)
        m = AUTH_RE.search(line)
        if m and m.group(0) not in seen:
            seen.add(m.group(0))
            emit("URL", m.group(0))

    tailscale_up(running, on_line)
    st, _ = ts_status()
    if st and st.get("BackendState") == "Running":
        return "ok", tr("вход выполнен, ключ продлён") if running else tr("вход выполнен")
    return "err", tr("вход не завершён — повтори и войди в браузере")


def grant_until(user, expires):
    body = (tr("# Создано программой «{0}». Снимается кнопкой «Отозвать»\n# или автоматически по истечении срока (kachaning-expire.timer).\n{1} ALL=(ALL:ALL) NOPASSWD: ALL\n").format(APP_NAME, user))
    tmp = SUDOERS_FILE + ".tmp"   # файлы с точкой в имени sudo игнорирует
    with open(tmp, "w") as f:
        f.write(body)
    os.chmod(tmp, 0o440)
    rc, out, err = run(["visudo", "-cf", tmp])
    if rc != 0:
        os.remove(tmp)
        return "err", tr("visudo отклонил файл: {0}").format(err or out)
    # сначала состояние, потом файл: expire-check снимает файл, если в состоянии прав нет
    prev = read_state().get("admin")
    update_state(admin={"granted": True, "user": user, "since": int(time.time()),
                        "expires": int(expires) if expires else None})
    try:
        os.replace(tmp, SUDOERS_FILE)
    except OSError:
        update_state(admin=prev)
        raise
    return "ok", tr("выданы на {0}").format(fmt_span(expires - time.time())) if expires else tr("выданы бессрочно")


def root_revoke():
    for p in (SUDOERS_FILE, LEGACY["sudoers"]):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
    update_state(admin={"granted": False, "revoked": int(time.time())})
    return "ok", tr("права отозваны")


def grant_for(user, secs):
    try:
        secs = int(secs)
    except (TypeError, ValueError):
        return "err", tr("неправильный срок")
    if not 0 <= secs <= 366 * 86400:
        return "err", tr("неправильный срок")
    return grant_until(user, time.time() + secs if secs else None)


def root_expire_check():
    adm = read_state().get("admin")
    adm = adm if isinstance(adm, dict) else {}
    exp = adm.get("expires")
    if adm.get("granted") is True and isinstance(exp, (int, float)) and time.time() > exp:
        root_revoke()
        print(tr("{0}: срок прав истёк, права сняты").format(APP_NAME))
    elif adm.get("granted") is not True and os.path.exists(SUDOERS_FILE):
        root_revoke()
        print(tr("{0}: права без записи о выдаче — сняты").format(APP_NAME))
    return 0


def root_main(args):
    if os.geteuid() != 0:
        print(tr("нужны права root"), file=sys.stderr)
        return 1
    if not args:
        return 2
    action, rest = args[0], args[1:]
    if action == "expire-check":
        return root_expire_check()
    uid = os.environ.get("PKEXEC_UID") or os.environ.get("SUDO_UID")
    if uid is None:
        print(tr("неизвестно, кто вызвал (нет PKEXEC_UID/SUDO_UID)"), file=sys.stderr)
        return 2
    pw = pwd.getpwuid(int(uid))
    user = pw.pw_name
    ok = True

    def do(sid, fn, *a):
        nonlocal ok
        emit("STEP", sid, "run", "")
        try:
            state, msg = fn(*a)
        except Exception as e:  # шаг упал — остальные всё равно пробуем
            state, msg = "err", f"{type(e).__name__}: {e}"
        emit("STEP", sid, state, msg)
        ok = ok and state != "err"
        return state

    def tailscale_steps():
        return do("ts", s_ts_install) != "err" and do("daemon", s_ts_service) != "err" \
            and do("operator", s_operator, user) != "err"

    if action == "setup-host":
        do("net", s_net)
        do("time", s_time)
        ts_ok = tailscale_steps()
        do("ssh", s_ssh)
        do("sshd_cfg", s_sshd_cfg, user)
        do("firewall", s_firewall)
        do("guard", s_guard)
        do("migrate", s_migrate, user)
        if ts_ok:
            do("login", s_login, user)
        if "--grant" in rest:
            do("access", grant_for, user, (rest[rest.index("--grant") + 1:] or [""])[0])
        update_state(setup_at=int(time.time()), user=user)
    elif action == "setup-ts":
        if tailscale_steps() and "--login" in rest:
            do("login", s_login, user)
    elif action == "operator":
        do("operator", s_operator, user)
    elif action == "login":
        do("operator", s_operator, user)
        do("login", s_login, user, "--force" in rest)
    elif action == "grant":
        do("access", grant_for, user, (rest or [""])[0])
    elif action == "harden-ssh":
        do("pwauth", s_nopass)
    elif action == "revoke":
        do("access", root_revoke)
    else:
        print(tr("неизвестное действие {0}").format(action), file=sys.stderr)
        return 2
    emit("DONE", 0 if ok else 1)
    return 0 if ok else 1


# ───────────────────────── уведомления и установка ─────────────────────────

def notify_check():
    cfg = load_config()
    msgs = []
    hint = tr("Открой «{0}» → «Сеть».").format(APP_NAME)
    st, err = ts_status()
    if st is None:
        if cfg["notify_ts"]:
            msgs.append(("critical", tr("Tailscale не работает"), f"{err}. {hint}"))
    else:
        if st.get("BackendState") != "Running" and cfg["notify_ts"]:
            msgs.append(("critical", tr("Нужен вход в Tailscale"),
                         f"{BACKEND_TEXT.get(st.get('BackendState'), '')}. {hint}"))
        me = st.get("Self") or {}
        if me.get("KeyExpiry"):
            state, detail, _ = key_expiry_result(me)
            if state != "ok":
                msgs.append(("critical" if state == "err" else "normal",
                             tr("Ключ Tailscale истёк") if state == "err" else tr("Ключ Tailscale скоро истечёт"),
                             tr("Срок: {0}. {1} и нажми «Продлить».").format(detail, hint)))
        for conn in cfg["connections"]:
            peer = find_peer(st, conn["node"])
            if peer:
                state, detail, _ = key_expiry_result(peer)
                if state != "ok":
                    msgs.append(("normal", tr("Ключ Tailscale у «{0}» истекает").format(conn['name']),
                                 tr("{0}. Попроси открыть «{1}» → «Сеть» → «Продлить».").format(detail, APP_NAME)))
    icon = os.path.join(USER_DIR, "icon.svg")
    for urgency, title, body in msgs:
        run(["notify-send", "-u", urgency, "-a", APP_NAME, "-i", icon, title, html.escape(body)])
    return 0


ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
<rect x="6" y="6" width="116" height="116" rx="38" fill="#BCF0B4"/>
<path d="M64 22 L99 36 V61 C99 84 84 99 64 106 C44 99 29 84 29 61 V36 Z" fill="#3B6939"/>
<circle cx="50" cy="66" r="9" fill="none" stroke="#BCF0B4" stroke-width="7"/>
<circle cx="78" cy="66" r="9" fill="none" stroke="#BCF0B4" stroke-width="7"/>
<path d="M59 66 H69" stroke="#BCF0B4" stroke-width="7" stroke-linecap="round"/>
</svg>
"""


def desktop_dir():
    rc, out, _ = run(["xdg-user-dir", "DESKTOP"])
    if rc == 0 and out and out != os.path.expanduser("~") and os.path.isdir(out):
        return out
    for d in ("~/Рабочий стол", "~/Desktop"):
        d = os.path.expanduser(d)
        if os.path.isdir(d):
            return d
    return None


def unit_quote(s):
    """Аргумент для ExecStart= в юните systemd."""
    s = s.replace("%", "%%")
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"' if re.search(r'[\s"\\]', s) else s


def desktop_quote(s):
    """Аргумент для Exec= в .desktop: кавычки по спецификации, затем экранирование строки."""
    if re.search(r'[\s"`$\\]', s):
        s = '"' + re.sub(r'(["`$\\])', r"\\\1", s) + '"'
    return s.replace("\\", "\\\\").replace("%", "%%")


def app_script():
    """Файл, который запускают ярлык и таймеры: из пакета — системный, иначе копия в ~/.local."""
    return os.path.realpath(__file__) if PACKAGED else os.path.join(USER_DIR, "kachaning.py")


def set_notify_timer(enabled):
    units = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(units, exist_ok=True)
    dst = app_script()
    with open(os.path.join(units, "kachaning-notify.service"), "w") as f:
        f.write(tr("[Unit]\nDescription={0}: проверка срока ключей Tailscale\n\n[Service]\nType=oneshot\nExecStart={1} {2} --notify-check\n").format(APP_NAME, unit_quote(sys.executable), unit_quote(dst)))
    with open(os.path.join(units, "kachaning-notify.timer"), "w") as f:
        f.write(tr("[Unit]\nDescription={0}: проверка Tailscale дважды в сутки\n\n[Timer]\nOnStartupSec=3min\nOnUnitActiveSec=12h\n\n[Install]\nWantedBy=timers.target\n").format(APP_NAME))
    run(["systemctl", "--user", "daemon-reload"])
    if enabled:
        return run(["systemctl", "--user", "enable", "--now", "kachaning-notify.timer"])[0] == 0
    run(["systemctl", "--user", "disable", "--now", "kachaning-notify.timer"])
    return True


def desktop_entry(script, icon):
    return (tr("[Desktop Entry]\nType=Application\nName={0}\nComment=Удалённая помощь через Tailscale\nExec={1} {2}\nIcon={3}\nTerminal=false\nCategories=Network;System;\nStartupNotify=true\nStartupWMClass=kachaning\n").format(APP_NAME, desktop_quote(sys.executable), desktop_quote(script), icon))


def adopt_package():
    """Установлено пакетом: убрать следы установки в ~/.local, перевести ярлык и таймер на пакет."""
    old_copy = os.path.join(USER_DIR, "kachaning.py")
    apps_entry = os.path.expanduser("~/.local/share/applications/kachaning.desktop")
    desk = desktop_dir()
    shortcuts = [os.path.join(desk, n) for n in ("Качанинг.desktop", "Kachaning.desktop")] if desk else []
    for p in [apps_entry] + shortcuts:
        try:
            with open(p) as f:
                points_old = old_copy in f.read()
        except OSError:
            continue
        if not points_old:
            continue
        if p == apps_entry:
            os.remove(p)   # в меню теперь ярлык из пакета
            continue
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            f.write(desktop_entry(app_script(), "kachaning"))
        os.chmod(tmp, 0o755)
        os.replace(tmp, p)
        run(["gio", "set", p, "metadata::trusted", "true"])
    if os.path.isdir(USER_DIR):
        shutil.rmtree(USER_DIR, ignore_errors=True)
    units = os.path.expanduser("~/.config/systemd/user/kachaning-notify.service")
    try:
        with open(units) as f:
            stale = app_script() not in f.read()
    except OSError:
        stale = True
    if stale:
        set_notify_timer(load_config()["notify"])


def install():
    if PACKAGED:
        adopt_package()
        print(tr("Качанинг установлен пакетом — обновления приходят через менеджер пакетов."))
        return 0
    os.makedirs(USER_DIR, exist_ok=True)
    dst = os.path.join(USER_DIR, "kachaning.py")
    if os.path.realpath(__file__) != os.path.realpath(dst):
        shutil.copyfile(os.path.realpath(__file__), dst)
    os.chmod(dst, 0o755)
    icon = os.path.join(USER_DIR, "icon.svg")
    with open(icon, "w") as f:
        f.write(ICON_SVG)
    entry = desktop_entry(dst, icon)
    apps = os.path.expanduser("~/.local/share/applications")
    os.makedirs(apps, exist_ok=True)
    paths = [os.path.join(apps, "kachaning.desktop")]
    desk = desktop_dir()
    old = [os.path.join(apps, n) for n in ("tsbridge-host.desktop", "tsbridge-client.desktop")]
    if desk:
        old += [os.path.join(desk, n) for n in ("Удалённая помощь.desktop", "Подключение к другу.desktop",
                                                "Качанинг.desktop", "Kachaning.desktop")
                if n != f"{APP_NAME}.desktop"]
        paths.append(os.path.join(desk, f"{APP_NAME}.desktop"))
    for p in old:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
    for p in paths:
        with open(p, "w") as f:
            f.write(entry)
        os.chmod(p, 0o755)
        run(["gio", "set", p, "metadata::trusted", "true"])

    # старая версия: таймер уведомлений и папка
    units = os.path.expanduser("~/.config/systemd/user")
    run(["systemctl", "--user", "disable", "--now", f"{LEGACY['user_unit']}.timer"])
    for ext in ("timer", "service"):
        try:
            os.remove(os.path.join(units, f"{LEGACY['user_unit']}.{ext}"))
        except FileNotFoundError:
            pass
    if os.path.isdir(LEGACY["user_dir"]):
        shutil.rmtree(LEGACY["user_dir"], ignore_errors=True)

    ok = set_notify_timer(load_config().get("notify", True))
    print(tr("Установлено:"), *paths, sep="\n  ")
    if not ok:
        print(tr("Таймер уведомлений не включился"))
    return 0


# ───────────────────────── оформление ─────────────────────────

def hsl(h, s, l):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, l / 100, s / 100)
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def make_palette(hue, dark):
    """Палитра в духе Material You из одного оттенка."""
    t = hue + 60
    if not dark:
        p = dict(primary=hsl(hue, 40, 32), on_primary="#FFFFFF", primary_c=hsl(hue, 58, 86),
                 on_primary_c=hsl(hue, 80, 10), secondary_c=hsl(hue, 22, 87), on_secondary_c=hsl(hue, 30, 12),
                 tertiary_c=hsl(t, 45, 87), on_tertiary_c=hsl(t, 70, 11),
                 surface=hsl(hue, 30, 97.5), surface_low=hsl(hue, 22, 95), surface_c=hsl(hue, 17, 92.5),
                 surface_high=hsl(hue, 14, 90), surface_highest=hsl(hue, 12, 87.5),
                 on_surface=hsl(hue, 12, 10), on_surface_v=hsl(hue, 8, 28),
                 outline=hsl(hue, 5, 46), outline_v=hsl(hue, 10, 78),
                 error="#BA1A1A", on_error="#FFFFFF", error_c="#FFDAD6", on_error_c="#410002",
                 warn="#7A5900", on_warn="#FFFFFF", warn_c="#FFDEA0", on_warn_c="#261A00")
    else:
        p = dict(primary=hsl(hue, 45, 72), on_primary=hsl(hue, 70, 14), primary_c=hsl(hue, 40, 24),
                 on_primary_c=hsl(hue, 60, 86), secondary_c=hsl(hue, 14, 27), on_secondary_c=hsl(hue, 22, 87),
                 tertiary_c=hsl(t, 35, 25), on_tertiary_c=hsl(t, 45, 87),
                 surface=hsl(hue, 12, 6.5), surface_low=hsl(hue, 10, 10), surface_c=hsl(hue, 10, 12),
                 surface_high=hsl(hue, 9, 15.5), surface_highest=hsl(hue, 8, 19.5),
                 on_surface=hsl(hue, 10, 88), on_surface_v=hsl(hue, 8, 77),
                 outline=hsl(hue, 5, 56), outline_v=hsl(hue, 8, 28),
                 error="#FFB4AB", on_error="#690005", error_c="#93000A", on_error_c="#FFDAD6",
                 warn="#F5BF48", on_warn="#402D00", warn_c="#5C4300", on_warn_c="#FFDEA0")
    p["inverse_surface"], p["inverse_on_surface"] = p["on_surface"], p["surface"]
    return p


CSS = """
.tsb, .tsb * {
  font-family: "Google Sans", "Roboto", "Noto Sans", "Ubuntu", "Cantarell", sans-serif;
  text-shadow: none; -gtk-icon-shadow: none;
}
window.tsb, .tsb scrolledwindow, .tsb viewport, .tsb .page, .tsb .wizard-body {
  background-color: @surface; background-image: none; color: @on_surface; border: none;
}
/* отступы — padding, а не margin: поля вокруг виджета никто не закрашивает */
.tsb .page { padding: 12px 24px 24px 24px; }
.tsb .wizard-body { padding: 28px 64px 20px 64px; }
.tsb headerbar {
  background-color: @surface; background-image: none; border: none; box-shadow: none;
  min-height: 52px; padding: 0 10px;
}
.tsb headerbar .title { font-size: 16px; font-weight: 600; color: @on_surface; }
.tsb headerbar .subtitle { font-size: 12px; color: @on_surface_v; }
.tsb headerbar button {
  background-color: transparent; background-image: none; border: none; box-shadow: none;
  border-radius: 20px; min-width: 34px; min-height: 34px; padding: 0; color: @on_surface_v;
}
.tsb headerbar button:hover { background-color: alpha(@on_surface, 0.08); }
.tsb label { color: inherit; }
.tsb separator { background-color: @outline_v; min-width: 1px; min-height: 1px; }

.rail { background-color: @surface; padding: 10px 6px; }
.tsb button.nav {
  background-color: transparent; background-image: none; border: none; box-shadow: none;
  padding: 4px 0; min-width: 84px; border-radius: 16px; outline: none;
}
.nav-pill { min-width: 56px; min-height: 32px; border-radius: 16px; transition: background-color 180ms ease; }
.tsb button.nav:hover .nav-pill { background-color: alpha(@on_surface_v, 0.10); }
.tsb button.nav:checked .nav-pill { background-color: @secondary_c; }
.tsb button.nav image { color: @on_surface_v; }
.tsb button.nav:checked image { color: @on_secondary_c; }
.tsb label.nav-label { font-size: 12px; font-weight: 500; color: @on_surface_v; }
.tsb button.nav:checked label.nav-label { color: @on_surface; font-weight: 700; }

.tsb label.page-title { font-size: 26px; font-weight: 600; color: @on_surface; margin: 4px 4px 0 4px; }
.tsb label.page-sub { font-size: 13px; color: @on_surface_v; margin: 0 4px 4px 4px; }
.tsb label.section { font-size: 14px; font-weight: 600; color: @primary; margin: 8px 4px 0 4px; }
.tsb label.hint { font-size: 12px; color: @on_surface_v; margin: 0 4px; }

.hero { background-color: @primary_c; color: @on_primary_c; border-radius: 28px; padding: 22px 24px; }
.hero.warn { background-color: @warn_c; color: @on_warn_c; }
.hero.err { background-color: @error_c; color: @on_error_c; }
.hero.run { background-color: @secondary_c; color: @on_secondary_c; }
.hero.info { background-color: @tertiary_c; color: @on_tertiary_c; }
.tsb label.hero-glyph {
  min-width: 60px; min-height: 60px; border-radius: 999px; font-size: 28px; font-weight: 700;
  background-color: @primary; color: @on_primary;
}
.tsb .hero.warn label.hero-glyph { background-color: @warn; color: @on_warn; }
.tsb .hero.err label.hero-glyph { background-color: @error; color: @on_error; }
.tsb .hero.info label.hero-glyph { background-color: @on_tertiary_c; color: @tertiary_c; }
.hero-spin { color: @primary; min-width: 60px; min-height: 60px; }
.tsb label.hero-title { font-size: 22px; font-weight: 600; }
.tsb label.hero-sub { font-size: 13px; }

.tsb button.filled, .tsb button.tonal, .tsb button.text-btn, .tsb button.chip, .tsb button.icon-btn,
.tsb button.outlined {
  background-image: none; box-shadow: none; border: none; text-shadow: none; outline: none;
  transition: background-color 160ms ease, box-shadow 160ms ease;
}
.tsb button.filled { background-color: @primary; border-radius: 20px; min-height: 40px; padding: 0 24px; }
.tsb button.filled label { color: @on_primary; font-weight: 600; }
.tsb button.filled:hover { background-color: mix(@primary, @on_primary, 0.08); box-shadow: 0 1px 3px alpha(black, 0.25); }
.tsb button.filled:active { background-color: mix(@primary, @on_primary, 0.14); }
.tsb button.tonal { background-color: @secondary_c; border-radius: 20px; min-height: 40px; padding: 0 22px; }
.tsb button.tonal label { color: @on_secondary_c; font-weight: 600; }
.tsb button.tonal:hover { background-color: mix(@secondary_c, @on_secondary_c, 0.08); }
.tsb button.tonal:active { background-color: mix(@secondary_c, @on_secondary_c, 0.14); }
.tsb button.outlined { background-color: transparent; border: 1px solid @outline; border-radius: 20px; min-height: 40px; padding: 0 22px; }
.tsb button.outlined label { color: @primary; font-weight: 600; }
.tsb button.outlined:hover { background-color: alpha(@primary, 0.08); }
.tsb button.text-btn { background-color: transparent; border-radius: 18px; min-height: 34px; padding: 0 12px; }
.tsb button.text-btn label { color: @primary; font-weight: 600; }
.tsb button.text-btn:hover { background-color: alpha(@primary, 0.08); }
.tsb button.text-btn:active { background-color: alpha(@primary, 0.14); }
.tsb button.icon-btn { background-color: transparent; border-radius: 18px; min-width: 36px; min-height: 36px; padding: 0; }
.tsb button.icon-btn label, .tsb button.icon-btn image { color: @on_surface_v; font-size: 18px; font-weight: 700; }
.tsb button.icon-btn:hover { background-color: alpha(@on_surface, 0.08); }
.tsb button.small { min-height: 34px; padding: 0 16px; border-radius: 17px; }
.tsb button:disabled { background-color: alpha(@on_surface, 0.10); }
.tsb button.text-btn:disabled, .tsb button.icon-btn:disabled { background-color: transparent; }
.tsb button:disabled label { color: alpha(@on_surface, 0.38); }
.tsb button.chip {
  background-color: transparent; border: 1px solid @outline_v; border-radius: 10px;
  min-height: 34px; padding: 0 14px;
}
.tsb button.chip label { color: @on_surface_v; font-weight: 500; }
.tsb button.chip:hover { background-color: alpha(@on_surface_v, 0.08); }
.tsb button.chip:checked { background-color: @secondary_c; border-color: @secondary_c; }
.tsb button.chip:checked label { color: @on_secondary_c; font-weight: 600; }

.card { background-color: @surface_low; border-radius: 24px; padding: 6px 0; }
.card.pad { padding: 18px 20px; }
.card.inner { background-color: @surface_c; border-radius: 18px; }
.row { padding: 12px 18px; }
.row.sep { border-top: 1px solid alpha(@outline_v, 0.6); }
.tsb label.row-title { font-size: 14px; font-weight: 500; color: @on_surface; }
.tsb label.row-detail { font-size: 12px; color: @on_surface_v; }
.tsb label.conn-title { font-size: 17px; font-weight: 600; color: @on_surface; }
.tsb label.badge { min-width: 34px; min-height: 34px; border-radius: 999px; font-size: 15px; font-weight: 700; }
.tsb label.badge.b-ok { background-color: @primary_c; color: @on_primary_c; }
.tsb label.badge.b-warn { background-color: @warn_c; color: @on_warn_c; }
.tsb label.badge.b-err { background-color: @error_c; color: @on_error_c; }
.tsb label.badge.b-info { background-color: @tertiary_c; color: @on_tertiary_c; }
.tsb label.badge.b-skip, .tsb label.badge.b-run { background-color: @surface_highest; color: @on_surface_v; }
.tsb label.pill { border-radius: 10px; padding: 3px 10px; font-size: 12px; font-weight: 600; }
.tsb label.pill.p-ok { background-color: @primary_c; color: @on_primary_c; }
.tsb label.pill.p-warn { background-color: @warn_c; color: @on_warn_c; }
.tsb label.pill.p-err { background-color: @error_c; color: @on_error_c; }
.tsb label.pill.p-info, .tsb label.pill.p-run, .tsb label.pill.p-skip { background-color: @surface_highest; color: @on_surface_v; }
.tsb label.dot-on { color: @primary; font-size: 15px; }
.tsb label.dot-off { color: @outline; font-size: 15px; }
.tsb spinner { color: @primary; }
.tsb label.code {
  font-family: "JetBrains Mono", "Ubuntu Mono", "DejaVu Sans Mono", monospace; font-size: 12px;
  background-color: @surface_highest; color: @on_surface; border-radius: 12px; padding: 12px 14px;
}

.tsb entry {
  background-color: @surface_highest; background-image: none; color: @on_surface; border: none;
  border-bottom: 2px solid @outline; border-radius: 10px 10px 2px 2px; min-height: 42px;
  padding: 0 12px; box-shadow: none; caret-color: @primary;
}
.tsb entry:focus { border-bottom-color: @primary; }
.tsb entry selection { background-color: @primary_c; color: @on_primary_c; }
.tsb combobox button, .tsb combobox button.combo {
  background-color: @surface_highest; background-image: none; border: none; box-shadow: none;
  border-radius: 10px; min-height: 40px; padding: 0 12px; color: @on_surface;
}
.tsb combobox button label, .tsb combobox arrow { color: @on_surface; }
.tsb switch {
  background-color: @surface_highest; background-image: none; border: 2px solid @outline;
  border-radius: 16px; min-width: 48px; min-height: 26px; box-shadow: none; color: transparent; font-size: 0;
}
.tsb switch:checked { background-color: @primary; border-color: @primary; }
.tsb switch slider {
  background-color: @outline; background-image: none; border: none; box-shadow: none;
  border-radius: 12px; min-width: 18px; min-height: 18px; margin: 3px;
}
.tsb switch:checked slider { background-color: @on_primary; }
.tsb switch:disabled { opacity: 0.4; }

.tsb expander title > arrow { color: @on_surface_v; }
.tsb expander title > label { color: @on_surface_v; font-weight: 500; }
.logbox { background-color: @surface_c; border-radius: 16px; padding: 8px; }
.tsb .logbox scrolledwindow, .tsb .logbox viewport,
.logbox textview, .logbox textview text {
  background-color: @surface_c; color: @on_surface_v;
  font-family: "JetBrains Mono", "Ubuntu Mono", "DejaVu Sans Mono", monospace; font-size: 11px;
}

.snackbar {
  background-color: @inverse_surface; border-radius: 12px; padding: 12px 18px; margin: 20px;
  box-shadow: 0 3px 10px alpha(black, 0.35);
}
.tsb .snackbar label { color: @inverse_on_surface; }
.tsb .snackbar spinner { color: @inverse_on_surface; }

.tsb button.swatch {
  min-width: 40px; min-height: 40px; border-radius: 999px; padding: 0;
  border: 3px solid transparent; box-shadow: none; background-image: none; outline: none;
}
.tsb button.swatch:checked { border-color: @on_surface; }
.tsb button.swatch label { color: white; font-size: 18px; font-weight: 700; }
.tsb label.wiz-title { font-size: 30px; font-weight: 600; color: @on_surface; }
.tsb label.wiz-text { font-size: 14px; color: @on_surface_v; }
.tsb label.wiz-dot { color: @outline_v; font-size: 11px; }
.tsb label.wiz-dot.on { color: @primary; }
.tsb label.set-value { font-size: 13px; color: @on_surface_v; }
.tsb .set-row { padding: 14px 18px; }
.set-row.sep { border-top: 1px solid alpha(@outline_v, 0.6); }
.wizard { background-color: @surface; }

menu, .menu, .context-menu {
  background-color: @surface_c; color: @on_surface; border-radius: 10px; padding: 6px 0;
  border: 1px solid @outline_v;
}
menu menuitem { padding: 8px 16px; color: @on_surface; }
menu menuitem:hover { background-color: alpha(@on_surface, 0.08); color: @on_surface; }
menu menuitem label { color: @on_surface; }
"""


def build_css(cfg, dark):
    hue = dict((s, h) for s, _, h in SEEDS).get(cfg["theme"].get("seed"), 125)
    pal = make_palette(hue, dark)
    scale = float(cfg["theme"].get("scale", 1.0))
    body = re.sub(r"font-size: (\d+)px", lambda m: f"font-size: {round(int(m.group(1)) * scale)}px", CSS)
    css = "".join(f"@define-color {k} {v};\n" for k, v in pal.items()) + body
    for sid, _, h in SEEDS:
        css += f".tsb button.swatch.sw-{sid} {{ background-color: {hsl(h, 45, 42)}; }}\n"
    return css


# ───────────────────────── окно ─────────────────────────

Gtk = Gdk = GLib = Pango = None  # заполняются в run_gui


def system_dark():
    if "dark" in os.environ.get("GTK_THEME", "").lower():
        return True
    for cmd in (["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                ["gsettings", "get", "org.cinnamon.desktop.interface", "gtk-theme"],
                ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"]):
        rc, out, _ = run(cmd, timeout=3)
        if rc == 0 and "dark" in out.lower():
            return True
    try:
        with open(os.path.expanduser("~/.config/kdeglobals")) as f:
            if re.search(r"^ColorScheme=.*dark", f.read(), re.M | re.I):
                return True
    except OSError:
        pass
    s = Gtk.Settings.get_default()
    return bool(s and "dark" in (s.props.gtk_theme_name or "").lower())


def open_url(url):
    subprocess.Popen(["xdg-open", url], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


TERMINALS = [("kitty", []), ("alacritty", ["-e"]), ("konsole", ["-e"]), ("foot", []), ("ghostty", ["-e"]),
             ("wezterm", ["start", "--"]), ("gnome-terminal", ["--"]), ("ptyxis", ["--"]),
             ("xfce4-terminal", ["-x"]), ("mate-terminal", ["-x"]), ("tilix", ["-e"]),
             ("x-terminal-emulator", ["-e"]), ("xterm", ["-e"])]


def installed_terminals():
    return [t for t, _ in TERMINALS if shutil.which(t)]


def terminal_cmd(argv, pref=""):
    """Команда, открывающая argv в терминале (pref — выбранный в настройках), или None."""
    for term, prefix in TERMINALS:
        if (not pref or term == pref) and shutil.which(term):
            return [term] + prefix + argv
    return terminal_cmd(argv) if pref else None


def add_cls(w, *names):
    ctx = w.get_style_context()
    for n in names:
        for part in n.split():
            ctx.add_class(part)
    return w


def mk_label(text="", cls=None, xalign=0.0, wrap=True, selectable=False):
    l = Gtk.Label(label=text, xalign=xalign, selectable=selectable)
    if wrap:
        l.set_line_wrap(True)
        l.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if cls:
        add_cls(l, cls)
    return l


def mk_button(label, cls, cb):
    b = Gtk.Button(label=label)
    add_cls(b, cls)
    b.connect("clicked", lambda *_: cb())
    return b


def box(vertical=True, spacing=0, cls=None):
    b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,
                spacing=spacing)
    if cls:
        add_cls(b, cls)
    return b


def clear(container):
    for c in container.get_children():
        c.destroy()


def icon_or_label(name, fallback, size=None):
    theme = Gtk.IconTheme.get_default()
    if theme and theme.has_icon(name):
        img = Gtk.Image.new_from_icon_name(name, size or Gtk.IconSize.LARGE_TOOLBAR)
        return img
    return mk_label(fallback, None, 0.5, False)


GLYPHS = {"ok": "✓", "warn": "!", "err": "✕", "info": "i", "skip": "–", "run": "…"}


def icon_slot(glyph, spin):
    """Место под значок или спиннер: показывается что-то одно, show_all его не трогает."""
    b = box(False, 0)
    b.set_valign(Gtk.Align.CENTER)
    for w in (glyph, spin):
        w.set_no_show_all(True)
        b.pack_start(w, False, False, 0)
    glyph.show()
    return b


class Hero:
    def __init__(self):
        self.box = box(False, 18, "hero")
        self.glyph = mk_label("…", "hero-glyph", 0.5, False)
        self.glyph.set_yalign(0.5)
        self.spin = Gtk.Spinner()
        add_cls(self.spin, "hero-spin")
        self.icon = icon_slot(self.glyph, self.spin)
        v = box(True, 4)
        v.set_valign(Gtk.Align.CENTER)
        self.title = mk_label("", "hero-title")
        self.sub = mk_label("", "hero-sub")
        v.pack_start(self.title, False, False, 0)
        v.pack_start(self.sub, False, False, 0)
        self.end = box(False, 10)
        self.end.set_valign(Gtk.Align.CENTER)
        self.box.pack_start(self.icon, False, False, 0)
        self.box.pack_start(v, True, True, 0)
        self.box.pack_end(self.end, False, False, 0)

    def set(self, state, title, sub=""):
        ctx = self.box.get_style_context()
        for s in ("ok", "warn", "err", "run", "info"):
            ctx.remove_class(s)
        ctx.add_class(state)
        if state == "run":
            self.spin.start()
        else:
            self.spin.stop()
            self.glyph.set_text(GLYPHS[state])
        self.spin.set_visible(state == "run")
        self.glyph.set_visible(state != "run")
        self.title.set_text(title)
        self.sub.set_text(sub or "")
        self.sub.set_visible(bool(sub))


class CheckRow:
    def __init__(self, title, first):
        self.box = box(False, 14, "row")
        if not first:
            add_cls(self.box, "sep")
        self.badge = mk_label("…", "badge b-skip", 0.5, False)
        self.badge.set_yalign(0.5)
        self.spin = Gtk.Spinner()
        self.spin.set_size_request(34, 34)
        self.icon = icon_slot(self.badge, self.spin)
        v = box(True, 2)
        v.set_valign(Gtk.Align.CENTER)
        self.title = mk_label(title, "row-title")
        self.detail = mk_label("", "row-detail")
        v.pack_start(self.title, False, False, 0)
        v.pack_start(self.detail, False, False, 0)
        self.btn = Gtk.Button(label=tr("Исправить"), valign=Gtk.Align.CENTER)
        add_cls(self.btn, "text-btn")
        self.btn.set_no_show_all(True)
        self.box.pack_start(self.icon, False, False, 0)
        self.box.pack_start(v, True, True, 0)
        self.box.pack_end(self.btn, False, False, 0)

    def set(self, state, detail, fix=None):
        ctx = self.badge.get_style_context()
        for s in GLYPHS:
            ctx.remove_class("b-" + s)
        if state == "run":
            self.spin.start()
        else:
            self.spin.stop()
            self.badge.set_text(GLYPHS[state])
            ctx.add_class("b-" + state)
        self.spin.set_visible(state == "run")
        self.badge.set_visible(state != "run")
        self.detail.set_text(detail or "")
        if fix and state != "run":
            self.btn.set_label(FIX_LABELS[fix])
            self.btn.show()
        else:
            self.btn.hide()


class ChecksCard:
    def __init__(self, checks, on_fix, cls="card"):
        self.checks = checks
        self.titles = dict(checks)
        self.box = box(True, 0, cls)
        self.rows = {}
        self.results = {}
        for i, (cid, title) in enumerate(checks):
            r = CheckRow(title, i == 0)
            r.btn.connect("clicked", lambda _b, c=cid: on_fix(c, self.results.get(c, (None, None, None))[2]))
            self.box.pack_start(r.box, False, False, 0)
            self.rows[cid] = r

    def reset(self, text=tr("проверяю…")):
        self.results = {}
        for r in self.rows.values():
            r.set("run", text)

    def set(self, cid, state, detail, fix=None):
        if cid in self.rows:
            self.results[cid] = (state, detail, fix)
            self.rows[cid].set(state, detail, fix)

    def state(self, cid):
        return self.results.get(cid, ("skip", "", None))[0]

    def ids(self, *states):
        return [c for c, _ in self.checks if self.state(c) in states]


class ConnCard:
    """Карточка одного подключения на странице «Подключиться»."""

    def __init__(self, app, conn):
        self.app, self.conn = app, conn
        self.ctx = {}
        self.running = False
        self.alive = True   # False, когда карточку заменили новой (refresh_connect)
        self.box = box(True, 0, "card pad")
        head = box(False, 14)
        self.badge = mk_label("…", "badge b-skip", 0.5, False)
        self.badge.set_valign(Gtk.Align.CENTER)
        v = box(True, 2)
        v.set_valign(Gtk.Align.CENTER)
        v.pack_start(mk_label(conn["name"], "conn-title"), False, False, 0)
        self.sub = mk_label(f"{conn['user']}@{conn['node']}", "row-detail")
        v.pack_start(self.sub, False, False, 0)
        self.term_btn = mk_button(tr("Терминал"), "filled small", self.open_terminal)
        self.term_btn.set_valign(Gtk.Align.CENTER)
        menu_btn = Gtk.MenuButton(valign=Gtk.Align.CENTER)
        menu_btn.add(mk_label("⋮", None, 0.5, False))
        add_cls(menu_btn, "icon-btn")
        menu = Gtk.Menu()
        for label, cb in ((tr("Скопировать команду"), self.copy_cmd), (tr("Изменить"), self.edit),
                          (tr("Удалить"), self.delete)):
            it = Gtk.MenuItem(label=label)
            it.connect("activate", lambda _i, f=cb: f())
            menu.append(it)
        menu.show_all()
        menu_btn.set_popup(menu)
        head.pack_start(self.badge, False, False, 0)
        head.pack_start(v, True, True, 0)
        head.pack_end(menu_btn, False, False, 0)
        head.pack_end(self.term_btn, False, False, 0)
        self.box.pack_start(head, False, False, 0)

        self.summary = mk_label("", "row-detail")
        self.summary.set_margin_top(10)
        self.box.pack_start(self.summary, False, False, 0)
        foot = box(False, 4)
        foot.set_margin_top(6)
        self.check_btn = mk_button(tr("Проверить"), "text-btn", self.run_checks)
        self.more_btn = mk_button(tr("Подробнее"), "text-btn", self.toggle)
        foot.pack_start(self.check_btn, False, False, 0)
        foot.pack_start(self.more_btn, False, False, 0)
        self.box.pack_start(foot, False, False, 0)
        self.checks = ChecksCard(CONN_CHECKS, self.on_fix, "card inner")
        self.rev = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.checks.box.set_margin_top(8)
        self.rev.add(self.checks.box)
        self.box.pack_start(self.rev, False, False, 0)

    def toggle(self):
        show = not self.rev.get_reveal_child()
        self.rev.set_reveal_child(show)
        self.more_btn.set_label(tr("Скрыть") if show else tr("Подробнее"))

    def set_badge(self, state):
        ctx = self.badge.get_style_context()
        for s in GLYPHS:
            ctx.remove_class("b-" + s)
        ctx.add_class("b-" + state)
        self.badge.set_text(GLYPHS[state])

    def run_checks(self):
        if self.running:
            return
        self.running = True
        self.ctx = {}
        self.checks.reset()
        self.set_badge("run")
        self.summary.set_text(tr("Проверяю…"))

        def work():
            try:
                for r in conn_checks(self.conn, self.ctx):
                    GLib.idle_add(lambda r=r: self.alive and self.checks.set(*r) and False)
            except Exception as e:
                GLib.idle_add(self.app.log, tr("Ошибка проверки: {0}: {1}").format(type(e).__name__, e))
            GLib.idle_add(self.done)

        threading.Thread(target=work, daemon=True).start()

    def done(self):
        self.running = False
        if not self.alive:
            return False
        c = self.checks
        where = self.ctx.get("ip", "")
        if self.ctx.get("route"):
            where += f" · {self.ctx['route']}"
        if c.state("auth") == "ok" and self.ctx.get("sudo"):
            self.set_badge("ok")
            self.summary.set_text(tr("Можно подключаться, права администратора есть · {0}").format(where))
        elif c.state("auth") == "ok":
            self.set_badge("ok")
            self.summary.set_text(tr("Можно подключаться, без прав администратора · {0}").format(where))
        else:
            errs = c.ids("err")
            self.set_badge("err" if errs else "warn")
            if errs:
                self.summary.set_text(f"{c.titles[errs[0]]}: {c.results[errs[0]][1]}")
                if not self.rev.get_reveal_child():
                    self.toggle()
            else:
                self.summary.set_text(tr("Есть замечания"))
        if self.app.cfg["auto_alias"] and self.ctx.get("alias_missing") and c.state("auth") == "ok":
            self.fix_alias(quiet=True)
        return False

    def on_fix(self, cid, fix):
        if fix == "hostkey":
            for h in filter(None, (self.ctx.get("ip"), self.conn.get("alias"), self.conn["node"])):
                run(["ssh-keygen", "-R", h])
            self.app.toast(tr("Старый ключ сервера удалён"))
            self.run_checks()
        elif fix == "alias":
            self.fix_alias()
        elif fix == "copycode":
            self.app.copy_helper_code()
        elif fix == "admin":
            self.app.show_share_help()
        elif fix == "net":
            self.app.goto("net")

    def fix_alias(self, quiet=False):
        ip = self.ctx.get("ip")
        if not ip:
            return
        alias = self.conn.get("alias") or alias_for(self.conn["node"])
        try:
            write_ssh_alias(alias, ip, self.conn["user"])
        except (OSError, ValueError) as e:
            self.app.log(f"~/.ssh/config: {e}")
            if not quiet:
                self.app.toast(tr("Не удалось записать ~/.ssh/config: {0}").format(e))
            return
        self.checks.set("alias", "ok", f"ssh {alias}")
        self.ctx["alias_ok"] = True
        if not quiet:
            self.app.toast(tr("Теперь можно просто: ssh {0}").format(alias))

    def ssh_args(self):
        alias = self.conn.get("alias") or alias_for(self.conn["node"])
        ip = self.ctx.get("ip")
        if ip and ssh_config_hostname(alias) == ip:
            return [alias]
        return ["-i", CLIENT_KEY, f"{self.conn['user']}@{ip or self.conn['node']}"]

    def open_terminal(self):
        cmd = terminal_cmd(["ssh"] + self.ssh_args(), self.app.cfg["terminal"])
        if not cmd:
            self.copy_cmd()
            self.app.toast(tr("Терминал не найден — команда скопирована"))
            return
        subprocess.Popen(cmd, start_new_session=True)
        self.app.log(tr("Открыт терминал: ") + " ".join(cmd))

    def copy_cmd(self):
        text = " ".join(shlex.quote(a) for a in ["ssh"] + self.ssh_args())
        self.app.copy(text, tr("Команда скопирована"))

    def edit(self):
        self.app.connection_dialog(edit=self.conn)

    def delete(self):
        if self.app.confirm(tr("Удалить подключение «{0}»?").format(self.conn['name']),
                            tr("Ключи и настройки у друга не изменятся.")):
            self.app.cfg["connections"] = [c for c in self.app.cfg["connections"] if c["id"] != self.conn["id"]]
            save_config(self.app.cfg)
            self.app.refresh_connect()


class App:
    PAGES = [("net", tr("Сеть"), "network-workgroup-symbolic", "◎"),
             ("connect", tr("Подключиться"), "utilities-terminal-symbolic", "›_"),
             ("host", tr("Принимать"), "system-users-symbolic", "⌂"),
             ("settings", tr("Настройки"), "emblem-system-symbolic", "⚙")]

    def __init__(self, start_page=None, force_wizard=False):
        self.cfg = load_config()
        self.busy = False
        self.opened_urls = set()
        self.loading = {}
        self.conn_cards = []
        self.st = None
        self.periodic_id = None
        self.duration_groups = {}
        self.ts_pref_switches = {}
        self.logbuf = Gtk.TextBuffer()
        self.provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), self.provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        self.sys_dark = system_dark()
        self.apply_theme()

        offscreen = bool(os.environ.get("KACH_SNAPSHOT"))
        self.win = Gtk.OffscreenWindow() if offscreen else Gtk.Window()
        add_cls(self.win, "tsb")
        if offscreen:
            self.win.set_size_request(1000, int(os.environ.get("KACH_HEIGHT", "820")))
        else:
            self.win.set_default_size(1000, 780)
        self.win.set_title(APP_NAME)
        icon = os.path.join(USER_DIR, "icon.svg")
        if PACKAGED:
            self.win.set_icon_name("kachaning")
        elif os.path.exists(icon):
            self.win.set_icon_from_file(icon)
        if PACKAGED and not os.environ.get("KACH_SNAPSHOT"):
            self.bg(adopt_package)
        self.win.connect("destroy", Gtk.main_quit)

        hb = Gtk.HeaderBar(show_close_button=True)
        hb.set_title(APP_NAME)
        self.hb = hb
        self.refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        self.refresh_btn.set_tooltip_text(tr("Обновить"))
        self.refresh_btn.connect("clicked", lambda *_: self.refresh_current())
        hb.pack_end(self.refresh_btn)
        if not offscreen:
            self.win.set_titlebar(hb)

        overlay = Gtk.Overlay()
        self.win.add(overlay)
        self.top = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=250)
        overlay.add(self.top)

        self.snack_rev = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_UP,
                                      halign=Gtk.Align.CENTER, valign=Gtk.Align.END)
        sb = box(False, 12, "snackbar")
        self.snack_spin = Gtk.Spinner()
        self.snack_spin.set_no_show_all(True)
        self.snack_label = mk_label("", None, 0, True)
        self.snack_label.set_max_width_chars(70)
        sb.pack_start(self.snack_spin, False, False, 0)
        sb.pack_start(self.snack_label, True, True, 0)
        self.snack_rev.add(sb)
        overlay.add_overlay(self.snack_rev)
        self.snack_timer = None

        self.top.add_named(self.build_main(), "main")
        self.win.show_all()
        if force_wizard or not self.cfg.get("wizard_done"):
            self.start_wizard()
        else:
            self.goto(start_page or self.first_page())
        self.schedule_periodic()

    # ── оформление ──

    def is_dark(self):
        mode = self.cfg["theme"].get("mode", "auto")
        return self.sys_dark if mode == "auto" else mode == "dark"

    def apply_theme(self):
        dark = self.is_dark()
        self.provider.load_from_data(build_css(self.cfg, dark).encode())
        gs = Gtk.Settings.get_default()
        gs.props.gtk_application_prefer_dark_theme = dark
        gs.props.gtk_enable_animations = self.cfg["theme"]["animations"]

    def set_theme(self, **kw):
        self.cfg["theme"].update(kw)
        save_config(self.cfg)
        self.apply_theme()

    def theme_picker(self):
        """Цвета и режим темы — общий виджет для мастера и настроек."""
        v = box(True, 12)
        sw = box(False, 10)
        group = None
        for sid, name, _ in SEEDS:
            rb = Gtk.RadioButton.new_from_widget(group)
            group = group or rb
            rb.set_mode(False)
            rb.set_tooltip_text(name)
            add_cls(rb, f"swatch sw-{sid}")
            mark = Gtk.Label(label="")
            rb.add(mark)
            rb.set_active(self.cfg["theme"].get("seed") == sid)
            mark.set_text("✓" if rb.get_active() else "")

            def toggled(b, s=sid, m=mark):
                m.set_text("✓" if b.get_active() else "")
                if b.get_active():
                    self.set_theme(seed=s)
            rb.connect("toggled", toggled)
            sw.pack_start(rb, False, False, 0)
        v.pack_start(sw, False, False, 0)
        v.pack_start(self.chips(MODES, self.cfg["theme"].get("mode", "auto"),
                                lambda m: self.set_theme(mode=m)), False, False, 0)
        return v

    def chips(self, items, current, on_change, registry=None):
        b = box(False, 8)
        group = None
        buttons = {}
        for value, label in items:
            rb = Gtk.RadioButton.new_with_label_from_widget(group, label)
            group = group or rb
            rb.set_mode(False)
            add_cls(rb, "chip")
            rb.set_active(value == current)
            rb.connect("toggled", lambda r, v=value: r.get_active() and on_change(v))
            b.pack_start(rb, False, False, 0)
            buttons[value] = rb
        if registry is not None:
            registry.update(buttons)
        return b

    # ── каркас ──

    def build_main(self):
        main = box(False, 0)
        rail = box(True, 4, "rail")
        self.nav = {}
        group = None
        for pid, label, icon, fallback in self.PAGES:
            rb = Gtk.RadioButton.new_from_widget(group)
            group = group or rb
            rb.set_mode(False)
            add_cls(rb, "nav")
            v = box(True, 4)
            pill = box(False, 0, "nav-pill")
            ic = icon_or_label(icon, fallback, Gtk.IconSize.LARGE_TOOLBAR)
            ic.set_halign(Gtk.Align.CENTER)
            pill.pack_start(ic, True, True, 0)
            pill.set_halign(Gtk.Align.CENTER)
            v.pack_start(pill, False, False, 0)
            v.pack_start(mk_label(label, "nav-label", 0.5, False), False, False, 0)
            rb.add(v)
            rb.connect("toggled", lambda r, p=pid: r.get_active() and self.goto(p))
            rail.pack_start(rb, False, False, 0)
            self.nav[pid] = rb
        rail.set_hexpand(False)
        main.pack_start(rail, False, False, 0)
        self.pages = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=180)
        self.pages.add_named(self.build_net(), "net")
        self.pages.add_named(self.build_connect(), "connect")
        self.pages.add_named(self.build_host(), "host")
        self.pages.add_named(self.build_settings(), "settings")
        main.pack_start(self.pages, True, True, 0)
        return main

    def page(self, title, sub):
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        outer = box(True, 14, "page")
        outer.pack_start(mk_label(title, "page-title"), False, False, 0)
        if sub:
            outer.pack_start(mk_label(sub, "page-sub"), False, False, 0)
        sc.add(outer)
        return sc, outer

    def section(self, text, end=None):
        if not end:
            return mk_label(text, "section")
        b = box(False, 8)
        b.pack_start(mk_label(text, "section"), True, True, 0)
        end.set_valign(Gtk.Align.END)
        b.pack_end(end, False, False, 0)
        return b

    def first_page(self):
        sp = self.cfg["start_page"]
        if sp == "last" and self.cfg["last_page"] in self.nav:
            return self.cfg["last_page"]
        if sp in self.nav:
            return sp
        return "connect" if self.cfg["connections"] else "host"

    def goto(self, pid):
        self.top.set_visible_child_name("main")
        if not self.nav[pid].get_active():
            self.nav[pid].set_active(True)
            return
        self.pages.set_visible_child_name(pid)
        self.hb.set_subtitle(dict((p, l) for p, l, _, _ in self.PAGES)[pid])
        if self.cfg["start_page"] == "last" and self.cfg["last_page"] != pid:
            self.cfg["last_page"] = pid
            save_config(self.cfg)
        self.refresh_page(pid)

    def refresh_current(self):
        if self.top.get_visible_child_name() == "main":
            self.refresh_page(self.pages.get_visible_child_name())
        elif hasattr(self, "wiz_refresh"):
            self.wiz_refresh()

    def refresh_page(self, pid, quiet=False):
        {"net": self.refresh_net, "connect": self.refresh_connect,
         "host": self.refresh_host, "settings": self.refresh_settings}[pid](quiet=quiet)

    def schedule_periodic(self):
        if self.periodic_id:
            GLib.source_remove(self.periodic_id)
            self.periodic_id = None
        if self.cfg["refresh"]:
            self.periodic_id = GLib.timeout_add_seconds(self.cfg["refresh"], self.periodic)

    def periodic(self):
        if not self.busy and self.win.is_active() and self.top.get_visible_child_name() == "main":
            pid = self.pages.get_visible_child_name()
            if pid in ("net", "host"):
                self.refresh_page(pid, quiet=True)
        return True

    # ── общие мелочи ──

    def log(self, text):
        self.logbuf.insert(self.logbuf.get_end_iter(), time.strftime("%H:%M:%S  ") + text + "\n")
        return False

    def toast(self, text, persistent=False):
        self.snack_label.set_text(text)
        self.snack_spin.set_visible(persistent)
        if persistent:
            self.snack_spin.start()
        else:
            self.snack_spin.stop()
        self.snack_rev.set_reveal_child(True)
        if self.snack_timer:
            GLib.source_remove(self.snack_timer)
            self.snack_timer = None
        if not persistent:
            self.snack_timer = GLib.timeout_add_seconds(5, self.hide_toast)
        return False

    def hide_toast(self):
        self.snack_timer = None
        self.snack_rev.set_reveal_child(False)
        return False

    def copy(self, text, note=tr("Скопировано")):
        cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        cb.set_text(text, -1)
        cb.store()
        self.toast(note)

    def bg(self, work, done=None):
        """work() в фоне, done(результат) — в главном потоке."""
        def runner():
            try:
                res = work()
            except Exception as e:
                res = e
                GLib.idle_add(self.log, tr("Ошибка: {0}: {1}").format(type(e).__name__, e))
            if done:
                GLib.idle_add(lambda: done(res) and False)
        threading.Thread(target=runner, daemon=True).start()

    def dialog(self, title):
        d = Gtk.Dialog(transient_for=self.win, modal=True, use_header_bar=True)
        add_cls(d, "tsb")
        d.set_title(title)
        d.set_default_size(520, -1)
        area = d.get_content_area()
        area.set_spacing(12)
        for side in ("top", "bottom", "start", "end"):
            getattr(area, f"set_margin_{side}")(20)
        return d, area

    def styled_dialog_buttons(self, d, cancel, ok):
        b1 = d.add_button(cancel, Gtk.ResponseType.CANCEL)
        add_cls(b1, "text-btn")
        b2 = d.add_button(ok, Gtk.ResponseType.OK)
        add_cls(b2, "filled small")
        d.set_default_response(Gtk.ResponseType.OK)

    def message(self, title, text):
        d, area = self.dialog(title)
        area.pack_start(mk_label(text, "wiz-text"), False, False, 0)
        b = d.add_button(tr("Понятно"), Gtk.ResponseType.OK)
        add_cls(b, "filled small")
        d.show_all()
        d.run()
        d.destroy()

    def confirm(self, title, text):
        d, area = self.dialog(title)
        area.pack_start(mk_label(text, "wiz-text"), False, False, 0)
        self.styled_dialog_buttons(d, tr("Отмена"), tr("Да"))
        d.show_all()
        ok = d.run() == Gtk.ResponseType.OK
        d.destroy()
        return ok

    def show_share_help(self):
        self.message(
            tr("Если у вас разные аккаунты Tailscale"),
            tr("Компьютер друга появится у тебя в Tailscale, только когда он им поделится:\n\n"
            "1. Друг открывает админ-панель Tailscale (кнопка в «Сеть»).\n"
            "2. Находит свой компьютер → «⋯» → «Share…» и отправляет тебе ссылку-приглашение.\n"
            "3. Ты открываешь ссылку и принимаешь приглашение.\n\n"
            "Если вы в одном аккаунте Tailscale, делать ничего не нужно."))
        open_url(ADMIN_URL)

    def show_noexpiry(self):
        self.message(
            tr("Ключ без срока"),
            tr("Tailscale раз в несколько месяцев требует войти заново — тогда связь пропадает.\n\nЧтобы этого не было, отключи срок ключа:\n1. Откроется админ-панель Tailscale — войди в свой аккаунт.\n2. Найди в списке «{0}».\n3. Нажми «⋯» справа → «Disable key expiry».\n\nПока срок не отключён, Качанинг предупредит за {1} до конца.").format(self_node(self.st, False), fmt_span(WARN_DAYS * 86400)))
        open_url(ADMIN_URL)

    # ── root и вход в Tailscale ──

    def set_busy(self, busy):
        self.busy = busy
        for w in self.busy_widgets():
            w.set_sensitive(not busy)

    def busy_widgets(self):
        return [self.refresh_btn] + getattr(self, "action_widgets", [])

    def root(self, args, title, on_done=None):
        if self.busy:
            self.toast(tr("Подожди, предыдущее действие ещё выполняется"))
            return
        self.set_busy(True)
        self.toast(title, persistent=True)
        self.log(f"{title} (pkexec {' '.join(args)})")

        def worker():
            rc = self._root_worker(args)
            GLib.idle_add(self._root_done, rc, on_done)

        threading.Thread(target=worker, daemon=True).start()

    def _root_worker(self, args):
        script = os.path.realpath(__file__)
        lines = []
        try:
            p = subprocess.Popen(["pkexec", root_python(), "-I", script, "--lang", LANG, "--root", *args],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                line = line.rstrip("\n")
                lines.append(line)
                GLib.idle_add(self._root_line, line)
            rc = p.wait()
        except FileNotFoundError:
            rc = 127
            lines.append(tr("pkexec не найден"))
        text = "\n".join(lines).lower()
        if rc in (126, 127) and not any(l.startswith("STEP") for l in lines):
            if "authentication agent" in text or tr("pkexec не найден") in text or "no session" in text:
                GLib.idle_add(self.log, tr("Окно пароля недоступно — открываю терминал с sudo"))
                inner = " ".join(shlex.quote(a) for a in ["sudo", root_python(), "-I", script, "--lang", LANG, "--root", *args])
                cmd = terminal_cmd(["bash", "-c", inner + tr("; echo; read -rp 'Готово. Нажми Enter…'")],
                                   self.cfg["terminal"])
                rc = subprocess.call(cmd) if cmd else 127
                # многие терминалы возвращаются сразу — код ничего не говорит об успехе
                GLib.idle_add(self.log, tr("Проверь результат в окне терминала") if cmd else tr("Терминал не найден"))
            else:
                GLib.idle_add(self.log, tr("Пароль не введён или не принят — ничего не изменено"))
                rc = 126
        return rc

    def _root_line(self, line):
        parts = line.split("\t")
        kind = parts[0]
        if kind == "STEP" and len(parts) >= 4:
            sid, state, msg = parts[1], parts[2], parts[3]
            label = dict(HOST_CHECKS).get(sid) or STEP_NAMES.get(sid, sid)
            if self.host_checks and sid in self.host_checks.rows:
                self.host_checks.set(sid, state, msg or tr("выполняю…"))
            if state == "run":
                self.toast(f"{label}…", persistent=True)
            else:
                self.log(f"{label}: {msg}")
        elif kind == "URL" and len(parts) >= 2:
            self.handle_url(parts[1])
        elif kind == "LOG":
            self.log(parts[1] if len(parts) > 1 else "")
        elif kind != "DONE":
            self.log(line)
        return False

    def _root_done(self, rc, on_done):
        self.set_busy(False)
        if rc == 0:
            self.toast(tr("Готово"))
        elif rc == 126:
            self.toast(tr("Пароль не введён — ничего не изменено"))
        else:
            self.toast(tr("Сделано не всё — подробности в «Настройки» → «Журнал»"))
        self.log(tr("Готово") if rc == 0 else tr("Завершено с кодом {0}").format(rc))
        if on_done:
            on_done(rc)
        else:
            self.refresh_current()
        return False

    def handle_url(self, url):
        if not AUTH_RE.fullmatch(url or ""):
            self.log(tr("Пропускаю неожиданную ссылку: {0}").format(url))
            return False
        if url in self.opened_urls:
            return False
        self.opened_urls.add(url)
        open_url(url)
        self.log(tr("Открыл страницу входа: ") + url)
        self.toast(tr("Открылась страница входа Tailscale — войди в аккаунт, программа подождёт"), persistent=True)
        return False

    def do_login(self, force, on_done=None):
        if self.busy:
            return
        self.set_busy(True)
        self.toast(tr("Вход в Tailscale…"), persistent=True)

        def on_line(line):
            GLib.idle_add(self.log, line)
            m = AUTH_RE.search(line)
            if m:
                GLib.idle_add(self.handle_url, m.group(0))

        def worker():
            rc, text = tailscale_up(force, on_line)
            low = text.lower()
            if rc != 0 and ("access denied" in low or "permission denied" in low):
                GLib.idle_add(self.log, tr("Нужны права администратора — запрашиваю пароль"))
                rc = self._root_worker(["login"] + (["--force"] if force else []))
            GLib.idle_add(self._root_done, rc, on_done)

        threading.Thread(target=worker, daemon=True).start()

    def ts_cmd(self, args, done=None, retried=False):
        """Команда tailscale; если не хватает прав — один раз делает пользователя оператором."""
        def after(res):
            rc, out, err = res
            text = (out + "\n" + err).strip()
            if rc != 0 and "access denied" in text.lower() and not retried:
                self.root(["operator"], tr("Разрешаю управлять Tailscale без пароля…"),
                          on_done=lambda rc2: rc2 == 0 and self.ts_cmd(args, done, True))
                return
            if done:
                done(rc, text)
        self.bg(lambda: run(["tailscale", *args], timeout=120), after)

    # ── «Сеть» ──

    def build_net(self):
        sc, v = self.page(tr("Сеть"), tr("Tailscale связывает компьютеры напрямую, где бы они ни были"))
        self.net_hero = Hero()
        self.ts_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.ts_switch_guard = False
        self.ts_switch.connect("notify::active", self.on_ts_switch)
        self.net_action = mk_button("", "filled", lambda: None)
        self.net_action.set_no_show_all(True)
        self.net_action_cb = None
        self.net_action.connect("clicked", lambda *_: self.net_action_cb and self.net_action_cb())
        self.net_hero.end.pack_start(self.net_action, False, False, 0)
        self.net_hero.end.pack_start(self.ts_switch, False, False, 0)
        v.pack_start(self.net_hero.box, False, False, 0)

        acts = box(False, 4)
        self.renew_btn = mk_button(tr("Продлить ключ"), "text-btn", lambda: self.do_login(True))
        acts.pack_start(self.renew_btn, False, False, 0)
        acts.pack_start(mk_button(tr("Ключ без срока"), "text-btn", self.show_noexpiry), False, False, 0)
        acts.pack_start(mk_button(tr("Админ-панель"), "text-btn", lambda: open_url(ADMIN_URL)), False, False, 0)
        acts.pack_start(mk_button(tr("Забрать файлы"), "text-btn", self.taildrop_get), False, False, 0)
        v.pack_start(acts, False, False, 0)

        info = box(True, 0, "card")
        self.info_rows = {}
        for i, (key, title) in enumerate((("account", tr("Аккаунт")), ("addr", tr("Мой адрес")),
                                          ("expiry", tr("Срок ключа")), ("exit", tr("Выходной узел")))):
            r = box(False, 14, "row")
            if i:
                add_cls(r, "sep")
            t = box(True, 2)
            t.pack_start(mk_label(title, "row-title"), False, False, 0)
            d = mk_label("—", "row-detail")
            t.pack_start(d, False, False, 0)
            r.pack_start(t, True, True, 0)
            end = box(False, 4)
            end.set_valign(Gtk.Align.CENTER)
            r.pack_end(end, False, False, 0)
            info.pack_start(r, False, False, 0)
            self.info_rows[key] = (d, end)
        v.pack_start(info, False, False, 0)

        v.pack_start(self.section(tr("Устройства")), False, False, 0)
        self.dev_list = box(True, 0, "card")
        v.pack_start(self.dev_list, False, False, 0)
        v.pack_start(mk_label(tr("«Подключиться» добавляет устройство в твои подключения. "
                              "Taildrop (отправка файлов) работает только между твоими устройствами."),
                              "hint"), False, False, 0)
        return sc

    def on_ts_switch(self, sw, _p):
        if self.ts_switch_guard:
            return
        if self.busy:
            self.set_switch(not sw.get_active())
            self.toast(tr("Подожди, предыдущее действие ещё выполняется"))
            return
        if sw.get_active():
            self.do_login(False, on_done=lambda rc: self.refresh_net())
        else:
            self.ts_cmd(["down"], lambda rc, t: (self.toast(tr("Tailscale выключен") if rc == 0 else t),
                                                 self.refresh_net()))

    def set_switch(self, active, sensitive=True):
        self.ts_switch_guard = True
        self.ts_switch.set_active(active)
        self.ts_switch.set_sensitive(sensitive)
        self.ts_switch_guard = False

    def set_net_action(self, label, cb):
        if label:
            self.net_action.set_label(label)
            self.net_action_cb = cb
            self.net_action.show()
        else:
            self.net_action.hide()

    def refresh_net(self, quiet=False):
        if self.loading.get("net"):
            return
        self.loading["net"] = True
        if not quiet:
            self.net_hero.set("run", tr("Проверяю Tailscale…"))

        def work():
            st, err = ts_status()
            return st, err, ts_profiles() if st else [], bool(shutil.which("tailscale"))

        self.bg(work, self.fill_net)

    def fill_net(self, res):
        self.loading["net"] = False
        if isinstance(res, Exception):
            return
        st, err, profiles, installed = res
        self.st = st
        d = {k: v[0] for k, v in self.info_rows.items()}
        ends = {k: v[1] for k, v in self.info_rows.items()}
        for e in ends.values():
            clear(e)
        for lbl in d.values():
            lbl.set_text("—")
        clear(self.dev_list)
        self.renew_btn.hide()
        if not installed:
            self.net_hero.set("err", tr("Tailscale не установлен"), tr("Установлю его сам — понадобится пароль."))
            self.set_net_action(tr("Установить"), lambda: self.root(["setup-ts", "--login"], tr("Устанавливаю Tailscale…")))
            self.set_switch(False, False)
            return
        if st is None:
            self.net_hero.set("err", tr("Служба Tailscale не работает"), err)
            self.set_net_action(tr("Запустить"), lambda: self.root(["setup-ts"], tr("Запускаю Tailscale…")))
            self.set_switch(False, False)
            return
        bs = st.get("BackendState")
        me = st.get("Self") or {}
        tailnet = (st.get("CurrentTailnet") or {}).get("Name", "")
        if bs == "Running":
            self.net_hero.set("ok", tr("Подключено"), f"{me.get('HostName')} · {first_ip(me)}"
                              + (f" · {tailnet}" if tailnet else ""))
            self.set_net_action(None, None)
            self.set_switch(True)
        elif bs == "Stopped":
            self.net_hero.set("warn", tr("Tailscale выключен"), tr("Включи переключатель, чтобы подключиться."))
            self.set_net_action(None, None)
            self.set_switch(False)
        elif bs == "NeedsLogin":
            self.net_hero.set("warn", tr("Нужно войти"), BACKEND_TEXT[bs])
            self.set_net_action(tr("Войти"), lambda: self.do_login(False))
            self.set_switch(False, False)
        else:
            self.net_hero.set("info", BACKEND_TEXT.get(bs, bs), "")
            self.set_net_action(tr("Админ-панель"), lambda: open_url(ADMIN_URL))
            self.set_switch(False, False)

        cur = next((p for p in profiles if p["current"]), None)
        d["account"].set_text(cur["account"] + (f" · {cur['tailnet']}" if cur and cur["tailnet"] != cur["account"]
                                                 else "") if cur else (tailnet or "—"))
        if len(profiles) > 1:
            mb = Gtk.MenuButton(label=tr("Сменить"))
            add_cls(mb, "text-btn")
            menu = Gtk.Menu()
            for p in profiles:
                it = Gtk.MenuItem(label=("✓ " if p["current"] else "    ") + p["account"])
                it.connect("activate", lambda _i, pid=p["id"]: self.ts_cmd(
                    ["switch", pid], lambda rc, t: (self.toast(tr("Аккаунт сменён") if rc == 0 else t),
                                                    self.refresh_net())))
                menu.append(it)
            menu.show_all()
            mb.set_popup(menu)
            ends["account"].pack_start(mb, False, False, 0)
        ip = first_ip(me) if me else "—"
        d["addr"].set_text(f"{ip} · {me.get('DNSName', '').rstrip('.')}" if me else "—")
        if me:
            ends["addr"].pack_start(mk_button(tr("Копировать"), "text-btn", lambda: self.copy(ip, tr("Скопировано: {0}").format(ip))),
                                    False, False, 0)
        if me.get("KeyExpiry") or bs == "Running":
            state, detail, fix = key_expiry_result(me)
            d["expiry"].set_text(detail)
            if fix == "renew":
                ends["expiry"].pack_start(mk_button(tr("Продлить"), "tonal small", lambda: self.do_login(True)),
                                          False, False, 0)
            elif fix == "noexpiry":
                ends["expiry"].pack_start(mk_button(tr("Навсегда"), "text-btn", self.show_noexpiry), False, False, 0)
        else:
            d["expiry"].set_text("—")
        self.renew_btn.set_visible(bs == "Running" and bool(parse_ts_time(me.get("KeyExpiry"))))

        exits = [p for p in peers(st) if p.get("ExitNodeOption")]
        current_exit = next((p for p in exits if p.get("ExitNode")), None)
        d["exit"].set_text(tr("через {0}").format(current_exit.get('HostName')) if current_exit else
                           (tr("не используется") if exits else tr("нет доступных узлов")))
        if exits:
            combo = Gtk.ComboBoxText()
            combo.append("", tr("Не использовать"))
            for p in exits:
                combo.append(first_ip(p), p.get("HostName"))
            combo.set_active_id(first_ip(current_exit) if current_exit else "")
            combo.connect("changed", lambda c: self.ts_cmd(
                ["set", f"--exit-node={c.get_active_id() or ''}"],
                lambda rc, t: (self.toast(tr("Выходной узел изменён") if rc == 0 else t), self.refresh_net(True))))
            ends["exit"].pack_start(combo, False, False, 0)

        plist = sorted(peers(st), key=lambda p: (not p.get("Online"), p.get("HostName", "").lower()))
        if not plist:
            r = box(False, 0, "row")
            r.pack_start(mk_label(tr("Других устройств пока нет. Поставь Tailscale на второй компьютер "
                                  "или попроси друга поделиться своим."), "row-detail"), True, True, 0)
            self.dev_list.pack_start(r, False, False, 0)
        for i, p in enumerate(plist):
            self.dev_list.pack_start(self.device_row(p, i == 0), False, False, 0)
        self.dev_list.show_all()
        for e in ends.values():
            e.show_all()

    def device_row(self, p, first):
        r = box(False, 14, "row")
        if not first:
            add_cls(r, "sep")
        online = p.get("Online")
        dot = mk_label("●", "dot-on" if online else "dot-off", 0.5, False)
        dot.set_valign(Gtk.Align.CENTER)
        t = box(True, 2)
        t.set_valign(Gtk.Align.CENTER)
        t.pack_start(mk_label(p.get("HostName", "?"), "row-title"), False, False, 0)
        os_name = {"linux": "Linux", "windows": "Windows", "macOS": "macOS", "android": "Android",
                   "iOS": "iOS"}.get(p.get("OS", ""), p.get("OS", ""))
        state = tr("в сети") if online else tr("был {0}").format(last_seen(p))
        t.pack_start(mk_label(" · ".join(filter(None, (os_name, first_ip(p), state))), "row-detail"),
                     False, False, 0)
        r.pack_start(dot, False, False, 0)
        r.pack_start(t, True, True, 0)
        mb = Gtk.MenuButton(valign=Gtk.Align.CENTER)
        mb.add(mk_label("⋮", None, 0.5, False))
        add_cls(mb, "icon-btn")
        menu = Gtk.Menu()
        items = [(tr("Скопировать адрес"), lambda: self.copy(first_ip(p), tr("Скопировано: {0}").format(first_ip(p)))),
                 (tr("Проверить связь"), lambda: self.ping_peer(p)),
                 (tr("Отправить файл…"), lambda: self.taildrop_send(p))]
        for label, cb in items:
            it = Gtk.MenuItem(label=label)
            it.connect("activate", lambda _i, f=cb: f())
            menu.append(it)
        menu.show_all()
        mb.set_popup(menu)
        r.pack_end(mb, False, False, 0)
        known = any(c["node"].lower() == p.get("HostName", "").lower() for c in self.cfg["connections"])
        b = mk_button(tr("Открыть") if known else tr("Подключиться"), "text-btn",
                      lambda: self.goto("connect") if known else self.connection_dialog(peer=p))
        b.set_valign(Gtk.Align.CENTER)
        r.pack_end(b, False, False, 0)
        return r

    def ping_peer(self, p):
        self.toast(tr("Проверяю связь с {0}…").format(p.get('HostName')), persistent=True)

        def done(res):
            rc, out, err = res
            pongs = re.findall(r"via (\S+) in ([\d.]+)ms", out)
            if pongs:
                via, ms = pongs[-1]
                how = tr("через ретранслятор ") + via if via.startswith("DERP") else tr("напрямую")
                self.toast(tr("{0}: {1}, {2} мс").format(p.get('HostName'), how, round(float(ms))))
            else:
                self.toast(tr("{0} не отвечает").format(p.get('HostName')))
        self.bg(lambda: run(["tailscale", "ping", "-c", "3", "--timeout=5s", first_ip(p)], timeout=30), done)

    def taildrop_send(self, p):
        fc = Gtk.FileChooserNative.new(tr("Файл для отправки"), self.win, Gtk.FileChooserAction.OPEN, None, None)
        if fc.run() != Gtk.ResponseType.ACCEPT:
            return
        path = fc.get_filename()
        self.toast(tr("Отправляю {0}…").format(os.path.basename(path)), persistent=True)
        self.ts_cmd(["file", "cp", path, f"{first_ip(p)}:"],
                    lambda rc, t: self.toast(tr("Отправлено") if rc == 0 else tr("Не отправлено: {0}").format(t.splitlines()[-1] if t else rc)))

    def taildrop_get(self):
        dest = downloads_dir()

        def listing():
            try:
                return set(os.listdir(dest))
            except OSError:
                return set()
        before = listing()

        def done(rc, t):
            new = listing() - before
            if rc == 0:
                self.toast(tr("Получено файлов: {0} → {1}").format(len(new), dest) if new else tr("Входящих файлов нет"))
            else:
                self.toast(t.splitlines()[-1] if t else tr("Не получилось"))
        self.ts_cmd(["file", "get", "--conflict=rename", dest], done)

    # ── «Подключиться» ──

    def build_connect(self):
        sc, v = self.page(tr("Подключиться"), tr("Ты помогаешь: заходишь на компьютеры друзей по SSH"))
        card = box(True, 10, "card pad")
        card.pack_start(mk_label(tr("Мой код помощника"), "row-title"), False, False, 0)
        card.pack_start(mk_label(tr("Отправь его другу. Он вставит код в «Качанинге» → «Принимать» → "
                                 "«Добавить помощника», и твой ключ начнёт пускать тебя к нему."),
                                 "row-detail"), False, False, 0)
        self.helper_code = mk_label("", "code", 0, True, True)
        card.pack_start(self.helper_code, False, False, 0)
        row = box(False, 8)
        self.helper_code_btn = mk_button(tr("Скопировать код"), "tonal small", self.copy_helper_code)
        row.pack_start(self.helper_code_btn, False, False, 0)
        card.pack_start(row, False, False, 0)
        v.pack_start(card, False, False, 0)

        v.pack_start(self.section(tr("Мои подключения"),
                                  mk_button(tr("Добавить"), "text-btn", lambda: self.connection_dialog())),
                     False, False, 0)
        self.conn_box = box(True, 12)
        v.pack_start(self.conn_box, False, False, 0)
        return sc

    def copy_helper_code(self):
        if not os.path.exists(CLIENT_KEY):
            ok, msg = ensure_client_key()
            self.log(tr("SSH-ключ: {0}").format(msg))
        code = my_helper_code(self.st, False)
        if code:
            self.helper_code.set_text(code)
            self.copy(code, tr("Код помощника скопирован — отправь его другу"))
        else:
            self.toast(tr("Не получилось прочитать ключ ~/.ssh/id_ed25519.pub"))

    def refresh_connect(self, quiet=False):
        for c in getattr(self, "conn_cards", []):
            c.alive = False
        code = my_helper_code(self.st, False) if os.path.exists(CLIENT_KEY + ".pub") else None
        self.helper_code.set_text(code or tr("Ключа ещё нет — он создастся, когда нажмёшь «Скопировать код»."))
        clear(self.conn_box)
        self.conn_cards = []
        if not self.cfg["connections"]:
            empty = box(True, 8, "card pad")
            empty.pack_start(mk_label(tr("Подключений пока нет"), "row-title"), False, False, 0)
            empty.pack_start(mk_label(tr("Попроси у друга его «код для подключения» (в «Качанинге» → «Принимать») "
                                      "или выбери его компьютер в списке устройств."), "row-detail"),
                             False, False, 0)
            b = mk_button(tr("Добавить подключение"), "filled small", lambda: self.connection_dialog())
            b.set_halign(Gtk.Align.START)
            empty.pack_start(b, False, False, 0)
            self.conn_box.pack_start(empty, False, False, 0)
        for conn in self.cfg["connections"]:
            c = ConnCard(self, conn)
            self.conn_cards.append(c)
            self.conn_box.pack_start(c.box, False, False, 0)
        self.conn_box.show_all()
        for c in self.conn_cards:
            if self.cfg["auto_check"]:
                c.run_checks()
            else:
                c.summary.set_text(tr("Нажми «Проверить», чтобы проверить связь"))

    def connection_dialog(self, peer=None, edit=None):
        d, area = self.dialog(tr("Изменить подключение") if edit else tr("Новое подключение"))
        code_entry = None
        if not edit:
            area.pack_start(mk_label(tr("Код для подключения от друга"), "row-title"), False, False, 0)
            code_entry = Gtk.Entry(placeholder_text="KCH1:…")
            area.pack_start(code_entry, False, False, 0)
            area.pack_start(mk_label(tr("или укажи вручную:"), "hint"), False, False, 0)
        names = sorted(p.get("HostName", "") for p in peers(self.st))
        node_combo = Gtk.ComboBoxText.new_with_entry()
        for n in names:
            node_combo.append(n, n)
        node = (edit or {}).get("node") or (peer or {}).get("HostName", "")
        node_combo.get_child().set_text(node)
        node_combo.get_child().set_placeholder_text(tr("имя компьютера в Tailscale"))
        user_entry = Gtk.Entry(placeholder_text=tr("пользователь на том компьютере"))
        user_entry.set_text((edit or {}).get("user", ""))
        name_entry = Gtk.Entry(placeholder_text=tr("как назвать (например, «Ваня»)"))
        name_entry.set_text((edit or {}).get("name", ""))
        for title, w in ((tr("Компьютер"), node_combo), (tr("Пользователь"), user_entry), (tr("Название"), name_entry)):
            area.pack_start(mk_label(title, "row-detail"), False, False, 0)
            area.pack_start(w, False, False, 0)
        err = mk_label("", "row-detail")
        area.pack_start(err, False, False, 0)
        self.styled_dialog_buttons(d, tr("Отмена"), tr("Сохранить") if edit else tr("Добавить"))
        d.show_all()
        while True:
            if d.run() != Gtk.ResponseType.OK:
                break
            try:
                code = code_entry.get_text().strip() if code_entry else ""
                if code:
                    data = parse_code(code)
                    if data["t"] != "host":
                        raise ValueError(tr("это код помощника — его вставляют в «Принимать». "
                                         "Тебе нужен «код для подключения» друга"))
                    n, u = data["node"], data["user"]
                else:
                    n = node_combo.get_child().get_text().strip()
                    u = user_entry.get_text().strip()
                    if not NODE_RE.fullmatch(n):
                        raise ValueError(tr("укажи имя компьютера (как в списке устройств)"))
                    if not USER_RE.fullmatch(u):
                        raise ValueError(tr("укажи пользователя латиницей, как при входе в систему"))
                name = name_entry.get_text().strip() or n
                if any(c is not edit and c["node"].lower() == n.lower() and c["user"] == u
                       for c in self.cfg["connections"]):
                    raise ValueError(tr("подключение {0}@{1} уже есть").format(u, n))
            except ValueError as e:
                err.set_text("⚠ " + str(e))
                continue
            if edit:
                if edit["node"] != n and edit.get("alias") == alias_for(edit["node"]):
                    edit["alias"] = alias_for(n)
                edit.update(node=n, user=u, name=name)
            else:
                self.cfg["connections"].append({"id": uuid.uuid4().hex[:8], "name": name, "node": n,
                                                "user": u, "alias": alias_for(n)})
            save_config(self.cfg)
            if not os.path.exists(CLIENT_KEY):
                ensure_client_key()
            self.toast(tr("Подключение сохранено"))
            break
        d.destroy()
        if self.pages.get_visible_child_name() == "connect":
            self.refresh_connect()
        else:
            self.goto("connect")

    # ── «Принимать» ──

    def build_host(self):
        sc, v = self.page(tr("Принимать"), tr("Тебе помогают: помощники заходят к тебе по SSH"))
        self.host_hero = Hero()
        v.pack_start(self.host_hero.box, False, False, 0)

        v.pack_start(self.section(tr("Права администратора для помощников")), False, False, 0)
        self.duration_groups["host"] = {}
        v.pack_start(self.chips([(str(s), l) for l, s in DURATIONS], str(self.cfg["duration"]),
                                self.set_duration, self.duration_groups["host"]), False, False, 0)
        v.pack_start(mk_label(tr("Когда срок выйдет, права снимутся сами. Входить по SSH без прав "
                              "администратора помощники смогут и дальше — пока ты не удалишь их ключ."),
                              "hint"), False, False, 0)
        row = box(False, 10)
        self.grant_btn = mk_button(tr("Выдать права"), "filled", self.host_grant)
        self.revoke_btn = mk_button(tr("Отозвать"), "tonal", lambda: self.root(["revoke"], tr("Отзываю права…")))
        row.pack_start(self.grant_btn, False, False, 0)
        row.pack_start(self.revoke_btn, False, False, 0)
        v.pack_start(row, False, False, 0)
        self.action_widgets = [self.grant_btn, self.revoke_btn]

        v.pack_start(self.section(tr("Мой код для подключения")), False, False, 0)
        card = box(True, 10, "card pad")
        card.pack_start(mk_label(tr("Отправь его помощнику — он добавит тебя в «Подключиться»."), "row-detail"),
                        False, False, 0)
        self.host_code = mk_label("", "code", 0, True, True)
        card.pack_start(self.host_code, False, False, 0)
        r = box(False, 8)
        r.pack_start(mk_button(tr("Скопировать код"), "tonal small",
                               lambda: self.copy(self.host_code.get_text(), tr("Код скопирован — отправь помощнику"))),
                     False, False, 0)
        r.pack_start(mk_button(tr("Разные аккаунты Tailscale?"), "text-btn", self.show_share_help), False, False, 0)
        card.pack_start(r, False, False, 0)
        v.pack_start(card, False, False, 0)

        v.pack_start(self.section(tr("Помощники"), mk_button(tr("Добавить"), "text-btn", self.helper_dialog)),
                     False, False, 0)
        self.helpers_box = box(True, 0, "card")
        v.pack_start(self.helpers_box, False, False, 0)

        v.pack_start(self.section(tr("Проверки"), mk_button(tr("Исправить всё"), "text-btn", self.host_fix_all)),
                     False, False, 0)
        self.host_checks = ChecksCard(HOST_CHECKS, self.host_fix)
        v.pack_start(self.host_checks.box, False, False, 0)
        return sc

    def set_duration(self, value):
        if self.cfg["duration"] != int(value):
            self.cfg["duration"] = int(value)
            save_config(self.cfg)
        for g in self.duration_groups.values():
            rb = g.get(str(value))
            if rb and not rb.get_active():
                rb.set_active(True)

    def host_grant(self):
        secs = self.cfg["duration"]
        # то, что setup-host не чинит, не повод гонять всю настройку
        todo = [c for c in self.host_checks.ids("err", "warn") if c not in ("helpers", "pwauth", "perms", "access")]
        self.fix_perms(quiet=True)
        if todo:
            self.root(["setup-host", "--grant", str(secs)], tr("Настраиваю и выдаю права…"))
        else:
            self.root(["grant", str(secs)], tr("Выдаю права…"))

    def host_fix_all(self, on_done=None):
        self.fix_perms(quiet=True)
        self.root(["setup-host"], tr("Настраиваю приём подключений…"), on_done=on_done)

    def fix_perms(self, quiet=False):
        if not ssh_perms_problems():
            return
        left = fix_ssh_perms()
        if left:
            self.log(tr("Права на ~/.ssh: ") + "; ".join(left))
        if not quiet:
            self.toast(tr("Не всё исправлено: ") + "; ".join(left) if left else tr("Права на ~/.ssh исправлены"))
            self.refresh_host(quiet=True)

    def disable_password(self):
        if self.confirm(tr("Отключить вход по паролю?"),
                        tr("К SSH-серверу можно будет войти только по ключу. Помощники входят по ключам, "
                        "им это не помешает. Если ты сам заходишь на этот компьютер по SSH с паролем, "
                        "сначала добавь свой ключ.")):
            self.root(["harden-ssh"], tr("Отключаю вход по паролю…"))

    def restrict_keys(self):
        for k in list_keys():
            if k["ours"] and not k["ts_only"]:
                add_helper_key(k["name"], k)
        self.toast(tr("Помощники теперь входят только через Tailscale"))
        self.refresh_host(quiet=True)

    def host_fix(self, cid, fix):
        if fix == "setup":
            self.host_fix_all()
        elif fix == "grant":
            self.host_grant()
        elif fix in ("login", "renew"):
            self.do_login(fix == "renew")
        elif fix == "admin":
            open_url(ADMIN_URL)
        elif fix == "noexpiry":
            self.show_noexpiry()
        elif fix == "addhelper":
            self.helper_dialog()
        elif fix == "perms":
            self.fix_perms()
        elif fix == "nopass":
            self.disable_password()
        elif fix == "restrict":
            self.restrict_keys()

    def refresh_host(self, quiet=False):
        if self.loading.get("host"):
            return
        self.loading["host"] = True
        self.host_code.set_text(my_host_code(self.st, False))
        self.fill_helpers()
        if not quiet:
            self.host_checks.reset()
            self.host_hero.set("run", tr("Проверяю…"))
        ctx = {}

        def work():
            for r in host_checks(ctx):
                GLib.idle_add(self.host_checks.set, *r)
            return ctx

        self.bg(work, self.host_done)

    def host_done(self, ctx):
        self.loading["host"] = False
        if isinstance(ctx, Exception):
            return
        c = self.host_checks
        errs = c.ids("err")
        if c.state("access") == "ok":
            self.host_hero.set("ok", tr("Права администратора выданы"),
                               tr("{0} · адрес {1}").format(ctx.get('access', '').capitalize(), ctx.get('self_ip', '?')))
        elif errs:
            self.host_hero.set("err", tr("Нужна настройка"),
                               tr("Не в порядке: ") + ", ".join(c.titles[e].lower() for e in errs)
                               + tr(".\nНажми «Исправить всё» — понадобится пароль."))
        elif c.ids("warn"):
            self.host_hero.set("warn", tr("Почти готово"),
                               tr("Обрати внимание: ") + ", ".join(c.titles[e].lower() for e in c.ids("warn")))
        else:
            self.host_hero.set("info", tr("Готово к приёму подключений"),
                               tr("Помощники могут заходить по SSH. Права администратора сейчас не выданы."))
        self.revoke_btn.set_visible(c.state("access") == "ok")

    def fill_helpers(self):
        clear(self.helpers_box)
        keys = list_keys()
        if not keys:
            r = box(False, 0, "row")
            r.pack_start(mk_label(tr("Пока никого. Попроси у помощника его «код помощника» и нажми «Добавить»."),
                                  "row-detail"), True, True, 0)
            self.helpers_box.pack_start(r, False, False, 0)
        for i, k in enumerate(keys):
            r = box(False, 14, "row")
            if i:
                add_cls(r, "sep")
            peer = find_peer(self.st, k["name"]) if self.st else None
            dot = mk_label("●", "dot-on" if peer and peer.get("Online") else "dot-off", 0.5, False)
            dot.set_valign(Gtk.Align.CENTER)
            t = box(True, 2)
            t.pack_start(mk_label(k["name"], "row-title"), False, False, 0)
            where = tr("в сети") if peer and peer.get("Online") else (tr("не в сети") if peer else tr("не найден в Tailscale"))
            if not k["ts_only"]:
                where += tr(" · вход из любой сети")
            t.pack_start(mk_label(f"{k['type'].replace('ssh-', '')} · {where}", "row-detail"), False, False, 0)
            r.pack_start(dot, False, False, 0)
            r.pack_start(t, True, True, 0)
            b = mk_button(tr("Удалить"), "text-btn", lambda kk=k: self.remove_helper(kk))
            b.set_valign(Gtk.Align.CENTER)
            r.pack_end(b, False, False, 0)
            self.helpers_box.pack_start(r, False, False, 0)
        self.helpers_box.show_all()

    def remove_helper(self, k):
        if self.confirm(tr("Удалить помощника «{0}»?").format(k['name']),
                        tr("Он больше не сможет заходить к тебе по SSH. Права администратора, если выданы, "
                        "остаются у всех помощников до отзыва.")):
            remove_helper_key(k["body"])
            self.toast(tr("«{0}» удалён").format(k['name']))
            self.fill_helpers()

    def helper_dialog(self, prefill=""):
        d, area = self.dialog(tr("Добавить помощника"))
        area.pack_start(mk_label(tr("Вставь «код помощника», который он тебе прислал. "
                                 "Можно и обычный открытый SSH-ключ (ssh-ed25519 …)."), "wiz-text"),
                        False, False, 0)
        entry = Gtk.Entry(placeholder_text="KCH1:…")
        entry.set_text(prefill)
        area.pack_start(entry, False, False, 0)
        name_entry = Gtk.Entry(placeholder_text=tr("имя (необязательно)"))
        area.pack_start(name_entry, False, False, 0)
        err = mk_label("", "row-detail")
        area.pack_start(err, False, False, 0)
        self.styled_dialog_buttons(d, tr("Отмена"), tr("Добавить"))
        d.show_all()
        added = False
        while not added and d.run() == Gtk.ResponseType.OK:
            try:
                added = self.add_helper_from_text(entry.get_text(), name_entry.get_text())
            except ValueError as e:
                err.set_text("⚠ " + str(e))
        d.destroy()
        if added:
            self.fill_helpers()
            self.refresh_host(quiet=True)

    def add_helper_from_text(self, text, name=""):
        text = text.strip()
        if text.upper().startswith(CODE_PREFIX):
            data = parse_code(text)
            if data["t"] != "helper":
                raise ValueError(tr("это код для подключения — его вставляют в «Подключиться». "
                                 "Здесь нужен «код помощника»"))
            key, node = parse_pubkey(data["key"]), data["node"]
        else:
            key = parse_pubkey(text)
            if not key:
                raise ValueError(tr("не похоже ни на код, ни на SSH-ключ"))
            node = key["comment"].split("@")[-1] if key["comment"] else ""
        who = safe_name(name.strip() or node)
        # код приходит через мессенджер — человек должен видеть, кого пускает
        if not self.confirm(tr("Пустить «{0}» к себе?").format(who),
                            tr("Владелец этого ключа сможет входить на этот компьютер по SSH как {0} (только через Tailscale), а пока выданы права администратора — управлять всей системой.\n\nОтпечаток ключа: {1}\n\nДобавляй только код, который тебе прислал тот, кому ты доверяешь.").format(getpass.getuser(), key_fingerprint(key) or '?')):
            return False
        add_helper_key(who, key)
        self.toast(tr("Помощник «{0}» добавлен").format(who))
        return True

    # ── «Настройки» ──

    def build_settings(self):
        sc, v = self.page(tr("Настройки"), tr("Оформление, уведомления, подключения и Tailscale"))
        self.settings_box = v

        card = self.settings_card(v, tr("Оформление"))
        self.chip_setting(card, tr("Язык"), tr("смена языка — после перезапуска"), LANGS, self.cfg["lang"], self.set_lang)
        r = self.set_row(card, tr("Цвет и тема"), None, vertical=True)
        r.pack_start(self.theme_picker(), False, False, 0)
        self.chip_setting(card, tr("Размер текста"), None, SCALES, str(self.cfg["theme"]["scale"]),
                          lambda x: self.set_theme(scale=float(x)))
        self.switch_setting(card, tr("Анимации"), tr("плавная смена страниц и появление подсказок"),
                            self.cfg["theme"]["animations"], lambda on: self.set_theme(animations=on))

        card = self.settings_card(v, tr("Общие"))
        self.chip_setting(card, tr("Открывать при запуске"),
                          tr("«Автоматически» — «Подключиться», если подключения уже есть, иначе «Принимать»"),
                          START_PAGES, self.cfg["start_page"], lambda x: self.set_cfg("start_page", x))
        self.chip_setting(card, tr("Обновлять открытую страницу"), tr("проверки и список устройств, пока окно активно"),
                          REFRESH, str(self.cfg["refresh"]),
                          lambda x: (self.set_cfg("refresh", int(x)), self.schedule_periodic()))
        self.set_row(card, tr("Мастер настройки"), tr("пройти первоначальную настройку заново"),
                     mk_button(tr("Запустить"), "tonal small", self.start_wizard))

        card = self.settings_card(v, tr("Уведомления"))
        self.switch_setting(card, tr("Напоминать о сроке ключей"),
                            tr("свой ключ Tailscale и ключи компьютеров, к которым подключаешься"),
                            self.cfg["notify"], self.set_notify)
        self.chip_setting(card, tr("Предупреждать заранее"), None, WARN_CHOICES, str(self.cfg["warn_days"]),
                          self.set_warn_days)
        self.switch_setting(card, tr("Сообщать о проблемах Tailscale"), tr("служба остановлена или нужен вход"),
                            self.cfg["notify_ts"], lambda on: self.set_cfg("notify_ts", on))

        card = self.settings_card(v, tr("Подключение к друзьям"))
        terms = installed_terminals()
        combo = Gtk.ComboBoxText()
        combo.append("", tr("Автоматически ({0})").format(terms[0]) if terms else tr("Автоматически"))
        for t in terms:
            combo.append(t, t)
        if self.cfg["terminal"] and self.cfg["terminal"] not in terms:
            combo.append(self.cfg["terminal"], tr("{0} (не найден)").format(self.cfg['terminal']))
        combo.set_active_id(self.cfg["terminal"])
        combo.connect("changed", lambda c: self.set_cfg("terminal", c.get_active_id() or ""))
        self.set_row(card, tr("Терминал"), tr("где открывается SSH по кнопке «Терминал»"), combo)
        self.switch_setting(card, tr("Проверять связь при открытии"), tr("иначе — по кнопке «Проверить» в карточке"),
                            self.cfg["auto_check"], lambda on: self.set_cfg("auto_check", on))
        self.switch_setting(card, tr("Настраивать команду «ssh имя»"),
                            tr("дописывать подключение в ~/.ssh/config после удачной проверки"),
                            self.cfg["auto_alias"], lambda on: self.set_cfg("auto_alias", on))
        self.key_row = self.set_row(card, tr("Мой SSH-ключ"), "…", box(False, 0))

        card = self.settings_card(v, tr("Приём подключений"))
        self.duration_groups["settings"] = {}
        r = self.set_row(card, tr("Срок прав администратора"), tr("выбор по умолчанию для кнопки «Выдать права»"),
                         vertical=True)
        r.pack_start(self.chips([(str(s), l) for l, s in DURATIONS], str(self.cfg["duration"]),
                                self.set_duration, self.duration_groups["settings"]), False, False, 0)
        self.set_row(card, tr("Помощники"), tr("ключи, которым разрешён вход, — на вкладке «Принимать»"),
                     mk_button(tr("Открыть"), "text-btn", lambda: self.goto("host")))

        card = self.settings_card(v, "Tailscale")
        self.ts_pref_guard = False
        for flag, field, title, sub in TS_PREFS:
            sw = Gtk.Switch()
            sw.set_sensitive(False)
            sw.connect("notify::active", lambda s, _p, f=flag: self.on_ts_pref(f, s))
            self.ts_pref_switches[field] = sw
            self.set_row(card, title, sub, sw)
        self.set_row(card, tr("Админ-панель"), tr("устройства, общий доступ, срок ключей"),
                     mk_button(tr("Открыть"), "text-btn", lambda: open_url(ADMIN_URL)))

        v.pack_start(self.section(tr("Журнал"), self.log_buttons()), False, False, 0)
        # скругление даёт рамка с отступом: GTK3 не обрезает содержимое по border-radius
        frame = box(True, 0, "logbox")
        logsc = Gtk.ScrolledWindow()
        logsc.set_min_content_height(200)
        logview = Gtk.TextView(buffer=self.logbuf, editable=False, cursor_visible=False,
                               wrap_mode=Gtk.WrapMode.WORD_CHAR)
        for side in ("left", "right", "top", "bottom"):
            getattr(logview, f"set_{side}_margin")(6)
        logsc.add(logview)
        frame.pack_start(logsc, True, True, 0)
        v.pack_start(frame, False, False, 0)

        card = self.settings_card(v, tr("О программе"))
        self.set_row(card, f"{APP_NAME} {VERSION}", tr("удалённая помощь через Tailscale и SSH"))
        self.set_row(card, tr("Установка"),
                     tr("пакетом — обновления через менеджер пакетов") if PACKAGED
                     else tr("в ~/.local — новая версия: пакет из AUR или .deb с GitHub"),
                     mk_button("GitHub", "text-btn", lambda: open_url("https://github.com/miahke/kachaning")))
        self.set_row(card, tr("Папка настроек"), CONFIG_DIR.replace(os.path.expanduser("~"), "~", 1),
                     mk_button(tr("Открыть"), "text-btn", lambda: open_url("file://" + CONFIG_DIR)))
        self.set_row(card, tr("Сбросить настройки"), tr("оформление и параметры; подключения и ключи останутся"),
                     mk_button(tr("Сбросить"), "text-btn", self.reset_settings))
        return sc

    def settings_card(self, v, title):
        v.pack_start(self.section(title), False, False, 0)
        card = box(True, 0, "card")
        v.pack_start(card, False, False, 0)
        return card

    def set_row(self, card, title, sub, widget=None, vertical=False):
        """Строка настроек: заголовок и пояснение, справа виджет (или под ними, если vertical)."""
        r = box(True, 12, "set-row") if vertical else box(False, 14, "set-row")
        if card.get_children():
            add_cls(r, "sep")
        t = box(True, 2)
        t.set_valign(Gtk.Align.CENTER)
        t.pack_start(mk_label(title, "row-title"), False, False, 0)
        r.sub = mk_label(sub or "", "row-detail")
        r.sub.set_no_show_all(not sub)
        t.pack_start(r.sub, False, False, 0)
        r.pack_start(t, not vertical, True, 0)
        r.end = widget
        if widget is not None:
            widget.set_valign(Gtk.Align.CENTER)
            r.pack_end(widget, False, False, 0)
        card.pack_start(r, False, False, 0)
        return r

    def chip_setting(self, card, title, sub, items, current, on_change):
        r = self.set_row(card, title, sub, vertical=True)
        r.pack_start(self.chips(items, current, on_change), False, False, 0)

    def switch_setting(self, card, title, sub, active, on_change):
        sw = Gtk.Switch()
        sw.set_active(bool(active))
        sw.connect("notify::active", lambda s, _p: on_change(s.get_active()))
        self.set_row(card, title, sub, sw)

    def log_buttons(self):
        b = box(False, 4)
        b.pack_start(mk_button(tr("Скопировать"), "text-btn", lambda: self.copy(
            self.logbuf.get_text(self.logbuf.get_start_iter(), self.logbuf.get_end_iter(), False),
            tr("Журнал скопирован"))), False, False, 0)
        b.pack_start(mk_button(tr("Очистить"), "text-btn", lambda: self.logbuf.set_text("")), False, False, 0)
        return b

    def set_cfg(self, key, value):
        self.cfg[key] = value
        save_config(self.cfg)

    def set_lang(self, value):
        self.set_cfg("lang", value)
        if self.confirm(tr("Перезапустить Качанинг?"), tr("Язык сменится после перезапуска программы.")):
            os.execv(sys.executable, [sys.executable, os.path.realpath(__file__)])

    def set_notify(self, on):
        self.set_cfg("notify", on)
        self.bg(lambda: set_notify_timer(on))

    def set_warn_days(self, value):
        global WARN_DAYS
        WARN_DAYS = int(value)
        self.set_cfg("warn_days", WARN_DAYS)

    def refresh_settings(self, quiet=False):
        k = None
        try:
            with open(CLIENT_KEY + ".pub") as f:
                k = parse_pubkey(f.read())
        except OSError:
            pass
        r = self.key_row
        clear(r.end)
        short = CLIENT_KEY.replace(os.path.expanduser("~"), "~", 1)
        if k:
            r.sub.set_text(f"{short} · {key_fingerprint(k)}")
            r.end.pack_start(mk_button(tr("Скопировать открытый"), "text-btn",
                                       lambda: self.copy(f"{k['type']} {k['body']}", tr("Открытый ключ скопирован"))),
                             False, False, 0)
        else:
            r.sub.set_text(tr("{0} — ещё не создан").format(short))
            r.end.pack_start(mk_button(tr("Создать"), "text-btn", self.create_key), False, False, 0)
        r.sub.show()
        r.end.show_all()

        def done(res):
            if isinstance(res, Exception):
                return
            rc, out, _ = res
            try:
                prefs = json.loads(out) if rc == 0 else {}
            except ValueError:
                prefs = {}
            self.ts_pref_guard = True
            for field, sw in self.ts_pref_switches.items():
                sw.set_active(bool(prefs.get(field)))
                sw.set_sensitive(field in prefs)
            self.ts_pref_guard = False
        self.bg(lambda: run(["tailscale", "debug", "prefs"], timeout=10), done)

    def create_key(self):
        ok, msg = ensure_client_key()
        self.toast(tr("SSH-ключ {0}").format(msg) if ok else tr("Ключ не создан: {0}").format(msg))
        self.refresh_settings()

    def on_ts_pref(self, flag, sw):
        if self.ts_pref_guard:
            return
        on = sw.get_active()
        sw.set_sensitive(False)

        def done(rc, text):
            if rc != 0:
                self.toast(text.splitlines()[-1] if text else tr("Не получилось"))
            self.refresh_settings()
        self.ts_cmd(["set", f"--{flag}={'true' if on else 'false'}"], done)

    def reset_settings(self):
        if not self.confirm(tr("Сбросить настройки?"), tr("Оформление, уведомления и остальные параметры вернутся "
                                                    "к исходным. Подключения, ключи и права не изменятся.")):
            return
        keep = {k: self.cfg[k] for k in ("connections", "wizard_done")}
        self.cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        self.cfg.update(keep)
        save_config(self.cfg)
        global WARN_DAYS
        WARN_DAYS = self.cfg["warn_days"]
        self.apply_theme()
        self.schedule_periodic()
        self.bg(lambda: set_notify_timer(True))
        old = self.pages.get_child_by_name("settings")
        self.pages.add_named(self.build_settings(), "settings-new")
        old.destroy()
        self.pages.child_set_property(self.pages.get_child_by_name("settings-new"), "name", "settings")
        self.pages.get_child_by_name("settings").show_all()
        self.pages.set_visible_child_name("settings")
        self.refresh_settings()
        self.toast(tr("Настройки сброшены"))

    # ── мастер настройки ──

    def start_wizard(self):
        old = self.top.get_child_by_name("wizard")
        if old:
            old.destroy()
        self.wiz = {}
        w = self.build_wizard()
        self.top.add_named(w, "wizard")
        w.show_all()
        self.top.set_visible_child_name("wizard")
        self.hb.set_subtitle(tr("Мастер настройки"))
        self.wiz_show("welcome")

    def wiz_steps(self):
        return ["welcome", "tailscale", "host", "client", "done"]

    def build_wizard(self):
        outer = box(True, 0, "wizard")
        self.wiz_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT,
                                   transition_duration=220)
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        clamp = box(True, 0, "wizard-body")
        clamp.pack_start(self.wiz_stack, True, True, 0)
        sc.add(clamp)
        outer.pack_start(sc, True, True, 0)

        for name, builder in (("welcome", self.wiz_welcome), ("tailscale", self.wiz_tailscale), ("host", self.wiz_host),
                              ("client", self.wiz_client), ("done", self.wiz_done)):
            self.wiz_stack.add_named(builder(), name)

        foot = box(False, 10)
        for side in ("start", "end", "bottom"):
            getattr(foot, f"set_margin_{side}")(24)
        self.wiz_back = mk_button(tr("Назад"), "text-btn", lambda: self.wiz_move(-1))
        self.wiz_dots = box(False, 6)
        self.wiz_dots.set_halign(Gtk.Align.CENTER)
        self.wiz_next = mk_button(tr("Далее"), "filled", lambda: self.wiz_move(1))
        foot.pack_start(self.wiz_back, False, False, 0)
        foot.pack_start(self.wiz_dots, True, True, 0)
        foot.pack_end(self.wiz_next, False, False, 0)
        outer.pack_end(foot, False, False, 0)
        return outer

    def wiz_page(self, title, text):
        v = box(True, 16)
        v.pack_start(mk_label(title, "wiz-title"), False, False, 0)
        if text:
            v.pack_start(mk_label(text, "wiz-text"), False, False, 0)
        return v

    def wiz_welcome(self):
        v = self.wiz_page(tr("Добро пожаловать в {0}").format(APP_NAME),
                          tr("Качанинг помогает друзьям помогать друг другу с компьютером: связывает вас через "
                          "Tailscale, настраивает вход по SSH и выдаёт права администратора на время.\n\n"
                          "Каждый компьютер с Качанингом умеет и то и другое: принимать помощь "
                          "и подключаться к друзьям. Для начала выбери, как программа будет выглядеть."))
        card = box(True, 0, "card pad")
        card.pack_start(self.theme_picker(), False, False, 0)
        v.pack_start(card, False, False, 0)
        return v

    def wiz_tailscale(self):
        v = self.wiz_page("Tailscale", tr("Tailscale соединяет ваши компьютеры, даже если они в разных городах "
                                      "и за роутерами. Нужен бесплатный аккаунт — войти можно через Google, "
                                      "GitHub или Microsoft."))
        self.wiz["ts_hero"] = Hero()
        v.pack_start(self.wiz["ts_hero"].box, False, False, 0)
        self.wiz["ts_btn"] = mk_button("", "filled", lambda: self.wiz.get("ts_cb") and self.wiz["ts_cb"]())
        self.wiz["ts_btn"].set_no_show_all(True)
        self.wiz["ts_hero"].end.pack_start(self.wiz["ts_btn"], False, False, 0)
        v.pack_start(mk_label(tr("Если Tailscale ещё не установлен, Качанинг поставит его сам и попросит "
                              "пароль администратора этого компьютера."), "hint"), False, False, 0)
        return v

    def wiz_host(self):
        v = self.wiz_page(tr("Принимать подключения"),
                          tr("Нужно включить SSH-сервер и защиту: прав администратора не будет, пока ты их "
                          "не выдашь, а выданные снимутся сами по сроку."))
        self.wiz["host_hero"] = Hero()
        b = mk_button(tr("Настроить"), "filled", lambda: self.host_fix_all(on_done=lambda rc: self.wiz_refresh()))
        self.wiz["host_hero"].end.pack_start(b, False, False, 0)
        v.pack_start(self.wiz["host_hero"].box, False, False, 0)

        v.pack_start(mk_label(tr("Код помощника"), "section"), False, False, 0)
        r = box(False, 8)
        self.wiz["helper_entry"] = Gtk.Entry(placeholder_text=tr("вставь код от помощника (можно позже)"))
        r.pack_start(self.wiz["helper_entry"], True, True, 0)
        r.pack_start(mk_button(tr("Добавить"), "tonal small", self.wiz_add_helper), False, False, 0)
        v.pack_start(r, False, False, 0)
        self.wiz["helper_err"] = mk_label("", "hint")
        v.pack_start(self.wiz["helper_err"], False, False, 0)

        v.pack_start(mk_label(tr("Мой код для подключения"), "section"), False, False, 0)
        v.pack_start(mk_label(tr("Отправь его помощнику, чтобы он добавил тебя к себе."), "hint"), False, False, 0)
        self.wiz["host_code"] = mk_label("", "code", 0, True, True)
        v.pack_start(self.wiz["host_code"], False, False, 0)
        r2 = box(False, 8)
        r2.pack_start(mk_button(tr("Скопировать"), "tonal small",
                                lambda: self.copy(self.wiz["host_code"].get_text(), tr("Код скопирован"))),
                      False, False, 0)
        r2.pack_start(mk_button(tr("Разные аккаунты Tailscale?"), "text-btn", self.show_share_help), False, False, 0)
        v.pack_start(r2, False, False, 0)
        return v

    def wiz_add_helper(self):
        try:
            if self.add_helper_from_text(self.wiz["helper_entry"].get_text()):
                self.wiz["helper_entry"].set_text("")
                self.wiz["helper_err"].set_text(tr("✓ Помощник добавлен"))
        except ValueError as e:
            self.wiz["helper_err"].set_text("⚠ " + str(e))

    def wiz_client(self):
        v = self.wiz_page(tr("Подключаться к другим"),
                          tr("Для входа к друзьям нужен SSH-ключ — Качанинг создал его. Отправь другу свой код "
                          "помощника, а его «код для подключения» вставь ниже."))
        v.pack_start(mk_label(tr("Мой код помощника"), "section"), False, False, 0)
        self.wiz["helper_code"] = mk_label("", "code", 0, True, True)
        v.pack_start(self.wiz["helper_code"], False, False, 0)
        r = box(False, 8)
        r.pack_start(mk_button(tr("Скопировать"), "tonal small", self.copy_helper_code), False, False, 0)
        v.pack_start(r, False, False, 0)
        v.pack_start(mk_label(tr("Код для подключения от друга"), "section"), False, False, 0)
        r2 = box(False, 8)
        self.wiz["conn_entry"] = Gtk.Entry(placeholder_text=tr("KCH1:… (можно позже)"))
        r2.pack_start(self.wiz["conn_entry"], True, True, 0)
        r2.pack_start(mk_button(tr("Добавить"), "tonal small", self.wiz_add_conn), False, False, 0)
        v.pack_start(r2, False, False, 0)
        self.wiz["conn_err"] = mk_label("", "hint")
        v.pack_start(self.wiz["conn_err"], False, False, 0)
        return v

    def wiz_add_conn(self):
        try:
            data = parse_code(self.wiz["conn_entry"].get_text())
            if data["t"] != "host":
                raise ValueError(tr("это код помощника — нужен «код для подключения» друга"))
            if any(c["node"].lower() == data["node"].lower() and c["user"] == data["user"]
                   for c in self.cfg["connections"]):
                raise ValueError(tr("такое подключение уже есть"))
            self.cfg["connections"].append({"id": uuid.uuid4().hex[:8], "name": data["node"],
                                            "node": data["node"], "user": data["user"],
                                            "alias": alias_for(data["node"])})
            save_config(self.cfg)
            self.wiz["conn_entry"].set_text("")
            self.wiz["conn_err"].set_text(tr("✓ Добавлено: {0}@{1}").format(data['user'], data['node']))
        except ValueError as e:
            self.wiz["conn_err"].set_text("⚠ " + str(e))

    def wiz_done(self):
        v = self.wiz_page(tr("Готово!"), "")
        self.wiz["summary"] = mk_label("", "wiz-text")
        v.pack_start(self.wiz["summary"], False, False, 0)
        return v

    def wiz_show(self, name):
        self.wiz_current = name
        self.wiz_stack.set_visible_child_name(name)
        self.wiz_update_footer()
        self.wiz_refresh()

    def wiz_update_footer(self):
        steps = self.wiz_steps()
        cur = getattr(self, "wiz_current", "welcome")
        idx = steps.index(cur) if cur in steps else 0
        clear(self.wiz_dots)
        for i in range(len(steps)):
            dot = mk_label("●", "wiz-dot" + (" on" if i == idx else ""), 0.5, False)
            self.wiz_dots.pack_start(dot, False, False, 0)
        self.wiz_dots.show_all()
        self.wiz_back.set_visible(idx > 0)
        last = cur == "done"
        self.wiz_next.set_label(tr("Начать") if last else tr("Далее"))

    def wiz_move(self, delta):
        steps = self.wiz_steps()
        cur = self.wiz_current
        if cur == "done" and delta > 0:
            self.cfg["wizard_done"] = True
            save_config(self.cfg)
            self.goto(self.first_page())
            old = self.top.get_child_by_name("wizard")
            GLib.timeout_add(400, lambda: old.destroy() and False)
            return
        idx = steps.index(cur) if cur in steps else 0
        idx = max(0, min(len(steps) - 1, idx + delta))
        self.wiz_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT if delta > 0
                                           else Gtk.StackTransitionType.SLIDE_RIGHT)
        self.wiz_show(steps[idx])

    def wiz_refresh(self):
        cur = getattr(self, "wiz_current", None)
        if cur == "tailscale":
            hero = self.wiz["ts_hero"]
            hero.set("run", tr("Проверяю Tailscale…"))

            def done(res):
                st, err, installed = res
                self.st = st
                btn = self.wiz["ts_btn"]
                btn.show()
                if not installed:
                    hero.set("warn", tr("Tailscale не установлен"), tr("Нажми «Установить» — понадобится пароль."))
                    btn.set_label(tr("Установить"))
                    self.wiz["ts_cb"] = lambda: self.root(["setup-ts", "--login"], tr("Устанавливаю Tailscale…"),
                                                          on_done=lambda rc: self.wiz_refresh())
                elif st is None:
                    hero.set("err", tr("Служба Tailscale не работает"), err)
                    btn.set_label(tr("Запустить"))
                    self.wiz["ts_cb"] = lambda: self.root(["setup-ts"], tr("Запускаю Tailscale…"),
                                                          on_done=lambda rc: self.wiz_refresh())
                elif st.get("BackendState") == "Running":
                    me = st.get("Self") or {}
                    hero.set("ok", tr("Tailscale подключён"), f"{me.get('HostName')} · {first_ip(me)}")
                    btn.hide()
                else:
                    hero.set("warn", tr("Нужно войти в Tailscale"),
                             tr("Откроется браузер — войди или создай аккаунт."))
                    btn.set_label(tr("Войти"))
                    self.wiz["ts_cb"] = lambda: self.do_login(False, on_done=lambda rc: self.wiz_refresh())
                return False
            self.bg(lambda: ts_status() + (bool(shutil.which("tailscale")),), done)
        elif cur == "host":
            self.wiz["host_code"].set_text(my_host_code(self.st, False))
            hero = self.wiz["host_hero"]
            hero.set("run", tr("Проверяю…"))

            def done(res):
                if isinstance(res, Exception):
                    return
                bad = [dict(HOST_CHECKS)[c].lower() for c, s, _, _ in res
                       if s in ("err", "warn") and c not in ("access", "helpers", "pwauth")]
                if bad:
                    hero.set("warn", tr("Нужно настроить"), tr("Не в порядке: ") + ", ".join(bad))
                else:
                    hero.set("ok", tr("Всё настроено"), tr("SSH-сервер работает, защита на месте."))
            self.bg(lambda: list(host_checks({})), done)
        elif cur == "client":
            if not os.path.exists(CLIENT_KEY):
                ok, msg = ensure_client_key()
                self.log(tr("SSH-ключ: {0}").format(msg))
            self.wiz["helper_code"].set_text(my_helper_code(self.st, False) or tr("не удалось создать ключ ~/.ssh/id_ed25519"))
        elif cur == "done":
            n = len(self.cfg["connections"])
            lines = [tr("• «Принимать» — выдавай права администратора, когда нужна помощь, "
                     "и добавляй помощников по их кодам."),
                     tr("• «Подключиться» — {0} {1}; там же твой код помощника.").format(n, plural(n, tr('подключение'), tr('подключения'), tr('подключений')))]
            lines.append(tr("• «Сеть» — Tailscale: включение, вход, устройства, отправка файлов."))
            lines.append(tr("\nКачанинг напомнит, если ключ Tailscale скоро истечёт. Оформление, уведомления "
                         "и остальное — в «Настройках», там же можно пройти мастер снова."))
            self.wiz["summary"].set_text("\n".join(lines))


def snapshot(app, path, delay):
    """Отладка: сохраняет содержимое окна в PNG (KACH_SNAPSHOT=путь)."""
    import cairo

    def shoot():
        w = app.win
        alloc = w.get_allocation()
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, alloc.width, alloc.height)
        w.draw(cairo.Context(surf))
        surf.write_to_png(path)
        Gtk.main_quit()
        return False
    GLib.timeout_add(delay, shoot)


def run_gui():
    global Gtk, Gdk, GLib, Pango
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk as _Gtk, Gdk as _Gdk, GLib as _GLib, Pango as _Pango
    Gtk, Gdk, GLib, Pango = _Gtk, _Gdk, _GLib, _Pango
    GLib.set_prgname("kachaning")
    app = App(start_page=os.environ.get("KACH_PAGE"), force_wizard=bool(os.environ.get("KACH_WIZARD")))
    if os.environ.get("KACH_WIZARD_STEP"):
        app.wiz_show(os.environ["KACH_WIZARD_STEP"])
    if os.environ.get("KACH_SNAPSHOT"):
        snapshot(app, os.environ["KACH_SNAPSHOT"], int(os.environ.get("KACH_DELAY", "6000")))
    Gtk.main()


def main():
    a = sys.argv[1:]
    if "--lang" in a[:-1]:
        i = a.index("--lang")
        del a[i:i + 2]
    if a[:1] == ["--root"]:
        return root_main(a[1:])
    if a[:1] == ["--check"]:
        return cli_check()
    if a[:1] == ["--notify-check"]:
        return notify_check()
    if a[:1] == ["--version"]:
        print(VERSION)
        return 0
    if a[:1] == ["--icon"]:
        sys.stdout.write(ICON_SVG)
        return 0
    if a[:1] == ["--install"]:
        return install()
    run_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
