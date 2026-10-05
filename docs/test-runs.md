# Test runs — `mongodb8_cis` on RHEL 8, 9, 10

The runs we do now, in order. Setup and certificates: [test-environment.md](test-environment.md).

## How to run

- One VM at a time (`--limit <vm>`), each starting from its `base` snapshot. Add `-K` if sudo asks for a password on the VMs. Order: `rhel9-mongo`, then `rhel8-mongo`
  (different Python and SELinux module), then `rhel10-mongo` (FIPS and SELinux differ).
- **Every switch is changed in `sysconfig/group_vars/mongodb.yml`, not with `-e`** (see "Your variables" in
  [test-environment.md](test-environment.md)). The column "Set in group_vars" says what to change before the run.
- The five CIS rules that can lock users out or break clients (2.1, 2.2, 4.3, 4.4, 6.1) are **off by default** in the
  role; they sit commented out at the bottom of `group_vars/mongodb.yml`.
- After each run, take a screenshot of the important messages and the `PLAY RECAP` line, and fill in the results table.

| # | Run | Set in `group_vars/mongodb.yml` | Command (add `--limit <vm>`) | Expect |
|---|-----|-------------------------------|------------------------------|--------|
| T1 | Connection | — (safe defaults) | `ansible mongodb -m ping` | `pong` (Python found) |
| T2 | Install + Level 1 | — | `ansible-playbook playbooks/site.yml` | MongoDB Enterprise installed; 5.1 adds `auditLog: syslog`; reports 1.1, 3.1–3.4, 4.2 FAIL (no TLS yet), 7.1, 7.2 FAIL (0755); one restart |
| T3 | Rerun | — | same as T2 | `changed=0` |
| T4 | Level 2 preview | `mongodb8_cis_level_2: true` | `ansible-playbook playbooks/site.yml --check --diff` | Reports 4.1 FAIL (no TLS), 4.5, 5.2, 6.2, 6.3, 3.5; nothing changed |
| T5 | Level 2 | (keep) | `ansible-playbook playbooks/site.yml` | `changed=0` (5.3, 5.4 already compliant on a fresh install) |
| T6 | Certificates | — | `ansible-playbook playbooks/prep-tls.yml` | `/etc/pki/mongodb/server.pem`, `ca.pem`: owner `mongod`, 0600 |
| T7 | Risky rules on | uncomment the 5 `mongodb8_cis_rule_*` lines | `ansible-playbook playbooks/site.yml` | Admin `frqadminDB` created; authorization on; localhost bypass off; requireTLS; TLS 1.0/1.1 off; FIPS; port 27100 labelled `mongod_port_t`; one restart, `mongod` back on 27100 |
| T8 | Rerun, hardened | (keep) | same as T7 | `changed=0`; 3.2/3.5 list `frqadminDB@admin` (the role logs in over TLS) |
| T9 | SELinux extra | `mongodb8_cis_selinux_policy: true` | `ansible-playbook playbooks/site.yml` | RHEL 9/10: module built and loaded (`200 mongodb`), restart; RHEL 8: message only |
| T10 | Rerun, SELinux | (keep) | same as T9 | `changed=0`; report shows `mongod_t` |

**Before the next VM:** put `group_vars/mongodb.yml` back to the safe defaults (`mongodb8_cis_level_2: false`,
`mongodb8_cis_selinux_policy: false`, the five rule lines commented out) and revert that VM to `base`.

If `mongod` does not come back after a restart (the handler *"Wait for mongod to accept connections"* fails):
`sudo journalctl -u mongod -n 50` and `sudo tail -50 /var/log/mongodb/mongod.log` on the VM, note the error in the
results table and in the role's `docs/troubleshooting.md` (next: T-M7), then revert the snapshot.

## Checks on the VM (after T7 and T9)

```bash
getenforce                                         # Enforcing
ps -eZ | grep mongod                               # 8/9: mongod_t; 10: mongod_t only after T9
sudo semodule -lfull | grep mongodb                # T9 on 9/10: "200 mongodb"
sudo semanage port -l | grep mongod_port_t         # includes 27100
sudo ausearch -m AVC -ts today | grep -i mongo     # nothing
sudo grep -c "FIPS 140 mode activated" /var/log/mongodb/mongod.log
sudo grep -A12 '^net:' /etc/mongod.conf            # tls block, port 27100

# Login over TLS: certificate for the connection + user/password for the login
sudo mongosh --port 27100 --tls --tlsCAFile /etc/pki/mongodb/ca.pem --tlsCertificateKeyFile /etc/pki/mongodb/server.pem \
  --tlsAllowInvalidHostnames -u frqadminDB -p --authenticationDatabase admin --eval 'db.runCommand({ping: 1})'
# Must FAIL: no TLS
mongosh --port 27100 --eval 'db.runCommand({ping: 1})'
```

