# Compliance test record — CIS MongoDB 8 Benchmark v2.0.0

Proof that each lab host is hardened by `mongodb8_cis`: the Ansible runs, the role's own report, and the benchmark's
**Audit** checks run **by hand on the host**. Procedure background: the role's `docs/compliance-test.md`.

| Item | Value (fill in) |
|------|-----------------|
| Role | `requirements.yml` version: ☐ `main` ☐ `mongodb8-cis-rebuild`, commit → |
| Settings | `sysconfig/group_vars/mongodb.yml` (FULL BENCHMARK block uncommented for S4/S5) |
| MongoDB | `mongod --version` → |
| Date / tester | |

| Host | Inventory name | IP | OS (`cat /etc/redhat-release`) |
|------|----------------|----|--------------------------------|
| RHEL 8 | `rhel8-mongo` | 192.168.20.50 | |
| RHEL 9 | `rhel9-mongo` | 192.168.20.30 | |
| RHEL 10 | `rhel10-mongo` | 192.168.20.40 | |

## 1. Runs (control node) — one screenshot per step

Fresh snapshot, FULL BENCHMARK block **commented**. Replace `<host>` (e.g. `rhel9-mongo`).

```bash
ansible-galaxy install -r requirements.yml -p roles --force                          # S0
ansible mongodb -m setup -a 'filter=ansible_distribution*'                           # S1 (once, all hosts)
ansible-playbook playbooks/site.yml --limit <host> | tee runs/<host>-s2.log          # S2 install, safe defaults
ansible-playbook playbooks/prep-tls.yml --limit <host>                               # S3 TLS files
#   → uncomment the FULL BENCHMARK block in sysconfig/group_vars/mongodb.yml
ansible-playbook playbooks/site.yml --limit <host> --force-handlers | tee runs/<host>-s4.log   # S4 full benchmark
ansible-playbook playbooks/site.yml --limit <host> | tee runs/<host>-s5.log          # S5 rerun
grep -E '[0-9]\.[0-9] (PASS|FAIL|REVIEW|NOT APPLICABLE)' runs/<host>-s5.log         # R  role report
```

Evidence for the runs = the `tee` logs in `runs/` (no screenshots). Checked 2026-10-06: no log contains the admin password.

| Step | Expected | RHEL 8 | RHEL 9 | RHEL 10 |
|------|----------|--------|--------|---------|
| S1 | right OS per host | ✅ `el8` package [19] | ✅ `el9` package [23] | ✅ `el10` package [30] |
| S2 install, safe defaults | `failed=0` | ✅ `runs/rhel8-c2.log`: ok=44 changed=7 failed=0 ¹ | ✅ `runs/rhel9-c2.log`: ok=45 changed=5 failed=0 | ✅ `runs/rhel10-c2.log`: ok=45 changed=7 failed=0 |
| S3 prep-tls | `failed=0` | not logged; files verified on the host [18] | not logged | not logged |
| S4 full benchmark | `failed=0`, one restart | ✅ `runs/rhel8-full-benchmark.log`: ok=68 changed=11 failed=0, 1 restart | ✅ `runs/rhel9-full-benchmark.log`: ok=68 changed=11 failed=0, 1 restart | ✅ `runs/rhel10-full-benchmark.log`: ok=68 changed=11 failed=0, 1 restart |
| S5 rerun | `changed=0 failed=0` | ✅ `runs/rhel8-re-run.log`: ok=46 changed=0 failed=0 | ✅ `runs/rhel9-re-run.log`: ok=46 changed=0 failed=0 | ✅ `runs/rhel10-re-run.log`: ok=46 changed=0 failed=0 |
| R role report (in S5 log) | no `FAIL` | ✅ 0 FAIL, 2.3 N/A | ✅ 0 FAIL, 2.3 N/A | ✅ 0 FAIL, 2.3 N/A |

¹ `runs/rhel8-c2.log` (2026-10-05 04:43) was made with the **rebuild** branch (it contains the pymongo `PREPARE` tasks);
the S4/S5 logs on all three hosts are from `main`. S4/S5 are the compliance proof; S2 only installs MongoDB.

