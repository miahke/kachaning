# Changelog

## 2.3.0

- First public release.
- Packages: AUR (`kachaning`) and `.deb` with an apt repository for automatic updates on Mint/Ubuntu.
- When installed from a package, the app runs from `/usr/share/kachaning`, removes an old `~/.local` copy and repoints shortcuts and the expiry timer.
- `--version` and `--icon` command-line options; "Installation" row and GitHub link in Settings → About.

## 2.2.0

- English interface; language picker in Settings.

## 2.1.0

- Detailed settings: scale, start page, refresh interval, expiry warnings, terminal, Tailscale options.
- Every computer can both connect and accept connections; the role step was removed from the wizard.
- UI rendering fixes.

## 2.0.0

- General-purpose app with a setup wizard and colour themes.
- Security audit: key restrictions, root actions only from a system-owned copy, validated configs.
