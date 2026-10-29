# Выпуск версий

## Один раз: настройка

1. **Репозиторий** `github.com/miahke/kachaning`, публичный. Отправить в него ветку `main`.
2. **Ключ подписи apt-репозитория.** Он уже создан и лежит вне репозитория: `~/.local/share/kachaning-release/APT_GPG_KEY.asc`. Публичная часть — `packaging/debian/kachaning-archive-keyring.gpg`.
   Содержимое `.asc` целиком вставить в Settings → Secrets and variables → Actions → New repository secret, имя `APT_GPG_KEY`. Потом сохранить `.asc` в надёжное место (менеджер паролей) — без него новые версии не подписать.
3. **Права для Actions:** Settings → Actions → General → Workflow permissions → *Read and write*.
4. **GitHub Pages** — после первого релиза, когда появится ветка `gh-pages`: Settings → Pages → Source: *Deploy from a branch*, ветка `gh-pages`, папка `/ (root)`.
5. **AUR (необязательно, пока регистрация на AUR закрыта):**
   - зарегистрироваться на https://aur.archlinux.org и добавить в профиль публичный SSH-ключ (отдельный, только для AUR);
   - первая публикация вручную: `packaging/arch/publish-aur.sh 2.3.0` (запускается после того, как тег `v2.3.0` есть на GitHub);
   - чтобы дальше AUR обновлялся сам, добавить приватную часть этого ключа в секрет `AUR_SSH_KEY`.

## Каждый выпуск

1. Описать изменения в `CHANGELOG.md` под заголовком `## X.Y.Z` и закоммитить.
2. `scripts/release.sh X.Y.Z` — меняет версию, проверяет тесты, делает коммит и тег, спрашивает про push.
3. GitHub Actions (`.github/workflows/release.yml`):
   - собирает `.deb` и выкладывает его в Releases;
   - добавляет `.deb` в apt-репозиторий на GitHub Pages и подписывает его;
   - собирает пакет для Arch и обновляет подписанный pacman-репозиторий на GitHub Pages (`/arch`);
   - обновляет PKGBUILD в AUR, если задан `AUR_SSH_KEY`.

После этого пользователи получают обновление через `yay -Syu`, `paru` и «Менеджер обновлений» Mint.