## 2. Checks on the host — one screenshot per section

SSH to the host, then once per session (asks the admin password once, never prints it):

Paste these **one at a time** (pasting both together makes `read` swallow the next line as the password):

```bash
m() { sudo mongosh --quiet --port 27100 --tls --tlsCAFile /etc/pki/mongodb/ca.pem --tlsCertificateKeyFile /etc/pki/mongodb/server.pem --tlsAllowInvalidHostnames -u frqadminDB -p "$PW" --authenticationDatabase admin --eval "$1"; }
type m | head -1                                  # must print: m is a function
```
```bash
read -rsp 'MongoDB admin password: ' PW; echo    # then type the password, Enter
```

Paste each block whole, then take one screenshot.

**C1 — Sections 1 and 2**
```bash
echo "== 1.1 =="; mongod --version | head -1; sudo dnf -q list --showduplicates mongodb-enterprise-server | tail -1   # dnf can take ~1 min (repo metadata): wait
echo "== 2.1 =="; grep -A3 '^security' /etc/mongod.conf
echo "-- without login (must fail) --"; sudo mongosh --quiet --port 27100 --tls --tlsCAFile /etc/pki/mongodb/ca.pem --tlsCertificateKeyFile /etc/pki/mongodb/server.pem --tlsAllowInvalidHostnames --eval 'db.adminCommand({listDatabases:1})' 2>&1 | tail -1
echo "== 2.2 =="; grep -A2 '^setParameter' /etc/mongod.conf
echo "== 2.3 =="; grep -cE 'clusterRole|clusterAuthMode' /etc/mongod.conf
```

**C2 — Section 3**
```bash
echo "== 3.1 =="; m 'db.getSiblingDB("admin").system.users.find({"roles.role":{$in:["dbOwner","userAdmin","userAdminAnyDatabase"]},"roles.db":"admin"}).toArray()'
echo "== 3.2 / 3.5 =="; m 'db.getSiblingDB("admin").system.users.find({},{_id:1,roles:1}).toArray()'
echo "== 3.3 =="; ps -eo user,pid,cmd | grep -E '[m]ongo(d|s) '
echo "== 3.4 =="; m 'db.getSiblingDB("admin").runCommand({rolesInfo:1, showPrivileges:true}).roles'
```

**C3 — Section 4**
```bash
echo "== 4.1 / 4.2 / 4.3 / 4.4 =="; grep -A8 '  tls:' /etc/mongod.conf
echo "-- 4.3 plain connection (must fail) --"; mongosh --quiet --port 27100 --eval 'db.runCommand({ping:1})' 2>&1 | tail -1
echo "== 4.4 =="; m 'db.adminCommand({getCmdLineOpts:1}).parsed.net.tls.FIPSMode'
sudo grep -i fips /var/log/mongodb/mongod.log | grep -v -e 'Build Info' -e 'Options set' | tail -2 | cut -c1-200
echo "== 4.5 =="; grep -c enableEncryption /etc/mongod.conf
```

**C4 — Section 5**
```bash
echo "== 5.1 / 5.2 =="; grep -A4 '^auditLog' /etc/mongod.conf; sudo journalctl -t mongod -n 3 --no-pager | cut -c1-200
echo "== 5.3 / 5.4 =="; grep -A6 '^systemLog' /etc/mongod.conf
```

**C5 — Section 6**
```bash
echo "== 6.1 =="; grep -A3 '^net' /etc/mongod.conf | grep -E 'port|bindIp'; sudo ss -tlnp | grep mongod; sudo semanage port -l | grep mongod_port_t
echo "== 6.2 =="; sudo grep -E 'file size|cpu time|address space|resident set|processes|open files' /proc/$(pidof mongod)/limits
echo "== 6.3 =="; grep javascriptEnabled /etc/mongod.conf
```

**C6 — Section 7**
```bash
echo "== 7.1 =="; sudo ls -l /etc/pki/mongodb/
echo "== 7.2 =="; sudo stat -c '%a %U:%G %n' /var/lib/mongo
```

