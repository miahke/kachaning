# Security model and audit notes

Kachaning configures persistent OpenSSH key access. Closing the GUI does not
stop sshd or remove authorized keys. Tailscale connectivity and its access
policy must also permit the connection. Installing the application alone does
not exchange SSH keys or authorize peers.

Administrator access grants NOPASSWD sudo to the receiving Unix account, not
just to one key or helper. Every login as that account can use the grant.
Revocation removes Kachaning's sudoers entry; it cannot undo root actions,
terminate already privileged processes, or remove independently configured
sudo grants. The timer checks every five minutes (with scheduling tolerance),
so an expiry is not an exact session boundary. Unlimited grants persist.

New helper keys are restricted to Tailscale source address ranges. This is
not a restriction to a single peer; protect keys and configure tailnet ACLs.
Removing a key prevents future authentication, not existing SSH sessions.

## Local review, 2026-11-03

Fixed in the working tree:
- Re-running the guard from its own standalone root copy deleted that copy.
- authorized_keys read failures could be mistaken for an empty key list.
- Invalid, missing or non-finite expiry values could leave sudo access enabled.
- Concurrent grant/revoke/expiry operations could interleave sudoers/state writes.
- Arch dependency installation used pacman -Sy, risking a partial upgrade;
  it now uses installed package databases via -S. If stale, update the system
  through the distribution's normal full-upgrade procedure.

Regression tests use temporary files and mocks. Cross-process admin locking
is tested with separate processes. Actual polkit prompts, remote sessions,
reboots and expiry on installed machines are not covered by these tests.
This review is not a guarantee that all vulnerabilities have been found.
