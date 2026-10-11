# Code signing policy

**Status: signing is wired into the release workflow but switched on only when its settings are present.** A release
built without them is clearly marked "NOT code-signed" in its read-me, and Windows SmartScreen shows "unknown publisher".
Whether a given download is signed: right-click `LegacyPlayer.exe` > Properties > Digital Signatures, or let the installer
check it (it refuses a signature that is present but not valid).

## How releases are signed
The workflow `.github/workflows/release.yml` (copy: `tools/release.workflow.yml`) signs `LegacyPlayer.exe` in one of two
ways, both optional:

1. **Azure Artifact Signing** (formerly Trusted Signing), preferred. It runs when the repository **variables**
   `ARTIFACT_SIGNING_ACCOUNT` and `AZURE_CLIENT_ID` (plus `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
   `ARTIFACT_SIGNING_ENDPOINT`, `ARTIFACT_SIGNING_PROFILE`) are set. No key or secret is stored on GitHub: the workflow
   proves who it is to Azure with OIDC, and Azure holds the certificate. Set-up: [AZURE_SIGNING.md](AZURE_SIGNING.md).
   If these variables are set and signing fails, the release fails rather than shipping unsigned.
2. **Your own certificate (.pfx)**, used only when the exe is not already signed by step 1: repository **secrets**
   `WINDOWS_SIGN_PFX_BASE64` (the .pfx as base64) and `WINDOWS_SIGN_PFX_PASSWORD`. `tools/package_release.ps1` signs and
   time-stamps the exe with `Set-AuthenticodeSignature` before it is zipped and hashed.

With neither, the release is published unsigned and says so.

## What is signed
Only `LegacyPlayer.exe` as built by the GitHub Actions release workflow from a tag on a commit that is already on this
repository's `main` branch. The workflow enforces this: it fetches `origin/main` and stops unless
`git merge-base --is-ancestor <tagged commit> origin/main` succeeds, and it stops unless the tag matches `VERSION` in
`launcher/version.py`. It also runs `python tools/release_check.py` (the full test suite and repository check) before it
builds anything, and smoke-tests the built exe before publishing. Nothing built on a developer's computer is published as
a release (a locally built exe is signed only if the developer sets `LP_SIGN_PFX` / `LP_SIGN_PASS` for their own use).

## Roles
- **Author and reviewer:** Alec Maiatico (repository owner). Changes reach `main` by commit by the owner or by pull request
  that the owner reviews.
- **Approver of releases:** Alec Maiatico. Pushing a `v*` tag is the approval; only the owner can push tags, and only
  tags on `main` that match `launcher/version.py` get past the workflow.

Installed copies of Legacy Player update themselves to the newest release, so a signed release reaches every user: tag
only commits you would install yourself.

## Privacy
The signed program follows [PRIVACY.md](../PRIVACY.md): it sends nothing to anyone unless the user chooses to.

## Verifying a download
Compare its SHA-256 with `SHA256SUMS.txt` on the release page, and check the build attestation:
`gh attestation verify LegacyPlayer-<version>-win64.exe --repo Alpallyoop/legacy-player`.
