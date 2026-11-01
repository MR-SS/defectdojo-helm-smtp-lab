# Local validation

Validated on November 1, 2026, on the existing local `defectdojo` release in namespace `defectdojo`.

- Published chart: 1.9.60, unchanged during the SMTP configuration upgrade.
- Application: 3.4.202.
- Receiver: Mailpit v1.32.0, plain unauthenticated SMTP on port 1025.
- Helm release revision: 1 to 2.

| Check | Observed outcome |
| --- | --- |
| Before SMTP configuration | Effective destination localhost:25; connection refused |
| Existing Secret data | Application, PostgreSQL and Valkey data unchanged after upgrade |
| Direct Django email | Backend returned 1; received in Mailpit |
| Direct worker email | Backend returned 1; received in Mailpit |
| HTTP password-reset request | Email received |
| Public reset link | Used http://dojo.lab.local:8080 |
| Password change | New password accepted; previous password no longer matched |
| HTTP login | Authenticated session belonged to the disposable user |
| Asynchronous notification | Broker/worker path used with eager mode off; notification received |
| Worker logs | Matched task received and succeeded events |
| Cleanup | Disposable users removed and original global mail settings restored |

A second successful run used a relative event URL and checked that the notification did not double-prefix the public URL.

The first password-change attempt used a generated password that did not meet the configured policy. The harness was adjusted to generate a password containing uppercase, lowercase, numbers and a special character. The application's policy was not weakened.

These are local observations, not CI or production certification. Fresh-machine installation, external-provider authentication, external inbox delivery and real TLS handshakes were not validated by these runs. The TLS URL examples were checked separately for parsing behavior.