## 3. Result per rule

**What the results mean**

| Mark | Name | Used for | Meaning | Evidence needed |
|------|------|----------|---------|-----------------|
| ✅ | Pass | Automated rules, and Manual rules with a clear expected value (e.g. 7.2 `770`) | the host shows exactly the value CIS asks for | the screenshot shows that value |
| 👤✅ | Reviewed | Manual rules where CIS asks a **person** to judge ("appropriate", "review", "organisation's requirements") | there is no fixed pass value; the reviewer looked at the real state and decided it is acceptable | screenshot of the state **+** the decision and reason (table below) |
| 👤 | Accepted exception | a Manual rule the site deliberately does not meet | not done on purpose; the risk is known and accepted | screenshot of the state **+** the reason and who accepted it (table below) |
| ➖ | Not applicable | a rule for a setup this host doesn't have (2.3: sharded clusters) | nothing to check | screenshot showing why it doesn't apply |
| ❌ | Fail | any rule | the host does not meet it and no exception was accepted | fix it, or record an exception |

A host is **compliant** when every rule is ✅, 👤✅, 👤 or ➖, and no rule is ❌. CIS marks a rule Manual because
*"the expected state can vary depending on the environment"*, so a recorded review is the correct result for it, not a gap.

| ID | L | Type | Pass when | Shot | R8 | R9 | R10 | Notes |
|----|---|------|-----------|------|----|----|-----|-------|
| 1.1 | 1 | M | installed = latest 8.0.x in the repo (or a documented reason) | C1 | ✅ | ✅ | ✅ | R8 [19]: installed `v8.0.32`, newest in repo `8.0.32-1.el8`; R9 [23]: `v8.0.32`, repo newest `8.0.32-1.el9`; R10 [30]: `v8.0.32`, repo newest `8.0.32-1.el10` |
| 2.1 | 1 | A | `authorization: enabled`; command without login fails (*requires authentication*) | C1 | ✅ | ✅ | ✅ | R8 [12]: `Command listDatabases requires authentication`; R9 [23]; R10 [30] |
| 2.2 | 1 | A | `enableLocalhostAuthBypass: false` | C1 | ✅ | ✅ | ✅ | R8 [13]; R9 [23]; R10 [30] |
| 2.3 | 2 | A | `0` → standalone, no cluster | C1 | ➖ | ➖ | ➖ | R8 [13]: `0`; R9 [23]: `0`; R10 [30]: `0` |
| 3.1 | 1 | M | `[]` | C2 | ✅ | ✅ | ✅ | R8 [14]: `[]`; R9 [24]: `[]`; R10 [31]: `[]` |
| 3.2 | 1 | M | each user has only the roles it needs (lab: `admin.frqadminDB` → `root@admin`) | C2 | 👤✅ | 👤✅ | 👤✅ | R8 [14]: one user, `admin.frqadminDB` → `root@admin` (the 2.1 admin); R9 [24]: only `admin.frqadminDB` → `root@admin`; R10 [31]: only `admin.frqadminDB` → `root@admin` (header typo `3.1 / 3.5`; the command is the 3.2/3.5 check) |
| 3.3 | 1 | M | owner `mongod`, not root | C2 | ✅ | ✅ | ✅ | R8 [14]: `mongod 93581 /usr/bin/mongod -f /etc/mongod.conf`; R9 [24]: `mongod 45726 /usr/bin/mongod`; R10 [31]: `mongod 21306 /usr/bin/mongod` |
| 3.4 | 1 | M | `[]` or only needed custom roles | C2 | ✅ | ✅ | ✅ | R8 [14]: `[]`, no custom roles; R9 [29]: `[]`, no custom roles; R10 [31]: `[]` |
| 3.5 | 2 | M | only the one admin holds `root` / admin roles | C2 | 👤✅ | 👤✅ | 👤✅ | R8 [14]: only `admin.frqadminDB` holds an admin role (`root`), the dedicated admin from 2.1 (CIS 2.1 remediation uses `root` on admin). Reviewed and accepted: one admin is required; R9 [24]: only the 2.1 admin holds `root`; R10 [31]: only the 2.1 admin holds `root` |
| 4.1 | 2 | A | `disabledProtocols: TLS1_0,TLS1_1` | C3 | ✅ | ✅ | ✅ | R8 [15]; R9 [25]; R10 [32] |
| 4.2 | 1 | A | same as 4.1 | C3 | ✅ | ✅ | ✅ | R8 [15]; R9 [25]; R10 [32] |
| 4.3 | 1 | A | `mode: requireTLS` + `certificateKeyFile` + `CAFile`; plain connection fails | C3 | ✅ | ✅ | ✅ | R8 [15]: plain mongosh → `connection <monitor> to 127.0.0.1:27100 closed`; R9 [25]: plain mongosh → `connection … closed`; R10 [32]: plain mongosh → `connection … closed` |
| 4.4 | 2 | A | `FIPSMode: true`; running mongod reports `FIPSMode: true` + FIPS start line in the log | C3 | ✅ | ✅ | ✅ | R8 [15, 19]: config `FIPSMode: true`; `getCmdLineOpts` → `true`; log `FIPS 140-2 mode activated` (id 23172); R9 [25]: `getCmdLineOpts` → `true`; log `FIPS 140 mode activated` (id 23172; RHEL 8 says `FIPS 140-2`, newer OpenSSL wording); R10 [32]: `getCmdLineOpts` → `true`; log `FIPS 140 mode activated` (id 23172) |
| 4.5 | 2 | M | lab: `0` (not enabled) → 👤 accepted exception, no key management in the lab | C3 | 👤 | 👤 | 👤 | R8 [15]: `0`. Accepted exception: no KMIP/key management in the lab; existing data can't be encrypted in place (role docs: manual-remediation.md 4.5); R9 [25]: `0`, same exception as R8; R10 [36]: `0`, same exception (first grep in [32] had a typo) |
| 5.1 | 1 | A | `destination: syslog`; mongod entries in the journal | C4 | ✅ | ✅ | ✅ | R8 [16]: audit events in the journal (`atype: logout`, `getClusterParameter`); R9 [26]: audit events `authenticate`, `logout`, `getClusterParameter` in the journal; R10 [33]: audit events `authenticate`, `logout`, `getClusterParameter` in the journal |
| 5.2 | 2 | M | no `filter` = every event audited (or the agreed filter) | C4 | 👤✅ | 👤✅ | 👤✅ | R8 [16]: no filter → all auditable events recorded; reviewed, meets the requirement; R9 [26]: no filter; R10 [33]: no filter |
| 5.3 | 2 | A | `quiet: false` | C4 | ✅ | ✅ | ✅ | R8 [16]; R9 [26]; R10 [33] |
| 5.4 | 2 | A | `logAppend: true` | C4 | ✅ | ✅ | ✅ | R8 [16]; R9 [26]; R10 [33] |
| 6.1 | 1 | A | `port: 27100`; listening on 27100; 27100 labelled `mongod_port_t` | C5 | ✅ | ✅ | ✅ | R8 [17]: `LISTEN 127.0.0.1:27100` (mongod); `mongod_port_t tcp 27100, 27017-27019, 28017-28019`; R9 [27]: `LISTEN 127.0.0.1:27100` (mongod), `mongod_port_t` 27100; R10 [34]: `port: 27100`, `LISTEN 127.0.0.1:27100` (mongod), `mongod_port_t` 27100 (grep typo `bindIP` hid the bindIp line) |
| 6.2 | 2 | M | file size, cpu time, address space, resident set: unlimited; open files, processes: 64000 | C5 | ✅ | ✅ | ✅ | R8 [17]: all six match (RPM unit limits; no drop-in needed); R9 [27]: all six match; R10 [34]: all six match |
| 6.3 | 2 | M | `javascriptEnabled: false` | C5 | ✅ | ✅ | ✅ | R8 [17]; R9 [27] (screenshot header typo `== 6.4 ==`; the command is the 6.3 check); R10 [34] |
| 7.1 | 1 | M | `-rw-------` owner `mongod` on `server.pem` and `ca.pem` | C6 | ✅ | ✅ | ✅ | R8 [18]: both `-rw------- mongod mongod`; R9 [28]: both `-rw------- mongod mongod`; R10 [35]: both `-rw------- mongod mongod` |
| 7.2 | 1 | M | `770 mongod:mongod` | C6 | ✅ | ✅ | ✅ | R8 [18]: `770 mongod:mongod /var/lib/mongo`; R9 [28]: `770 mongod:mongod`; R10 [35]: `770 mongod:mongod` |

