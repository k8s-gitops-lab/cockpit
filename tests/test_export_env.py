from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "export-env.py"


def load_export_env():
    spec = importlib.util.spec_from_file_location("export_env", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ExportEnvTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_export_env()

    def test_shell_quote_handles_single_quotes(self) -> None:
        """Verifie l'echappement shell des valeurs contenant une apostrophe."""
        self.assertEqual(self.module.shell_quote("a'b"), "'a'\"'\"'b'")

    def test_main_exports_expected_variables(self) -> None:
        """Verifie que platform.yml est converti en exports shell attendus."""
        config = {
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
                    "cluster": "../cluster",
                    "platform": "../platform-cicd",
                    "gitops": "../platform-gitops",
                    "toolbox": "../toolbox",
                    "ciTemplates": "../ci-templates",
                },
                "ciTemplate": {
                    "projectPath": "root/ci-templates",
                    "projectName": "ci-templates",
                    "sourceDir": "../ci-templates",
                    "ref": "v1.2.3",
                    "file": "/gitlab-ci.yml",
                },
            },
            "versions": {
                "argocd": "v3.4.4",
                "kubernetes": "1.36.2",
                "kubernetesMinor": "1.36",
                "flannel": "v0.28.5",
                "metricsServer": "v0.8.1",
                "helm": "3.18.6",
                "localPathProvisioner": "v0.0.31",
                "traefikChart": "41.0.0",
                "metallbChart": "0.14.9",
                "gatewayApi": "v1.5.1",
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "platform.yml"
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

            stdout = io.StringIO()
            with mock.patch.dict(os.environ, {"CONFIG": str(config_path)}):
                with contextlib.redirect_stdout(stdout):
                    self.module.main()

        output = stdout.getvalue().splitlines()
        exports = dict(line.removeprefix("export ").split("=", 1) for line in output)

        self.assertEqual(exports["GITLAB_DOMAIN"], "'example.test'")
        self.assertEqual(exports["ARGOCD_VERSION"], "'v3.4.4'")
        self.assertEqual(exports["CLUSTER_REPO"], "'../cluster'")
        self.assertEqual(exports["CI_TEMPLATE_REF"], "'v1.2.3'")
        self.assertIn("PLATFORM_CONFIG", exports)

    def test_main_reports_missing_required_key(self) -> None:
        """Verifie qu'une cle obligatoire manquante est signalee."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "platform.yml"
            config_path.write_text("platform: {}\nversions: {}\n", encoding="utf-8")

            with mock.patch.dict(os.environ, {"CONFIG": str(config_path)}):
                with self.assertRaises(KeyError):
                    self.module.main()


if __name__ == "__main__":
    unittest.main()
