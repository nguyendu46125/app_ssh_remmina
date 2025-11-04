#!/bin/bash

APP_NAME="ssh_manager"
VERSION="1.0.0"
DEB_DIR="${APP_NAME}_deb"

echo "🔥 BUILD EXECUTABLE..."
pyinstaller --noconfirm --onefile --windowed \
  --icon=icon.png \
  --add-data "connections.db:." \
  --add-data "icon.png:." \
  --collect-all PyQt6 \
  --collect-all PyQt6.QtCore \
  --collect-all PyQt6.QtGui \
  --collect-all PyQt6.QtWidgets \
  --collect-all PyQt6.QtNetwork \
  --collect-all PyQt6.QtWebEngineWidgets \
  ssh_manager.py

echo "=== build deb: cleanup ==="
rm -rf "$DEB_DIR"
mkdir -p $DEB_DIR/DEBIAN
mkdir -p $DEB_DIR/usr/bin
mkdir -p $DEB_DIR/usr/share/$APP_NAME
mkdir -p $DEB_DIR/usr/share/applications
mkdir -p $DEB_DIR/usr/share/icons/hicolor/64x64/apps

echo "=== copy binary ==="
# copy pyinstaller binary into /usr/bin (or /usr/share and link)
cp dist/$APP_NAME $DEB_DIR/usr/bin/$APP_NAME
chmod 755 $DEB_DIR/usr/bin/$APP_NAME

echo "=== copy data ==="
cp connections.db $DEB_DIR/usr/share/$APP_NAME/
cp icon.png $DEB_DIR/usr/share/$APP_NAME/
cp icon.png $DEB_DIR/usr/share/icons/hicolor/64x64/apps/$APP_NAME.png

echo "=== desktop entry ==="
cat > $DEB_DIR/usr/share/applications/$APP_NAME.desktop <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=SSH Manager
Comment=SSH manager tool
Exec=/usr/bin/$APP_NAME
Icon=$APP_NAME
Terminal=false
Categories=Utility;
EOF

echo "=== control ==="
cat > $DEB_DIR/DEBIAN/control <<EOF
Package: ssh-manager
Version: $VERSION
Section: utils
Priority: optional
Architecture: amd64
Maintainer: You <you@example.com>
Description: SSH manager tool built with Python + PyQt6
Depends: python3, python3-pip
EOF

echo "=== postinst ==="
cat > $DEB_DIR/DEBIAN/postinst <<'EOF'
#!/bin/bash
set -e
TARGET_USER="${SUDO_USER:-$USER}"
USER_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)
mkdir -p "$USER_HOME/.ssh_manager" || true
if [ ! -f "$USER_HOME/.ssh_manager/connections.db" ]; then
    if [ -f /usr/share/ssh_manager/connections.db ]; then
        cp /usr/share/ssh_manager/connections.db "$USER_HOME/.ssh_manager/"
    fi
fi
chmod -R 755 "$USER_HOME/.ssh_manager" || true
# install runtime packages (best-effort, won't fail install)
if ! command -v pip3 >/dev/null 2>&1; then
    apt-get update || true
    apt-get install -y python3-pip || true
fi
pip3 install --no-cache-dir PyQt6 PyQt6-WebEngine paramiko || true
exit 0
EOF
chmod 755 $DEB_DIR/DEBIAN/postinst

echo "=== build deb ==="
dpkg-deb --build $DEB_DIR
echo "DONE: ${DEB_DIR}.deb"