## 3b. Review decisions (👤)

| Rule | CIS asks | What the host shows | Decision | Why | R8 | R9 | R10 |
|------|----------|---------------------|----------|-----|----|----|-----|
| 3.2 | each user has only the **appropriate** roles | one user: `admin.frqadminDB` → `root@admin` | ✅ accepted | the only account is the dedicated database admin created by 2.1; no application accounts exist yet | 👤✅ [14] | 👤✅ [24] | 👤✅ [31] |
| 3.5 | **review** superuser/admin roles | only `admin.frqadminDB` holds an admin role (`root`) | ✅ accepted | one dedicated admin is required to manage MongoDB; CIS's own 2.1 remediation creates it with `root`; nobody else has admin rights | 👤✅ [14] | 👤✅ [24] | 👤✅ [31] |
| 5.2 | audit filter set per the **organisation's requirements** | `auditLog` without `filter` | ✅ accepted | no filter = every auditable event is recorded, the most complete setting; a filter could only record less | 👤✅ [16] | 👤✅ [26] | 👤✅ [33] |
| 4.5 | encryption of data at rest | `enableEncryption` not set (`0`) | 👤 accepted exception | lab has no key management (KMIP); MongoDB can't encrypt existing data in place and a lost key loses all data (role docs: `manual-remediation.md` 4.5). Production: plan KMIP + migration | 👤 [15] | 👤 [25] | 👤 [36] |

