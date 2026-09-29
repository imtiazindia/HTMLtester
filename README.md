# HTMLtester

A private PDF-to-HTML comparison workspace. Upload a digitally generated PDF, view it using PDF.js, and compare actual outputs from pdf2htmlEX, Docling and OpenDataLoader PDF. Each engine's result is retained in the browser while switching between engines. Includes isolated HTML preview, HTML source view and original HTML download.

## Run the frontend

Requires Node.js 22+.

```sh
npm ci
npm run dev
npm run build
```

`public/config.json` contains public API/Cognito configuration, never credentials. PDF previews run locally without login. Conversions require the deployed backend and an administrator-created Cognito account. The development origin allowed by the deployment is `http://localhost:5173`; use `npm run dev -- --host localhost` for cloud-backed local development.

## Backend and AWS

AWS Mumbai (`ap-south-1`): Amplify static hosting, HTTP API with Cognito JWT authorization, private S3 uploads/results, a small Python API Lambda, and an on-demand 4 GB conversion Lambda container. An SQS queue limits conversion concurrency to two. CodeBuild builds the Linux image and ECR stores it; no local Docker installation is required. Resources are isolated from other applications.

```sh
python -m venv .venv
# Activate the venv, then:
pip install boto3 awscrt pypdf pytest
python infra/deploy.py bootstrap
python infra/deploy.py build
# Wait for the recorded CodeBuild job to succeed:
python infra/deploy.py deploy
python infra/deploy.py web
pytest backend/test_backend.py
```

The two CloudFormation stacks are `HTMLtesterBuild` and `HTMLtesterApp`. Amplify is created by the deployment script. Local `.deploy/state.json` tracks resource IDs and build/deployment jobs. It is excluded from Git. Initial administrator credentials are saved outside the repository at `~/.codex/htmltester-login.json`; they are not emailed, committed or put in frontend configuration. Deployment updates preserve the account and password.

## Limits and behavior

- Digitally generated PDFs: 20 MB, 40 pages. Encrypted PDFs are rejected. Docling OCR is disabled. OpenDataLoader uses deterministic local mode, not hybrid AI.
- Maximum converter subprocess time: 12 minutes. Workers time out at 14 minutes. The UI reports a stalled job after 16 minutes; automatic Lambda retries are disabled.
- Uploaded files and outputs are private, scoped to the signed-in Cognito subject. Presigned links expire after 15 minutes. S3 lifecycle marks objects for expiry after one day; deletion is asynchronous.
- Preview sanitizes HTML, blocks external resources and runs in an iframe with no script or same-origin permission. pdf2htmlEX visibility CSS is adapted for script-free display. Download preserves original converter output, including its scripts. The preview can therefore differ from an independently opened download.
- Tokens are held in memory and expire after one hour. Reloading or signing out clears the browser session. Files/results are not persisted across browser reloads.
- The PDF viewer renders one page at a time, with page and zoom controls. Semantic HTML may reflow and has independent scrolling; synchronized scrolling would imply a page correspondence that these engines do not guarantee.

## Costs

No always-on VM or GPU. Lambda compute is billed per use; ECR image storage, S3, Amplify, CodeBuild and API requests may still incur charges. At the standard x86 Lambda rate of $0.0000166667/GB-second, a 4 GB worker running for 60 seconds costs approximately $0.004 before free-tier allowances, other services, and regional pricing differences. A 12-minute conversion is approximately $0.048 of worker compute. This is an estimate, not a hard budget cap. The account's existing budget alerts are unchanged.

## Research and licenses

See [research notes](docs/RESEARCH.md) for primary sources, model/license distinctions and benchmark caveats. Application code is separate from upstream engines; each engine retains its own license. The worker uses pinned direct Python dependencies and the published pdf2htmlEX release. Python transitive dependencies/model revisions can change on rebuild; record the deployed image digest for reproducibility.
