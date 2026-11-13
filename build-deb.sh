#!/bin/sh
# Build the AppStore package. Needs dpkg-deb and python3-pil, so run it on the
# CardputerZero (or any Debian box):  sh build-deb.sh "Name <email>"
# Output: zero-stocks_<version>_all.deb in this folder.
set -eu
cd "$(dirname "$0")"
VERSION=$(python3 -c "import json; print(json.load(open('app-builder.json'))['version'])")
PKG=zero-stocks
MAINTAINER=${1:?usage: build-deb.sh "Name <email>"}

umask 022
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT
chmod 755 "$ROOT"
APP=$ROOT/usr/share/$PKG
L=$ROOT/usr/share/APPLaunch
mkdir -p "$APP" "$L/bin" "$L/applications" "$L/share/images" "$ROOT/DEBIAN"

install -m 644 zero_stocks.py quotes.py views.py theme.py config.py keys.py hold_exit.py \
    add_ui.py settings_ui.py net.py "$APP/"
printf '#!/bin/sh\nexec /usr/bin/python3 /usr/share/%s/zero_stocks.py "$@"\n' "$PKG" > "$L/bin/$PKG"
chmod 755 "$L/bin/$PKG"
install -m 644 zero-stocks.desktop "$L/applications/$PKG.desktop"
python3 zero_stocks.py --make-icon "$L/share/images/$PKG.png"
chmod 644 "$L/share/images/$PKG.png"

cat > "$ROOT/DEBIAN/control" <<CTRL
Package: $PKG
Version: $VERSION
Architecture: all
Maintainer: $MAINTAINER
Depends: python3, python3-pil, python3-numpy
Section: utils
Priority: optional
Installed-Size: $(du -sk "$ROOT/usr" | cut -f1)
Description: Live stock watchlist and K-line charts for CardputerZero
 A watchlist with live prices and intraday sparklines for US, Hong Kong,
 Taiwan, China and Japan stocks, indices and crypto, plus a candlestick
 chart per stock with a selectable candle period (1 minute to 1 month).
 Data from Yahoo Finance; no API key needed.
CTRL

dpkg-deb --root-owner-group --build "$ROOT" "${PKG}_${VERSION}_all.deb"