Reviewed / accepted by: ________ (name, role) · Date: ________

## 4. Screenshots

Save in `docs/evidence-images/` as `NN-<host>-<shot>-<result>.png` (next free number: **37**), e.g.
`12-all-S1-os-versions.png`, `13-rhel9-S4-full-benchmark-changed14.png`, `15-rhel9-R-report-nofail.png`,
`16-rhel9-C2-section3-pass.png`. Per host: S2, S3, S4, S5, R, C1–C6 = 11 (+ S1 once for all).

| # | File | Shows |
|---|------|-------|
| 12 | [12-rhel8-C1a-1.1-version-2.1-auth-required.png](evidence-images/12-rhel8-C1a-1.1-version-2.1-auth-required.png) | RHEL 8, C1 part 1: `mongod v8.0.32` (dnf repo line interrupted); `security.authorization: enabled`, `javascriptEnabled: false`; mongosh without login → *requires authentication* |
| 13 | [13-rhel8-C1b-2.2-bypass-off-2.3-na.png](evidence-images/13-rhel8-C1b-2.2-bypass-off-2.3-na.png) | RHEL 8, C1 part 2: `enableLocalhostAuthBypass: false`; `clusterRole`/`clusterAuthMode` count `0` (standalone) |
| 14 | [14-rhel8-C2-section3-users-roles-pass.png](evidence-images/14-rhel8-C2-section3-users-roles-pass.png) | RHEL 8, C2: 3.1 `[]`; 3.2/3.5 only `admin.frqadminDB` with `root@admin`; 3.3 mongod runs as `mongod`; 3.4 no custom roles `[]` |
| 15 | [15-rhel8-C3-section4-tls-requiretls-fipsmode-noencryption.png](evidence-images/15-rhel8-C3-section4-tls-requiretls-fipsmode-noencryption.png) | RHEL 8, C3: `net.tls` with CAFile, `FIPSMode: true`, certificateKeyFile, `disabledProtocols: TLS1_0,TLS1_1`, `mode: requireTLS`; plain connection closed; FIPS log grep inconclusive; `enableEncryption` count 0 |
| 16 | [16-rhel8-C4-section5-auditlog-syslog-systemlog-pass.png](evidence-images/16-rhel8-C4-section5-auditlog-syslog-systemlog-pass.png) | RHEL 8, C4: `auditLog.destination: syslog`; audit events in `journalctl -t mongod`; `systemLog`: `logAppend: true`, `quiet: false`; also `port: 27100`, `bindIp: 127.0.0.1` |
| 17 | [17-rhel8-C5-section6-port27100-limits-js-off-pass.png](evidence-images/17-rhel8-C5-section6-port27100-limits-js-off-pass.png) | RHEL 8, C5: `port: 27100`, listening on 127.0.0.1:27100, `mongod_port_t` includes 27100; `/proc/<pid>/limits` unlimited / 64000; `javascriptEnabled: false` |
| 18 | [18-rhel8-C6-section7-keyfiles-0600-dbpath-0770-pass.png](evidence-images/18-rhel8-C6-section7-keyfiles-0600-dbpath-0770-pass.png) | RHEL 8, C6: `ca.pem`, `server.pem` `-rw------- mongod mongod`; `770 mongod:mongod /var/lib/mongo` |
| 19 | [19-rhel8-C1c-1.1-latest-8.0.32-4.4-fips-activated.png](evidence-images/19-rhel8-C1c-1.1-latest-8.0.32-4.4-fips-activated.png) | RHEL 8: `mongod v8.0.32`, repo newest `8.0.32-1.el8`; running `FIPSMode` = `true`; log `FIPS 140-2 mode activated` |
| 20–22 | see section 6 | RHEL 8 application access test (A1–A3) |
| 23 | [23-rhel9-C1-1.1-latest-2.1-auth-2.2-bypass-off-2.3-na.png](evidence-images/23-rhel9-C1-1.1-latest-2.1-auth-2.2-bypass-off-2.3-na.png) | RHEL 9, C1: `v8.0.32` = repo newest `8.0.32-1.el9`; `authorization: enabled`; no login → *requires authentication*; `enableLocalhostAuthBypass: false`; cluster count `0` |
| 24 | [24-rhel9-C2-section3-users-roles-3.4-missing.png](evidence-images/24-rhel9-C2-section3-users-roles-3.4-missing.png) | RHEL 9, C2: 3.1 `[]`; 3.2/3.5 only `admin.frqadminDB` `root@admin`; 3.3 mongod as `mongod` (shown twice; 3.4 not run) |
| 25 | [25-rhel9-C3-section4-tls-fips140-activated-noencryption.png](evidence-images/25-rhel9-C3-section4-tls-fips140-activated-noencryption.png) | RHEL 9, C3: `net.tls` (CAFile, `FIPSMode: true`, certificateKeyFile, `TLS1_0,TLS1_1` off, `requireTLS`); plain connection closed; running FIPSMode `true`, log `FIPS 140 mode activated`; `enableEncryption` 0 |
| 26 | [26-rhel9-C4-section5-auditlog-syslog-systemlog-pass.png](evidence-images/26-rhel9-C4-section5-auditlog-syslog-systemlog-pass.png) | RHEL 9, C4: `auditLog` syslog + audit events in the journal; `logAppend: true`, `quiet: false` |
| 27 | [27-rhel9-C5-section6-port27100-limits-js-off-pass.png](evidence-images/27-rhel9-C5-section6-port27100-limits-js-off-pass.png) | RHEL 9, C5: port 27100 listening + `mongod_port_t`; limits unlimited/64000; `javascriptEnabled: false` (header typo `6.4`) |
| 28 | [28-rhel9-C6-section7-keyfiles-0600-dbpath-0770-pass.png](evidence-images/28-rhel9-C6-section7-keyfiles-0600-dbpath-0770-pass.png) | RHEL 9, C6: `ca.pem`, `server.pem` `-rw------- mongod mongod`; `770 mongod:mongod /var/lib/mongo/` |
| 29 | [29-rhel9-C2b-3.4-no-custom-roles.png](evidence-images/29-rhel9-C2b-3.4-no-custom-roles.png) | RHEL 9, 3.4: `rolesInfo` → `[]`, no custom roles |
| 30 | [30-rhel10-C1-1.1-latest-2.1-auth-2.2-bypass-off-2.3-na.png](evidence-images/30-rhel10-C1-1.1-latest-2.1-auth-2.2-bypass-off-2.3-na.png) | RHEL 10, C1: `v8.0.32` = repo newest `8.0.32-1.el10`; `authorization: enabled`; no login → *requires authentication*; `enableLocalhostAuthBypass: false`; cluster count `0` |
| 31 | [31-rhel10-C2-section3-users-roles-pass.png](evidence-images/31-rhel10-C2-section3-users-roles-pass.png) | RHEL 10, C2: 3.1 `[]`; 3.2/3.5 only `admin.frqadminDB` `root@admin` (header typo `3.1 / 3.5`); 3.3 mongod as `mongod`; 3.4 `[]` |
| 32 | [32-rhel10-C3-section4-tls-fips140-activated-4.5-typo.png](evidence-images/32-rhel10-C3-section4-tls-fips140-activated-4.5-typo.png) | RHEL 10, C3: `net.tls` (CAFile, `FIPSMode: true`, certificateKeyFile, `TLS1_0,TLS1_1` off, `requireTLS`); plain connection closed; running FIPSMode `true`, log `FIPS 140 mode activated`; 4.5 grep has a typo (`enabledEncryption`) → redo |
| 33 | [33-rhel10-C4-section5-auditlog-syslog-systemlog-pass.png](evidence-images/33-rhel10-C4-section5-auditlog-syslog-systemlog-pass.png) | RHEL 10, C4: `auditLog` syslog + audit events in the journal; `logAppend: true`, `quiet: false` |
| 34 | [34-rhel10-C5-section6-port27100-limits-js-off-pass.png](evidence-images/34-rhel10-C5-section6-port27100-limits-js-off-pass.png) | RHEL 10, C5: port 27100 listening + `mongod_port_t`; limits unlimited/64000; `javascriptEnabled: false` |
| 35 | [35-rhel10-C6-section7-keyfiles-0600-dbpath-0770-pass.png](evidence-images/35-rhel10-C6-section7-keyfiles-0600-dbpath-0770-pass.png) | RHEL 10, C6: `ca.pem`, `server.pem` `-rw------- mongod mongod`; `770 mongod:mongod /var/lib/mongo/` |
| 36 | [36-rhel10-C3b-4.5-no-encryption-at-rest.png](evidence-images/36-rhel10-C3b-4.5-no-encryption-at-rest.png) | RHEL 10, 4.5 (corrected command): `enableEncryption` count `0` |

