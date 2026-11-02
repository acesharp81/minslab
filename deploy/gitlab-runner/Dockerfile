FROM mcr.microsoft.com/dotnet/runtime-deps:8.0-noble

ARG RUNNER_VERSION=2.338.0
ARG RUNNER_SHA256=af4b794c1bc41d73d40535e3fe092a39f9679cd8d965954c2aca25a05ca41d32

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git python3 libicu74 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --user-group runner

WORKDIR /opt/actions-runner
RUN curl --fail --location --silent --show-error \
      "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz" \
      --output /tmp/runner.tar.gz \
    && printf '%s  %s\n' "${RUNNER_SHA256}" /tmp/runner.tar.gz | sha256sum --check - \
    && tar xzf /tmp/runner.tar.gz \
    && rm /tmp/runner.tar.gz

COPY entrypoint.sh /usr/local/bin/gitlab-runner-entrypoint
COPY job-guard.sh /usr/local/lib/minslab-gitlab-job-guard.sh
RUN chmod 755 /usr/local/bin/gitlab-runner-entrypoint /usr/local/lib/minslab-gitlab-job-guard.sh
USER 10001:10001
WORKDIR /home/runner
ENV DOTNET_PROCESSOR_COUNT=1
ENV ACTIONS_RUNNER_HOOK_JOB_STARTED=/usr/local/lib/minslab-gitlab-job-guard.sh
ENTRYPOINT ["/usr/local/bin/gitlab-runner-entrypoint"]
CMD ["run"]
