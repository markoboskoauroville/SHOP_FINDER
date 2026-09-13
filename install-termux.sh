#!/data/data/com.termux/files/usr/bin/bash
# Install the Shop & Pool Finder in Termux. One command, no token (the repository is public):
#   curl -fsSL https://raw.githubusercontent.com/markoboskoauroville/SHOP_FINDER/main/install-termux.sh | bash
set -euo pipefail
REPO_URL="https://github.com/markoboskoauroville/SHOP_FINDER.git"
INSTALL_DIR="$HOME/SHOP_FINDER"
if [ -t 1 ]; then AM="\033[38;5;214m"; OK="\033[1;32m"; BAD="\033[1;31m"; OFF="\033[0m"; else AM=""; OK=""; BAD=""; OFF=""; fi
printf "\n  ${AM}Shop & Pool Finder${OFF}  the Zagreb shops and pools, on this phone\n\n"
printf "  %-12s " "python"; command -v python3 >/dev/null && printf "${OK}ok${OFF} $(python3 --version 2>&1)\n" || { printf "${BAD}MISSING${OFF}  pkg install python\n"; MISSING=1; }
printf "  %-12s " "git";    command -v git >/dev/null && printf "${OK}ok${OFF}\n" || { printf "${BAD}MISSING${OFF}  pkg install git\n"; MISSING=1; }
if [ "${MISSING:-}" = 1 ]; then pkg install -y python git; fi
if [ -d "$INSTALL_DIR/.git" ]; then git -C "$INSTALL_DIR" pull -q --ff-only; else git clone -q "$REPO_URL" "$INSTALL_DIR"; fi
chmod +x "$INSTALL_DIR/mapool"
bash "$INSTALL_DIR/mapool" install
printf "\n  done. ${AM}mapool${OFF} starts it (q quits, u updates). Standard library only, nothing to pip install.\n"
printf "  keys: the ⚙ gear on the page, or the keyring (keyring get anthropic / google) if it is installed.\n\n"
