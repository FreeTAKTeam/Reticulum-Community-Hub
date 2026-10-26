#!/usr/bin/env bash
set -euo pipefail

# This test installs/removes packages and must never run on the operator host.
[[ -f /.dockerenv && $EUID == 0 ]] || { echo "Run only in a disposable root Docker container." >&2; exit 1; }
[[ $# == 1 && -f "$1" ]] || { echo "Usage: $0 <rch-server.deb>" >&2; exit 2; }
[[ ! -e /var/lib/rch && ! -e /etc/rch ]] || { echo "Expected an unused container." >&2; exit 1; }
[[ $(dpkg-deb -f "$1" Package) == rch-server ]]
[[ $(dpkg-deb -f "$1" Architecture) == amd64 ]]
version=$(dpkg-deb -f "$1" Version)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/bin" /run/systemd/system
export RCH_DEB_TEST_SERVICE_LOG="$work/services.log"
cat > "$work/bin/systemctl" <<'EOF'
#!/bin/sh
echo "$*" >> "$RCH_DEB_TEST_SERVICE_LOG"
case "$*" in
    daemon-reload|"stop rch-server.service reticulumd.service") exit 0 ;;
    *) echo "Unexpected service action: $*" >&2; exit 1 ;;
esac
EOF
chmod +x "$work/bin/systemctl"
cp "$work/bin/systemctl" /usr/bin/systemctl
export PATH="$work/bin:$PATH"

apt-get install -y --no-install-recommends "$1"
[[ $(id -u rch) != 0 ]]
[[ $(stat -c %U /var/lib/rch) == rch ]]
[[ $(stat -c %U /var/log/rch) == rch ]]
runuser -u rch -- test -r /etc/rch/config.ini
runuser -u rch -- test -w /etc/rch/config.ini
runuser -u rch -- test -w /etc/rch/reticulumd.toml
[[ $(stat -c '%U:%G:%a' /etc/rch) == root:rch:1770 ]]
[[ $(stat -c '%U:%G:%a' /etc/rch/rch-server.env) == root:rch:640 ]]
for config in /etc/rch/config.ini /etc/rch/reticulumd.toml; do
  [[ $(stat -c '%U:%G:%a' "$config") == rch:rch:640 ]]
  runuser -u rch -- sh -c 'printf "\n# runtime config write\n" >> "$1"; cp "$1" "$1.setup-test.tmp"; mv "$1.setup-test.tmp" "$1"' sh "$config"
done
if runuser -u rch -- sh -c 'echo changed >> /etc/rch/rch-server.env'; then
  echo "Runtime can modify root-managed environment." >&2; exit 1
fi
if runuser -u rch -- rm /etc/rch/rch-server.env; then
  echo "Runtime can unlink root-managed environment." >&2; exit 1
fi
runuser -u rch -- touch /etc/rch/env-replacement.tmp
if runuser -u rch -- mv /etc/rch/env-replacement.tmp /etc/rch/rch-server.env; then
  echo "Runtime can replace root-managed environment." >&2; exit 1
fi
runuser -u rch -- rm /etc/rch/env-replacement.tmp
runuser -u rch -- test -w /var/lib/rch
for entry in bin/r3akt-rch-server bin/r3akt-tak-service bin/reticulumd ui/index.html release-manifest.json; do
  [[ -f "/opt/rch/$entry" ]]
done
grep -Fx 'identity_path = /var/lib/rch/identity' /etc/rch/config.ini
grep -Fx 'RCH_UI_DIST_PATH=/opt/rch/ui' /etc/rch/rch-server.env
grep -F -- '--rpc-unix /run/rch/reticulumd.sock' /usr/lib/systemd/system/reticulumd.service
grep -Fx 'RuntimeDirectoryMode=0700' /usr/lib/systemd/system/reticulumd.service
grep -Fx 'WorkingDirectory=/var/lib/rch' /usr/lib/systemd/system/rch-server.service
grep -F -- '--ui-dist-path ${RCH_UI_DIST_PATH}' /usr/lib/systemd/system/rch-server.service
grep -F -- '--reticulum-config-path /etc/rch/reticulumd.toml' /usr/lib/systemd/system/rch-server.service
grep -Fx 'discover_interfaces = false' /etc/rch/reticulumd.toml
[[ $(cat "$RCH_DEB_TEST_SERVICE_LOG") == daemon-reload ]]
echo '# operator configuration preserved' >> /etc/rch/rch-server.env
for config in /etc/rch/config.ini /etc/rch/reticulumd.toml; do
  runuser -u rch -- sh -c 'echo "# operator configuration preserved" >> "$1"' sh "$config"
done
printf 'retained identity\n' > /var/lib/rch/identity
printf 'retained database\n' > /var/lib/rch/rch_state.sqlite3
chmod 600 /var/lib/rch/identity /var/lib/rch/rch_state.sqlite3
mkdir -p /etc/systemd/system/rch-server.service.d
echo '# operator unit' > /etc/systemd/system/reticulumd.service
echo '# operator drop-in' > /etc/systemd/system/rch-server.service.d/local.conf
sha256sum /etc/rch/* /var/lib/rch/* /etc/systemd/system/reticulumd.service \
  /etc/systemd/system/rch-server.service.d/local.conf > "$work/preserved.sha256"
owner=$(stat -c '%u:%g:%a' /var/lib/rch/identity)

# Repack the actual payload with a later version; no second Rust build is needed.
dpkg-deb --raw-extract "$1" "$work/upgrade"
next_version="${version}+installtest1"
sed -i "s/^Version: .*/Version: $next_version/" "$work/upgrade/DEBIAN/control"
echo '# changed package default' >> "$work/upgrade/etc/rch/config.ini"
dpkg-deb --root-owner-group --build "$work/upgrade" "$work/upgrade.deb"
dpkg --force-confold -i "$work/upgrade.deb"
sha256sum -c "$work/preserved.sha256"
[[ $(stat -c '%u:%g:%a' /var/lib/rch/identity) == "$owner" ]]
[[ $(dpkg-query -W -f='${Version}' rch-server) == "$next_version" ]]
dpkg --remove rch-server
sha256sum -c "$work/preserved.sha256"
[[ $(stat -c '%u:%g:%a' /var/lib/rch/identity) == "$owner" ]]
[[ ! -e /opt/rch/bin/r3akt-rch-server ]]
grep -Fx 'stop rch-server.service reticulumd.service' "$RCH_DEB_TEST_SERVICE_LOG"
if grep -E '(^| )(start|enable|restart|try-restart)( |$)' "$RCH_DEB_TEST_SERVICE_LOG"; then
  echo "Package attempted to start/enable a service." >&2
  exit 1
fi
echo 'Debian package install/upgrade/remove, configuration/state preservation, and no-autostart checks passed.'
