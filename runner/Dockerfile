ARG BASE_IMAGE=ubuntu:22.04
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
#ENV TZ=Etc/UTC

RUN apt-get update -y && \
    apt-get install -y curl tar jq git sudo awscli tzdata

RUN useradd -m runner

WORKDIR /home/runner

# Download x86_64 GitHub Actions runner
RUN RUNNER_VERSION=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | jq -r '.tag_name' | sed 's/v//') && \
    curl -o actions-runner-linux-x64.tar.gz -L "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz" && \
    tar xzf actions-runner-linux-x64.tar.gz && \
    rm actions-runner-linux-x64.tar.gz

# Install dependencies as root
RUN ./bin/installdependencies.sh

# Entry point script
COPY entrypoint.sh /home/runner/entrypoint.sh
COPY runner_status.sh /home/runner/runner_status.sh
COPY job_started.sh /home/runner/job_started.sh
COPY job_completed.sh /home/runner/job_completed.sh
RUN chmod +x /home/runner/entrypoint.sh && chown runner:runner /home/runner/entrypoint.sh
RUN chmod +x /home/runner/runner_status.sh /home/runner/job_started.sh /home/runner/job_completed.sh && \
    chown runner:runner /home/runner/runner_status.sh /home/runner/job_started.sh /home/runner/job_completed.sh

ENV ACTIONS_RUNNER_HOOK_JOB_STARTED=/home/runner/job_started.sh \
    ACTIONS_RUNNER_HOOK_JOB_COMPLETED=/home/runner/job_completed.sh

USER runner

ENTRYPOINT ["/home/runner/entrypoint.sh"]
