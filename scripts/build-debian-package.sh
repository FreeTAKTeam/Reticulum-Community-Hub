#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 3 ]]; then
  echo "Usage: $0 <full-server-stage> <debian-version> <output-dir>" >&2
  exit 2
fi
stage=$(realpath "$1")
version=$2
dpkg --validate-version "$version"
[[ $(dpkg --print-architecture) == amd64 ]] || { echo "Build this package on Debian amd64." >&2; exit 1; }
mkdir -p "$3"
output=$(realpath "$3")
repo=$(cd "$(dirname "$0")/.." && pwd)
templates="$repo/packaging/debian"
for entry in bin/r3akt-rch-server bin/r3akt-tak-service bin/reticulumd ui/index.html release-manifest.json; do
  [[ -f "$stage/$entry" ]] || { echo "Missing staged payload: $entry" >&2; exit 1; }
done

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
package="$work/debian/rch-server"
mkdir -p "$package/DEBIAN" "$package/opt/rch" "$package/etc/rch" \
  "$package/usr/lib/systemd/system" "$package/usr/share/doc/rch-server" "$work/debian"
cp -a "$stage/." "$package/opt/rch/"
chmod 755 "$package/opt/rch/bin/"{r3akt-rch-server,r3akt-tak-service,reticulumd}
install -m 644 "$templates/"{rch-server.service,reticulumd.service} "$package/usr/lib/systemd/system/"
install -m 640 "$templates/rch-server.env" "$package/etc/rch/rch-server.env"
install -m 640 "$templates/config.ini" "$package/etc/rch/config.ini"
install -m 640 "$templates/reticulumd.toml" "$package/etc/rch/reticulumd.toml"
install -m 755 "$templates/"{postinst,prerm,postrm} "$package/DEBIAN/"
install -m 644 "$repo/LICENSE" "$package/usr/share/doc/rch-server/copyright"
printf '%s\n' /etc/rch/rch-server.env /etc/rch/config.ini /etc/rch/reticulumd.toml > "$package/DEBIAN/conffiles"

# Resolve dependencies against the build distribution, including the bundled daemon.
cat > "$work/debian/control" <<'EOF'
Source: rch-server
Section: net
Priority: optional
Maintainer: FreeTAKTeam <support@freetakteam.org>

Package: rch-server
Architecture: amd64
Description: Reticulum Community Hub Rust server
EOF
dependencies=$(cd "$work" && dpkg-shlibdeps -O \
  -e "$package/opt/rch/bin/r3akt-rch-server" \
  -e "$package/opt/rch/bin/r3akt-tak-service" \
  -e "$package/opt/rch/bin/reticulumd")
[[ "$dependencies" == shlibs:Depends=* ]] || { echo "Shared-library dependency resolution failed." >&2; exit 1; }
dependencies=${dependencies#shlibs:Depends=}
cat > "$package/DEBIAN/control" <<EOF
Package: rch-server
Version: $version
Architecture: amd64
Maintainer: FreeTAKTeam <support@freetakteam.org>
Section: net
Priority: optional
Depends: adduser, ca-certificates${dependencies:+, $dependencies}
Installed-Size: $(du -sk "$package/opt/rch" | cut -f1)
Homepage: https://github.com/FreeTAKTeam/Reticulum-Community-Hub
Description: Reticulum Community Hub Rust server and paired daemon
 Includes the shared operator UI and standalone TAK service.
 Configure the hub and Reticulum interfaces before manually starting services.
EOF
archive="rch-server_${version}_amd64.deb"
dpkg-deb --root-owner-group --build "$package" "$output/$archive"
(cd "$output" && sha256sum "$archive" > "$archive.sha256")
printf '%s\n' "$output/$archive" "$output/$archive.sha256"
