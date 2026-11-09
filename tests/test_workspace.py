"""Run with: python3 -m unittest discover -s tests -v.

Podman is mocked; JSON import and container initialization execute real shell
code against a temporary home. The tmux environment test uses a real server.
"""

import json
import os
from pathlib import Path
import pty
import shutil
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "bin/workspace"
CONFIG = {
    "$schema": "https://pi.dev/schemas/models.schema.json",
    "providers": {
        "local-openai": {
            "baseUrl": "https://gateway.example.com/openai/v1/",
            "api": "openai-responses",
            "apiKey": "$OPENAI_API_KEY",
            "authHeader": False,
            "headers": {"api-key": "$OPENAI_API_KEY"},
            "models": [{"id": "example-model", "input": ["text"]}],
        }
    },
}

FAKE_PODMAN = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import subprocess
import sys

args = sys.argv[1:]
root = Path(os.environ["TEST_ROOT"])
with (root / "calls").open("a") as log:
    log.write(json.dumps(args) + "\n")
home = root / "container-home"
if args[0] == os.environ.get("TEST_FAIL_COMMAND"):
    print("podman: simulated runtime failure", file=sys.stderr)
    sys.exit(int(os.environ.get("TEST_FAIL_STATUS", "125")))
if args[:2] == ["container", "exists"]:
    sys.exit(0 if (root / "exists").exists() else 1)
if args[0] == "run":
    (root / "exists").touch()
    home.mkdir(exist_ok=True)
    env = dict(os.environ, HOME=str(home))
    for i, arg in enumerate(args):
        if arg == "-e":
            name, _, value = args[i + 1].partition("=")
            env[name] = value
    sys.exit(subprocess.run(["bash", os.environ["TEST_INIT"]], env=env).returncode)
if args[0] == "inspect":
    print("project")
if args[0] == "ps":
    print("ws-demo")
if args[0] == "rm":
    print("suppressed removal error", file=sys.stderr)
    sys.exit(1)
if args[0] == "exec":
    env = dict(os.environ, HOME=str(home))
    env.pop("OPENAI_API_KEY", None)
    i = 1
    while args[i].startswith("-"):
        if args[i] in ("-e", "-w"):
            if args[i] == "-e":
                name = args[i + 1]
                assert "=" not in name, "credentials must be passed by name"
                env[name] = os.environ[name]
            i += 2
        else:
            i += 1
    command = args[i + 1:]
    if command[0] == "sh":
        sys.exit(subprocess.run(command, env=env).returncode)
    assert command == ["tmux", "new", "-A", "-s", "main"]
    (root / "forwarded-key").write_text(env.get("OPENAI_API_KEY", ""))