(`sudo` because `server.pem` is readable only by `mongod` and root.)

## Evidence

Screenshots go in [evidence-images/](evidence-images/), named `NN-<vm>-<test>-<what>.png`, for example
`01-rhel9-T2-install-level1.png`, `02-rhel9-T3-rerun-changed0.png`, `08-rhel9-T7-vm-checks.png`.

## Results

| Date | VM | Test | Command | Result | Notes | Image |
|------|----|------|---------|--------|-------|-------|
| | rhel8-mongo | T1 | `ansible mongodb -m ping --limit rhel8-mongo` | | | |
| 2026-10-01 13:47 | rhel8-mongo | T2 | `ansible-playbook playbooks/site.yml --limit rhel8-mongo -K` | ✅ `ok=36 changed=6 failed=0 skipped=60` | 6 changes = install (signing key, repo, packages, start service) + 5.1 `auditLog` + restart handler; mongod back up ("Wait for mongod to accept connections": ok) | [01](evidence-images/01-rhel8-T2-install-level1-changed6.png) |
| 2026-10-01 13:48 | rhel8-mongo | T3 | same as T2 | ✅ `ok=31 changed=0 failed=0 skipped=63` | Idempotent: nothing changed, no restart | [02](evidence-images/02-rhel8-T3-rerun-changed0.png) |
| | rhel8-mongo | T4 | | | | |
| | rhel8-mongo | T5 | | | | |
| 2026-10-01 | rhel8-mongo | T6 | `ansible-playbook playbooks/prep-tls.yml -K` (all 3 VMs at once) | ✅ `ok=4 changed=3 failed=0` | 3 changes = `/etc/pki/mongodb/` folder + `server.pem` + `ca.pem` (see "What T6 put on the VMs") | [05](evidence-images/05-all-T6-prep-tls-changed3.png) |
| 2026-10-01 14:30 | rhel8-mongo | T7 | 5 risky rules uncommented, `level_2: true`, then `ansible-playbook playbooks/site.yml --limit rhel8-mongo -K` | ✅ `ok=63 changed=9 failed=0 skipped=33` | Restart handler ran and mongod accepted connections on the **new port 27100** with SELinux enforcing (see "What T7 changed") | [07](evidence-images/07-rhel8-T7-risky-rules-changed9.png) |
| 2026-10-01 | rhel8-mongo | T8 | same as T7 (no changes to `group_vars`) | ✅ `ok=43 changed=0 failed=0 skipped=51` | Idempotent on a hardened server: every rule already compliant, no restart. The role's Section 2/3 reads now log in as `frqadminDB` over TLS on port 27100 | [08](evidence-images/08-rhel8-T8-rerun-hardened-changed0.png) |
| 2026-10-01 15:10 | rhel8-mongo | T9 | `mongodb8_cis_selinux_policy: true`, then `ansible-playbook playbooks/site.yml --limit rhel8-mongo -K` | ❌ `ok=53 changed=5 failed=1` | mongod did not restart (exit 14): SELinux denied unlinking the old `/tmp/mongodb-27100.sock`, labelled `mongod_tmp_t` by the replaced base module. **Role bug, fixed** (role `docs/troubleshooting.md` T-M7); host recovered with `rm /tmp/mongodb-*.sock` + `systemctl start mongod` | — |
| 2026-10-01 | rhel9-mongo | T6 | same run as rhel8-mongo T6 | ✅ `ok=4 changed=3 failed=0` | same 3 changes | [05](evidence-images/05-all-T6-prep-tls-changed3.png) |
| | rhel9-mongo | other tests | | | | |
| 2026-10-01 | rhel10-mongo | T4 | `mongodb8_cis_level_2: true`, then `ansible-playbook playbooks/site.yml --limit rhel10-mongo -K --check --diff` | ✅ `ok=38 changed=0 failed=0 skipped=56` | Preview (nothing written): no diff shown, so the real run will change nothing either; same counts as T5 (see below) | [04](evidence-images/04-rhel10-T4-level2-check-changed0.png) |
| 2026-10-01 | rhel10-mongo | T5 | `mongodb8_cis_level_2: true`, then `ansible-playbook playbooks/site.yml --limit rhel10-mongo -K` | ✅ `ok=38 changed=0 failed=0 skipped=56` | Expected: Level 2 ran (`ok=38` vs 31 for Level 1 only) but had nothing to fix, see below | [03](evidence-images/03-rhel10-T5-level2-changed0.png) |
| 2026-10-01 | rhel10-mongo | T6 | same run as rhel8-mongo T6 | ✅ `ok=4 changed=3 failed=0` | same 3 changes | [05](evidence-images/05-all-T6-prep-tls-changed3.png) |
| 2026-10-01 14:29 | rhel10-mongo | T7 | 5 risky rules uncommented, `level_2: true`, then `ansible-playbook playbooks/site.yml --limit rhel10-mongo -K` | ✅ `ok=63 changed=9 failed=0 skipped=33` | Restart handler ran and mongod accepted connections on the **new port 27100** (see "What T7 changed") | [06](evidence-images/06-rhel10-T7-risky-rules-changed9.png) |
| 2026-10-01 14:33 | rhel10-mongo | T8 | same as T7 (no changes to `group_vars`) | ✅ `ok=43 changed=0 failed=0 skipped=51` | Idempotent on a hardened server: every rule already compliant, no restart. The role's Section 2/3 reads now log in as `frqadminDB` over TLS on port 27100 | [09](evidence-images/09-rhel10-T8-rerun-hardened-changed0.png) |
| 2026-10-01 15:23 | rhel10-mongo | T9 | `mongodb8_cis_selinux_policy: true` **and** `mongodb8_cis_port: 27001` (changed from 27100), then `ansible-playbook playbooks/site.yml --limit rhel10-mongo -K` | ✅ `ok=57 changed=9 failed=0 skipped=41` | With the fixed role. MongoDB's module built and loaded, port moved 27100 → 27001 and labelled `mongod_port_t` (6.1), one restart, mongod back on 27001. Report before the restart: `unconfined_service_t` (RHEL 10 has no base `mongodb` module) | [10](evidence-images/10-rhel10-T9-selinux-port27001-changed9.png) |
| 2026-10-01 15:24 | rhel10-mongo | T10 | same as T9 | ✅ `ok=50 changed=0 failed=0 skipped=46` | Idempotent; report: **`mongod runs as system_u:system_r:mongod_t:s0`**, so mongod is now confined by MongoDB's policy | [11](evidence-images/11-rhel10-T10-rerun-mongod_t-changed0.png) |

