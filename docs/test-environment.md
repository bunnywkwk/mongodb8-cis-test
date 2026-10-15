# Test environment — `mongodb8_cis` lab

How this lab is built: VMs, certificates, variables. How to **run** it: [../README.md](../README.md).
The role is installed from GitHub into `roles/mongodb8_cis` (`requirements.yml`); its design docs stay in that repo.

> **Revised 2026-10-06:** the lab moved from KVM on a Fedora laptop to **Proxmox** VMs; the role comes from
> `ansible-galaxy`, not a symlink; `docs/test-runs.md` and the profiles were replaced by the README run order.

## 1. The lab

| Part | Value |
|------|-------|
| Control node | AlmaLinux 10 workstation (earlier: Fedora 44 laptop with KVM) |
| Ansible | `~/.ansible-2.16.1-env`: ansible-core **2.16.19**. One environment for RHEL 8, 9 and 10 |
| Collections | `~/.ansible/collections`: `community.mongodb` 1.8.0, `community.general` 11.4.9 (+ `ansible.posix`) |
| SSH user on the VMs | `frqadmin` (sudo), key-based |

| VM | IP | OS |
|----|----|----|
| `rhel8-mongo` | 192.168.20.50 | RHEL 8, Minimal Install, SELinux enforcing |
| `rhel9-mongo` | 192.168.20.30 | RHEL 9, Minimal Install, SELinux enforcing |
| `rhel10-mongo` | 192.168.20.40 | RHEL 10, Minimal Install, SELinux enforcing |

Proxmox VMs with CPU type `host` (RHEL 10 needs x86-64-v3, MongoDB 8 needs AVX), registered to Red Hat so `dnf`
reaches BaseOS/AppStream, each with a fresh "base" snapshot. SSH key `~/.ssh/id_ed25519_cis` (set in the inventory).

## 2. Folder layout

