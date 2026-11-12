#!/usr/bin/env python3
"""Cut RustDesk's CI down to what Santalvo Support needs, and make it private-safe.

- keeps only: Windows x64, macOS (Intel + Apple), Linux x64 .deb, Android arm64 + armv7
- injects our server name + key from repo secrets right after every checkout
- removes every public GitHub Release upload and every plain artifact upload of built apps
- adds one final step per job: encrypt the built installers with ARTIFACT_PASSWORD and
  upload only the encrypted files (*.enc) as workflow artifacts
- deletes the other upstream workflows (nightly, tag, CI, F-Droid, ...)

Run from the repo root after apply_branding.py.  Needs: pip install ruamel.yaml
"""
import copy
import sys
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString as L

APP = "SantalvoSupport"
WF = Path(".github/workflows")
KEEP_FILES = {"flutter-build.yml", "bridge.yml", "third-party-RustDeskTempTopMostWindow.yml", "santalvo-build.yml", "santalvo-tests.yml"}
KEEP_JOBS = {"validate-update-metadata-keys", "generate-bridge", "build-RustDeskTempTopMostWindow",
             "build-for-windows-flutter", "build-for-macOS", "build-rustdesk-android", "build-rustdesk-linux"}
MATRIX = {"build-for-windows-flutter": {"x86_64"}, "build-rustdesk-linux": {"x86_64"},
          "build-rustdesk-android": {"aarch64", "armv7"}, "build-for-macOS": {"x86_64", "aarch64"}}
# which files each job produces (bash globs, relative to the workspace) -> encrypted at the end
OUTPUTS = {"build-for-windows-flutter": "SignOutput/rustdesk-*.exe",
           "build-for-macOS": "rustdesk-*.dmg",
           "build-rustdesk-android": "signed-apk/*.apk",
           "build-rustdesk-linux": "rustdesk-*.deb"}
DROP_STEPS = {  # by job: step names removed outright
    "build-for-windows-flutter": {"Add MSBuild to PATH", "Build msi", "Build pre-built MSI template",
                                  "Upload unsigned msi template", "Upload unsigned template packer",
                                  "Build template packer", "Verify template payload signatures"},
    "build-rustdesk-linux": {"Patch archlinux PKGBUILD", "Build archlinux package", "Publish archlinux package"},
    "build-rustdesk-android": {"Upload Rustdesk library to Artifacts"},
}

GATE = {  # first job: stop the whole build at once if a secret is missing
    "name": "Check Santalvo secrets",
    "shell": "bash",
    "env": {"RENDEZVOUS_SERVER": "${{ secrets.RENDEZVOUS_SERVER }}", "RS_PUB_KEY": "${{ secrets.RS_PUB_KEY }}",
            "ARTIFACT_PASSWORD": "${{ secrets.ARTIFACT_PASSWORD }}"},
    "run": L('missing=""\n'
             'for v in RENDEZVOUS_SERVER RS_PUB_KEY ARTIFACT_PASSWORD; do [ -n "${!v}" ] || missing="$missing $v"; done\n'
             'if [ -n "$missing" ]; then echo "::error::Missing repository secrets:$missing (Settings > Secrets and variables > Actions)"; exit 1; fi\n'
             'echo "Secrets present."\n'),
}

INJECT = {
    "name": "Inject Santalvo server settings",
    "shell": "bash",
    "env": {"RENDEZVOUS_SERVER": "${{ secrets.RENDEZVOUS_SERVER }}", "RS_PUB_KEY": "${{ secrets.RS_PUB_KEY }}"},
    "run": "bash branding/inject_secrets.sh\n",
}


