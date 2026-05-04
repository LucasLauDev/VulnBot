# Kali Linux with OpenSSH for VulnBot Paramiko/SSH targets (see basic_config.yaml kali.*).
FROM kalilinux/kali-rolling

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-server \
    && mkdir -p /var/run/sshd \
    && echo 'root:kali123' | chpasswd \
    && printf '%s\n' 'PermitRootLogin yes' 'PasswordAuthentication yes' \
        > /etc/ssh/sshd_config.d/50-vulnbot.conf \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 22
# ssh-keygen -A on each start avoids missing host keys; sshd stays foreground for Docker.
CMD ["/bin/bash", "-c", "ssh-keygen -A && exec /usr/sbin/sshd -D -e"]
