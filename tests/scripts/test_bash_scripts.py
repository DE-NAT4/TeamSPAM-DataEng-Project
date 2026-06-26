"""
Tests for deployment/deploy.sh and deployment/teardown.sh

Bash scripts can't be unit tested like Python, but we can still catch a
surprisingly large class of bugs:

  1. Syntax check  (bash -n)  — catches typos, unclosed quotes, bad substitutions
                                 without executing a single AWS call
  2. Argument validation       — deploy.sh uses `set -eu` so missing positional
                                 args cause an immediate non-zero exit
  3. Required variable checks  — critical variables must appear in the scripts
  4. shellcheck  (optional)    — static analysis; skipped if not installed

None of these tests call AWS or require credentials.
"""
import os
import shutil
import subprocess
import tempfile
import pytest

# Resolve paths relative to this file so tests work from any working directory
SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "deployment"))
DEPLOY_SH = os.path.join(SCRIPTS_DIR, "deploy.sh")
TEARDOWN_SH = os.path.join(SCRIPTS_DIR, "teardown.sh")

# Locate bash: try PATH first, then common Git for Windows install locations.
# This handles the common case where Git Bash exists but isn't on the
# PowerShell PATH (so plain "bash" fails with FileNotFoundError).
def _find_bash():
    import shutil
    found = shutil.which("bash")
    if found:
        return found
    candidates = [
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

BASH = _find_bash()
BASH_AVAILABLE = BASH is not None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def bash_syntax_check(script_path):
    """Run `bash -n <script>` and return the CompletedProcess."""
    return subprocess.run(
        [BASH, "-n", script_path],
        capture_output=True, text=True, check=False,
    )


def bash_run(script_path, args=None, env=None, timeout=10):
    """Run a bash script with optional args, returning CompletedProcess.

    Copies the script to a temp file first so that deploy.sh's self-modifying
    `sed -i 's/\\r//' "$0"` line cannot alter the real file in the repo.
    """
    with tempfile.NamedTemporaryFile(suffix=".sh", delete=False) as tmp:
        shutil.copy2(script_path, tmp.name)
        tmp_path = tmp.name
    try:
        cmd = [BASH, tmp_path] + (args or [])
        return subprocess.run(
            cmd, capture_output=True, text=True,
            env=env, timeout=timeout, check=False,
        )
    finally:
        os.unlink(tmp_path)


def shellcheck_available():
    """Return True if shellcheck is installed and on PATH."""
    try:
        result = subprocess.run(
            ["shellcheck", "--version"], capture_output=True, check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------------------
# File existence — sanity checks before anything else
# ---------------------------------------------------------------------------

def test_deploy_sh_exists():
    # If someone accidentally deleted or renamed the script this catches it immediately
    assert os.path.exists(DEPLOY_SH), f"deploy.sh not found at {DEPLOY_SH}"


def test_teardown_sh_exists():
    assert os.path.exists(TEARDOWN_SH), f"teardown.sh not found at {TEARDOWN_SH}"


requires_bash = pytest.mark.skipif(not BASH_AVAILABLE, reason="bash not found on this system")

# ---------------------------------------------------------------------------
# Syntax checks — `bash -n` parses the script without executing it
# ---------------------------------------------------------------------------

@requires_bash
def test_deploy_sh_syntax_is_valid():
    # A syntax error here would crash every deployment attempt
    result = bash_syntax_check(DEPLOY_SH)
    assert result.returncode == 0, (
        f"deploy.sh has syntax errors:\n{result.stderr}"
    )


@requires_bash
def test_teardown_sh_syntax_is_valid():
    result = bash_syntax_check(TEARDOWN_SH)
    assert result.returncode == 0, (
        f"teardown.sh has syntax errors:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Argument validation for deploy.sh
# ---------------------------------------------------------------------------

@requires_bash
def test_deploy_sh_fails_with_no_args():
    # deploy.sh starts with `set -eu`.  $1 (aws_profile) is unbound when no
    # args are passed, so bash immediately exits non-zero.
    # This guards against accidentally removing `set -eu` from the script.
    result = bash_run(DEPLOY_SH, args=[])
    assert result.returncode != 0, (
        "deploy.sh should exit non-zero when called with no arguments"
    )


@requires_bash
def test_deploy_sh_fails_with_only_one_arg():
    # $2 (your_name) is also required; one arg is not enough
    result = bash_run(DEPLOY_SH, args=["data-course"])
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# Content checks — critical variables and patterns must be present
# ---------------------------------------------------------------------------

def _read_script(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_deploy_sh_uses_set_eu():
    # `set -eu` makes the script fail fast on errors and unbound variables.
    # Without it, a missing variable would silently pass an empty string to AWS.
    content = _read_script(DEPLOY_SH)
    assert "set -eu" in content, "deploy.sh must contain 'set -eu' for safe error handling"


def test_deploy_sh_targets_correct_region():
    # The project deploys to eu-west-1; changing this would deploy to the wrong region
    content = _read_script(DEPLOY_SH)
    assert "eu-west-1" in content, "deploy.sh must target eu-west-1"


def test_teardown_sh_deletes_both_stacks():
    # The teardown must remove both the ETL stack and the deployment bucket stack
    content = _read_script(TEARDOWN_SH)
    assert "delete-stack" in content, "teardown.sh must call 'delete-stack'"
    assert "wait stack-delete-complete" in content, \
        "teardown.sh must wait for stack deletion to complete before continuing"


def test_teardown_sh_empties_buckets_before_delete():
    # S3 buckets must be emptied before CloudFormation can delete the stack.
    # The empty_stack_buckets function must be called before delete-stack.
    content = _read_script(TEARDOWN_SH)
    empty_pos = content.find("empty_stack_buckets")
    delete_pos = content.find("delete-stack")
    assert empty_pos != -1, "teardown.sh must define/call empty_stack_buckets"
    assert empty_pos < delete_pos, \
        "Buckets must be emptied BEFORE delete-stack is called"


def test_teardown_sh_waits_for_stack_b_before_deleting_stack_a():
    # Stack A (deployment bucket) must not be deleted until Stack B (ETL) is fully
    # gone, because Stack B's resources live inside Stack A's S3 bucket.
    # Expected ordering in the script:
    #   1. delete-stack  (Stack B)
    #   2. wait stack-delete-complete  (Stack B gone)
    #   3. delete-stack  (Stack A)
    content = _read_script(TEARDOWN_SH)
    first_delete_pos = content.find("delete-stack")
    first_wait_pos = content.find("wait stack-delete-complete")
    # Find the SECOND delete-stack call (Stack A), starting after the first one
    second_delete_pos = content.find("delete-stack", first_delete_pos + len("delete-stack"))
    assert first_delete_pos != -1 and first_wait_pos != -1 and second_delete_pos != -1, \
        "teardown.sh must have two delete-stack calls and a wait between them"
    assert first_delete_pos < first_wait_pos < second_delete_pos, \
        "Stack B must be deleted and waited on before Stack A is deleted"


def test_deploy_sh_skips_pip_install_when_env_var_set():
    # SKIP_PIP_INSTALL lets developers re-deploy without reinstalling packages.
    # This variable must be checked in the script.
    content = _read_script(DEPLOY_SH)
    assert "SKIP_PIP_INSTALL" in content, \
        "deploy.sh must respect the SKIP_PIP_INSTALL environment variable"


# ---------------------------------------------------------------------------
# shellcheck — optional static analysis (skipped if not installed)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not shellcheck_available(), reason="shellcheck not installed")
def test_shellcheck_deploy_sh():
    # shellcheck catches common bash pitfalls: unquoted variables, word splitting,
    # deprecated syntax, etc.  Install with: brew install shellcheck
    result = subprocess.run(
        ["shellcheck", DEPLOY_SH],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (
        f"shellcheck found issues in deploy.sh:\n{result.stdout}"
    )


@pytest.mark.skipif(not shellcheck_available(), reason="shellcheck not installed")
def test_shellcheck_teardown_sh():
    result = subprocess.run(
        ["shellcheck", TEARDOWN_SH],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (
        f"shellcheck found issues in teardown.sh:\n{result.stdout}"
    )
