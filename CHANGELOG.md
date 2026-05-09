# CHANGELOG

<!-- version list -->

## v1.0.0-rc.1 (2026-05-09)

### Bug Fixes

- **ci**: Drop container from dev release job
  ([`b2b9c2e`](https://github.com/bartei/wiregui/commit/b2b9c2eb78ec8b9ed60ffb177cd1bbc2a0cb822c))

- **deps**: Bump gitpython, mako, python-multipart for security advisories
  ([`01046d8`](https://github.com/bartei/wiregui/commit/01046d8df8221532370ec63741d707237d86bae4))

### Chores

- Remove forgejo CI workflows
  ([`e723dd6`](https://github.com/bartei/wiregui/commit/e723dd6914fc1371c811657b6792eb26e3d65b02))

- Switch semantic-release remote from gitea to github
  ([`d237cc5`](https://github.com/bartei/wiregui/commit/d237cc532bb53bd2bf2f3ef7967b7c66b2cb9444))


## v0.1.3 (2026-04-03)

### Bug Fixes

- Use HMAC-SHA256 with secret key for API token hashing
  ([`604446f`](https://github.com/bartei/wiregui/commit/604446f8ca41119d7fb6e76745d79f0250bceaa8))

### Continuous Integration

- Exclude weak-sensitive-data-hashing rule from CodeQL
  ([`31b31b7`](https://github.com/bartei/wiregui/commit/31b31b7946b3fb4523d29a3355fa4c7849a028f0))


## v0.1.2 (2026-04-03)

### Bug Fixes

- Replace python-jose with PyJWT to eliminate vulnerable ecdsa dependency
  ([`4963341`](https://github.com/bartei/wiregui/commit/496334137d048a74de4b9e5be6d5c08e5603539a))


## v0.1.1 (2026-04-03)

### Bug Fixes

- Address CodeQL findings — sha512 for token hashing, secure tempfile
  ([`5c02598`](https://github.com/bartei/wiregui/commit/5c02598a46f32a5bce919a71b1d64a3f2289ec45))

### Continuous Integration

- Add security policy, CodeQL scanning, enable Dependabot
  ([`aa38c37`](https://github.com/bartei/wiregui/commit/aa38c3797e134f9a52db91248217d2caf8aaef4a))


## v0.1.0 (2026-04-03)

- Initial Release
