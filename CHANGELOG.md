# CHANGELOG

<!-- version list -->

## v1.0.0-rc.3 (2026-08-18)

### Bug Fixes

- **deps**: Upgrade locked dependencies to clear security advisories
  ([`b963345`](https://github.com/bartei/wiregui/commit/b963345c6df53d1ac195cc6792d31151fb209d87))

### Documentation

- **scim**: Add SCIM provisioning design and todo
  ([`75232da`](https://github.com/bartei/wiregui/commit/75232da640e799fa9a80516aa35816868d123554))


## v1.0.0-rc.2 (2026-08-18)

### Bug Fixes

- **deps**: Clear 40 known CVEs in Python dependencies
  ([#6](https://github.com/bartei/wiregui/pull/6),
  [`9f38b0c`](https://github.com/bartei/wiregui/commit/9f38b0c402dbe5ad6c148178dbf8803436db27ab))

- **deps**: Clear 6 CVEs in website dependencies ([#6](https://github.com/bartei/wiregui/pull/6),
  [`9f38b0c`](https://github.com/bartei/wiregui/commit/9f38b0c402dbe5ad6c148178dbf8803436db27ab))

- **users**: Cascade-delete OIDC-created users and their data
  ([#7](https://github.com/bartei/wiregui/pull/7),
  [`ccf4c26`](https://github.com/bartei/wiregui/commit/ccf4c26f9314b13838ec5c723da9b665ebeca04a))


## v0.4.1 (2026-06-26)

### Bug Fixes

- **deps**: Release security dependency updates
  ([`547dae8`](https://github.com/bartei/wiregui/commit/547dae8f53774f4d245ff9331cd9caa3e5bfd796))

### Chores

- **deps**: Bump dependencies to clear security advisories
  ([#5](https://github.com/bartei/wiregui/pull/5),
  [`fdba123`](https://github.com/bartei/wiregui/commit/fdba1235a0f419d868fe07127e482303facf6e7f))

### Documentation

- **website**: Add site-to-site relay feature card
  ([`f9ceb10`](https://github.com/bartei/wiregui/commit/f9ceb10fc737b6c3fc917ff2be0b7495c678133c))


## v0.4.0 (2026-06-26)

### Bug Fixes

- Prune orphaned relay routes on device delete/update and reconcile
  ([`f0a2368`](https://github.com/bartei/wiregui/commit/f0a2368ff04180fe2125554f39f742f239b5b8e7))

### Features

- Add allowed_subnets for VPN relay configuration
  ([`9c3ad64`](https://github.com/bartei/wiregui/commit/9c3ad64d9e417b0530311ca317527410e9abb3c2))

- Add routes for peer allowed ip list
  ([`0dd25f1`](https://github.com/bartei/wiregui/commit/0dd25f1336218862bd289bb0e40caa513f103eaa))

- Ensure user firewall chain is jumped to when src address is from users device allowed subnets
  ([`48e4c18`](https://github.com/bartei/wiregui/commit/48e4c1828445447705a5b19ddb80b964fb3ef6ae))

### Testing

- Acceptance coverage for relay subnet validation and admin-only gating
  ([`e134415`](https://github.com/bartei/wiregui/commit/e13441591551ba63937b7ac69df27fca3dc4d593))


## v1.0.0-rc.1 (2026-05-09)


## v0.3.0 (2026-06-26)

### Bug Fixes

- Widen device byte counters to bigint and use IP for reachability check
  ([`931d061`](https://github.com/bartei/wiregui/commit/931d0619d26224f0f37b18c17e1f1a69f9c01966))

### Features

- Firewall rule priorities with drag-and-drop ordering and per-user filtering
  ([`5cdeeb8`](https://github.com/bartei/wiregui/commit/5cdeeb8e1a597168f583950c451028995a437cf4))


## v0.2.3 (2026-05-09)

### Bug Fixes

- **deps**: Bump pillow, lxml, nicegui, cryptography, pytest, authlib for advisories
  ([`6a2fb0e`](https://github.com/bartei/wiregui/commit/6a2fb0e45e99029096c53342629dc89f14f7862a))


## v0.2.2 (2026-05-09)

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


## v0.2.1 (2026-04-24)

### Bug Fixes

- Update dependencies
  ([`fdbc204`](https://github.com/bartei/wiregui/commit/fdbc2042953017af76ccbd6c71ff75e9096026bf))

### Chores

- Remove forgejo workflows and refresh TODO
  ([`8f0898e`](https://github.com/bartei/wiregui/commit/8f0898ebb56ccd295be929454b356a295994fdf5))

### Documentation

- Add LAN-to-peer routing section to product website
  ([`a5df2c6`](https://github.com/bartei/wiregui/commit/a5df2c60ff0f2251fa4f0194862c9a99940c03b2))


## v0.2.0 (2026-04-18)

### Features

- Add product website with GitHub Pages deployment
  ([`1ace819`](https://github.com/bartei/wiregui/commit/1ace819fd91e97acc840b86b6b49092152a80662))


## v0.1.8 (2026-04-18)

### Bug Fixes

- Patch 3 dependency vulnerabilities and add screenshots to README
  ([`6535d4f`](https://github.com/bartei/wiregui/commit/6535d4f4155b4a12081990bb0512d81f6793d266))


## v0.1.7 (2026-04-09)

### Bug Fixes

- Update compose prod with proper reference to our built image stored in ghcr
  ([`746cc9c`](https://github.com/bartei/wiregui/commit/746cc9ce13e754a21d3fa954c32a0e2be25a43b9))


## v0.1.6 (2026-04-09)

### Bug Fixes

- Always print the seed admin password in the logs
  ([`50b7800`](https://github.com/bartei/wiregui/commit/50b78000e0e2a1729aa239d239798ba56ca7ca86))

- Configure prod compose to bind the logs folder instead of creating a volume
  ([`f9fb0d3`](https://github.com/bartei/wiregui/commit/f9fb0d35ab21214d8928f644f07268b71e4d844c))

### Chores

- Migrate repository references from Forgejo to GitHub
  ([`397b28d`](https://github.com/bartei/wiregui/commit/397b28d5489e1d9128bd10aca9ec21b2ba931522))


## v0.1.5 (2026-04-08)

### Bug Fixes

- Add test to verify the generation of the admin password at first start of the application stack
  ([`96235d4`](https://github.com/bartei/wiregui/commit/96235d4d6ef11d29ea9f5759f9099570b490aa70))

- Update dependencies
  ([`8471210`](https://github.com/bartei/wiregui/commit/8471210230bc35461b3f2971cfb86cb9d8516174))


## v0.1.4 (2026-04-07)

### Bug Fixes

- Prevent collector subprocess from deadlocking on full pipe buffer
  ([`cca49ca`](https://github.com/bartei/wiregui/commit/cca49ca2cf07119023d6dffb9fa6d21cbc8f0b67))


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
