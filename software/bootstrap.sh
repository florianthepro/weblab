#!/usr/bin/env bash
# bootstrap.sh — Basis-Härtung + Firewall + Storage auf frischem Ubuntu 24.04.
# Läuft als root, wird vom GitHub-Actions-Workflow per SSH ausgeführt.
# SSH-Härtung lockt NUR bei gesetztem ADMIN_SSH_PUBKEY auf key-only (sonst bleibt
# root+Passwort erreichbar, damit der passwortbasierte Workflow re-laufen kann).
set -euo pipefail

ADMIN_SSH_PUBKEY="${ADMIN_SSH_PUBKEY:-}"
DATA_DEVICE="${DATA_DEVICE:-}"
DATA_MOUNT="${DATA_MOUNT:-/mnt/data}"
WIREGUARD_ENABLE="${WIREGUARD_ENABLE:-false}"
WIREGUARD_PORT="${WIREGUARD_PORT:-51820}"

[ "$(id -u)" -eq 0 ] || { echo "root nötig"; exit 1; }
export DEBIAN_FRONTEND=noninteractive

echo "== apt + Basis =="
apt-get update -y
apt-get install -y --no-install-recommends ca-certificates curl gnupg jq \
  unattended-upgrades apt-listchanges fail2ban chrony ufw cloud-guest-utils

echo "== sysctl-Härtung =="
cat >/etc/sysctl.d/99-hardening.conf <<'EOF'
net.ipv4.conf.all.rp_filter=1
net.ipv4.conf.all.accept_redirects=0
net.ipv6.conf.all.accept_redirects=0
net.ipv4.conf.all.send_redirects=0
net.ipv4.conf.all.accept_source_route=0
net.ipv6.conf.all.accept_source_route=0
net.ipv4.tcp_syncookies=1
kernel.randomize_va_space=2
kernel.kptr_restrict=2
kernel.dmesg_restrict=1
fs.protected_hardlinks=1
fs.protected_symlinks=1
EOF
sysctl --system >/dev/null

echo "== auto-updates + fail2ban + chrony =="
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
EOF
cat >/etc/fail2ban/jail.d/sshd.local <<'EOF'
[sshd]
enabled = true
maxretry = 4
bantime  = 1h
findtime = 10m
EOF
systemctl enable --now unattended-upgrades chrony fail2ban

echo "== SSH-Härtung (nur key-only, wenn Pubkey gesetzt) =="
if [ -n "$ADMIN_SSH_PUBKEY" ]; then
  getent group ssh-admins >/dev/null || groupadd ssh-admins
  id ops >/dev/null 2>&1 || adduser --disabled-password --gecos "" ops
  usermod -aG sudo,ssh-admins ops
  install -d -m 700 -o ops -g ops /home/ops/.ssh
  echo "$ADMIN_SSH_PUBKEY" > /home/ops/.ssh/authorized_keys
  chmod 600 /home/ops/.ssh/authorized_keys; chown ops:ops /home/ops/.ssh/authorized_keys
  echo "ops ALL=(ALL) ALL" >/etc/sudoers.d/90-ops; chmod 440 /etc/sudoers.d/90-ops
  cat >/etc/ssh/sshd_config.d/99-hardening.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
KbdInteractiveAuthentication no
AuthenticationMethods publickey
AllowGroups ssh-admins
MaxAuthTries 3
X11Forwarding no
EOF
  sshd -t && systemctl reload ssh
else
  echo "   kein ADMIN_SSH_PUBKEY -> SSH bleibt wie ist (root+Passwort), damit Re-Runs gehen."
  echo "   NACH Setup: Key hinterlegen + root/Passwort sperren (siehe fertig.md)."
fi

echo "== Firewall (ufw): 22/80/443${WIREGUARD_ENABLE:+/WG} =="
sed -i 's/^IPV6=.*/IPV6=yes/' /etc/default/ufw
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw limit 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
[ "$WIREGUARD_ENABLE" = "true" ] && ufw allow "${WIREGUARD_PORT}"/udp comment 'WireGuard'
ufw --force enable

echo "== Storage/Laufwerk (optional) =="
if [ -n "$DATA_DEVICE" ] && [ -b "$DATA_DEVICE" ]; then
  [ -z "$(blkid -s TYPE -o value "$DATA_DEVICE" || true)" ] && mkfs.ext4 -F -L data "$DATA_DEVICE" || echo "   $DATA_DEVICE hat FS"
  UUID=$(blkid -s UUID -o value "$DATA_DEVICE")
  grep -q "$UUID" /etc/fstab || echo "UUID=$UUID $DATA_MOUNT ext4 defaults,noatime,nofail 0 2" >> /etc/fstab
fi
mkdir -p "$DATA_MOUNT"
mountpoint -q "$DATA_MOUNT" || mount -a || true
echo "== bootstrap fertig =="
