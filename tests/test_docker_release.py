"""Release policy tests use local temporary Git repos; never publish images."""
import os
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / '.github/scripts/docker_release.py'
release_outputs = runpy.run_path(str(SCRIPT))['release_outputs']
REPOSITORY = 'example/soundtouch-service'


@pytest.fixture
def repository(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def git(*args):
        return subprocess.check_output(['git', *args], text=True).strip()

    git('init', '-q')
    git('config', 'user.email', 'test@example.invalid')
    git('config', 'user.name', 'Release test')
    git('commit', '--allow-empty', '-qm', 'main commit')
    git('update-ref', 'refs/remotes/origin/main', 'HEAD')
    return git


@pytest.mark.parametrize('tag', [
    'v1', 'v1.2', 'v01.2.3', 'v1.02.3', 'v1.2.03', 'v1.2.3-beta',
    'v1.2.3-beta.0', 'v1.2.3-beta.01', 'v1.2.3-beta.-1', 'v1.2.3-BETA.1',
    'v1.2.3-rc.1', 'v1.2.3+build', 'v1.2.3-beta.1+build', 'v1.2.3-beta.1/extra',
    'v1.2.3\nchannel=beta', 'v1.2.3;echo nope', 'v' + '9' * 125 + '.0.0',
])
def test_malformed_tags_rejected_before_git(tag, monkeypatch):
    monkeypatch.setattr(subprocess, 'check_output', lambda *a, **kw: pytest.fail('Invalid tag reached Git'))
    with pytest.raises(ValueError):
        release_outputs('refs/tags/' + tag, REPOSITORY)


def test_branch_ref_rejected():
    with pytest.raises(ValueError):
        release_outputs('refs/heads/main', REPOSITORY)


@pytest.mark.parametrize('annotated', [False, True])
@pytest.mark.parametrize('off_main', [False, True])
@pytest.mark.parametrize('beta', [False, True])
def test_release_matrix_and_exact_outputs(repository, annotated, off_main, beta):
    git = repository
    if off_main:
        git('commit', '--allow-empty', '-qm', 'feature commit')
    tag = 'v0.2.3-beta.1' if beta else 'v0.2.3'
    git('tag', *(['-a', '-m', 'release'] if annotated else []), tag)
    if off_main and not beta:
        with pytest.raises(subprocess.CalledProcessError):
            release_outputs('refs/tags/' + tag, REPOSITORY)
        return
    channel = 'beta' if beta else 'stable'
    latest = '' if beta else f'{REPOSITORY}:latest\n'
    assert release_outputs('refs/tags/' + tag, REPOSITORY) == (
        f'tag={tag}\nchannel={channel}\ntags<<RELEASE_TAGS\n'
        f'{REPOSITORY}:{tag}\n{latest}RELEASE_TAGS\n'
    )


def test_stable_ancestor_of_main_allowed(repository):
    git = repository
    git('tag', 'v1.2.3')
    git('commit', '--allow-empty', '-qm', 'later main')
    git('update-ref', 'refs/remotes/origin/main', 'HEAD')
    git('checkout', '-q', 'v1.2.3')
    assert ':latest\n' in release_outputs('refs/tags/v1.2.3', REPOSITORY)


def test_mismatched_checkout_rejected_even_for_beta(repository):
    repository('tag', 'v1.2.3-beta.1')
    repository('commit', '--allow-empty', '-qm', 'wrong checkout')
    with pytest.raises(ValueError, match='does not match'):
        release_outputs('refs/tags/v1.2.3-beta.1', REPOSITORY)


def test_missing_main_ref_fails_stable_but_not_beta(repository):
    repository('update-ref', '-d', 'refs/remotes/origin/main')
    repository('tag', 'v1.2.3')
    repository('tag', 'v1.2.3-beta.2')
    with pytest.raises(subprocess.CalledProcessError):
        release_outputs('refs/tags/v1.2.3', REPOSITORY)
    assert 'channel=beta\n' in release_outputs('refs/tags/v1.2.3-beta.2', REPOSITORY)


@pytest.mark.parametrize('ref', ['refs/tags/v1.2.3-beta.4', 'refs/tags/v1.2.3', 'refs/tags/v1oops'])
def test_cli_output_is_written_only_after_success(repository, tmp_path, ref):
    repository('commit', '--allow-empty', '-qm', 'off main')
    repository('tag', ref.removeprefix('refs/tags/'))
    output = tmp_path / 'output'
    output.write_text('existing=value\n')
    result = subprocess.run([sys.executable, str(SCRIPT)], env={
        **os.environ, 'GITHUB_REF': ref, 'GITHUB_OUTPUT': str(output),
        'DOCKER_REPOSITORY': REPOSITORY,
    }, capture_output=True, text=True)
    if '-beta.' in ref:
        assert result.returncode == 0, result.stderr
        assert output.read_text() == 'existing=value\n' + release_outputs(ref, REPOSITORY)
        assert 'latest' not in output.read_text()
    else:
        assert result.returncode != 0
        assert output.read_text() == 'existing=value\n'


def test_workflow_wires_validated_outputs_before_login():
    workflow = (ROOT / '.github/workflows/docker-publish.yml').read_text()
    assert "- 'v*'" in workflow
    assert 'fetch-depth: 0' in workflow
    assert workflow.index('run: python3 .github/scripts/docker_release.py') < workflow.index('uses: docker/login-action')
    assert 'tags: ${{ steps.release.outputs.tags }}' in workflow
    assert ':latest' not in workflow
    assert 'steps.extract_tag' not in workflow


@pytest.mark.parametrize('repository_name', ['', 'Upper/soundtouch-service', 'example/other', 'example/soundtouch-service\nRELEASE_TAGS\nchannel=stable'])
def test_invalid_repository_cannot_inject_outputs(repository_name, monkeypatch):
    monkeypatch.setattr(subprocess, 'check_output', lambda *a, **kw: pytest.fail('Invalid repository reached Git'))
    with pytest.raises(ValueError):
        release_outputs('refs/tags/v1.2.3-beta.1', repository_name)


def test_missing_tag_ref_fails_closed(repository):
    with pytest.raises(subprocess.CalledProcessError):
        release_outputs('refs/tags/v1.2.3-beta.1', REPOSITORY)
