"""Validate release refs and emit Docker tags before registry login or build."""
import os
from pathlib import Path
import re
import subprocess
import sys

VERSION = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"


def release_outputs(ref: str, repository: str) -> str:
    """Only explicit beta versions may bypass the stable main-ancestry guard."""
    if not ref.startswith('refs/tags/'):
        raise ValueError('A version tag ref is required')
    tag = ref.removeprefix('refs/tags/')
    if len(tag) > 128:
        raise ValueError('Docker tags must not exceed 128 characters')
    if re.fullmatch(rf'v{VERSION}-beta\.[1-9][0-9]*', tag):
        channel = 'beta'
    elif re.fullmatch(rf'v{VERSION}', tag):
        channel = 'stable'
    else:
        raise ValueError('Expected vMAJOR.MINOR.PATCH or vMAJOR.MINOR.PATCH-beta.N (N >= 1)')
    if not re.fullmatch(r'[a-z0-9]+(?:[._-][a-z0-9]+)*/soundtouch-service', repository):
        raise ValueError('Expected a Docker Hub namespace/soundtouch-service repository')
    # Resolve both annotated and lightweight tags; reject missing/mismatched checkout refs.
    commit = subprocess.check_output(
        ['git', 'rev-parse', '--verify', f'{ref}^{{commit}}'], text=True
    ).strip()
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if commit != head:
        raise ValueError('Checked-out commit does not match the release tag')
    if channel == 'stable':
        subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'origin/main'], check=True)
    tags = [f'{repository}:{tag}']
    if channel == 'stable':
        tags.append(f'{repository}:latest')
    return f'tag={tag}\nchannel={channel}\ntags<<RELEASE_TAGS\n' + '\n'.join(tags) + '\nRELEASE_TAGS\n'


def main() -> None:
    try:
        outputs = release_outputs(os.environ['GITHUB_REF'], os.environ['DOCKER_REPOSITORY'])
    except (ValueError, KeyError, subprocess.CalledProcessError) as error:
        sys.exit(f'Release rejected: {error}')
    with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as output:
        output.write(outputs)


if __name__ == '__main__':
    main()