def encrypt_step(job, glob):
    return {
        "name": "Encrypt and upload Santalvo Support build",
        "if": "env.UPLOAD_ARTIFACT == 'true'",
        "shell": "bash",
        "env": {"ARTIFACT_PASSWORD": "${{ secrets.ARTIFACT_PASSWORD }}"},
        "run": L(
            'set -euo pipefail\n'
            'if [ -z "${ARTIFACT_PASSWORD:-}" ]; then echo "::error::secret ARTIFACT_PASSWORD missing"; exit 1; fi\n'
            'mkdir -p santalvo-out\n'
            'shopt -s nullglob\n'
            f'files=({glob})\n'
            'if [ ${#files[@]} -eq 0 ]; then echo "::error::no build output found"; exit 1; fi\n'
            'for f in "${files[@]}"; do\n'
            '  b=$(basename "$f")\n'
            f'  n="{APP}${{b#rustdesk}}"\n'
            '  sha256sum "$f" 2>/dev/null | awk -v n="$n" \'{print $1"  "n}\' >> santalvo-out/SHA256SUMS.txt || shasum -a 256 "$f" | awk -v n="$n" \'{print $1"  "n}\' >> santalvo-out/SHA256SUMS.txt\n'
            '  openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 -salt -pass env:ARTIFACT_PASSWORD -in "$f" -out "santalvo-out/$n.enc"\n'
            '  echo "encrypted $n"\n'
            'done\n'
        ),
    }


def upload_step(job):
    return {
        "name": "Upload encrypted build",
        "if": "env.UPLOAD_ARTIFACT == 'true'",
        "uses": "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "with": {"name": f"{APP}-{job}-${{{{ matrix.job.arch }}}}", "path": "santalvo-out/", "retention-days": 14},
    }


def main():
    src = (WF / "flutter-build.yml").read_text(encoding="utf-8")
    # renamed macOS bundle
    src = src.replace("RustDesk.app", f"{APP}.app").replace("Contents/MacOS/RustDesk", f"Contents/MacOS/{APP}")
    y = YAML(); y.preserve_quotes = True; y.width = 4096
    wf = y.load(src)
    wf["name"] = "Build Santalvo Support"
    wf["env"]["TAG_NAME"] = "unused"
    jobs = wf["jobs"]
    for j in list(jobs):
        if j not in KEEP_JOBS:
            del jobs[j]
    for j, job in jobs.items():
        if isinstance(job.get("needs"), list):
            job["needs"] = [n for n in job["needs"] if n in KEEP_JOBS]
        m = job.get("strategy", {}).get("matrix", {})
        if j in MATRIX and "job" in m:
            m["job"] = [e for e in m["job"] if e.get("arch") in MATRIX[j]]
            job["strategy"]["fail-fast"] = False
        steps = job.get("steps")
        if not steps:
            continue
        new = []
        for st in steps:
            uses = str(st.get("uses", ""))
            name = st.get("name", "")
            if "action-gh-release" in uses:
                continue                       # never publish public releases
            if j in OUTPUTS and "upload-artifact" in uses:
                continue                       # no plain uploads of built apps
            if name in DROP_STEPS.get(j, ()):
                continue
            if j == "build-rustdesk-linux" and name == "Build rustdesk":
                run = st["with"]["run"]
                cut = run.index("# rpm package")  # rpm specs still use the old paths: .deb only
                st["with"]["run"] = L(run[:cut])
            new.append(st)
            if "actions/checkout" in uses and j != "validate-update-metadata-keys":
                inj = copy.deepcopy(INJECT)
                if st.get("if"):
                    inj["if"] = st["if"]
                new.append(inj)
            if j == "validate-update-metadata-keys" and "actions/checkout" in uses:
                new.insert(0, copy.deepcopy(GATE))
        if j in OUTPUTS:
            new.append(encrypt_step(j, OUTPUTS[j]))
            new.append(upload_step(j))
        job["steps"] = new
    with open(WF / "flutter-build.yml", "w", encoding="utf-8") as f:
        y.dump(wf, f)
    for p in WF.iterdir():
        if p.name not in KEEP_FILES:
            p.unlink()
    print("workflow trimmed")


if __name__ == "__main__":
    main()
