# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| latest  | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in WireGUI, please report it responsibly through **GitHub's private vulnerability reporting**:

1. Go to the [Security Advisories](https://github.com/bartei/wiregui/security/advisories) page
2. Click **"Report a vulnerability"**
3. Fill in the details of the vulnerability

Please **do not** open a public issue for security vulnerabilities.

## What to Expect

- You will receive an acknowledgment within **48 hours**
- We will provide a timeline for a fix within **7 days**
- Security patches will be released as soon as possible

## Scope

The following are in scope for security reports:

- Authentication and authorization bypasses
- SQL injection, XSS, CSRF, or other injection vulnerabilities
- WireGuard configuration issues that could expose private keys
- API token or session handling flaws
- Privilege escalation between user roles

## Out of Scope

- Denial of service (DoS) attacks
- Issues in third-party dependencies (report these upstream)
- Social engineering attacks