RHEL 9 (`rhel9-mongo`) is tested with the same sequence, without screenshots.

### What T7 changed

T7 turned on the five rules that are off by default (2.1, 2.2, 4.3, 4.4, 6.1). One run applied all of them and
restarted mongod once:

| Rule | Change on the VM |
|------|------------------|
| 2.1 | admin user `frqadminDB` created (role `root` on `admin`), then `security.authorization: enabled` |
| 2.2 | `setParameter.enableLocalhostAuthBypass: false` |
| 4.3 | `net.tls.mode: requireTLS` with `/etc/pki/mongodb/server.pem` and `ca.pem` (from T6) |
| 4.1 / 4.2 | `net.tls.disabledProtocols: TLS1_0,TLS1_1` (now possible because 4.3 ran first in the same run) |
| 4.4 | `net.tls.FIPSMode: true` |
| 6.1 | port 27017 → 27100, labelled `mongod_port_t` for SELinux first |

The last handler, *"Wait for mongod to accept connections"*, waits on the **new** port (27100). `ok` there means
mongod started again with authorization, TLS, FIPS and the new port, and on RHEL 8 SELinux (which already confines
mongod as `mongod_t`) allowed the new port. The exact list of the 9 changed tasks is in the run output; the VM checks
below confirm each setting.

### What T6 put on the VMs, and what it is for

`prep-tls.yml` plays the company's certificate process (the role never makes certificates). It copied two files from
the laptop's test CA (`pki/`) to each VM, owned by `mongod`, mode 0600:

| File on the VM | From the laptop | Used for |
|----------------|-----------------|----------|
| `/etc/pki/mongodb/server.pem` | `pki/<vm>.pem` (certificate + private key) | mongod proves it is the real server (like the SSH host key); the role's own `mongosh` also shows it as its client certificate |
| `/etc/pki/mongodb/ca.pem` | `pki/ca.pem` | checks certificates: clients use it to trust mongod, mongod uses it to accept only clients signed by our CA |

Nothing in MongoDB changes yet: the files are only used once rule **4.3** turns on `requireTLS` in T7. They are what
`mongodb8_cis_tls_certificate_key_file` and `mongodb8_cis_tls_ca_file` in `group_vars` point to. The private CA key
(`pki/ca.key`) stays on the laptop.

### Why Level 2 (T4 preview and T5) returned `ok` with `changed=0`

A fresh MongoDB 8.0 install already meets both Level 2 rules that change files, and the others only report or are off:

| Rule | Type | In T5 |
|------|------|-------|
| 5.3 `systemLog.quiet: false` | Automated | compliant: the shipped `mongod.conf` does not set `quiet` (default `false`) |
| 5.4 `systemLog.logAppend: true` | Automated | compliant: the shipped `mongod.conf` has `logAppend: true` |
| 4.1 TLS 1.0/1.1 off | Automated | report `4.1 FAIL`: needs TLS first (4.3, T7) |
| 2.3, 4.4 | Automated | skipped: off by default (2.3 sharded clusters only; 4.4 risky, T7) |
| 3.5, 4.5, 5.2, 6.2, 6.3 | Manual | report only (6.3 changes only with `mongodb8_cis_javascript_needed: false`) |