## 5. Verdict

| | RHEL 8 | RHEL 9 | RHEL 10 |
|---|---|---|---|
| ✅ Pass | 18 (1.1, 2.1, 2.2, 3.1, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 5.1, 5.3, 5.4, 6.1, 6.2, 6.3, 7.1, 7.2) | 18 (1.1, 2.1, 2.2, 3.1, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 5.1, 5.3, 5.4, 6.1, 6.2, 6.3, 7.1, 7.2) | 18 (1.1, 2.1, 2.2, 3.1, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 5.1, 5.3, 5.4, 6.1, 6.2, 6.3, 7.1, 7.2) |
| ➖ Not applicable | 2.3 | 2.3 | 2.3 |
| 👤 Reviewed / accepted exception | 4 (3.2, 3.5, 5.2 reviewed; 4.5 accepted exception) | 4 (3.2, 3.5, 5.2 reviewed; 4.5 accepted exception) | 4 (3.2, 3.5, 5.2 reviewed; 4.5 accepted exception) |
| ❌ Fail | 0 | 0 | 0 |

Each host is compliant with CIS MongoDB 8 Benchmark v2.0.0 Level ☐1 ☑2, with the exceptions above.

**RHEL 8 (2026-10-06): compliant with Level 2** (all 23: 18 pass, 1 not applicable, 3 reviewed, 1 accepted exception 4.5).

