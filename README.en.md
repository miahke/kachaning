# Kachaning

[Русский](README.md)

Remote help between friends on Linux. One person helps, the other accepts help, and the connection goes over [Tailscale](https://tailscale.com) — no public IPs, port forwarding or TeamViewer.

- **Setup wizard** on first launch: installs Tailscale, signs in, configures the SSH server.
- **Every computer can do both**: connect to friends and accept connections.
- **Helper keys only work from inside the Tailscale network.** A leaked key is useless from the internet.
- **Time-limited admin rights**: 2 hours, a day, a week or unlimited. Timed rights are revoked by a systemd timer, even with the app closed.
- **Step-by-step connection check**: Tailscale, node reachability, SSH, key, sudo — with a "Fix" button on each failure.
- Material You themes, light and dark, scaling, Russian and English UI.

## Install

### Arch, CachyOS, Manjaro, EndeavourOS — from the AUR

```bash
yay -S kachaning
```

Or `paru -S kachaning`. Updates come with the rest of the system: `yay -Syu`.

### Linux Mint, Ubuntu, Debian, Pop!_OS

Download `kachaning_*_all.deb` from [Releases](https://github.com/miahke/kachaning/releases/latest) and double-click it, or:

```bash
sudo apt install ./kachaning_*_all.deb
```

The package enables the app's apt repository, so new versions arrive through Update Manager with your other system updates.

<details>
<summary>Add the repository manually</summary>

```bash
sudo curl -fsSLo /usr/share/keyrings/kachaning-archive-keyring.gpg https://miahke.github.io/kachaning/kachaning-archive-keyring.gpg
```

```bash
echo "deb [signed-by=/usr/share/keyrings/kachaning-archive-keyring.gpg] https://miahke.github.io/kachaning stable main" | sudo tee /etc/apt/sources.list.d/kachaning.list
```

```bash
sudo apt update && sudo apt install kachaning
```

Repository key fingerprint: `0504 ADA5 305E 316D 8D6B  C7B6 5E85 D3F4 1F4E 99E0`
</details>

### Without a package

```bash
python3 kachaning.py --install
```

Installs a copy into `~/.local`; you update it by hand. If you install the package later, the app removes this copy and switches to the packaged one.

**Requirements:** Python 3.8+, PyGObject, GTK 3, polkit (pkexec), OpenSSH, sudo, systemd. The wizard installs Tailscale.

## Usage

1. Both friends install Kachaning and go through the wizard, signing in to the **same** Tailscale network — or one shares their machine with the other from the Tailscale admin console.
2. Friends swap codes (`KCH1:…` strings):
   - the helper copies their **helper code** on the Connect tab, the friend pastes it on the Accept tab;
   - the friend copies their **connection code** on the Accept tab, the helper pastes it on the Connect tab.
3. The friend grants the helper admin rights for a set time and can revoke them at any moment.

## Security

- The helper's key goes into `~/.ssh/authorized_keys` restricted with `from="100.64.0.0/10,fd7a:115c:a1e0::/48"` — Tailscale addresses only.
- Rights are granted through `/etc/sudoers.d/90-kachaning`, validated with `visudo`, and removed by `kachaning-expire.timer`.
- Root actions run through `pkexec`, only from a system-owned file the user cannot replace.
- Removing the package revokes rights and removes the timer. Helper keys stay — remove them on the Accept tab first if you want.

Found a vulnerability? Please report it via [Security advisories](https://github.com/miahke/kachaning/security/advisories/new), not public issues.

## Development

```bash
python3 tests/test_core.py
```

```bash
packaging/debian/build-deb.sh
```

```bash
cd packaging/arch && makepkg -si
```

To release: add a section to `CHANGELOG.md`, then run `scripts/release.sh X.Y.Z`. The tag triggers GitHub Actions: build the `.deb`, create the release, update the apt repository on GitHub Pages, update the AUR. See [RELEASING.md](RELEASING.md).

## License

[GPL-3.0-or-later](LICENSE) © 2026 miahke
