#!/usr/bin/env python3
# Genere secrets/ghcr-pull-secret.yaml (secret K8s dockerconfigjson chiffre
# SOPS/age) a partir d'un compte + PAT GitHub. Remplace le parcours manuel
# (age-keygen, edition .sops.yaml, edition sops a la main du JSON docker
# config) par une seule commande, idempotente pour un operateur local.
#
# Cree la cle age locale si absente, l'enregistre comme unique recipient
# dans .sops.yaml (modele : un operateur = un environnement local), puis
# chiffre le secret.
#
# Usage :
#   python3 scripts/ghcr-token-init.py
#   # ou via make :
#   make ghcr-token-init
#
# Variables optionnelles (sinon prompt interactif) :
#   GITHUB_USERNAME, GITHUB_TOKEN, SOPS_AGE_KEY_FILE
import getpass
import json
import os
import re
import subprocess
import sys
from base64 import b64encode
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET_FILE = ROOT / "secrets" / "ghcr-pull-secret.yaml"
SECRET_TMP_FILE = ROOT / "secrets" / ".ghcr-pull-secret.tmp.yaml"
SOPS_CONFIG_FILE = ROOT / ".sops.yaml"
AGE_KEY_FILE = Path(os.environ.get("SOPS_AGE_KEY_FILE", str(Path.home() / ".config/sops/age/keys.txt")))
TOKEN_CREATE_URL = "https://github.com/settings/tokens/new?scopes=read:packages&description=ghcr-pull-k8s-gitops-lab"


def ensure_age_key() -> str:
    if AGE_KEY_FILE.exists():
        print(f"Cle age existante reutilisee : {AGE_KEY_FILE}")
    else:
        AGE_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["age-keygen", "-o", str(AGE_KEY_FILE)], check=True)
        AGE_KEY_FILE.chmod(0o600)
        print(f"Nouvelle cle age generee : {AGE_KEY_FILE}")

    for line in AGE_KEY_FILE.read_text().splitlines():
        if line.startswith("# public key:"):
            return line.split(":", 1)[1].strip()

    sys.exit(f"Cle publique introuvable dans {AGE_KEY_FILE}")


def ensure_sops_recipient(public_key: str) -> None:
    text = SOPS_CONFIG_FILE.read_text()
    if f"age: {public_key}" in text:
        print(".sops.yaml deja configure avec cette cle age.")
        return

    new_text, count = re.subn(r"(age:\s*)age1[0-9a-z]+", rf"\1{public_key}", text, count=1)
    if count == 0:
        sys.exit(f"Impossible de trouver une entree 'age:' a remplacer dans {SOPS_CONFIG_FILE}")

    SOPS_CONFIG_FILE.write_text(new_text)
    print(f".sops.yaml mis a jour avec la cle age locale ({public_key}).")


def prompt_credentials() -> tuple[str, str]:
    print()
    print("PAT GitHub requis, scope 'read:packages' (lecture des images GHCR).")
    print(f"Creation rapide : {TOKEN_CREATE_URL}")
    username = os.environ.get("GITHUB_USERNAME") or input("Compte GitHub (proprietaire du token) : ").strip()
    token = os.environ.get("GITHUB_TOKEN") or getpass.getpass("Token GitHub (saisie masquee) : ").strip()

    if not username or not token:
        sys.exit("Compte GitHub et token requis.")
    return username, token


def build_secret_yaml(username: str, token: str) -> str:
    auth = b64encode(f"{username}:{token}".encode()).decode()
    dockerconfigjson = json.dumps({
        "auths": {
            "ghcr.io": {"username": username, "password": token, "auth": auth},
        }
    })
    return (
        "apiVersion: v1\n"
        "kind: Secret\n"
        "metadata:\n"
        "    name: ghcr-pull-secret\n"
        "type: kubernetes.io/dockerconfigjson\n"
        "stringData:\n"
        f"    .dockerconfigjson: {json.dumps(dockerconfigjson)}\n"
    )


def encrypt_secret(plaintext: str) -> None:
    SECRET_TMP_FILE.write_text(plaintext)
    SECRET_TMP_FILE.chmod(0o600)
    try:
        result = subprocess.run(
            [
                "sops", "--encrypt",
                "--encrypted-regex", "^(stringData|data)$",
                str(SECRET_TMP_FILE.relative_to(ROOT)),
            ],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as exc:
        sys.exit(f"Echec du chiffrement sops : {exc.stderr.strip()}")
    finally:
        SECRET_TMP_FILE.unlink(missing_ok=True)

    SECRET_FILE.write_text(result.stdout)
    print(f"Secret chiffre ecrit dans {SECRET_FILE}")


def verify_secret() -> None:
    result = subprocess.run(
        ["sops", "--decrypt", str(SECRET_FILE.relative_to(ROOT))],
        cwd=ROOT, env={**os.environ, "SOPS_AGE_KEY_FILE": str(AGE_KEY_FILE)},
        capture_output=True, text=True,
    )
    if result.returncode != 0 or ".dockerconfigjson" not in result.stdout:
        sys.exit(f"Verification echouee : le secret chiffre n'est pas dechiffrable avec {AGE_KEY_FILE}.\n{result.stderr}")
    print("Verification OK : le secret est dechiffrable avec la cle age locale.")


def main() -> None:
    public_key = ensure_age_key()
    ensure_sops_recipient(public_key)
    username, token = prompt_credentials()
    encrypt_secret(build_secret_yaml(username, token))
    verify_secret()

    print()
    print("Termine. Prochaines etapes :")
    print("  - git status : verifier les changements (.sops.yaml, secrets/ghcr-pull-secret.yaml)")
    print("  - committer/pousser ces fichiers avant 'make platform-up' / 'make ghcr-pull-secret'")


if __name__ == "__main__":
    main()