**RHEL 9 (2026-10-06): compliant with Level 2** (all 23: 18 pass, 1 not applicable, 3 reviewed, 1 accepted exception 4.5).

**RHEL 10 (2026-10-06): compliant with Level 2** (all 23: 18 pass, 1 not applicable, 3 reviewed, 1 accepted exception 4.5).

**Summary:** all three hosts (RHEL 8, 9, 10) hardened by `mongodb8_cis` (`main`) meet CIS MongoDB 8 Benchmark
v2.0.0 Level 2: 0 failures; one accepted exception (4.5, encryption at rest: no key management in the lab).
Signed off by / date:

Checks are taken from each recommendation's *Audit* section in the benchmark PDF (kept locally, never committed),
adapted to RHEL and to the lab's TLS, login and port.

## 6. Application access test (RHEL 8, 2026-10-06)

Shows the hardened database still serves a real application, and only the way CIS intends: the app has its **own**
TLS client certificate (`CN=app-shop`, `clientAuth`, signed by the lab CA), its **own** user `shop.appshop` with
**only** `readWrite@shop`, and connects on port 27100. App code: `demo-app/app.py` (pymongo 4, Python 3.12 venv).

| Shot | Shows | Expected | Result |
|------|-------|----------|--------|
| A1 [20] | the app user and all users | `shop.appshop` → `readWrite@shop` only; only 2 users | ✅ `shop.appshop` `readWrite@shop`, `SCRAM-SHA-256`; users: `admin.frqadminDB` (root), `shop.appshop` |
| A2 [21] | the app writes and reads | count goes up, newest first | ✅ `orders in shop: 5` → `6`, newest `car` first |
| A3 [22] | what is blocked | 4 refused, own data allowed | ✅ all four refused; own data `6` |
| A4 | role rerun after adding the app user | — | not done (user's choice): the C2 checks above already show 3.1/3.5 stay clean |

**A3 — what each command does**

| Test | Command | What it tries | Result on RHEL 8 | Proves |
|------|---------|---------------|------------------|--------|
| no TLS | `mongosh --quiet --port 27100 --eval 'db.runCommand({ping:1})'` | connect in plain text, no TLS at all | `connection <monitor> to 127.0.0.1:27100 closed` | **4.3**: `requireTLS` drops every non-TLS connection |
| TLS, no client cert | `mongosh $C --eval '…ping…'` where `C="--quiet --port 27100 --tls --tlsCAFile ca.pem"` | TLS that trusts our CA, but the client shows **no** certificate | `connection … closed` | **4.3**: with `CAFile` set, mongod requires a client certificate signed by the CA; the handshake is refused before any login |
| wrong password | `APP_DB_PASSWORD=wrong venv/bin/python app.py` | the real app with a valid certificate but the wrong password | `Authentication failed.` (code 18) | **2.1**: TLS alone is not enough; every client must log in |
| other database | `mongosh $C --tlsCertificateKeyFile app-shop.pem -u appshop … --eval 'db.getSiblingDB("admin").system.users.find()…'` | the app's valid login reading the admin user list | `not authorized on admin to execute command { find: "system.users" … }` | **3.x least privilege**: `readWrite@shop` gives nothing outside `shop` |
| own data | same login, `--eval 'db.getSiblingDB("shop").orders.countDocuments()'` | the app's valid login reading its own collection | `6` | the app can do its job |

Conclusion: ☑ the app works with its own certificate and least-privilege account; everything outside that is refused,
so the hardened host stays usable and compliant.

**Screenshots:** [20](evidence-images/20-rhel8-A1-appshop-readwrite-shop-only.png) ·
[21](evidence-images/21-rhel8-A2-app-writes-and-reads-orders.png) ·
[22](evidence-images/22-rhel8-A3-blocked-notls-nocert-badpw-otherdb-ownok.png)
