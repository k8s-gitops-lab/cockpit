from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "validate-workspace.py"


def load_validate_workspace():
    spec = importlib.util.spec_from_file_location("validate_workspace", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def valid_config(tmpdir: Path) -> dict:
    return {
        "platform": {
            "domain": "example.test",
            "gitlab": {
                "namespace": "gitlab",
                "internalHost": "gitlab.gitlab.svc:8181",
            },
            "argocd": {"namespace": "argocd"},
            "registry": {
                "namespace": "registry",
                "host": "registry.registry.svc:5000",
            },
            "repositories": {
                "cluster": str(tmpdir / "cluster"),
                "platform": str(tmpdir / "platform-cicd"),
                "gitops": str(tmpdir / "platform-gitops"),
                "toolbox": str(tmpdir / "toolbox"),
                "ciTemplates": str(tmpdir / "ci-templates"),
            },
            "ciTemplate": {
                "projectPath": "root/ci-templates",
                "projectName": "ci-templates",
                "sourceDir": str(tmpdir / "ci-templates"),
                "ref": "v1.2.3",
                "file": "/gitlab-ci.yml",
            },
        },
        "versions": {
            "kubernetes": "1.36.2",
            "kubernetesMinor": "1.36",
            "flannel": "v0.28.5",
            "metricsServer": "v0.8.1",
            "gatewayApi": "v1.5.1",
            "helm": "3.18.6",
            "localPathProvisioner": "v0.0.31",
            "metallbChart": "0.14.9",
            "traefikChart": "41.0.0",
            "argocd": "v3.4.4",
        },
    }


class ValidateWorkspaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_validate_workspace()

    def test_schema_accepts_complete_pinned_config(self) -> None:
        """Verifie qu'une configuration complete et epinglee est acceptee."""
        with tempfile.TemporaryDirectory() as tmpdir:
            errors = self.module.validate_schema(valid_config(Path(tmpdir)))
        self.assertEqual(errors, [])

    def test_schema_rejects_unpinned_ci_template_ref(self) -> None:
        """Verifie que la reference du template CI ne peut pas pointer sur main."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = valid_config(Path(tmpdir))
            config["platform"]["ciTemplate"]["ref"] = "main"
            errors = self.module.validate_schema(config)
        self.assertIn(
            "platform.ciTemplate.ref must be pinned, not main/master/latest",
            errors,
        )

    def test_workspace_validates_required_make_targets(self) -> None:
        """Verifie que les repos voisins exposent les cibles Make requises."""
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            config = valid_config(tmpdir)

            makefiles = {
                "cluster": "up:\ncreate-cluster:\ndown:\ndestroy:\n",
                "platform-cicd": (
                    "bootstrap:\nstatus:\nargocd-password:\ngitlab-password:\n"
                ),
                "toolbox": "gitlab-seed:\nargocd-repo-creds:\n",
            }
            for repo, makefile_content in makefiles.items():
                repo_path = tmpdir / repo
                repo_path.mkdir()
                (repo_path / "Makefile").write_text(makefile_content, encoding="utf-8")

            (tmpdir / "platform-gitops").mkdir()
            (tmpdir / "ci-templates").mkdir()
            config_path = tmpdir / "platform.yml"
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

            errors = self.module.validate_workspace(config, config_path)

        self.assertEqual(errors, [])

    def test_workspace_reports_missing_target(self) -> None:
        """Verifie qu'une cible Make manquante est reportee explicitement."""
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            config = valid_config(tmpdir)

            for repo in (
                "cluster",
                "platform-cicd",
                "toolbox",
                "platform-gitops",
                "ci-templates",
            ):
                (tmpdir / repo).mkdir()

            (tmpdir / "cluster" / "Makefile").write_text("up:\n", encoding="utf-8")
            (tmpdir / "platform-cicd" / "Makefile").write_text(
                "bootstrap:\nstatus:\nargocd-password:\ngitlab-password:\n",
                encoding="utf-8",
            )
            (tmpdir / "toolbox" / "Makefile").write_text(
                "gitlab-seed:\nargocd-repo-creds:\n",
                encoding="utf-8",
            )
            config_path = tmpdir / "platform.yml"
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

            errors = self.module.validate_workspace(config, config_path)

        self.assertIn("missing Make target cluster:create-cluster", errors)


if __name__ == "__main__":
    unittest.main()