See [../README.md](../README.md) "Layout". `ansible.cfg` sets `inventory = sysconfig/inventory.yml` and
`roles_path = roles`; `roles_path` is required because the playbooks sit in `playbooks/` (without it: *"the role
'mongodb8_cis' was not found"*).

## 3. One-time setup of the control node

See [../README.md](../README.md) §1. Collections must be the 2.16-compatible versions (`community.general` 11.x);
a newer `community.general` (12+/13.x) needs ansible-core 2.17/2.18+.

## 4. `pki/`: our own test certificates

### What it is

A small certificate authority (CA) that **we made ourselves** on the laptop with `openssl`, plus one certificate per
VM signed by it. It is **not official**: nobody outside this lab trusts it, and it is only meant for testing.
In a real company the certificates come from the company's CA (or a public one); MongoDB does not provide any.

### Why it is needed

Only for **CIS rule 4.3** (and the rules that build on it: 4.1, 4.2, 4.4). 4.3 sets `net.tls.mode: requireTLS`, so
`mongod` accepts **only encrypted (TLS) connections**. To do TLS, `mongod` needs two files on the VM:

- its own certificate and private key (`server.pem`): proves to clients that they talk to the real server;
- the CA certificate (`ca.pem`): used to check the certificates that clients present.

The role does not create certificates. It only points `mongod` at existing files, and 4.3 stops with a clear message
if they are missing. So for the test we need some certificates: that is what `pki/` is. Rules outside Section 4 do not
need it at all.

### Do you need a certificate to log in with the shell?

**Not on a default install.** MongoDB Enterprise as installed has no TLS and no login at all.
Two separate things are switched on by the CIS rules:

| | Switched on by | What a client (mongosh, an app) needs |
|---|---|---|
| **Login** (authentication) | rule 2.1: `security.authorization: enabled` | a **username and password** |
| **Encrypted connection** (TLS) | rule 4.3: `requireTLS` with a `CAFile` | `--tls`, the **CA certificate** to trust the server, and a **client certificate** |

The client certificate is needed because `net.tls.allowConnectionsWithoutCertificates` defaults to `false`. MongoDB
8.0 docs (configuration options): *"If `false`, all clients must provide client TLS certificates."* So after 4.3,
every client must present a certificate signed by the CA, **and** after 2.1 also log in with a user. The certificate is
for the connection; the user and password are for the login. (Logging in *with* a certificate instead of a password,
x.509 authentication, is a different feature that this role does not set up.)

What you see when something is missing (tested 2026-10-01 against MongoDB 8.0.32 Enterprise with requireTLS + CAFile):

| How you connect | mongosh says | mongod log says |
|-----------------|--------------|-----------------|
| plain `mongosh`, no `--tls` | `MongoServerSelectionError: connection ... closed` | `The server is configured to only allow SSL connections` |
| `--tls`, no `--tlsCAFile` | `MongoNetworkError: self-signed certificate in certificate chain` | — (the client refused the server) |
| `--tls --tlsCAFile`, no client certificate | `MongoServerSelectionError: connection ... closed` | `no SSL certificate provided by peer; connection rejected` |
| client certificate not signed by our CA | `MongoServerSelectionError: connection ... closed` | `SSL peer certificate validation failed: self-signed certificate` |
| `--tls --tlsCAFile --tlsCertificateKeyFile` | works (then needs `-u`/`-p` once 2.1 is on) | `Accepted TLS connection from peer` |

That is why each VM certificate here allows both uses (`serverAuth,clientAuth`): the role's own `mongosh` reuses
`server.pem` as its client certificate when TLS is on.

### What we ran (once, on the laptop)

```bash
cd ~/mongodb8-cis-test/pki

# 1. The CA: its private key (ca.key) and self-signed certificate (ca.pem), valid 30 days
openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.pem -days 30 -subj "/CN=mongodb8-cis-test-ca"

# 2. Per VM: a key + signing request, extensions, the signed certificate, and certificate+key in one file
for h in rhel8-mongo rhel9-mongo rhel10-mongo; do
  openssl req -newkey rsa:2048 -nodes -keyout $h.key -out $h.csr -subj "/CN=$h"
  printf "subjectAltName=DNS:$h,DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth,clientAuth\n" > $h.ext
  openssl x509 -req -in $h.csr -CA ca.pem -CAkey ca.key -CAcreateserial -out $h.crt -days 30 -extfile $h.ext
  cat $h.crt $h.key > $h.pem
done
```

| File | What it is | Goes to the VM? |
|------|------------|-----------------|
| `ca.key` | private key of our CA (signs certificates) | **no**, stays on the laptop |
| `ca.pem` | CA certificate | yes, as `/etc/pki/mongodb/ca.pem` |
| `ca.srl` | serial-number counter used by `openssl` | no |
| `<vm>.key` | VM private key | only inside `<vm>.pem` |
| `<vm>.csr` | signing request (input for step 2) | no |
| `<vm>.ext` | extensions: names the certificate is valid for (SAN) and its uses (server + client) | no |
| `<vm>.crt` | VM certificate, signed by our CA | only inside `<vm>.pem` |
| `<vm>.pem` | certificate + private key in one file, the format `mongod` wants | yes, as `/etc/pki/mongodb/server.pem` |

Check them any time:

```bash
openssl verify -CAfile pki/ca.pem pki/rhel9-mongo.crt                      # OK
openssl x509 -in pki/rhel9-mongo.crt -noout -subject -dates -ext subjectAltName,extendedKeyUsage
```

The certificates expire on **31 Oct 2026** (30 days). After that, rerun the commands above and `prep-tls.yml`.
Keep `pki/` private and out of git: it holds private keys.

## 5. `playbooks/prep-tls.yml`: put the certificates on the VMs

Plays the part of the company's certificate process: copies `ca.pem` and the VM's own `<vm>.pem` into
`/etc/pki/mongodb/`, owned by `mongod` with mode 0600 (what rule 7.1 expects). Run it **after MongoDB is installed**
(the `mongod` user must exist) and **before** the run that turns on rule 4.3 (FULL BENCHMARK block).

```bash
ansible-playbook playbooks/prep-tls.yml --limit rhel9-mongo
```

## 6. Your variables (`sysconfig/group_vars/mongodb.yml`)

All switches are set in this file, not with `-e`. The role checks them with plain `when: <variable>`, so they must be
**real YAML booleans**:

| Write | Means | Result |
|-------|-------|--------|
| `mongodb8_cis_level_2: true` | boolean true | OK: runs |
| `mongodb8_cis_level_2: false` | boolean false | OK: skipped |
| `mongodb8_cis_level_2: "false"` | **text**, not a boolean | Wrong: ansible-core 2.16 treats it as **true** and runs the rules (only a deprecation warning) |
| `mongodb8_cis_level_2: yes` / `no` | boolean in YAML 1.1, but not the project style (yamllint `truthy`) | avoid |

- **No quotes around `true`/`false`.** Quotes are only for text values: passwords, paths (`"changeme"`, `/etc/pki/...`).
- **Numbers** such as `mongodb8_cis_port: 27100` need no quotes either.
- **Turning a rule off:** set it to `false` or comment the line out (the role's default then applies; for the five
  risky rules the default is `false`).
- **If you ever need the command line**, use JSON so the value stays a boolean:
  `ansible-playbook playbooks/site.yml -e '{"mongodb8_cis_level_2": true}'`. Never `-e mongodb8_cis_level_2=false`:
  that is text, and 2.16 would run the rules anyway.
- **Check what Ansible sees** before a run:

```bash
ansible-inventory --host rhel9-mongo | grep mongodb8_cis
# "mongodb8_cis_level_2": true      <- no quotes around true/false = boolean, correct
# "mongodb8_cis_level_2": "false"   <- quotes = text, fix the file
```

## 7. Before every test session

```bash
cd ~/mongodb8-cis-test
source ~/.ansible-2.16.1-env/bin/activate
ansible --version                                  # core 2.16.x
ansible mongodb -m ping --limit rhel9-mongo        # pong
```

Then follow the run order in [../README.md](../README.md) §3.
