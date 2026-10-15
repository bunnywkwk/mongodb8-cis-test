# mongodb8-cis-test — how to use `mongodb8_cis`

The lab project that runs the Ansible role [`mongodb8_cis`](https://github.com/bunnywkwk/mongodb-cis) against RHEL 8,
9 and 10 and proves the result. Use it as the example of how to apply the role: an inventory, one settings file, two
playbooks and a fixed run order. The role hardens a standalone MongoDB 8.0 Enterprise server to the
**CIS MongoDB 8 Benchmark v2.0.0**; this repo holds everything *around* it.

**Result (2026-10-06):** all three hosts compliant with **Level 2** (18 pass, 2.3 not applicable, 3 reviewed,
4.5 accepted exception, 0 fail). Record: [docs/compliance-test.md](docs/compliance-test.md).

> **Lab only.** This repo contains a plaintext lab password and is set up for a private test CA. For real servers use
> Ansible Vault for the password and your organisation's certificates.

## Layout

| Path | What it is |
|------|------------|
| `ansible.cfg` | inventory path and `roles_path = roles` |
| `requirements.yml` | the role (from GitHub, `version:` = branch) and its collections |
| `sysconfig/inventory.yml` | group `mongodb`: the three VMs, SSH user and key |
| `sysconfig/group_vars/mongodb.yml` | **all settings**: site values, TLS sources, levels, and the commented FULL BENCHMARK block |
| `playbooks/site.yml` | runs the role on group `mongodb` (`become: true`) |
| `playbooks/prep-tls.yml` | copies each host's certificate and the CA to `/etc/pki/mongodb/` (for rule 4.3) |
| `pki/` (not in git) | the lab CA and one certificate per host ([docs/test-environment.md](docs/test-environment.md) §4) |
| `demo-app/app.py` | a small app that uses the hardened database (TLS client cert + least-privilege user) |
| `runs/` (not in git) | `tee` logs of each run |
| `docs/` | lab details, compliance record, screenshots |

## 1. Set up the control node (once)

```bash
python3.12 -m venv ~/.ansible-2.16.1-env
~/.ansible-2.16.1-env/bin/pip install 'ansible-core>=2.16.1,<2.17'     # 2.16 = last version that manages RHEL 8
source ~/.ansible-2.16.1-env/bin/activate
cd ~/mongodb8-cis-test
ansible-galaxy install -r requirements.yml -p roles --force          # role → roles/mongodb8_cis
ansible-galaxy collection install -r requirements.yml               # community.mongodb 1.8.x, community.general 11.x
ansible mongodb -m ping                                             # pong from each host
ansible mongodb -m setup -a 'filter=ansible_distribution*'          # confirm which OS each name really is
```

To test another role version, change `version:` in `requirements.yml` (e.g. `mongodb8-cis-rebuild`) and reinstall.

## 2. Settings — `sysconfig/group_vars/mongodb.yml`

| Part | State | Contains |
|------|-------|----------|
| Install | on | `mongodb8_cis_install: true` — adds the Enterprise repo and installs MongoDB 8.0 on a fresh VM |
| Site values | on | admin user/password (2.1), TLS destination paths (4.3), port 27100 (6.1) |
| TLS sources | on | `lab_tls_cert_src` (`pki/<host>.pem`, cert + key) and `lab_tls_ca_src` (`pki/ca.pem`) for `prep-tls.yml` |
| Levels | on | `mongodb8_cis_level_1: true`, `mongodb8_cis_level_2: true` (all 23 rules) |
| **FULL BENCHMARK** | **commented** | the risky rules 2.1, 2.2, 2.3, 4.3, 4.4, 6.1 and the site decisions for 3.1, 3.4, 3.5, 5.2, 6.2, 6.3, 7.1, 7.2 |

Why the block starts commented: 4.3 needs the certificates on the host, and `prep-tls.yml` needs the `mongod` user,
which only exists after MongoDB is installed. So: install safely first, copy certificates, then switch everything on.

Write switches as unquoted `true`/`false`. Every role variable: the role's `defaults/main.yml`.

## 3. Run order (per host, fresh snapshot)

```bash
H=rhel9-mongo
ansible-playbook playbooks/site.yml --limit $H | tee runs/$H-c2.log                       # 1. install + safe defaults
ansible-playbook playbooks/prep-tls.yml --limit $H                                         # 2. certificates
#    3. uncomment the FULL BENCHMARK block in sysconfig/group_vars/mongodb.yml
ansible-playbook playbooks/site.yml --limit $H --force-handlers | tee runs/$H-full-benchmark.log   # 4. full benchmark
ansible-playbook playbooks/site.yml --limit $H | tee runs/$H-re-run.log                    # 5. rerun
```

| Step | Expected (lab logs) |
|------|---------------------|
| 1 | `failed=0`, about `changed=7` (repo, packages, service, auditLog, one restart) |
| 2 | `failed=0`; files `-rw------- mongod mongod` in `/etc/pki/mongodb/` |
| 4 | `ok=68 changed=11 failed=0`, **one** `RUNNING HANDLER [Restart mongod]` |
| 5 | `ok=46 changed=0 failed=0` — idempotent; the role's report has no `FAIL` |

`--force-handlers` makes mongod restart with what was already written even if a later task fails (T-M8).
Comment the block again before step 1 on the next fresh VM.

Read the role's own report: `grep -E '[0-9]\.[0-9] (PASS|FAIL|REVIEW|NOT APPLICABLE)' runs/$H-re-run.log`.
Read-only preview without changing anything: add `--check --diff`.

## 4. Check compliance on the host

[docs/compliance-test.md](docs/compliance-test.md) has six copy-paste blocks (C1–C6, one per CIS section) and the
expected result of each rule. On the host, define the `mongosh` helper first, then the password, **one line at a time**:

```bash
m() { sudo mongosh --quiet --port 27100 --tls --tlsCAFile /etc/pki/mongodb/ca.pem --tlsCertificateKeyFile /etc/pki/mongodb/server.pem --tlsAllowInvalidHostnames -u frqadminDB -p "$PW" --authenticationDatabase admin --eval "$1"; }
read -rsp 'MongoDB admin password: ' PW; echo
```

## 5. Connect an application

`demo-app/app.py` shows what a real client needs after hardening: its own TLS client certificate (signed by the CA,
`clientAuth`), its own user with only `readWrite` on its database, and port 27100. Steps and the "what is refused"
test: [docs/compliance-test.md](docs/compliance-test.md) §6.

## 6. Live demo (presentation)

**Before the meeting** (install takes minutes):
1. Revert `rhel9-mongo` to its fresh snapshot; FULL BENCHMARK block **commented**.
2. Run steps 1 and 2 of the run order. Check `ansible rhel9-mongo -m ping`.
3. Open two terminals: control node (`~/mongodb8-cis-test`) and `ssh frqadmin@192.168.20.30`.

**Live (~8 minutes):**

| # | Show | Command | Point to make |
|---|------|---------|---------------|
| 1 | config before | `sudo cat /etc/mongod.conf` (VM) | RPM defaults: no auth, no TLS, port 27017 |
| 2 | switch on | uncomment the FULL BENCHMARK block | values and switches live in one file |
| 3 | harden | `ansible-playbook playbooks/site.yml --limit rhel9-mongo --force-handlers` | `changed=11`, one restart |
| 4 | idempotent | same command again | `changed=0`: a compliant host is never touched |
| 5 | config after | `sudo cat /etc/mongod.conf` | auditLog, port 27100, TLS + FIPS, authorization, bypass off |
| 6 | refused | `mongosh --quiet --port 27100 --eval 'db.runCommand({ping:1})'` | no TLS → connection closed (4.3) |
| 7 | login required | C1 "without login" line | `requires authentication` (2.1) |
| 8 | FIPS live | `m 'db.adminCommand({getCmdLineOpts:1}).parsed.net.tls.FIPSMode'` | `true` (4.4) |

**Fallback** if the lab misbehaves: show the saved logs in `runs/` and the screenshots in `docs/evidence-images/`.

## 7. Lab notes

- The lab CA and host certificates expire **2026-10-31**; recreate them with the commands in
  [docs/test-environment.md](docs/test-environment.md) §4, then rerun `prep-tls.yml`.
- `pki/`, `roles/` and `runs/` are gitignored. Keep `pki/` private (private keys).
- Errors met during testing and their fixes: the role's `docs/troubleshooting.md` (T-M8 run order, T-M9 install first).
