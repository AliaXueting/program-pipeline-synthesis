FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
ENV RUSTUP_DIST_SERVER="https://static.rust-lang.org"
ENV RUSTUP_UPDATE_ROOT="https://static.rust-lang.org/rustup"
ENV CARGO_REGISTRIES_CRATES_IO_PROTOCOL=sparse
ENV CARGO_REGISTRIES_CRATES_IO_INDEX="sparse+https://index.crates.io/"
ENV CARGO_NET_GIT_FETCH_WITH_CLI=true
ENV GOPROXY="https://proxy.golang.org,direct"
ENV GOSUMDB=sum.golang.google.cn
ENV GOTOOLCHAIN=auto
ENV UV_INSECURE_HOST=""
ENV UV_INDEX_URL="https://pypi.org/simple"
ENV UV_EXTRA_INDEX_URL=https://pypi.org/simple
ENV UV_CACHE_DIR=/workspace/.cache/uv
ENV npm_config_registry="https://registry.npmjs.org/"
ENV npm_config_strict_ssl=false
ENV npm_config_cache=/workspace/.cache/npm
ENV PIP_INDEX_URL="https://pypi.org/simple"
ENV PIP_EXTRA_INDEX_URL=https://pypi.org/simple
ENV PIP_TRUSTED_HOST=""
ENV HOME=/workspace
ENV XDG_CACHE_HOME=/workspace/.cache
ENV PIP_CACHE_DIR=/workspace/.cache/pip
ENV PYTHONUSERBASE=/workspace/.local
ENV GOROOT=/usr/local/go
ENV GOPATH=/workspace/.go
ENV GOCACHE=/workspace/.cache/go-build
ENV PIP_BREAK_SYSTEM_PACKAGES=1
ENV PATH=/opt/programgym-venv/bin:/usr/local/go/bin:/workspace/.go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV PAGER=cat
ENV MANPAGER=cat
ENV LESS=-R
ENV TQDM_DISABLE=1
ENV VIRTUAL_ENV=/opt/programgym-venv
RUN apt-get update && apt-get install -y --no-install-recommends bash build-essential ca-certificates git make pkg-config python3 python3-pip curl wget xz-utils unzip zip bzip2 zstd patch file binutils python3-venv tar && rm -rf /var/lib/apt/lists/*
COPY programgym-go.tar.gz /tmp/programgym-go.tar.gz
RUN set -eux; rm -rf /usr/local/go; tar -C /usr/local -xzf /tmp/programgym-go.tar.gz; rm -f /tmp/programgym-go.tar.gz; if [ ! -x /usr/local/go/bin/go ]; then   echo "official Go tarball did not create /usr/local/go/bin/go" >&2; exit 1; fi; /usr/local/go/bin/go version
RUN python3 -m venv /opt/programgym-venv && /opt/programgym-venv/bin/python -m pip install --no-cache-dir --only-binary=:all: pytest pytest-xdist coverage
WORKDIR /workspace
ADD workspace.tar.gz /workspace/
COPY executable /workspace/executable
COPY download.sh /workspace/download.sh
RUN chmod 755 /workspace/download.sh
RUN ["bash","-lc","set -euo pipefail; cd /workspace; set -a; source /workspace/download.sh; set +a; python3 - <<'PY' > /etc/profile.d/programgym_download_env.sh\nimport os\nimport re\nimport shlex\nignored = {\"OLDPWD\", \"PWD\", \"SHLVL\", \"_\"}\nvalid_name = re.compile(r\"^[A-Za-z_][A-Za-z0-9_]*$\")\nfor key in sorted(os.environ):\n    if key in ignored or key.startswith(\"BASH_FUNC_\") or not valid_name.fullmatch(key):\n        continue\n    value = os.environ[key]\n    if \"\\n\" in value:\n        continue\n    print(f\"export {key}={shlex.quote(value)}\")\nPY\n"]
ENV BASH_ENV=/etc/profile.d/programgym_download_env.sh
RUN chmod 111 /workspace/executable
WORKDIR /workspace
# programgym-runtime-workspace-cleanup: v1
RUN ["bash","-lc","rm -f -- /workspace/download.sh /workspace/reference/build.sh && rm -rf -- /workspace/.programgym_build_env"]
# Harbor uses tests/ as the separate verifier build context. Start with the
# same toolchain as the agent, then remove every cleanroom workspace artifact.
RUN rm -rf /workspace/* /workspace/.[!.]* 2>/dev/null || true \
 && mkdir -p /workspace /tests

# Synthetic cleanroom Dockerfiles commonly install Ubuntu's pytest-xdist 2.5.0.
# Installing a newer pytest alone leaves that apt package importable and creates
# an incompatible mixed apt/pip stack (xdist 2.5 imports the removed py.log).
# Install and constrain the verifier test runner as one coherent pip toolchain.
RUN printf 'pytest<9\n' > /etc/pip-constraint.txt
ENV PIP_CONSTRAINT=/etc/pip-constraint.txt
RUN python3 -m pip install --no-cache-dir --disable-pip-version-check \
    'pytest<9' 'pytest-xdist>=3,<4' pytest-rerunfailures pytest-timeout

COPY test.sh /tests/test.sh
COPY programgym_evaluator.py /tests/programgym_evaluator.py
COPY programgym_task.json /tests/programgym_task.json
COPY blobs/ /tests/blobs/
RUN chmod +x /tests/test.sh
RUN ["bash","-lc","rm -f -- /workspace/download.sh /tmp/programgym-download.sh /tmp/download.sh /workspace/reference/build.sh && rm -rf -- /workspace/.programgym_build_env"]
