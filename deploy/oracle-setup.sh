#!/bin/sh
# One-time setup for a fresh Oracle Cloud Ubuntu server (22.04 / 24.04, ARM or x86).
# Installs Docker, opens ports 80/443 in the server firewall and adds swap.
#   sh deploy/oracle-setup.sh
set -e

echo "==> Installing Docker"
sudo apt-get update -y
sudo apt-get install -y docker.io docker-compose-v2 git iptables-persistent
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

echo "==> Opening ports 80 and 443 (Oracle's Ubuntu image blocks them by default)"
for port in 80 443; do
  sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null || \
    sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport "$port" -j ACCEPT
done
sudo netfilter-persistent save

echo "==> Adding 2 GB swap (helps on small instances)"
if [ ! -f /swapfile ]; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "==> Done. Log out and back in (so the docker group applies), then follow docs/DEPLOY_ORACLE.md step 5."
