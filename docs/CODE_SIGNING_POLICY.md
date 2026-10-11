# Code signing policy

**Status: releases are not code-signed yet.** This page is the policy that applies once they are. The project applies for
free code signing from the SignPath Foundation (https://signpath.org); until the application is approved and wired in,
nothing here is claimed to be signed.

When enabled: free code signing provided by [SignPath.io](https://signpath.io), certificate by
[SignPath Foundation](https://signpath.org).

## What is signed
Only `LegacyPlayer.exe` as built by the GitHub Actions workflow `.github/workflows/release.yml` from a tagged commit on
this repository's `main` line. Nothing built on a developer's computer is submitted for signing.

## Roles
- **Author and reviewer:** Alec Maiatico (repository owner). Changes reach `main` by commit by the owner or pull request
  that the owner reviews.
- **Approver of signing requests:** Alec Maiatico. A signing request is approved only for a release tag that the
  version-check step in the workflow has matched to `launcher/version.py`.

## Privacy
The signed program follows [PRIVACY.md](../PRIVACY.md): it sends nothing to anyone unless the user chooses to.

## Verifying a download
Compare its SHA-256 with `SHA256SUMS.txt` on the release page, and check the build attestation:
`gh attestation verify LegacyPlayer-<version>-win64.exe --repo Alpallyoop/legacy-player`.
