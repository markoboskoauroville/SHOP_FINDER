#!/data/data/com.termux/files/usr/bin/bash
# shopfinder-v1.sh  -  control panel. Single keypress, no Enter.

WEBDIR="$HOME/storage/downloads/SHOP_FINDER"
SERVE="$WEBDIR/serve.py"
BOOT="$HOME/.termux/boot/start-server.sh"
LOG="$HOME/serve.log"
PORT="8080"
URL="http://localhost:$PORT"

if [ -t 1 ]; then
  C_OK="\033[1;32m"; C_WARN="\033[1;33m"; C_KEY="\033[1;37m"
  C_DIM="\033[0;90m"; C_CMD="\033[0;37m"; C_OFF="\033[0m"
else
  C_OK=""; C_WARN=""; C_KEY=""; C_DIM=""; C_CMD=""; C_OFF=""
fi

teach() {
  printf "${C_DIM}\$${C_OFF} ${C_CMD}%s${C_OFF}\n" "$1"
  eval "$1"
}

is_running() { pgrep -f "serve.py" >/dev/null 2>&1; }

start_server() {
  is_running && { printf "${C_WARN}already running${C_OFF} %s\n" "$URL"; return; }
  [ -f "$SERVE" ] || { printf "${C_WARN}serve.py missing${C_OFF}\n"; return; }
  teach "nohup python $SERVE >> $LOG 2>&1 &"
  sleep 1
  is_running && printf "${C_OK}started${C_OFF} %s\n" "$URL" \
             || printf "${C_WARN}failed, check log (l)${C_OFF}\n"
}

stop_server() {
  is_running && { teach "pkill -f serve.py"; sleep 1; printf "${C_OK}stopped${C_OFF}\n"; } \
             || printf "${C_DIM}not running${C_OFF}\n"
}

restart_server() { stop_server; start_server; }

show_log() {
  [ -f "$LOG" ] && teach "tail -n 20 $LOG" \
                || printf "${C_DIM}no log yet${C_OFF}\n"
}

open_url() { printf "${C_KEY}%s${C_OFF}\n" "$URL"; }

install_boot() {
  teach "mkdir -p $HOME/.termux/boot"
  cat > "$BOOT" << 'BOOTEOF'
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
test -d "$HOME/storage" || termux-setup-storage
sleep 5
exec python "$HOME/storage/downloads/SHOP_FINDER/serve.py" >> "$HOME/serve.log" 2>&1
BOOTEOF
  teach "sed -i 's/\\r\$//' $BOOT"
  teach "chmod +x $BOOT"
  printf "${C_OK}boot autostart installed${C_OFF}\n"
}

menu() {
  echo
  if is_running; then
    printf "  ${C_OK}running${C_OFF}  %s\n\n" "$URL"
  else
    printf "  ${C_WARN}stopped${C_OFF}\n\n"
  fi
  printf "  ${C_KEY}s${C_OFF}  start the server\n"
  printf "  ${C_KEY}t${C_OFF}  stop the server\n"
  printf "  ${C_KEY}r${C_OFF}  restart the server\n"
  printf "  ${C_KEY}o${C_OFF}  show the URL to open\n"
  printf "  ${C_KEY}l${C_OFF}  show the last log lines\n"
  printf "  ${C_KEY}b${C_OFF}  install boot autostart\n"
  printf "  ${C_KEY}q${C_OFF}  quit (server keeps running)\n"
  printf "\n  > "
}

while true; do
  menu
  IFS= read -rsn1 key
  printf "%s\n\n" "$key"
  key="$(printf '%s' "$key" | tr '[:upper:]' '[:lower:]')"
  case "$key" in
    s) start_server ;;
    t) stop_server ;;
    r) restart_server ;;
    o) open_url ;;
    l) show_log ;;
    b) install_boot ;;
    q) exit 0 ;;
    *) printf "${C_DIM}unknown key: %s${C_OFF}\n" "$key" ;;
  esac
done
