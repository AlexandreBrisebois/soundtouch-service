"""Linux child-only resource boundary: never call setrlimit/preexec_fn in Flask."""
import os
import resource
import shutil


def main():
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    executable = shutil.which('ffmpeg')
    if executable is None:
        raise SystemExit(1)
    # No shell, file input, network protocol, playlist demuxer, or user arguments.
    os.execv(executable, [executable, '-hide_banner', '-loglevel', 'error', '-nostdin',
        '-max_alloc', '16777216', '-protocol_whitelist', 'pipe', '-f', 'aac',
        '-threads', '1', '-i', 'pipe:0', '-map', '0:a:0', '-vn', '-sn', '-dn',
        '-threads', '1', '-c:a', 'libmp3lame', '-b:a', '128k', '-ar', '48000',
        '-ac', '2', '-write_xing', '0', '-id3v2_version', '0', '-f', 'mp3', 'pipe:1'])


if __name__ == '__main__':
    main()
