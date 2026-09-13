#!/bin/bash
# install.sh, run ON the Oracle machine: the Shop & Pool Finder as a service on 127.0.0.1:8900 under
# /shopfinder, updated from GitHub every minute (the shape of MAHA_TRANSCRIBE_FLASK/install.sh), and
# a timer that refreshes the pool hours every morning. Caddy routes /shopfinder/* here
# (ABLETON_TEACHER/oracle/second.sh). No key is in the repo: update_pools.py reads
# /home/ubuntu/.shopfinder/anthropic_key (Claude Haiku; groq_key is the fallback), which deploy.sh
# (from the Mac) writes over ssh.
#   ssh teacher-vm 'bash -s' < install.sh
set -euo pipefail
REPO=https://github.com/markoboskoauroville/SHOP_FINDER.git
APP=/home/ubuntu/apps/shopfinder
DATA=/home/ubuntu/.shopfinder

echo "== code from GitHub"
mkdir -p /home/ubuntu/apps "$DATA"
if [ ! -d $APP/.git ]; then git clone -q $REPO $APP; fi
cd $APP && git pull -q --ff-only || true

echo "== service"
sudo tee /etc/systemd/system/shopfinder.service >/dev/null <<EOF
[Unit]
Description=Shop & Pool Finder (/shopfinder, :8900)
After=network-online.target
[Service]
User=ubuntu
WorkingDirectory=$APP
Environment=PYTHONUNBUFFERED=1
Environment=TZ=Europe/Zagreb
Environment=HOST=127.0.0.1
Environment=PORT=8900
Environment=PREFIX=/shopfinder
Environment=SHOPFINDER_DATA=$DATA
ExecStart=/usr/bin/python3 $APP/serve.py
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
sudo tee /usr/local/bin/shopfinder-update >/dev/null <<'EOF'
#!/bin/bash
cd /home/ubuntu/apps/shopfinder || exit 0
git fetch -q origin
LOCAL=$(git rev-parse @); REMOTE=$(git rev-parse @{u})
if [ "$LOCAL" != "$REMOTE" ]; then
  echo "$(date -Is) shopfinder update $LOCAL -> $REMOTE" >> /home/ubuntu/apps/update.log
  git pull -q --ff-only && sudo systemctl restart shopfinder
fi
EOF
sudo chmod +x /usr/local/bin/shopfinder-update
sudo tee /etc/systemd/system/shopfinder-update.service >/dev/null <<EOF
[Unit]
Description=shopfinder: pull from GitHub and restart when it changed
[Service]
Type=oneshot
User=ubuntu
ExecStart=/usr/local/bin/shopfinder-update
EOF
sudo tee /etc/systemd/system/shopfinder-update.timer >/dev/null <<EOF
[Unit]
Description=shopfinder: check GitHub every minute
[Timer]
OnBootSec=2min
OnUnitActiveSec=1min
[Install]
WantedBy=timers.target
EOF
echo "== the pool hours every morning (and at boot, so a woken machine has today's hours)"
sudo tee /etc/systemd/system/shopfinder-pools.service >/dev/null <<EOF
[Unit]
Description=shopfinder: today's pool hours from sportskiobjekti.hr
After=network-online.target
[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=$APP
Environment=TZ=Europe/Zagreb
Environment=SHOPFINDER_DATA=$DATA
ExecStart=/usr/bin/python3 $APP/update_pools.py
EOF
sudo tee /etc/systemd/system/shopfinder-pools.timer >/dev/null <<EOF
[Unit]
Description=shopfinder: refresh the pool hours at 06:15 Zagreb and 5 min after boot
[Timer]
OnBootSec=5min
OnCalendar=*-*-* 06:15:00 Europe/Zagreb
Persistent=true
[Install]
WantedBy=timers.target
EOF
echo "ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart shopfinder" | sudo tee /etc/sudoers.d/shopfinder-update >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now shopfinder.service shopfinder-update.timer shopfinder-pools.timer >/dev/null 2>&1
sudo systemctl restart shopfinder
sleep 2
systemctl is-active shopfinder
curl -s http://127.0.0.1:8900/shopfinder/health; echo
if [ -s "$DATA/anthropic_key" ] || [ -s "$DATA/groq_key" ]; then
  echo "== the first pool hours"
  sudo systemctl start shopfinder-pools.service && curl -s http://127.0.0.1:8900/shopfinder/health; echo
else
  echo "== no key yet at $DATA/anthropic_key (Claude Haiku reads the pool pages): from the Mac, bash deploy.sh key"
fi
