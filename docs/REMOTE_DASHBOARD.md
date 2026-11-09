# Remote dashboard access

The remote-control dashboard binds to loopback by default. It does not accept LAN
connections until the owner explicitly enables them.

Add both settings to `config/api_keys.json` to enable remote access:

```json
{
  "dashboard_https": true,
  "dashboard_allow_lan": true
}
```

The application creates a local self-signed certificate when HTTPS is enabled. Each
phone or browser may ask you to trust that certificate. Do not enable LAN access on
a public or untrusted network. LAN binding is refused when HTTPS is disabled or when
the certificate is missing.

To disable remote access, set `dashboard_allow_lan` to `false` or remove it. The
dashboard remains available on this computer through loopback.
