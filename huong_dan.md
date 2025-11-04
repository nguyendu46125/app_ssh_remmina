sudo apt update
sudo apt install -y libxcb1 libxcb-xinerama0 libxkbcommon-x11-0 libxcb-icccm4 libx11-6 libglu1-mesa libxcb-xtest0
# thêm nếu cần:
sudo apt install -y libxcb-render0 libxcb-render-util0 libxcb-keysyms1

chmod +x build_deb.sh
./build_deb.sh
sudo dpkg -i ssh_manager_deb.deb
sudo apt --fix-broken install -y
