#!/usr/bin/env python3
"""Быстрые проверки без GUI и без root: запускаются при сборке пакета и в CI."""
import ast
import importlib.util
import os
import re
import string
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "kachaning.py")
CYR = re.compile("[А-Яа-яЁё]")
failed = 0


def check(name, ok):
    global failed
    print(("ok   " if ok else "FAIL ") + name)
    failed += not ok


def load(lang):
    os.environ["HOME"] = tempfile.mkdtemp()
    os.environ["KACH_LANG"] = lang
    spec = importlib.util.spec_from_file_location("kach_" + lang, SRC)
    m = importlib.util.module_from_spec(spec)
    saved, sys.argv = sys.argv, [SRC]
    try:
        spec.loader.exec_module(m)
    finally:
        sys.argv = saved
    return m


def fields(s):
    return sorted(f for _, f, _, _ in string.Formatter().parse(s) if f is not None)


ru, en = load("ru"), load("en")

# все строки tr("…") переведены, подстановки совпадают, в переводе нет кириллицы
keys = set()
for node in ast.walk(ast.parse(open(SRC, encoding="utf-8").read())):
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr"
            and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
        keys.add(node.args[0].value)
check("tr() keys found", len(keys) > 400)
missing = [k for k in keys if k not in en.EN]
check("every tr() string has English translation (%d missing)" % len(missing), not missing)
bad = [k for k, v in en.EN.items() if fields(k) != fields(v)]
check("placeholders match in translations (%d bad)" % len(bad), not bad)
cyr = [k for k, v in en.EN.items() if CYR.search(v) and k != "Русский"]
check("no Cyrillic in English values (%d)" % len(cyr), not cyr)

check("language switch", ru.tr("Настройки") == "Настройки" and en.tr("Настройки") != "Настройки")
check("app name per language", ru.APP_NAME == "Качанинг" and en.APP_NAME == "Kachaning")
check("russian plurals", [ru.plural(n, "день", "дня", "дней") for n in (1, 3, 5, 11, 21, 22)]
      == ["день", "дня", "дней", "дней", "день", "дня"])
check("english plurals", [en.plural(n, "day", "x", "days") for n in (1, 2, 21)] == ["day", "days", "days"])
check("version format", re.fullmatch(r"\d+\.\d+\.\d+", ru.VERSION) is not None)

good = {"id": "a1", "name": "Друг", "node": "friend-pc", "user": "bob"}
check("valid connection accepted", bool(ru.valid_conn(good)))
for k, v in (("node", "x;rm -rf /"), ("node", "-oProxyCommand=sh"), ("user", "bob root"), ("user", "$(id)")):
    check("connection with bad %s rejected: %r" % (k, v), not ru.valid_conn(dict(good, **{k: v})))

check("not in packaged mode from source tree", ru.PACKAGED is False)

print("\n%s" % ("all passed" if not failed else "%d failed" % failed))
sys.exit(1 if failed else 0)