'''


@unittest.skipUnless(shutil.which("jq"), "JSON import requires jq")
class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fake = self.root / "podman"
        fake.write_text(FAKE_PODMAN)
        fake.chmod(0o755)
        self.home = self.root / "container-home"
        self.target = self.home / ".pi/agent/models.json"
        self.source = self.root / "models with spaces.json"
        self.source.write_text(json.dumps(CONFIG, indent=2) + "\n")
        self.env = dict(
            os.environ,
            PATH=str(self.root) + os.pathsep + os.environ["PATH"],
            TEST_ROOT=str(self.root),
            TEST_INIT=str(ROOT / "image/init-workspace.sh"),
            HOME=str(self.root / "host-home"),
            WORKSPACE_ROOT=str(self.root / "projects"),
            WORKSPACE_SKILLS="",
            WORKSPACE_FOLDER="project",
        )
        self.env.pop("OPENAI_API_KEY", None)
        self.env.pop("WORKSPACE_MODELS_IMPORT", None)

    def run_workspace(self, *args, key=None):
        env = dict(self.env)
        if key is not None:
            env["OPENAI_API_KEY"] = key
        result = subprocess.run(
            [str(WORKSPACE), *map(str, args)],
            env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode:
            self.assertEqual(result.stderr.count("usage: workspace"), 1, result.stderr)
            self.assertIn("workspace: failed", result.stderr)
            self.assertLess(result.stderr.index("workspace: failed"), result.stderr.index("usage: workspace"))
        else:
            self.assertNotIn("usage: workspace", result.stderr)
        return result

    def calls(self):
        path = self.root / "calls"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def existing(self, contents):
        (self.root / "exists").touch()
        self.target.parent.mkdir(parents=True)
        self.target.write_text(contents)

    def test_import_preserves_custom_headers_and_environment_references(self):
        token = "secret-do-not-log"
        result = self.run_workspace("--verbose", "demo", "--models-file", self.source, key=token)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(token, result.stdout + result.stderr + self.target.read_text())
        self.assertNotIn(token, json.dumps(self.calls()))
        self.assertEqual((self.root / "forwarded-key").read_text(), token)
        creation = next(call for call in self.calls() if call[0] == "run")
        self.assertIn("WORKSPACE_MODELS_IMPORT=1", creation)
        self.assertNotIn("OPENAI_API_KEY", creation)
        self.assertIn("OPENAI_API_KEY", self.calls()[-1])

    def test_direct_openai_without_model_definitions(self):
        self.source.write_text('{"providers":{"openai":{"apiKey":"$OPENAI_API_KEY"}}}')
        result = self.run_workspace("demo", "--models-file", self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())
        self.assertNotIn("-e", self.calls()[-1])

    def test_invalid_files_fail_before_any_podman_command(self):
        invalid = [
            '{"providers":{},}', "[]", '{}', '{"providers":[]}',
            '{"providers":{"bad":null}}',
            '{"providers":{"bad":{"models":[{}]}}}',
            '{"providers":{"bad":{"models":[{"id":""}]}}}',
            '{"providers":{"bad":{"models":{}}}}',
            '{"providers":{}} {"providers":{}}',
        ]
        for content in invalid:
            with self.subTest(content=content):
                self.source.write_text(content)
                result = self.run_workspace("demo", "--models-file", self.source)
                self.assertEqual(result.returncode, 2)
                self.assertIn("invalid models.json", result.stderr)
                self.assertEqual(self.calls(), [])

    def test_replacement_requires_explicit_permission(self):
        original = '{"providers":{"ollama":{"models":[]}}}'
        self.existing(original)
        result = self.run_workspace("demo", "--models-file", self.source)
        self.assertEqual(result.returncode, 1)
        self.assertIn("--replace-models", result.stderr)
        self.assertEqual(self.target.read_text(), original)
        self.assertEqual(list(self.target.parent.glob(".models.json.*")), [])
        result = self.run_workspace("demo", "--models-file", self.source, "--replace-models")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())

    def test_recreated_container_protects_configuration_in_reused_volume(self):
        original = '{"providers":{"ollama":{"models":[]}}}'
        self.existing(original)
        (self.root / "exists").unlink()
        result = self.run_workspace("demo", "--models-file", self.source)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.target.read_text(), original)
        result = self.run_workspace("demo", "--models-file", self.source, "--replace-models")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())

    def test_identical_import_does_not_replace_file(self):
        self.existing(self.source.read_text())
        before = self.target.stat()
        result = self.run_workspace("demo", "--models-file", self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.stat().st_ino, before.st_ino)
        self.assertEqual(self.target.stat().st_mtime_ns, before.st_mtime_ns)

    def test_replacement_does_not_follow_target_symlink(self):
        self.existing("original")
        victim = self.root / "victim"
        victim.write_text("untouched")
        self.target.unlink()
        self.target.symlink_to(victim)
        result = self.run_workspace("demo", "--models-file", self.source, "--replace-models")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.target.is_symlink())
        self.assertEqual(victim.read_text(), "untouched")

    def test_no_import_keeps_default_ollama_and_existing_configuration(self):
        result = self.run_workspace("demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ollama", json.loads(self.target.read_text())["providers"])
        self.target.write_bytes(self.source.read_bytes())
        result = self.run_workspace("demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())

    def test_missing_mount_is_created_with_absolute_path_warning(self):
        mount = self.root / "missing parent" / "project with spaces"
        relative = os.path.relpath(mount)
        result = self.run_workspace("demo", "--mount", relative)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(mount.is_dir())
        self.assertIn(f"warning: created missing --mount directory: {mount}", result.stderr)
        creation = next(call for call in self.calls() if call[0] == "run")
        self.assertIn(f"{mount}:/home/dev/project", creation)

    def test_existing_mount_is_reused_without_creation_warning(self):
        mount = self.root / "existing project"
        mount.mkdir()
        sentinel = mount / "keep.txt"
        sentinel.write_text("keep")
        result = self.run_workspace("demo", "--mount", mount)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("created missing --mount", result.stderr)
        self.assertEqual(sentinel.read_text(), "keep")

    def test_rejected_mount_change_does_not_create_directory(self):
        self.existing(self.source.read_text())
        mount = self.root / "do-not-create" / "project"
        result = self.run_workspace("demo", "--mount", mount)
        self.assertEqual(result.returncode, 1)
        self.assertIn("mounts are set at creation", result.stderr)
        self.assertFalse(mount.parent.exists())
        self.assertNotIn("created missing --mount", result.stderr)

    def test_mount_cannot_be_a_regular_file(self):
        result = self.run_workspace("demo", "--mount", self.source)
        self.assertEqual(result.returncode, 2)
        self.assertIn("not a directory", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_mount_creation_failure_does_not_create_container(self):
        mount = self.source / "project"
        result = self.run_workspace("demo", "--mount", mount)
        self.assertEqual(result.returncode, 1)
        self.assertIn("could not create --mount directory", result.stderr)
        self.assertFalse(any(call[0] == "run" for call in self.calls()))

    def test_invalid_creation_settings_do_not_create_mount(self):
        self.env["WORKSPACE_FOLDER"] = "invalid/folder"
        mount = self.root / "do-not-create"
        result = self.run_workspace("demo", "--mount", mount)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(mount.exists())

    def test_bad_usage_and_missing_file(self):
        for args in [(), ("demo", "--replace-models"), ("demo", "--models-file"),
                     ("demo", "--models-file", self.root / "absent"),
                     ("demo", "--models-file", self.root),
                     ("ls", "--models-file", self.source),
                     ("rm", "demo", "--replace-models")]:
            with self.subTest(args=args):
                result = self.run_workspace(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.calls(), [])

    def test_missing_jq_explains_ubuntu_installation(self):
        path = self.root / "without-jq"
        path.mkdir()
        for command in ("bash", "realpath"):
            (path / command).symlink_to(shutil.which(command))
        self.env["PATH"] = str(path)
        result = self.run_workspace("demo", "--models-file", self.source)
        self.assertEqual(result.returncode, 2)
        self.assertIn("JSON validation tool", result.stderr)
        self.assertIn("Ubuntu host", result.stderr)
        self.assertIn("sudo apt-get update && sudo apt-get install -y jq", result.stderr)
        self.assertIn("run your workspace command again", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_podman_failures_preserve_status_and_show_error_then_help(self):
        cases = [
            ("container", ("demo",)),
            ("run", ("demo",)),
            ("start", ("demo",)),
            ("inspect", ("demo",)),
            ("exec", ("demo",)),
            ("ps", ("ls",)),
            ("volume", ("purge", "demo")),
        ]
        for command, args in cases:
            with self.subTest(command=command):
                self.env["TEST_FAIL_COMMAND"] = command
                result = self.run_workspace(*args, key="secret-do-not-log")
                self.assertEqual(result.returncode, 125)
                self.assertIn("podman: simulated runtime failure", result.stderr)
                self.assertLess(result.stderr.index("simulated runtime failure"), result.stderr.index("usage: workspace"))
                self.assertNotIn("secret-do-not-log", result.stderr)

    def test_missing_or_empty_api_key_warns_without_failing(self):
        for key in (None, ""):
            with self.subTest(key=key):
                result = self.run_workspace("demo", key=key)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("warning: OPENAI_API_KEY is not set or is empty", result.stderr)
                self.assertIn('export OPENAI_API_KEY="your-token"', result.stderr)
                self.assertIn("new tmux window/pane", result.stderr)
                self.assertIn("Other authentication methods may still work", result.stderr)
        result = self.run_workspace("ls")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("warning: OPENAI_API_KEY", result.stderr)

    def test_set_api_key_does_not_warn_or_expose_value(self):
        result = self.run_workspace("--verbose", "demo", key="secret-do-not-log")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("warning: OPENAI_API_KEY", result.stderr)
        self.assertNotIn("secret-do-not-log", result.stdout + result.stderr)

    def test_help_and_verbose_subcommands(self):
        for flag in ("--help", "-h"):
            result = self.run_workspace(flag)
            self.assertEqual(result.returncode, 0)
            self.assertIn("--models-file", result.stdout)
            self.assertEqual(result.stderr, "")
        for args in [("--verbose", "ls"), ("ls", "--verbose"),
                     ("rm", "demo", "--verbose"), ("--verbose", "purge", "demo")]:
            result = self.run_workspace(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("+ podman", result.stderr)
            self.assertNotIn("suppressed removal error", result.stderr)


@unittest.skipUnless(shutil.which("tmux"), "tmux is not installed")
class TmuxEnvironmentTests(unittest.TestCase):
    def test_key_updates_on_attach_for_new_panes(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "tmux.conf"
            settings = (ROOT / "image/tmux.conf").read_text().splitlines()
            config.write_text("\n".join(line for line in settings if line.startswith("set -ag update-environment")))
            base = ["tmux", "-S", str(Path(tmp) / "socket"), "-f", str(config)]
            env = dict(os.environ, TERM="xterm", OPENAI_API_KEY="first")
            try:
                subprocess.run([*base, "new", "-d", "-s", "main"], env=env, check=True, capture_output=True)
                for key in ("rotated", None):
                    client_env = dict(env)
                    if key is None:
                        client_env.pop("OPENAI_API_KEY")
                    else:
                        client_env["OPENAI_API_KEY"] = key
                    master, slave = pty.openpty()
                    client = subprocess.Popen([*base, "new", "-A", "-s", "main"], env=client_env, stdin=slave, stdout=slave, stderr=slave)
                    os.close(slave)
                    try:
                        expected = f"OPENAI_API_KEY={key}" if key else "-OPENAI_API_KEY"
                        deadline = time.monotonic() + 5
                        while time.monotonic() < deadline:
                            result = subprocess.run([*base, "show-environment", "-t", "main", "OPENAI_API_KEY"], capture_output=True, text=True)
                            if result.stdout.strip() == expected:
                                break
                            time.sleep(0.05)
                        self.assertEqual(result.stdout.strip(), expected)
                        probe = Path(tmp) / "pane-environment"
                        probe.unlink(missing_ok=True)
                        subprocess.run(
                            [*base, "new-window", "-t", "main", "-n", "probe",
                             f'printf "%s" "${{OPENAI_API_KEY-unset}}" > "{probe}"'],
                            check=True, capture_output=True,
                        )
                        deadline = time.monotonic() + 5
                        while time.monotonic() < deadline and not probe.exists():
                            time.sleep(0.05)
                        self.assertEqual(probe.read_text(), key if key else "unset")
                        subprocess.run([*base, "detach-client", "-s", "main"], check=True, capture_output=True)
                        client.wait(timeout=5)
                    finally:
                        if client.poll() is None:
                            client.kill()
                            client.wait()
                        os.close(master)
            finally:
                subprocess.run([*base, "kill-server"], capture_output=True)


if __name__ == "__main__":
    unittest.main()
