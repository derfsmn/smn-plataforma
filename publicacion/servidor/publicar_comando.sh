#!/usr/bin/env bash
# Se instala como /usr/local/bin/publicar.  Uso:  publicar v1.1
# Trae lo nuevo de GitHub y corre el publicar.sh DE ESA VERSIÓN.
set -euo pipefail
V=${1:-}
[ -n "$V" ] || { echo "Uso: publicar v1.1"; exit 1; }
export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/smn_github -o IdentitiesOnly=yes"
R=/datos/plataforma/repo.git
echo "Trayendo versiones de GitHub..."
git --git-dir=$R fetch -q --prune --tags origin '+refs/heads/*:refs/heads/*'
git --git-dir=$R rev-parse -q --verify "refs/tags/$V" >/dev/null || {
  echo "ERROR: $V no está en GitHub. Versiones que sí hay:"; git --git-dir=$R tag --sort=-creatordate | head -5
  echo "¿Ya corriste cerrar_version en tu laptop?"; exit 1; }
T=$(mktemp -d)
git --git-dir=$R show "$V:publicacion/servidor/publicar.sh" | tr -d '\r' > "$T/publicar.sh"
exec bash "$T/publicar.sh" "$V"
