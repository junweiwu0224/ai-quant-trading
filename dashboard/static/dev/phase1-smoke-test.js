#!/usr/bin/env node

const { runAcceptanceSuite } = require('./v2-acceptance-suite.js');

if (require.main === module) {
    runAcceptanceSuite().catch((error) => {
        console.error('[FATAL]', error && error.stack ? error.stack : error);
        process.exitCode = 1;
    });
}
