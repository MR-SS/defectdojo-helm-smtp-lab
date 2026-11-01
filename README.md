# DefectDojo Helm SMTP lab

A small local lab for understanding how DefectDojo receives SMTP configuration through Helm and for checking that email actually arrives.

This repository accompanies a beginner-friendly walkthrough. It uses the existing Open Source chart's `extraSecrets.DD_EMAIL_URL` setting; it does not modify DefectDojo or its chart.

## Tested scope

The email workflow was validated on an existing Minikube installation with Helm chart **1.9.60**, DefectDojo **3.4.202**, and a local Mailpit receiver reporting **v1.32.0**. Fresh-install commands below are preparation instructions, not a claim that the complete workflow was rerun on a clean machine. The version pin is for reproducing this local test, not a production-version recommendation.

Verified: direct delivery from Django and Celery, HTTP password reset, the public reset URL, login with the new password, a real asynchronous notification and preservation of existing application/database/broker Secret data.

Not verified end to end: external inbox delivery, provider authentication, STARTTLS or implicit TLS handshakes.

## Files

| File | Purpose |
| --- | --- |
| `lab-values.yaml` | Local HTTP access and lab resource settings |
| `mailpit.yaml` | Test receiver Deployment and Service |
| `smtp-values.yaml` | SMTP override for an already installed release |
| `scripts/verify_email.py` | Local end-to-end check using a disposable user |
| `VALIDATION.md` | Observed results and limitations |

## Prerequisites

Install Docker, Minikube, kubectl and Helm 3. For a fresh lab, allow roughly 4 CPUs, 8 GB of available memory and 25 GB of disk. This is a local learning environment, not a production deployment.

Before using an existing cluster, check `kubectl config current-context`. Keep your maintained values and installed chart version. Do not replace an existing installation's configuration with the example lab values.

## Fresh local lab

```bash
minikube start -p dojo-smtp --driver=docker --cpus=4 --memory=8192 --disk-size=25g
kubectl config use-context dojo-smtp
kubectl get nodes
kubectl create namespace defectdojo

CHART_VERSION=1.9.60
helm pull defectdojo \
  --repo https://raw.githubusercontent.com/DefectDojo/django-DefectDojo/helm-charts \
  --version "$CHART_VERSION"

helm install defectdojo "./defectdojo-${CHART_VERSION}.tgz" \
  -n defectdojo -f lab-values.yaml \
  --set createSecret=true \
  --set createPostgresqlSecret=true \
  --set createValkeySecret=true \
  --wait --timeout 15m
```

Map `dojo.lab.local` to `127.0.0.1` in your hosts file. Open the application with `kubectl -n defectdojo port-forward svc/defectdojo-django 8080:80`, then visit `http://dojo.lab.local:8080`.

## Add SMTP to that installation

```bash
kubectl apply -f mailpit.yaml
kubectl -n defectdojo rollout status deployment/mailpit

helm upgrade defectdojo "./defectdojo-${CHART_VERSION}.tgz" \
  -n defectdojo -f lab-values.yaml -f smtp-values.yaml \
  --wait --timeout 15m

kubectl -n defectdojo rollout status deployment/defectdojo-django
kubectl -n defectdojo rollout status deployment/defectdojo-celery-worker
kubectl -n defectdojo rollout status deployment/defectdojo-celery-beat
```

For an existing release, replace `lab-values.yaml` with your maintained installation values and use its installed chart version. Preserve other `extraSecrets` entries. The SMTP override explicitly disables the three first-install Secret creation settings, including values that may still be true in an older file.

The receiver manifest preserves the lab's `latest`/`IfNotPresent` configuration. Its cached image ran Mailpit v1.32.0. Pin an image version or digest you have verified for a reproducible new environment.

## Check email

Open Mailpit in another terminal:

```bash
kubectl -n defectdojo port-forward svc/mailpit 8025:8025
```

Visit `http://localhost:8025`. The following command checks the real HTTP password-reset/login flow and an asynchronous application notification:

```bash
kubectl -n defectdojo exec -i deployment/defectdojo-django -c uwsgi -- \
  python /app/manage.py shell < scripts/verify_email.py
```

**Local lab only:** the script creates a disposable user and temporarily changes the global sender and mail-notification flag. It restores those flags and removes the user when it finishes. Do not run it on a production/shared instance. It expects exactly the local Service names, public URL and chart behavior described above. It prints no passwords, reset tokens or session cookies.

A successful run prints `SMTP_E2E_RESULT` and cleanup confirmation. Verify actual receipt in Mailpit too. The script requires SMTP to be configured first; it is not an installer.

## Keep credentials private

The supplied SMTP URL contains no credentials. Do not commit real provider passwords, Secret exports, Helm backups or reset links. Kubernetes Secret base64 encoding is not encryption, and Helm release values can also contain credentials.

## References

- [DefectDojo configuration](https://docs.defectdojo.com/get_started/open_source/configuration/)
- [Minikube setup](https://minikube.sigs.k8s.io/docs/start/)
- [Mailpit SMTP](https://mailpit.axllent.org/docs/configuration/smtp/)
