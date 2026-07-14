# Security policy

## Reporting a vulnerability

Do not open a public issue containing credentials, tokens, customer information, or an exploitable vulnerability.

Use GitHub's private vulnerability reporting for this repository when available. Include the affected file or workflow, reproduction steps, expected impact, and a suggested mitigation if you have one.

If you discover a committed credential in an application being ported, treat it as compromised: stop the deployment, remove it from the target configuration, and rotate it with the relevant provider.

## Scope

The toolkit is designed for empty pre-production recreation. Production data migration, source teardown, and destructive recovery are outside its safety boundary.