So `changed=0` here means "already compliant or report-only", not "Level 2 did not run".

### What Level 1 did in T2 (defaults)

Level 1 has 13 rules. With the safe defaults only **one** of them changes the server; the rest report or are off:

| Rule | Type | In T2 |
|------|------|-------|
| 5.1 Audit logging | Automated | **applied**: `auditLog: {destination: syslog}` added to `/etc/mongod.conf`, then restart |
| 4.2 Weak TLS protocols | Automated | report `4.2 FAIL`: TLS is not on yet, and mongod refuses TLS settings without it |
| 1.1 Version/patches | Manual | report: installed version + where to check for updates |
| 3.1–3.4 Accounts, roles, service account | Manual | report: no database users yet; 3.3 PASS (runs as `mongod`) |
| 7.1 Key file permissions | Manual | report: not applicable (no key or TLS files yet) |
| 7.2 Database file permissions | Manual | report `7.2 FAIL`: `/var/lib/mongo` is 0755 (CIS wants 0770) |
| 2.1, 2.2, 4.3, 6.1 | Automated | **skipped**: off by default, turned on in T7 |

That is why Level 1 is quick: the Manual rules only report (CIS says a person decides), and the four rules that can
lock users out wait for T7. The other "skipping" lines are Level 2 rules (off until T4) and the SELinux extra (off until T9).

## Summary (testing closed 2026-10-01; VMs move to Proxmox)

| VM (inventory name) | OS actually running | Tested | Result |
|---------------------|---------------------|--------|--------|
| `rhel10-mongo` (192.168.122.56) | RHEL 10 | T4–T10 | ✅ all passed; SELinux extra confines mongod (`mongod_t`); FIPS, TLS, login, port 27100 → 27001 work |
| `rhel8-mongo` (192.168.122.83) | **RHEL 9.8** (mongod log: *"Red Hat Enterprise Linux release 9.8 (Plow)"*, kernel `el9_8`) | T2–T9 | ✅ T2–T8; ❌ T9 found the socket bug (fixed in the role, not re-run on this VM) |
| `rhel9-mongo` (192.168.122.62) | to confirm | same sequence, no screenshots | not recorded |

**Findings from the lab:**
- The role installs MongoDB 8.0 Enterprise, applies Level 1 and Level 2, and the risky rules (2.1, 2.2, 4.3, 4.4, 6.1)
  in one run with one restart; every rerun is `changed=0` (T3, T5, T8, T10).
- Rule 6.1 labels the new port `mongod_port_t` itself, so mongod starts on it with SELinux enforcing.
- Bug found and fixed: loading MongoDB's SELinux module on RHEL 9 left a socket with a label the new policy does not
  know, so mongod could not restart (T-M7). The fix was re-tested in a Rocky 9 container; **re-run T9 on RHEL 9**.

**Still to do (on Proxmox):**
1. Check which OS each inventory name really points to: `ansible mongodb -m setup -a 'filter=ansible_distribution*'`.
   The rows above marked `rhel8-mongo` ran on RHEL 9.8; **RHEL 8 is not tested yet**.
2. RHEL 8: T2–T10 (base SELinux module only, no module build; Python 3.6 with ansible-core 2.16).
3. RHEL 9: T9–T10 with the fixed role (module replaces the base one).

## Compliance check (rebuild branch, 2026-10-05)

Site values: `sysconfig/group_vars/mongodb/main.yml`. Each run picks a profile:

```bash
ansible-galaxy role install -r requirements.yml --force          # role from branch mongodb8-cis-rebuild
ansible mongodb -m setup -a 'filter=ansible_distribution*'        # confirm which OS each host really runs
ansible-playbook playbooks/site.yml -e @profiles/c1-level1-defaults.yml | tee runs/c1-$(date +%F).log
```

| Run | Profile | On | Proves |
|-----|---------|----|--------|
| C1 | `c1-level1-defaults.yml` | fresh VM | Level 1, safe defaults; rerun `changed=0` |
| C2 | `c2-level2-defaults.yml` | same VM | Level 2 defaults; rerun `changed=0` |
| — | `playbooks/prep-tls.yml` | same VM | TLS files in place for 4.3 |
| C3 | `c3-full-benchmark.yml` | same VM | full benchmark; rerun `changed=0`; then the role's `docs/cis-requirements.md` Verify commands |

Expected per rule: header of each profile file. Read the report lines with
`grep -E '[0-9]\.[0-9] (PASS|FAIL|REVIEW|NOT APPLICABLE)' runs/<file>.log`.
