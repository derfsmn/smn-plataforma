#!/usr/bin/env bash
# Crea tu usuario propio con llave SSH y prende el firewall local.
# Antes, en tu equipo (PowerShell):  ssh-keygen -t ed25519   (Enter a todo)
#                                    scp "$env:USERPROFILE\.ssh\id_ed25519.pub" smnnatural@172.31.104.4:mi_llave.pub
# Uso en el servidor:  bash ~/asegurar_servidor.sh diego ~/mi_llave.pub
# No quita el usuario smnnatural ni cambia su contraseña.
set -euo pipefail
U=${1:-}; LLAVE=${2:-}
[ -n "$U" ] && [ -f "$LLAVE" ] || { echo "Uso: bash asegurar_servidor.sh <usuario> ~/mi_llave.pub"; exit 1; }
grep -q "^ssh-" "$LLAVE" || { echo "ERROR: $LLAVE no parece una llave pública SSH."; exit 1; }

# 1. Usuario con llave (sin contraseña: solo entra quien tiene la llave)
id "$U" >/dev/null 2>&1 || sudo adduser --disabled-password --gecos "" "$U"
sudo usermod -aG sudo,docker "$U"
echo "$U ALL=(ALL) NOPASSWD:ALL" | sudo tee "/etc/sudoers.d/90-$U" >/dev/null; sudo chmod 440 "/etc/sudoers.d/90-$U"
sudo install -d -m 700 -o "$U" -g "$U" "/home/$U/.ssh"
sudo install -m 600 -o "$U" -g "$U" "$LLAVE" "/home/$U/.ssh/authorized_keys"
# llave de GitHub (solo lectura) para que el nuevo usuario también pueda publicar
for f in smn_github smn_github.pub known_hosts; do [ -f ~/.ssh/$f ] && sudo install -m 600 -o "$U" -g "$U" ~/.ssh/$f "/home/$U/.ssh/$f"; done
echo "[usuario] $U creado, en sudo y docker, entra con tu llave."

# 2. Que los dos usuarios puedan publicar (carpeta de la plataforma compartida con el grupo docker)
if [ -d /datos/plataforma ]; then
  sudo chgrp -R docker /datos/plataforma
  sudo chmod -R g+rwX /datos/plataforma
  sudo find /datos/plataforma -type d -exec chmod g+s {} +
  echo "[permisos] /datos/plataforma compartida con el grupo docker"
fi

# 3. Firewall local: solo SSH, web y SQL Server (Docker abre aparte los puertos que publica)
sudo ufw allow 22/tcp >/dev/null
sudo ufw allow 80/tcp >/dev/null
sudo ufw allow 443/tcp >/dev/null
sudo ufw allow 1433/tcp >/dev/null
sudo ufw default deny incoming >/dev/null
sudo ufw --force enable
sudo ufw status verbose | head -20
echo
echo "=== Listo. SIN cerrar esta ventana, abre otra y prueba:  ssh $U@172.31.104.4 ==="
echo "=== Si entra sin pedir contraseña, ya puedes usar tu usuario. ==="
