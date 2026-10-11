# Signing releases with Azure Artifact Signing

Optional. Without it releases are built and clearly marked unsigned. With it, the exe is signed before it is zipped and hashed,
so Windows shows your verified publisher name. No key or password is stored in GitHub: the workflow proves who it is to Azure
with GitHub's own sign-in (OIDC).

## In Azure (once)
1. Create an Artifact Signing account (done: resource group `signing-rg`).
2. Account > **Identity validation**: complete it. Certificates are only issued after Microsoft confirms who you are.
3. Account > **Certificate profiles** > create a **Public Trust** profile. Note its name.
4. Microsoft Entra ID > **App registrations** > New registration. Note the Application (client) ID and Directory (tenant) ID.
   - Certificates & secrets > **Federated credentials** > Add > *GitHub Actions deploying Azure resources*:
     organization `Alpallyoop`, repository `legacy-player`, entity type **Tag**, tag `v*` (or **Branch** `main` for manual runs).
5. Signing account > **Access control (IAM)** > Add role assignment > **Artifact Signing Certificate Profile Signer**
   (older name: *Trusted Signing Certificate Profile Signer*) > assign to the app registration.

## In GitHub (once)
Repository > Settings > Secrets and variables > Actions > **Variables** (these are not secrets):

| Variable | Value |
|---|---|
| `AZURE_CLIENT_ID` | the app registration's client ID |
| `AZURE_TENANT_ID` | the directory (tenant) ID |
| `AZURE_SUBSCRIPTION_ID` | the subscription ID |
| `ARTIFACT_SIGNING_ENDPOINT` | the account's regional endpoint, e.g. `https://eus.codesigning.azure.net` (shown on the account page) |
| `ARTIFACT_SIGNING_ACCOUNT` | the signing account name |
| `ARTIFACT_SIGNING_PROFILE` | the certificate profile name |

When `ARTIFACT_SIGNING_ACCOUNT` and `AZURE_CLIENT_ID` are set, the next tagged release signs the exe. If they are set and signing
fails, the release fails instead of shipping an unsigned file.

## Notes
- Microsoft renamed Trusted Signing to Artifact Signing; the GitHub action is pinned in `.github/workflows/release.yml` and may
  need its name or version updated.
- Not yet verified against a real Azure account.
