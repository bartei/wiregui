<?php
/**
 * SAML 2.0 remote SP metadata for WireGUI testing.
 * Registers SPs for dev (port 13000) and e2e test (port 13003).
 */

// Dev instance
$metadata['http://localhost:13000/auth/saml/test-saml/metadata'] = [
    'AssertionConsumerService' => 'http://localhost:13000/auth/saml/test-saml/callback',
];

// E2E test instance
$metadata['http://localhost:13003/auth/saml/test-saml/metadata'] = [
    'AssertionConsumerService' => 'http://localhost:13003/auth/saml/test-saml/callback',
];